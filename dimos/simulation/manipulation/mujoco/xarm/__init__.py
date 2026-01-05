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

"""xArm simulation driver and blueprints.

This module provides xArm-specific simulation implementations that mirror
the hardware xArm driver interface.

Usage:
    # Direct instantiation
    from dimos.simulation.manipulation.mujoco.xarm import XArmSimDriver
    driver = XArmSimDriver(dof=7)
    driver.start()

    # Via blueprints
    from dimos.simulation.manipulation.mujoco.xarm import xarm7_sim_servo
    coordinator = xarm7_sim_servo.build()
    coordinator.loop()
"""

from .xarm_sim_blueprints import (
    xarm7_sim_servo,
    xarm7_sim_trajectory,
)
from .xarm_sim_driver import XArmSimDriver, xarm_sim_driver

__all__ = [
    # Driver
    "XArmSimDriver",
    # Blueprints
    "xarm7_sim_servo",
    "xarm7_sim_trajectory",
    "xarm_sim_driver",
]
