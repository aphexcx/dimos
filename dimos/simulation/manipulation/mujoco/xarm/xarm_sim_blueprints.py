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

"""
Blueprints for xArm simulation - mirrors hardware xarm_blueprints.py

This module provides declarative blueprints for xArm simulation that are
identical in interface to the hardware blueprints. Swap between hardware
and simulation by changing imports.

Usage:
    # Run via CLI (TODO: register with dimos CLI):
    # dimos run xarm-sim-servo         # Simulation driver only
    # dimos run xarm-sim-trajectory    # Simulation + trajectory controller
    # dimos run xarm-sim-cartesian     # Simulation + Cartesian controller

    # Or programmatically:
    from dimos.simulation.manipulation.mujoco.xarm import xarm7_sim_servo
    coordinator = xarm7_sim_servo.build()
    coordinator.loop()

    # Swap to hardware by changing import:
    from dimos.hardware.manipulators.xarm.xarm_blueprints import xarm7_servo
    coordinator = xarm7_servo.build()  # Same interface!
"""

from pathlib import Path
from typing import Any

from dimos.core.blueprints import autoconnect
from dimos.core.transport import LCMTransport
from dimos.manipulation.control import cartesian_motion_controller, joint_trajectory_controller
from dimos.msgs.geometry_msgs import PoseStamped
from dimos.msgs.sensor_msgs import JointCommand, JointState, RobotState
from dimos.msgs.trajectory_msgs import JointTrajectory

from .xarm_sim_driver import xarm_sim_driver as xarm_sim_driver_blueprint

# Data directory for model files
DATA_DIR = Path(__file__).parent.parent.parent / "data"


def xarm_sim_driver(**config: Any) -> Any:
    """Create a blueprint for XArmSimDriver.

    This mirrors the hardware xarm_driver() function for seamless swapping.

    Args:
        **config: Configuration parameters:
            - dof: Degrees of freedom (5, 6, or 7). Default: 7
            - model_path: Path to MJCF model (auto-detected if not provided)
            - has_gripper: Whether to simulate gripper. Default: False
            - has_force_torque: Whether to simulate F/T sensor. Default: False
            - control_rate: Joint feedback rate in Hz. Default: 100
            - physics_rate: Physics simulation rate in Hz. Default: 500

    Returns:
        Blueprint configuration for XArmSimDriver
    """
    # Set defaults (same as hardware)
    dof = config.setdefault("dof", 7)
    config.setdefault("has_gripper", False)
    config.setdefault("has_force_torque", False)
    config.setdefault("control_rate", 100)
    config.setdefault("physics_rate", 500)
    config.setdefault("monitor_rate", 10)

    # Auto-detect model path if not provided
    if "model_path" not in config:
        model_path = DATA_DIR / f"xarm{dof}" / "scene.xml"
        if model_path.exists():
            config["model_path"] = str(model_path)
        else:
            # Try alternative paths
            alt_path = DATA_DIR / f"xarm{dof}" / f"xarm{dof}.xml"
            if alt_path.exists():
                config["model_path"] = str(alt_path)

    return xarm_sim_driver_blueprint(**config)


# =============================================================================
# xArm7 Simulation Servo Control Blueprint
# =============================================================================
# Mirrors hardware xarm7_servo blueprint - same topics, same interface.
# =============================================================================

xarm7_sim_servo = xarm_sim_driver(
    dof=7,
    has_gripper=False,
    has_force_torque=False,
    control_rate=100,
    physics_rate=500,
).transports(
    {
        # Joint state feedback (position, velocity, effort)
        ("joint_state", JointState): LCMTransport("/xarm/joint_states", JointState),
        # Robot state feedback (mode, state, errors)
        ("robot_state", RobotState): LCMTransport("/xarm/robot_state", RobotState),
        # Position commands input
        ("joint_position_command", JointCommand): LCMTransport(
            "/xarm/joint_position_command", JointCommand
        ),
        # Velocity commands input
        ("joint_velocity_command", JointCommand): LCMTransport(
            "/xarm/joint_velocity_command", JointCommand
        ),
    }
)

# =============================================================================
# xArm7 Simulation Trajectory Control Blueprint
# =============================================================================

xarm7_sim_trajectory = autoconnect(
    xarm_sim_driver(
        dof=7,
        has_gripper=False,
        has_force_torque=False,
        control_rate=100,
        physics_rate=100,
        enable_viewer=True,
    ),
    joint_trajectory_controller(
        control_frequency=100.0,
    ),
).transports(
    {
        ("joint_state", JointState): LCMTransport("/xarm/joint_states", JointState),
        ("robot_state", RobotState): LCMTransport("/xarm/robot_state", RobotState),
        ("joint_position_command", JointCommand): LCMTransport(
            "/xarm/joint_position_command", JointCommand
        ),
        ("trajectory", JointTrajectory): LCMTransport("/trajectory", JointTrajectory),
    }
)


__all__ = [
    "xarm7_sim_servo",
    "xarm7_sim_trajectory",
]
