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

"""Shared memory helpers for MuJoCo engine subprocess control/state."""

from dataclasses import dataclass
from multiprocessing import resource_tracker
from multiprocessing.shared_memory import SharedMemory
from typing import Any

import numpy as np
from numpy.typing import NDArray

CMD_MODE_POSITION = 0
CMD_MODE_VELOCITY = 1


def _unregister(shm: SharedMemory) -> SharedMemory:
    try:
        resource_tracker.unregister(shm._name, "shared_memory")  # type: ignore[attr-defined]
    except Exception:
        pass
    return shm


def _shm_size(count: int, item_size: int) -> int:
    return max(1, count) * item_size


@dataclass(frozen=True)
class EngineShmSet:
    positions: SharedMemory
    velocities: SharedMemory
    efforts: SharedMemory
    cmd: SharedMemory
    cmd_mode: SharedMemory
    seq: SharedMemory
    control: SharedMemory

    @classmethod
    def from_sizes(cls, nq: int, nv: int, nu: int) -> "EngineShmSet":
        sizes = {
            "positions": _shm_size(nq, 8),  # float64
            "velocities": _shm_size(nv, 8),  # float64
            "efforts": _shm_size(nu, 8),  # float64
            "cmd": _shm_size(nu, 8),  # float64
            "cmd_mode": 4,  # int32
            "seq": 16,  # 2 x int64
            "control": 8,  # 2 x int32
        }
        return cls(
            **{
                name: _unregister(SharedMemory(create=True, size=size))
                for name, size in sizes.items()
            }
        )

    @classmethod
    def from_names(cls, shm_names: dict[str, str]) -> "EngineShmSet":
        return cls(**{name: _unregister(SharedMemory(name=shm_names[name])) for name in shm_names})

    def to_names(self) -> dict[str, str]:
        return {field: getattr(self, field).name for field in self.__dataclass_fields__}

    def as_list(self) -> list[SharedMemory]:
        return [getattr(self, field) for field in self.__dataclass_fields__]


class EngineShmReader:
    shm: EngineShmSet
    _last_cmd_seq: int

    def __init__(self, shm_names: dict[str, str], nq: int, nv: int, nu: int) -> None:
        self.shm = EngineShmSet.from_names(shm_names)
        self.nq = nq
        self.nv = nv
        self.nu = nu
        self._last_cmd_seq = 0

    def signal_ready(self) -> None:
        control_array: NDArray[Any] = np.ndarray((2,), dtype=np.int32, buffer=self.shm.control.buf)
        control_array[0] = 1

    def should_stop(self) -> bool:
        control_array: NDArray[Any] = np.ndarray((2,), dtype=np.int32, buffer=self.shm.control.buf)
        return bool(control_array[1] == 1)

    def write_state(self, positions, velocities, efforts) -> None:  # type: ignore[no-untyped-def]
        pos_array: NDArray[Any] = np.ndarray(
            (self.nq,), dtype=np.float64, buffer=self.shm.positions.buf
        )
        vel_array: NDArray[Any] = np.ndarray(
            (self.nv,), dtype=np.float64, buffer=self.shm.velocities.buf
        )
        eff_array: NDArray[Any] = np.ndarray(
            (self.nu,), dtype=np.float64, buffer=self.shm.efforts.buf
        )

        if self.nq:
            pos_array[:] = 0.0
            pos_array[: min(self.nq, len(positions))] = positions[: self.nq]
        if self.nv:
            vel_array[:] = 0.0
            vel_array[: min(self.nv, len(velocities))] = velocities[: self.nv]
        if self.nu:
            eff_array[:] = 0.0
            eff_array[: min(self.nu, len(efforts))] = efforts[: self.nu]

        self._increment_seq(0)

    def read_command(self) -> tuple[int, NDArray[Any]] | None:
        seq = self._get_seq(1)
        if seq > self._last_cmd_seq:
            self._last_cmd_seq = seq
            cmd_array: NDArray[Any] = np.ndarray(
                (self.nu,), dtype=np.float64, buffer=self.shm.cmd.buf
            )
            mode_array: NDArray[Any] = np.ndarray(
                (1,), dtype=np.int32, buffer=self.shm.cmd_mode.buf
            )
            return int(mode_array[0]), cmd_array.copy()
        return None

    def _increment_seq(self, index: int) -> None:
        seq_array: NDArray[Any] = np.ndarray((2,), dtype=np.int64, buffer=self.shm.seq.buf)
        seq_array[index] += 1

    def _get_seq(self, index: int) -> int:
        seq_array: NDArray[Any] = np.ndarray((2,), dtype=np.int64, buffer=self.shm.seq.buf)
        return int(seq_array[index])

    def cleanup(self) -> None:
        for shm in self.shm.as_list():
            try:
                shm.close()
            except Exception:
                pass


