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

"""MuJoCo engine subprocess for macOS viewer support."""

from __future__ import annotations

import base64
import json
from pathlib import Path
import pickle
import signal
import sys
import time

import mujoco
from mujoco import viewer
import numpy as np
from robot_descriptions.loaders.mujoco import load_robot_description

from dimos.simulation.manipulators.engine_shared_memory import (
    CMD_MODE_POSITION,
    CMD_MODE_VELOCITY,
    EngineShmReader,
)


def _load_model(asset: str, config_path: str | None) -> tuple[mujoco.MjModel, mujoco.MjData]:
    if config_path:
        resolved = Path(config_path).expanduser()
        xml_path = resolved / "scene.xml" if resolved.is_dir() else resolved
        if not xml_path.exists():
            raise FileNotFoundError(f"MuJoCo XML not found: {xml_path}")
        model = mujoco.MjModel.from_xml_path(str(xml_path))
    else:
        model = load_robot_description(asset)

    data = mujoco.MjData(model)
    return model, data


def _run_engine(config: dict, shm_names: dict[str, str]) -> None:
    asset = config["asset"]
    config_path = config.get("config_path")
    headless = bool(config.get("headless", False))
    nq = int(config["nq"])
    nv = int(config["nv"])
    nu = int(config["nu"])

    shm = EngineShmReader(shm_names, nq=nq, nv=nv, nu=nu)
    try:
        model, data = _load_model(asset=asset, config_path=config_path)

        n_act = min(nu, int(model.nu))
        n_q = min(nq, int(model.nq))
        position_targets = np.zeros(max(1, n_act), dtype=np.float64)
        if n_act and n_q:
            position_targets[: min(n_act, n_q)] = data.qpos[: min(n_act, n_q)]

        shm.signal_ready()

        dt = float(model.opt.timestep)

        def _apply_command(cmd_mode: int, cmd_values: np.ndarray) -> None:
            if not n_act:
                return
            if cmd_mode == CMD_MODE_VELOCITY:
                position_targets[:n_act] += cmd_values[:n_act] * dt
            else:
                position_targets[:n_act] = cmd_values[:n_act]

        def _step_once(sync_viewer: bool) -> None:
            loop_start = time.time()
            cmd = shm.read_command()
            if cmd is not None:
                cmd_mode, cmd_values = cmd
                _apply_command(cmd_mode, cmd_values)
            if n_act:
                data.ctrl[:n_act] = position_targets[:n_act]
            mujoco.mj_step(model, data)
            if sync_viewer:
                m_viewer.sync()
            shm.write_state(data.qpos, data.qvel, data.qfrc_actuator)
            elapsed = time.time() - loop_start
            sleep_time = dt - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

        if headless:
            while not shm.should_stop():
                _step_once(sync_viewer=False)
            return

        with viewer.launch_passive(
            model, data, show_left_ui=False, show_right_ui=False
        ) as m_viewer:
            while m_viewer.is_running() and not shm.should_stop():
                _step_once(sync_viewer=True)
    finally:
        shm.cleanup()


if __name__ == "__main__":

    def _signal_handler(_signum: int, _frame) -> None:  # type: ignore[no-untyped-def]
        sys.exit(0)

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    engine_config = pickle.loads(base64.b64decode(sys.argv[1]))
    engine_shm_names = json.loads(sys.argv[2])

    _run_engine(engine_config, engine_shm_names)
