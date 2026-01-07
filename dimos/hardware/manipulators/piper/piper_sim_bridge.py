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
Piper Simulation Bridge - MuJoCo backend that mimics the Piper SDK interface.

This bridge allows the PiperSDKWrapper to use the same code path for both
hardware and simulation by implementing the subset of C_PiperInterface_V2
methods used by the wrapper.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import mujoco

from dimos.simulation.manipulators.mujoco_sim import MujocoSimBridgeBase
from dimos.utils.logging_config import setup_logger

logger = setup_logger()

# Unit conversion constants (matching piper_wrapper.py)
RAD_TO_PIPER = 57295.7795  # radians to Piper units (0.001 degrees)
PIPER_TO_RAD = 1.0 / RAD_TO_PIPER  # Piper units to radians


@dataclass
class JointState:
    """Mimics Piper SDK joint state message."""

    joint_1: float = 0.0
    joint_2: float = 0.0
    joint_3: float = 0.0
    joint_4: float = 0.0
    joint_5: float = 0.0
    joint_6: float = 0.0


@dataclass
class JointMsgs:
    """Mimics Piper SDK joint messages."""

    joint_state: JointState = None  # type: ignore

    def __post_init__(self):
        if self.joint_state is None:
            self.joint_state = JointState()


@dataclass
class ArmStatus:
    """Mimics Piper SDK arm status."""

    err_code: int = 0
    motion_status: int = 0


@dataclass
class ArmStatusMsg:
    """Mimics Piper SDK arm status message."""

    arm_status: ArmStatus = None  # type: ignore

    def __post_init__(self):
        if self.arm_status is None:
            self.arm_status = ArmStatus()


