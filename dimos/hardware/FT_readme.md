### Force Torque README

We have already migrated the FT sensor code from using ZMQ to using the dimos modules approach. The driver and the visualizer are run whenever we run the `ft_module_test.py` script, which deploys the FT driver and visualizer modules.

For the handle grasping, we can run normal_move_test.py, which takes the frames from the ZED camera and a user selected point on the handle and then estimates the normal at the selected point and move the arm to be in front of it. The changes that we need to make here are that we need to take the ZED data from the LCM streams instead of directly through the ZED SDK. We also need to integrate the querying with qwen as a part of the function itself so it should do the find point -> estimate normal -> move to normal direction all in one function. The next thing we need to do is to make that function run twice or thrice since the first time, the normal estimation is a little off, but it gets us close and the second or third times, we are close enough to be decently aligned with the handle. We will leave the code to move forward and actually grab the handle to a separate function/program.

For the opener, we have the olg logic in continuous_door_opener.py. This takes some parameters on which axis to rotate about and which direction to rotate in. This script needs a few changes. We need to get the data for the forces and torques from the LCM streams instead of from ZMQ since we have made that change. We also need to have a stop angle parameter that checks how far we have rotated in the global coordinate system to know how much the hinge has been opened by from when we originally started rotating. Currently, it's only tested to be realiable to rotate hinges in the Z axis- like microwave doors, fridge handles, etc. The logic should work for other axes and the logic is in there, but it's untested for other axes and probably has some bugs.

We also need the dim_cpp folder and the urdfs from the assets folder from https://github.com/dimensionalOS/dimos_utils/tree/openft_test/assets. This is so that we have the meshes, URDF, etc that Drake needs in order to establish context on the robot. Currently, I have the URDF set up and generated for the xarm6, but the arguments in the xacro file can be easily modified to make a URDF for the xarm7. We just need to change the mesh path and types to match the format that Drake is looking for- so no package:// tags and all the meshes need to be objs.

The force torque sensor also needs to be mounted in exactly the orientation that we had it on in the demo videos of the fridge and microwave/how it was on the xarm6. Otherwise, we won't be able to correlate the force axes to the axes of the force torque sensor in the URDF.

python3 dimos/hardware/ft_pull_test.py --xarm 192.168.1.210 --end-angle 45 --port /dev/ttyACM0 --calibration dimos/hardware/ft_calibration.json --auto-run

python handle_grab_test.py --xarm 192.168.1.210 --grab --qwen


# OpenFT Force–Torque Sensor (Branch Guide)

This document summarizes the FT sensor setup in this branch and provides clear steps to run, visualize, and use the data in downstream skills.

## Overview
- Hardware: Custom 16‑channel magnetic FT sensor on a microcontroller streaming 16 comma‑separated values over a serial port (default 115200 baud).
- Software (current path): Serial → moving average → calibration (6×16 + bias) → publish as LCM `Vector3` topics → optional Dash visualizer.
- Legacy path (for reference): Serial → moving average → ZMQ → separate calibration/visualizers.

## Key Components
- Driver (LCM): `dimos/hardware/ft_driver_module.py`
  - Dimos Module. Reads serial, moving averages per channel, applies calibration, publishes LCM:
    - Force: `/ft/force` (`geometry_msgs/Vector3` in N)
    - Torque: `/ft/torque` (`geometry_msgs/Vector3` in N·m)
    - Optional raw: `/ft/raw_sensors` (custom dataclass via pLCM)

- Visualizer (LCM): `dimos/hardware/ft_visualizer_module.py`
  - Dimos Module. Subscribes to force/torque LCM topics and serves a Dash dashboard.

- Orchestrator: `dimos/hardware/ft_module_test.py`
  - One‑shot launcher that deploys the driver, attaches LCM transports, and optionally launches the visualizer.

- Calibration: `dimos/hardware/calc_calibration_matrix.py`
  - Computes 6×16 calibration matrix (+ optional 6×1 bias) from recorded CSV (`sensor_1..sensor_16`, `force_local_*`, `torque_local_*`).
  - Saves to JSON/NPZ. Example provided: `dimos/hardware/ft_calibration.json`.

