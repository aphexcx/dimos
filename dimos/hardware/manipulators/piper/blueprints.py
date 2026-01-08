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

"""Blueprints for Piper manipulator using B-lite architecture.

Usage:
    # Run via CLI:
    dimos run piper-servo           # Driver only
    dimos run piper-trajectory      # Driver + Joint trajectory controller

    # Or programmatically:
    from dimos.hardware.manipulators.piper.blueprints import piper_trajectory
    coordinator = piper_trajectory.build()
    coordinator.loop()
"""

from dimos.core.blueprints import autoconnect
from dimos.core.transport import LCMTransport
from dimos.hardware.manipulators.piper.arm import piper as piper_blueprint
from dimos.manipulation.control import joint_trajectory_controller
from dimos.msgs.sensor_msgs import (
    JointCommand,
    JointState,
    RobotState,
)
from dimos.msgs.trajectory_msgs import JointTrajectory

# =============================================================================
# Piper Servo Control Blueprint
# =============================================================================
# Piper driver in servo mode - publishes joint states, accepts joint commands.
# =============================================================================

piper_servo = piper_blueprint(
    can_port="can0",
    dof=6,
    control_rate=100.0,
    monitor_rate=10.0,
).transports(
    {
        # Joint state feedback (position, velocity, effort)
        ("joint_state", JointState): LCMTransport("/piper/joint_states", JointState),
        # Robot state feedback (mode, state, errors)
        ("robot_state", RobotState): LCMTransport("/piper/robot_state", RobotState),
    }
)

# =============================================================================
# Piper Servo with Gripper Blueprint
# =============================================================================

piper_servo_gripper = piper_blueprint(
    can_port="can0",
    dof=6,
    control_rate=100.0,
    monitor_rate=10.0,
    has_gripper=True,
).transports(
    {
        ("joint_state", JointState): LCMTransport("/piper/joint_states", JointState),
        ("robot_state", RobotState): LCMTransport("/piper/robot_state", RobotState),
    }
)

# =============================================================================
# Piper Trajectory Control Blueprint (Driver + Trajectory Controller)
# =============================================================================
# Combines Piper driver with JointTrajectoryController for trajectory execution.
# The controller receives JointTrajectory messages and executes them.
# =============================================================================

piper_trajectory = autoconnect(
    piper_blueprint(
        can_port="can0",
        dof=6,
        control_rate=100.0,  # Higher rate for smoother trajectory execution
        monitor_rate=10.0,
    ),
    joint_trajectory_controller(
        control_frequency=100.0,
    ),
).transports(
    {
        # Shared topics between driver and controller
        ("joint_state", JointState): LCMTransport("/piper/joint_states", JointState),
        ("robot_state", RobotState): LCMTransport("/piper/robot_state", RobotState),
        ("joint_position_command", JointCommand): LCMTransport(
            "/piper/joint_position_command", JointCommand
        ),
        # Trajectory input topic
        ("trajectory", JointTrajectory): LCMTransport("/trajectory", JointTrajectory),
    }
)

# =============================================================================
# Piper Dual Arm Blueprint (for dual-arm robots)
# =============================================================================

piper_left = piper_blueprint(
    can_port="can0",
    dof=6,
    control_rate=100.0,
    monitor_rate=10.0,
).transports(
    {
        ("joint_state", JointState): LCMTransport("/piper/left/joint_states", JointState),
        ("robot_state", RobotState): LCMTransport("/piper/left/robot_state", RobotState),
    }
)

piper_right = piper_blueprint(
    can_port="can1",
    dof=6,
    control_rate=100.0,
    monitor_rate=10.0,
).transports(
    {
        ("joint_state", JointState): LCMTransport("/piper/right/joint_states", JointState),
        ("robot_state", RobotState): LCMTransport("/piper/right/robot_state", RobotState),
    }
)


__all__ = [
    "piper_left",
    "piper_right",
    "piper_servo",
    "piper_servo_gripper",
    "piper_trajectory",
]
