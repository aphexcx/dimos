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

"""Registry for simulation engines and robot specs."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dimos.simulation.engines.base import RobotSpec, SimulationEngine


class SimulationRegistry:
    """Lookup table for simulator engines and robot specs."""

    def __init__(self) -> None:
        self._engines: dict[str, type[SimulationEngine]] = {}
        self._robots: dict[str, RobotSpec] = {}

    def register_engine(self, name: str, engine_cls: type[SimulationEngine]) -> None:
        key = name.lower()
        self._engines[key] = engine_cls

    def register_robot(self, name: str, spec: RobotSpec) -> None:
        key = name.lower()
        self._robots[key] = spec

    def get_engine(self, name: str) -> type[SimulationEngine]:
        key = name.lower()
        if key not in self._engines:
            raise KeyError(f"Unknown simulation engine: {name}")
        return self._engines[key]

    def get_robot(self, name: str) -> RobotSpec:
        key = name.lower()
        if key not in self._robots:
            raise KeyError(f"Unknown robot spec: {name}")
        return self._robots[key]

    def create_engine(
        self,
        engine: str,
        robot: str,
        config_path: str | None,
        headless: bool,
    ) -> SimulationEngine:
        spec = self.get_robot(robot)
        if spec.engine and spec.engine.lower() != engine.lower():
            raise ValueError(
                f"Robot '{spec.name}' registered for engine '{spec.engine}', got '{engine}'."
            )
        engine_cls = self.get_engine(engine)
        return engine_cls(spec=spec, config_path=config_path, headless=headless)

    def list_engines(self) -> list[str]:
        return sorted(self._engines.keys())

    def list_robots(self) -> list[str]:
        return sorted(self._robots.keys())


registry = SimulationRegistry()

__all__ = [
    "SimulationRegistry",
    "registry",
]
