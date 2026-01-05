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

"""Base classes for MuJoCo manipulation simulation.

These base classes provide the core simulation functionality that can be
extended by arm-specific implementations.
"""

from .constants import (
    CONTROL_RATE,
    DEFAULT_KD,
    DEFAULT_KP,
    DEFAULT_TIMESTEP,
    MONITOR_RATE,
    PHYSICS_RATE,
    ROBOT_CONFIGS,
    get_robot_config,
)
from .sdk_wrapper import MuJoCoManipulatorSDK, SimulationConfig
from .sim_driver import MuJoCoManipulatorDriver, SimDriverConfig

__all__ = [
    "CONTROL_RATE",
    "DEFAULT_KD",
    "DEFAULT_KP",
    "DEFAULT_TIMESTEP",
    "MONITOR_RATE",
    # Constants
    "PHYSICS_RATE",
    "ROBOT_CONFIGS",
    "MuJoCoManipulatorDriver",
    # Core classes
    "MuJoCoManipulatorSDK",
    "SimDriverConfig",
    # Config classes
    "SimulationConfig",
    "get_robot_config",
]
