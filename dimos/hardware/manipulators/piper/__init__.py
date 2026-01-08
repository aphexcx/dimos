# Copyright 2025-2026 Dimensional Inc.
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

"""Piper manipulator driver.

Usage:
    >>> from dimos.hardware.manipulators.piper import Piper
    >>> arm = Piper(can_port="can0")
    >>> arm.start()
    >>> arm.enable_servos()
    >>> arm.move_joint([0, 0, 0, 0, 0, 0])

Testing:
    >>> from dimos.hardware.manipulators.mock import MockBackend
    >>> from dimos.hardware.manipulators.piper import Piper
    >>> arm = Piper(backend=MockBackend())
    >>> arm.start()  # No hardware needed!
"""

from dimos.hardware.manipulators.piper.arm import Piper, PiperConfig, piper
from dimos.hardware.manipulators.piper.backend import PiperBackend

__all__ = ["Piper", "PiperBackend", "PiperConfig", "piper"]
