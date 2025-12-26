# Hardware

This directory contains hardware drivers and interfaces for the DIMOS framework.

## Contents

- [FlowBase Driver](#flowbase-driver) - Omnidirectional mobile robot driver
- [Camera Streaming](#camera-streaming) - Remote camera stream with timestamps

---

## FlowBase Driver

A DIMOS hardware driver for the FlowBase omnidirectional mobile robot platform. This driver interfaces with the FlowBase controller via Portal RPC and provides velocity command handling and odometry publishing through LCM.

### Overview

The FlowBase driver provides a high-level interface to control the FlowBase mobile base and receive odometry feedback. It integrates seamlessly with the DIMOS framework, supporting both programmatic control and manual teleoperation.

### Features

- **Velocity Command Control**: Subscribe to Twist commands via LCM and forward velocities (x, y, theta) to FlowBase
- **Odometry Publishing**: Continuously publish odometry data at configurable rates (default 20 Hz)
- **RPC Interface**: Remote procedure calls for:
  - Getting current odometry
  - Resetting odometry to zero
  - Checking driver status
  - Starting/stopping the driver
- **Teleoperation Support**: Built-in integration with keyboard teleoperation for manual control
- **Thread-Safe**: Handles concurrent command sending and odometry publishing

### Architecture

```
┌─────────────────────┐
│  Twist Commands     │
│  (LCM Channel)      │
└──────────┬──────────┘
           │
           v
┌─────────────────────────────┐
│   FlowBaseDriver Module     │
│                             │
│  - Twist subscriber         │
│  - Portal RPC client        │
│  - Odometry publisher       │
└──────────┬──────────────────┘
           │ Portal RPC
           v
┌─────────────────────┐        ┌──────────────────┐
│  FlowBase           │───────>│  Odometry Output │
│  Controller         │        │  (LCM Channel)   │
│  (172.6.2.20:11323) │        └──────────────────┘
└─────────────────────┘
```

### Requirements

- Python 3.8+
- DIMOS framework
- Portal RPC library
- NumPy
- Access to FlowBase controller (default: `172.6.2.20:11323`)

### Quick Start

#### Basic Usage

```python
from dimos.core import start, LCMTransport
from dimos.msgs.geometry_msgs import Twist
from dimos.msgs.nav_msgs import Odometry
from dimos.hardware.flow_base_driver import FlowBaseDriver

# Start DIMOS
dimos = start(1)

# Deploy FlowBase driver
driver = dimos.deploy(
    FlowBaseDriver,
    host="172.6.2.20",
    port=11323,
    verbose=False,
    odom_rate=20.0
)

# Setup LCM transport for twist commands
driver.twist_cmd.transport = LCMTransport("/flowbase/cmd_vel", Twist)

# Setup LCM transport for odometry output
driver.odom_out.transport = LCMTransport("/flowbase/odom", Odometry)

# Start the driver
driver.start()
```

#### Using the Test Script

The [flow_base_test.py](flow_base_test.py) script provides a comprehensive test harness:

**Basic Test (No Teleoperation)**

```bash
python -m dimos.hardware.flow_base_test \
    --host 172.6.2.20 \
    --port 11323 \
    --odom-rate 20.0
```

**With Keyboard Teleoperation**

```bash
python -m dimos.hardware.flow_base_test \
    --host 172.6.2.20 \
    --teleop \
    --teleop-speed 0.1 \
    --teleop-turn 0.2
```

**With Odometry Testing**

```bash
python -m dimos.hardware.flow_base_test \
    --test-odometry \
    --verbose
```

#### Command-Line Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--host` | str | `172.6.2.20` | FlowBase controller IP address |
| `--port` | int | `11323` | FlowBase controller port |
| `--lcm-channel` | str | `/flowbase/cmd_vel` | LCM channel for twist commands |
| `--odom-channel` | str | `/flowbase/odom` | LCM channel for odometry output |
| `--odom-rate` | float | `5.0` | Odometry publishing rate in Hz |
| `--verbose` | flag | `False` | Enable verbose logging |
| `--test-odometry` | flag | `False` | Run odometry tests |
| `--teleop` | flag | `False` | Launch teleop_twist_keyboard |
| `--teleop-speed` | float | `0.1` | Initial linear velocity (m/s) |
| `--teleop-turn` | float | `0.2` | Initial angular velocity (rad/s) |

### API Reference

#### FlowBaseDriver Class

**Constructor Parameters**

```python
FlowBaseDriver(
    host: str = "172.6.2.20",
    port: int = 11323,
    verbose: bool = False,
    odom_rate: float = 20.0
)
```

**Ports**

- `twist_cmd: In[Twist]` - Input port for velocity commands
- `odom_out: Out[Odometry]` - Output port for odometry messages

**RPC Methods**

- `start() -> bool` - Start the driver, connect to FlowBase, and begin odometry publishing
- `stop() -> bool` - Stop the driver, send zero velocity, and close connection
- `get_odometry() -> dict` - Get current odometry (returns `{"translation": [x, y], "rotation": theta}`)
- `reset_odometry() -> bool` - Reset odometry to zero position
- `get_status() -> dict` - Get driver status and statistics

### Odometry Message Format

The driver publishes `nav_msgs/Odometry` messages with the following structure:

```python
Odometry(
    ts: float,                    # Timestamp
    frame_id: "odom",            # Fixed frame
    child_frame_id: "base_link", # Robot frame
    pose: Pose(
        position: Vector3(x, y, 0.0),
        orientation: Quaternion(0, 0, sin(θ/2), cos(θ/2))
    ),
    twist: None  # Not populated
)
```

### Troubleshooting

**Cannot Connect to FlowBase**

Problem: `Failed to connect to FlowBase at 172.6.2.20:11323`

Solutions:
- Verify the FlowBase controller is powered on
- Check network connectivity: `ping 172.6.2.20`
- Ensure the controller is running and listening on port 11323
- Check firewall settings

**No Commands Being Sent**

Problem: Driver receives no twist commands

Solutions:
- Verify LCM channel name matches between publisher and subscriber
- Check if LCM transport is properly configured
- Enable verbose logging with `--verbose` flag
- Confirm twist messages are being published to the correct channel

**Odometry Not Publishing**

Problem: No odometry messages on output channel

Solutions:
- Check that `odom_out` port has LCM transport configured
- Verify odometry rate is reasonable (1-50 Hz recommended)
- Check logs for errors in odometry publisher thread
- Confirm connection to FlowBase controller is active

### Files

- [flow_base_driver.py](flow_base_driver.py) - Main driver implementation
- [flow_base_test.py](flow_base_test.py) - Test script and examples

---

## Camera Streaming

Remote camera stream with timestamps using GStreamer.

### Required Ubuntu packages

```bash
sudo apt install gstreamer1.0-tools gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-libav python3-gi python3-gi-cairo gir1.2-gstreamer-1.0 gir1.2-gst-plugins-base-1.0 v4l-utils gstreamer1.0-vaapi
```

### Usage

On sender machine (with the camera):

```bash
python3 dimos/hardware/gstreamer_sender.py --device /dev/video0 --host 0.0.0.0 --port 5000
```

If it's a stereo camera and you only want to send the left side (the left camera):

```bash
python3 dimos/hardware/gstreamer_sender.py --device /dev/video0 --host 0.0.0.0 --port 5000 --single-camera
```

On receiver machine:

```bash
python3 dimos/hardware/gstreamer_camera_test_script.py --host 10.0.0.227 --port 5000
```

---

## License

Copyright 2025 Dimensional Inc.

Licensed under the Apache License, Version 2.0. See LICENSE file for details.