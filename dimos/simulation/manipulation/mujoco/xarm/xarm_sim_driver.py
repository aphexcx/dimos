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

"""xArm simulation driver - same interface as hardware XArmDriver.

This module provides an xArm-specific simulation driver that mirrors
the hardware XArmDriver interface. Controllers using the XArmDriver
work identically with this simulation driver.

Usage:
    # Same pattern as hardware XArmDriver!
    from dimos.simulation.manipulation.mujoco.xarm import XArmSimDriver

    driver = XArmSimDriver(dof=7)
    driver.start()

    # Use exactly like hardware
    driver.move_joint([0, 0, 0, 0, 0, 0, 0])
    state = driver.get_joint_state()
"""

import logging
from pathlib import Path
from typing import Any

from dimos.core import rpc
from dimos.hardware.manipulators.base.components import (
    StandardMotionComponent,
    StandardServoComponent,
    StandardStatusComponent,
)

from ..base import MuJoCoManipulatorDriver, MuJoCoManipulatorSDK, get_robot_config

logger = logging.getLogger(__name__)

# Fixed model path for xArm7
MODEL_PATH = Path(__file__).parent.parent.parent / "data" / "xarm7" / "scene.xml"


class XArmSimDriver(MuJoCoManipulatorDriver):
    """xArm simulation driver with same interface as hardware XArmDriver.

    This driver provides a MuJoCo-based simulation that implements the exact
    same interface as the hardware XArmDriver. Controllers (CartesianMotionController,
    JointTrajectoryController, etc.) work identically with this simulation.

    Example:
        # Same usage as hardware XArmDriver!
        driver = XArmSimDriver(dof=7)
        driver.start()

        # Standard interface (works on hw and sim)
        positions = driver.get_joint_state()
        driver.move_joint([0.1, -0.2, 0.3, 0, 0, 0, 0])

        # Simulation-specific (not available on hardware)
        driver.reset_simulation()
        driver.reset_to_state([0] * 7)
    """

    def __init__(self, **kwargs: Any) -> None:
        """Initialize the xArm simulation driver.

        Args:
            **kwargs: Configuration parameters:
                - dof: Degrees of freedom. Default: 7
                - has_gripper: Whether to simulate gripper. Default: False
                - has_force_torque: Whether to simulate F/T sensor. Default: False
                - control_rate: Joint feedback rate in Hz. Default: 100
                - physics_rate: Physics simulation rate in Hz. Default: 500
                - kp: Position gain (scalar or per-joint list)
                - kd: Velocity gain (scalar or per-joint list)
                - enable_viewer: Launch MuJoCo viewer window. Default: False
        """
        # Extract config
        config: dict[str, Any] = kwargs.pop("config", {})

        # Extract params that might be passed directly
        driver_params = [
            "dof",
            "has_gripper",
            "has_force_torque",
            "control_rate",
            "physics_rate",
            "monitor_rate",
            "kp",
            "kd",
            "enable_viewer",
            "enable_rendering",
        ]
        for param in driver_params:
            if param in kwargs:
                config[param] = kwargs.pop(param)

        # Set DOF (only 7 supported for now)
        dof = config.get("dof", 7)
        config["dof"] = dof

        # Get xArm-specific defaults (PD gains, etc.)
        robot_type = f"xarm{dof}"
        try:
            robot_defaults = get_robot_config(robot_type)
            for key, value in robot_defaults.items():
                config.setdefault(key, value)
        except ValueError:
            logger.warning(f"No preset config for {robot_type}, using generic defaults")

        # Set model path - fixed location, error if not found
        if not MODEL_PATH.exists():
            raise FileNotFoundError(
                f"xArm7 model not found at: {MODEL_PATH}\n"
                f"Please place the model file at this location."
            )
        config["model_path"] = str(MODEL_PATH)

        # Set driver name
        config.setdefault("name", f"XArm{dof}SimDriver")

        logger.info(f"Initializing XArmSimDriver: dof={dof}, model={config.get('model_path')}")

        # Initialize base simulation driver
        super().__init__(config)

        logger.info(f"XArm{dof}SimDriver initialized successfully")


# Blueprint configuration for declarative composition
def get_blueprint() -> dict[str, Any]:
    """Get blueprint configuration for XArmSimDriver."""
    return {
        "name": "XArmSimDriver",
        "class": XArmSimDriver,
        "config": {
            "dof": 7,
            "has_gripper": False,
            "has_force_torque": False,
            "control_rate": 100,
            "physics_rate": 500,
            "monitor_rate": 10,
        },
        "inputs": {
            "joint_position_command": "JointCommand",
            "joint_velocity_command": "JointCommand",
        },
        "outputs": {
            "joint_state": "JointState",
            "robot_state": "RobotState",
        },
    }


# Expose blueprint for declarative composition
xarm_sim_driver = XArmSimDriver.blueprint
