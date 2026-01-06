# MuJoCo Simulation Bridge

This module provides infrastructure for connecting MuJoCo physics simulation with robot manipulator drivers, enabling the same driver code to work seamlessly with both hardware and simulation.

## Overview

The `mujoco_sim` package provides a base class (`MujocoSimBridgeBase`) that handles:
- MuJoCo model loading and initialization
- Threading infrastructure for simulation loops
- Joint state management (positions, velocities, efforts)
- Connection management
- Viewer integration

Robot-specific implementations inherit from this base class and implement the robot SDK interfaces, allowing existing driver code to work without modification.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│         Robot Driver (e.g., XArmDriver)                │
│         Uses robot SDK interface                       │
└────────────────────┬────────────────────────────────────┘
                     │
         ┌───────────┴───────────┐
         │                       │
┌────────▼────────┐    ┌─────────▼─────────┐
│  Hardware SDK   │    │  Simulation Bridge │
│  (XArmAPI, etc) │    │  (XArmSimBridge)   │
└─────────────────┘    └─────────┬──────────┘
                                 │
                      ┌──────────▼──────────┐
                      │  MujocoSimBridgeBase │
                      │  (Base Infrastructure)│
                      └──────────┬───────────┘
                                 │
                      ┌──────────▼──────────┐
                      │    MuJoCo Physics    │
                      │    Simulation        │
                      └─────────────────────┘
```

## Components

### `bridge_base.py`

The `MujocoSimBridgeBase` abstract base class provides:

**Core Functionality:**
- Model loading via `load_manipulator_model()`
- Thread-safe simulation loop running at configurable control frequency
- Joint state tracking (positions, velocities, efforts)
- Connection management (`connect()`, `disconnect()`)
- MuJoCo viewer integration

**Abstract Methods (must be implemented by subclasses):**
- `_apply_control()`: Apply control commands to MuJoCo actuators
- `_update_joint_state()`: Update internal joint state from simulation

**Properties:**
- `connected`: Connection status
- `num_joints`: Number of joints
- `joint_positions`: Current joint positions (radians)
- `joint_velocities`: Current joint velocities (rad/s)
- `joint_efforts`: Current joint efforts/torques
- `model`: MuJoCo model (read-only)
- `data`: MuJoCo data (read-only)

### `model_utils.py`

Utilities for loading MuJoCo models:

- `find_model_path(robot_name, num_joints)`: Automatically finds model XML files
  - Looks in `dimos/simulation/manipulators/data/`
  - Supports DOF-based paths (e.g., `xarm6/`, `xarm7/`)
  - Falls back to simple robot name (e.g., `piper/`)

- `load_manipulator_model(robot_name, num_joints, model_path)`: Loads MuJoCo model and data

### `constants.py`

Configuration constants:
- `DEFAULT_CONTROL_FREQUENCY = 100.0` Hz
- `MIN_CONTROL_FREQUENCY = 0.01` Hz
- `THREAD_JOIN_TIMEOUT = 2.0` seconds
- `VELOCITY_STOP_THRESHOLD = 1e-6` rad/s
- `POSITION_ZERO_THRESHOLD = 1e-6` rad

## Available Robot Models

Robot models are located in `dimos/simulation/manipulators/data/`:

### Piper
- **Path**: `data/piper/`
- **Model Files**: `scene.xml`, `piper.xml`
- **DOF**: 6
- **Implementation**: `PiperSimBridge` in `dimos/hardware/manipulators/piper/piper_sim_bridge.py`

### xArm6
- **Path**: `data/xarm6/`
- **Model Files**: `scene.xml`, `xarm6.xml`
- **DOF**: 6
- **Implementation**: `XArmSimBridge` in `dimos/hardware/manipulators/xarm/xarm_sim_bridge.py`

### xArm7
- **Path**: `data/xarm7/`
- **Model Files**: `scene.xml`, `xarm7.xml`
- **DOF**: 7
- **Implementation**: `XArmSimBridge` in `dimos/hardware/manipulators/xarm/xarm_sim_bridge.py`

## Usage

**Important**: Simulation bridges are **internal implementation details**. They should **never** be used directly. Always use them through driver wrappers by setting `connection_type="sim"` in the configuration.

### Using XArm with Simulation

The simulation bridges are used automatically when you set `connection_type="sim"` in the driver configuration:

```python
from dimos.hardware.manipulators.xarm.xarm_driver import XArmDriver

# Create driver with simulation connection
driver = XArmDriver(
    config={
        "connection_type": "sim",  # Use simulation instead of hardware
        "dof": 7,              # 7-DOF xArm
        "control_rate": 100,   # Control loop frequency (Hz)
        "monitor_rate": 10,    # State monitoring frequency (Hz)
    }
)

# Start the driver (starts MuJoCo viewer and simulation)
driver.start()

# Use the driver as if it were hardware
# The driver automatically uses XArmSimBridge internally
positions = driver.sdk.get_joint_positions()
driver.sdk.set_joint_positions([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7])
```


### Using Piper with Simulation

```python
from dimos.hardware.manipulators.piper.piper_driver import PiperDriver

# Create driver with simulation connection
driver = PiperDriver(
    config={
        "connection_type": "sim",  # Use simulation
        "control_rate": 100,
        "monitor_rate": 10,
    }
)

# Start the driver
driver.start()

# Use the driver normally
# The driver automatically uses PiperSimBridge internally
```

## Extending for New Robots

To add support for a new robot manipulator:

1. Create MuJoCo Model
2. Create simulation bridge class
3. Update Driver Wrapper

Modify your robot's driver wrapper to use the simulation bridge when `connection_type="sim"`

## Implementation Details

### Simulation Loop

The base class runs a simulation loop in a separate thread:
1. Launches MuJoCo passive viewer
2. At each timestep:
   - Calls `_apply_control()` to apply control commands
   - Steps simulation: `mujoco.mj_step(model, data)`
   - Syncs viewer
   - Calls `_update_joint_state()` to update internal state
3. Maintains accurate control frequency by accounting for execution time

### Thread Safety

All state access is protected by `self._lock`. Subclasses should:
- Acquire lock when reading/writing shared state
- Keep lock-held sections minimal
- Use `with self._lock:` context manager

### Control Modes

The base class supports position control. Subclasses can extend:
- **XArmSimBridge**: Also supports velocity control by integrating velocities to positions
- Custom control modes can be added by modifying `_apply_control()`
