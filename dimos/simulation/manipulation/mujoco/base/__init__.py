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

from .sdk_wrapper import MuJoCoManipulatorSDK, SimulationConfig
from .sim_driver import MuJoCoManipulatorDriver, SimDriverConfig
from .constants import (
    PHYSICS_RATE,
    CONTROL_RATE,
    MONITOR_RATE,
    DEFAULT_TIMESTEP,
    DEFAULT_KP,
    DEFAULT_KD,
    ROBOT_CONFIGS,
    get_robot_config,
)

__all__ = [
    # Core classes
    "MuJoCoManipulatorSDK",
    "MuJoCoManipulatorDriver",
    # Config classes
    "SimulationConfig",
    "SimDriverConfig",
    # Constants
    "PHYSICS_RATE",
    "CONTROL_RATE",
    "MONITOR_RATE",
    "DEFAULT_TIMESTEP",
    "DEFAULT_KP",
    "DEFAULT_KD",
    "ROBOT_CONFIGS",
    "get_robot_config",
]

