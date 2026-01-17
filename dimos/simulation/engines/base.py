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

"""Base interfaces for simulator engines and robot specs."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dimos.hardware.manipulators.spec import JointLimits


@dataclass(frozen=True)
class RobotSpec:
    """Robot description metadata for simulation engines."""

    name: str
    engine: str
    asset: str | None = None
    dof: int | None = None
    joint_names: list[str] | None = None
    limits: JointLimits | None = None
    vendor: str | None = None
    model: str | None = None


class SimulationEngine(ABC):
    """Abstract base class for a simulator engine instance."""

    def __init__(self, spec: RobotSpec, config_path: str | None, headless: bool) -> None:
        self._spec = spec
        self._config_path = config_path
        self._headless = headless

    @property
    def spec(self) -> RobotSpec:
        return self._spec

    @property
    def config_path(self) -> str | None:
        return self._config_path

    @property
    def headless(self) -> bool:
        return self._headless

    @abstractmethod
    def connect(self) -> None:
        """Connect to simulation and start the engine."""

    @abstractmethod
    def disconnect(self) -> None:
        """Disconnect from simulation and stop the engine."""

    @property
    @abstractmethod
    def connected(self) -> bool:
        """Whether the engine is connected."""

    @property
    @abstractmethod
    def num_joints(self) -> int:
        """Number of joints for the loaded robot."""

    @abstractmethod
    def read_joint_positions(self) -> list[float]:
        """Read joint positions in radians."""

    @abstractmethod
    def read_joint_velocities(self) -> list[float]:
        """Read joint velocities in rad/s."""

    @abstractmethod
    def read_joint_efforts(self) -> list[float]:
        """Read joint efforts in Nm."""

    @abstractmethod
    def write_joint_positions(self, positions: list[float]) -> None:
        """Command joint positions in radians."""

    @abstractmethod
    def write_joint_velocities(self, velocities: list[float]) -> None:
        """Command joint velocities in rad/s."""
