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

"""Simulation backends for manipulation control.

This module provides simulation implementations that match the hardware
manipulator interfaces, allowing control code to work seamlessly with
either real hardware or simulation.

Structure:
    simulation/manipulation/
    ├── data/               # Model files (MJCF/URDF) for each arm
    │   ├── xarm7/          # xArm7 model and assets
    │   └── piper/          # (Future) Piper model
    └── mujoco/             # MuJoCo simulation backend
        ├── base/           # Base classes
        ├── xarm/           # xArm-specific driver and blueprints
        └── piper/          # (Future) Piper-specific

Usage:
    # xArm simulation driver
    from dimos.simulation.manipulation.mujoco.xarm import XArmSimDriver
    driver = XArmSimDriver(dof=7)
    driver.start()

    # xArm simulation blueprints (same interface as hardware!)
    from dimos.simulation.manipulation.mujoco.xarm import xarm7_sim_servo
    coordinator = xarm7_sim_servo.build()

    # Swap to hardware by changing import:
    from dimos.hardware.manipulators.xarm import xarm7_servo
    coordinator = xarm7_servo.build()  # Same interface!
"""

# Base classes (for creating new arm-specific drivers)
from .mujoco.base import (
    MuJoCoManipulatorDriver,
    MuJoCoManipulatorSDK,
)

# xArm simulation
from .mujoco.xarm import (
    XArmSimDriver,
    xarm7_sim_servo,
    xarm7_sim_trajectory,
    xarm_sim_driver,
)

__all__ = [
    "MuJoCoManipulatorDriver",
    # Base classes
    "MuJoCoManipulatorSDK",
    # xArm simulation
    "XArmSimDriver",
    "xarm7_sim_servo",
    "xarm7_sim_trajectory",
    "xarm_sim_driver",
]