class PiperSimBridge(MujocoSimBridgeBase):
    """
    Lightweight, in-process backend that mimics the subset of the Piper SDK
    (C_PiperInterface_V2) used by PiperSDKWrapper.

    The bridge keeps an internal joint state, runs MuJoCo simulation, and
    provides implementations for the SDK methods so the driver stack can
    operate without modification.
    """

    def __init__(
        self,
        control_frequency: float = 100.0,
    ):
        # Initialize base class (loads model, sets up threading, etc.)
        super().__init__(
            robot_name="piper",
            num_joints=6,  # Piper is always 6-DOF
            control_frequency=control_frequency,
        )

        # --- Piper-specific state variables --- #
        self._enabled: bool = False
        self._err_code: int = 0

        # Joint state in Piper units (0.001 degrees) for SDK compatibility
        self._joint_positions_piper = [0.0] * self._num_joints

        # Initialize Piper units from base class positions
        with self._lock:
            for i in range(self._num_joints):
                self._joint_positions_piper[i] = self._joint_positions[i] * RAD_TO_PIPER

        # --- Gripper control support --- #
        # Find gripper actuator ID (if it exists in the model)
        # mj_name2id returns -1 if not found
        self._gripper_actuator_id = mujoco.mj_name2id(
            self._model, mujoco.mjtObj.mjOBJ_ACTUATOR, "gripper"
        )
        if self._gripper_actuator_id >= 0:
            self._gripper_position_target = 0.0  # Target position (0-1000, 0=closed, 1000=open)
            self._gripper_position_current = 0.0  # Current position (0-1000)
            logger.info("Gripper actuator found in MuJoCo model")
        else:
            # Gripper not found in model
            self._gripper_position_target = 0.0
            self._gripper_position_current = 0.0
            logger.warning("Gripper actuator not found in MuJoCo model")

    # ============= Abstract Method Implementations =============

    def _apply_control(self) -> None:
        """Apply control commands to MuJoCo actuators."""
        with self._lock:
            pos_targets = list(self._joint_position_targets)
            enabled = self._enabled
            gripper_target = self._gripper_position_target
            gripper_actuator_id = self._gripper_actuator_id

        # Apply control if enabled
        if enabled:
            for i in range(self._num_joints):
                if i < self._model.nu:
                    self._data.ctrl[i] = pos_targets[i]

        # Apply gripper control (independent of enabled state)
        if gripper_actuator_id >= 0:
            # Convert Piper gripper units (0-1000) to MuJoCo position (0-0.035)
            # 0 = closed, 1000 = open
            gripper_ctrl = (gripper_target / 1000.0) * 0.035
            gripper_ctrl = max(0.0, min(0.035, gripper_ctrl))  # Clamp to valid range
            with self._lock:
                if gripper_actuator_id < self._model.nu:
                    self._data.ctrl[gripper_actuator_id] = gripper_ctrl

    def _update_joint_state(self) -> None:
        """Update internal joint state from MuJoCo simulation."""
        with self._lock:
            for i in range(min(self._num_joints, self._model.nq)):
                # Update base class positions (in radians)
                self._joint_positions[i] = float(self._data.qpos[i])
                # Store in Piper units (0.001 degrees)
                self._joint_positions_piper[i] = self._data.qpos[i] * RAD_TO_PIPER

            # Update gripper position from MuJoCo
            if self._gripper_actuator_id >= 0 and self._gripper_actuator_id < self._model.nu:
                # Read current gripper control value and convert back to Piper units (0-1000)
                gripper_ctrl = float(self._data.ctrl[self._gripper_actuator_id])
                # Convert from MuJoCo position (0-0.035) to Piper units (0-1000)
                self._gripper_position_current = (gripper_ctrl / 0.035) * 1000.0

    # ============= Connection Management =============

    def ConnectPort(self, piper_init: bool = True, start_thread: bool = True) -> None:
        """Connect to simulation (mimics C_PiperInterface_V2.ConnectPort)."""
        logger.info("PiperSimBridge: ConnectPort()")
        if start_thread:
            self.connect()  # Use base class connect method

    def DisconnectPort(self) -> None:
        """Disconnect from simulation (mimics C_PiperInterface_V2.DisconnectPort)."""
        logger.info("PiperSimBridge: DisconnectPort()")
        with self._lock:
            self._enabled = False
        self.disconnect()  # Use base class disconnect method

    # ============= Enable/Disable =============

    def EnablePiper(self) -> bool:
        """Enable the arm (mimics C_PiperInterface_V2.EnablePiper)."""
        with self._lock:
            self._enabled = True
        # Lock current positions when enabling to prevent movement
        self.hold_current_position()
        logger.info("PiperSimBridge: Arm enabled")
        return True

    def DisablePiper(self) -> None:
        """Disable the arm (mimics C_PiperInterface_V2.DisablePiper)."""
        with self._lock:
            self._enabled = False
        logger.info("PiperSimBridge: Arm disabled")

    # ============= Motion Control =============

    def MotionCtrl_2(
        self,
        ctrl_mode: int = 0x01,
        move_mode: int = 0x01,
        move_spd_rate_ctrl: int = 30,
        is_mit_mode: int = 0x00,
    ) -> None:
        """Set motion control parameters (mimics C_PiperInterface_V2.MotionCtrl_2)."""
        logger.debug(f"PiperSimBridge: MotionCtrl_2(ctrl_mode={ctrl_mode}, move_mode={move_mode})")

    def JointCtrl(
        self,
        joint_1: float,
        joint_2: float,
        joint_3: float,
        joint_4: float,
        joint_5: float,
        joint_6: float,
    ) -> None:
        """Set joint positions (mimics C_PiperInterface_V2.JointCtrl).

        Args:
            joint_1-6: Target positions in Piper units (0.001 degrees)
        """
        with self._lock:
            # Convert from Piper units (0.001 degrees) to radians for MuJoCo
            self._joint_position_targets[0] = joint_1 * PIPER_TO_RAD
            self._joint_position_targets[1] = joint_2 * PIPER_TO_RAD
            self._joint_position_targets[2] = joint_3 * PIPER_TO_RAD
            self._joint_position_targets[3] = joint_4 * PIPER_TO_RAD
            self._joint_position_targets[4] = joint_5 * PIPER_TO_RAD
            self._joint_position_targets[5] = joint_6 * PIPER_TO_RAD

        logger.debug(f"PiperSimBridge: JointCtrl targets (rad): {self._joint_position_targets}")

    def EmergencyStop(self) -> None:
        """Emergency stop (mimics C_PiperInterface_V2.EmergencyStop)."""
        self.hold_current_position()  # Use base class helper
        logger.info("PiperSimBridge: Emergency stop")

    # ============= State Query =============

    def GetArmJointMsgs(self) -> JointMsgs:
        """Get joint state messages (mimics C_PiperInterface_V2.GetArmJointMsgs).

        Returns:
            JointMsgs with joint_state containing positions in Piper units
        """
        with self._lock:
            joint_state = JointState(
                joint_1=self._joint_positions_piper[0],
                joint_2=self._joint_positions_piper[1],
                joint_3=self._joint_positions_piper[2],
                joint_4=self._joint_positions_piper[3],
                joint_5=self._joint_positions_piper[4],
                joint_6=self._joint_positions_piper[5],
            )
        return JointMsgs(joint_state=joint_state)

    def GetArmStatus(self) -> ArmStatusMsg:
        """Get arm status (mimics C_PiperInterface_V2.GetArmStatus).

        Returns:
            ArmStatusMsg with arm_status
        """
        with self._lock:
            arm_status = ArmStatus(
                err_code=self._err_code,
                motion_status=1 if self._enabled else 0,
            )
        return ArmStatusMsg(arm_status=arm_status)

    def GetPiperFirmwareVersion(self) -> str:
        """Get firmware version (mimics C_PiperInterface_V2.GetPiperFirmwareVersion).

        Returns:
            Firmware version string
        """
        return "PiperSimBridge v1.0.0"

    def ClearError(self) -> None:
        """Clear errors (mimics C_PiperInterface_V2.ClearError if it exists)."""
        with self._lock:
            self._err_code = 0
        logger.info("PiperSimBridge: Errors cleared")

    # ============= Gripper Control =============

    def GripperCtrl(
        self,
        gripper_angle: int,
        gripper_effort: int = 100,
        gripper_enable: int = 0x01,
        gripper_state: int = 0x00,
    ) -> bool:
        """Control gripper (mimics C_PiperInterface_V2.GripperCtrl).

        Args:
            gripper_angle: Gripper angle (0-1000, 0=closed, 1000=open)
            gripper_effort: Gripper effort/force (0-1000, not used in sim)
            gripper_enable: Gripper enable (0x00=disabled, 0x01=enabled, not used in sim)
            gripper_state: Gripper state (not used in sim)

        Returns:
            True if successful
        """
        # Clamp gripper angle to valid range
        gripper_angle = max(0, min(1000, int(gripper_angle)))

        with self._lock:
            self._gripper_position_target = float(gripper_angle)

        logger.debug(f"PiperSimBridge: GripperCtrl angle={gripper_angle}")
        return True

    def GetGripperState(self) -> int:
        """Get gripper state (mimics C_PiperInterface_V2.GetGripperState).

        Returns:
            Gripper position 0-100 (percentage)
        """
        with self._lock:
            # Convert from 0-1000 to 0-100
            position_pct = int(self._gripper_position_current / 10.0)
        return position_pct
