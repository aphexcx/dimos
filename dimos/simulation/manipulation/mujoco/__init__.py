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
    CONTROL_RATE,
    MONITOR_RATE,
    PHYSICS_RATE,
    ROBOT_CONFIGS,
    MuJoCoManipulatorDriver,
    MuJoCoManipulatorSDK,
    SimDriverConfig,
    SimulationConfig,
    get_robot_config,
)

# xArm simulation
from .xarm import (
    XArmSimDriver,
    xarm7_sim_servo,
    xarm7_sim_trajectory,
    xarm_sim_driver,
)

__all__ = [
    "CONTROL_RATE",
    "MONITOR_RATE",
    # Constants
    "PHYSICS_RATE",
    "ROBOT_CONFIGS",
    "MuJoCoManipulatorDriver",
    # Base classes
    "MuJoCoManipulatorSDK",
    "SimDriverConfig",
    "SimulationConfig",
    # xArm
    "XArmSimDriver",
    "get_robot_config",
    "xarm7_sim_servo",
    "xarm7_sim_trajectory",
    "xarm_sim_driver",
]