- Legacy utilities (ZMQ):
  - Minimal driver: `dimos/hardware/ft_min_driver.py`
  - Visualizer: `dimos/hardware/force_torque_visualizer.py`

## Quick Start (LCM path)
1) Connect the sensor MCU; identify your serial port (e.g., `/dev/ttyACM0`). Ensure permissions (e.g., user in `dialout`).
2) Run the orchestrator with calibration:
   ```bash
   python dimos/hardware/ft_module_test.py \
     --port /dev/ttyACM0 \
     --calibration dimos/hardware/ft_calibration.json \
     --dash-port 8052
   ```
3) Open LCM spy and confirm topics:
   - `/ft/force` and `/ft/torque` should appear once data is flowing.
4) Visit the dashboard: `http://127.0.0.1:8052`.

Notes:
- `ft_driver_module.py` alone will read serial and log, but won’t publish to LCM unless transports are attached. Use `ft_module_test.py` for LCM out‑of‑the‑box.
- Visualizer requires a calibration file; without one, only raw data can be sent (no vector outputs).

## Calibration Workflow
1) Record a calibration CSV with columns:
   - Sensors: `sensor_1` … `sensor_16`
   - Ground truth (local frame): `force_local_x/y/z`, `torque_local_x/y/z`
2) Compute the matrix and bias:
   ```bash
   python dimos/hardware/calc_calibration_matrix.py --csv path/to/cal.csv \
     --out dimos/hardware/ft_calibration.json
   ```
   The script prints RMSE per axis and condition numbers.
3) Use the resulting file with the driver/orchestrator via `--calibration`.

## Downstream Skills and Tests
- Examples consuming FT and motion:
  - `dimos/hardware/ft_pull_test.py` (pull/door open flow; can auto‑run).
  - `dimos/hardware/continuous_door_opener.py` (rotation about specified axis).
  - `dimos/hardware/handle_grab_test.py`, `normal_move_test.py` (pose planning; ZED + Drake).

Run example (pull):
```bash
python3 dimos/hardware/ft_pull_test.py \
  --xarm 192.168.1.210 \
  --end-angle 45 \
  --port /dev/ttyACM0 \
  --calibration dimos/hardware/ft_calibration.json \
  --auto-run
```

## Frames, URDF, and Assets
- The sensor must be mounted in the same orientation used to generate the calibration and URDF assumptions. Many flows expect `link_openft` as the tool frame.
- Ensure Drake can load the correct URDF/meshes. As noted previously, you may need assets from:
  - https://github.com/dimensionalOS/dimos_utils/tree/openft_test/assets
  - Use `.obj` meshes and absolute/relative paths (no `package://`).
- Current URDF provided for xArm6: `dimos/hardware/xarm6_openft_gripper.urdf`. Adapt xacro args and mesh paths for xArm7 if needed.

## Troubleshooting
- No LCM topics in spy:
  - Use `ft_module_test.py` (attaches transports). Confirm serial connection log: “Successfully connected to …”.
  - Check correct serial device and permissions.
- Visualizer page blank or won’t start:
  - Ensure calibration is provided; confirm port/host not in use.
- Force axes look wrong:
  - Check sensor mounting matches calibration and URDF frames.
  - Re‑calibrate with correct local frame definitions.

## Firmware
- Firmware for the MCU is not in this repo. The driver expects a stream of 16 comma‑separated floats per line at 115200 baud, optionally with a trailing comma.
- If you need firmware sources or flashing steps, refer to your MCU/board project or vendor; keep the output protocol as above.

## Reference Commands
```bash
# Orchestrated driver + visualizer (LCM)
python dimos/hardware/ft_module_test.py --port /dev/ttyACM0 --calibration dimos/hardware/ft_calibration.json

# Minimal (legacy) ZMQ driver
python dimos/hardware/ft_min_driver.py --port /dev/ttyACM0 --zmq-port 5555 --verbose

# ZMQ visualizer for calibrated stream (legacy)
python dimos/hardware/force_torque_visualizer.py
```


