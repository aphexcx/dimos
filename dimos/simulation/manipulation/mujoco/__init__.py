# Copyright 2025 Dimensional Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""MuJoCo simulation backend for manipulator control.

Provides MuJoCo-based simulation that implements the same interface as
hardware manipulator drivers, enabling seamless switching between
simulation and real hardware.

Structure:
    mujoco/
    ├── base/           # Base classes (MuJoCoManipulatorSDK, MuJoCoManipulatorDriver)
    ├── xarm/           # xArm-specific driver and blueprints
    └── piper/          # (Future) Piper-specific driver and blueprints

Usage:
    # Base classes (for creating new arm-specific drivers)
    from dimos.simulation.manipulation.mujoco.base import (
        MuJoCoManipulatorSDK,
        MuJoCoManipulatorDriver,
    )

    # xArm simulation (same interface as hardware)
    from dimos.simulation.manipulation.mujoco.xarm import (
        XArmSimDriver,
        xarm7_sim_servo,
        xarm_sim_cartesian,
    )
"""

# Base classes
from .base import (
    MuJoCoManipulatorSDK,
    MuJoCoManipulatorDriver,
    SimulationConfig,
    SimDriverConfig,
    PHYSICS_RATE,
    CONTROL_RATE,
    MONITOR_RATE,
    ROBOT_CONFIGS,
    get_robot_config,
)

# xArm simulation
from .xarm import (
    XArmSimDriver,
    xarm_sim_driver,
    xarm7_sim_servo,    
    xarm7_sim_trajectory,
)

__all__ = [
    # Base classes
    "MuJoCoManipulatorSDK",
    "MuJoCoManipulatorDriver",
    "SimulationConfig",
    "SimDriverConfig",
    # Constants
    "PHYSICS_RATE",
    "CONTROL_RATE",
    "MONITOR_RATE",
    "ROBOT_CONFIGS",
    "get_robot_config",
    # xArm
    "XArmSimDriver",
    "xarm_sim_driver",
    "xarm7_sim_servo",
    "xarm7_sim_trajectory",
]