class EngineShmWriter:
    shm: EngineShmSet
    _last_state_seq: int

    def __init__(self, nq: int, nv: int, nu: int) -> None:
        self.shm = EngineShmSet.from_sizes(nq=nq, nv=nv, nu=nu)
        self.nq = nq
        self.nv = nv
        self.nu = nu
        self._last_state_seq = 0

        seq_array: NDArray[Any] = np.ndarray((2,), dtype=np.int64, buffer=self.shm.seq.buf)
        seq_array[:] = 0

        cmd_array: NDArray[Any] = np.ndarray((self.nu,), dtype=np.float64, buffer=self.shm.cmd.buf)
        cmd_array[:] = 0.0

        mode_array: NDArray[Any] = np.ndarray((1,), dtype=np.int32, buffer=self.shm.cmd_mode.buf)
        mode_array[:] = 0

        control_array: NDArray[Any] = np.ndarray((2,), dtype=np.int32, buffer=self.shm.control.buf)
        control_array[:] = 0

    def is_ready(self) -> bool:
        control_array: NDArray[Any] = np.ndarray((2,), dtype=np.int32, buffer=self.shm.control.buf)
        return bool(control_array[0] == 1)

    def signal_stop(self) -> None:
        control_array: NDArray[Any] = np.ndarray((2,), dtype=np.int32, buffer=self.shm.control.buf)
        control_array[1] = 1

    def read_state(self) -> tuple[NDArray[Any], NDArray[Any], NDArray[Any]] | None:
        seq = self._get_seq(0)
        if seq > self._last_state_seq:
            self._last_state_seq = seq
            pos_array: NDArray[Any] = np.ndarray(
                (self.nq,), dtype=np.float64, buffer=self.shm.positions.buf
            )
            vel_array: NDArray[Any] = np.ndarray(
                (self.nv,), dtype=np.float64, buffer=self.shm.velocities.buf
            )
            eff_array: NDArray[Any] = np.ndarray(
                (self.nu,), dtype=np.float64, buffer=self.shm.efforts.buf
            )
            return pos_array.copy(), vel_array.copy(), eff_array.copy()
        return None

    def write_command(self, mode: int, values) -> None:  # type: ignore[no-untyped-def]
        cmd_array: NDArray[Any] = np.ndarray((self.nu,), dtype=np.float64, buffer=self.shm.cmd.buf)
        cmd_array[:] = 0.0
        if self.nu:
            cmd_array[: min(self.nu, len(values))] = values[: self.nu]
        mode_array: NDArray[Any] = np.ndarray((1,), dtype=np.int32, buffer=self.shm.cmd_mode.buf)
        mode_array[0] = int(mode)
        self._increment_seq(1)

    def _increment_seq(self, index: int) -> None:
        seq_array: NDArray[Any] = np.ndarray((2,), dtype=np.int64, buffer=self.shm.seq.buf)
        seq_array[index] += 1

    def _get_seq(self, index: int) -> int:
        seq_array: NDArray[Any] = np.ndarray((2,), dtype=np.int64, buffer=self.shm.seq.buf)
        return int(seq_array[index])

    def cleanup(self) -> None:
        for shm in self.shm.as_list():
            try:
                shm.unlink()
            except Exception:
                pass
            try:
                shm.close()
            except Exception:
                pass
