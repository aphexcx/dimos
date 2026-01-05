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

"""MuJoCo SDK wrapper implementing the standard manipulator interface.

This module provides a MuJoCo-based implementation of BaseManipulatorSDK,
allowing simulation to be used interchangeably with real hardware.

The wrapper implements all required methods from BaseManipulatorSDK plus
simulation-specific extensions for physics stepping, state reset, etc.
"""

from dataclasses import dataclass, field
import logging
import math
from typing import Any

import mujoco
import mujoco.viewer
import numpy as np
from numpy.typing import NDArray

from dimos.hardware.manipulators.base.sdk_interface import (
    BaseManipulatorSDK,
    ManipulatorInfo,
)


@dataclass
class SimulationConfig:
    """Configuration for MuJoCo manipulator simulation."""

    model_path: str  # Path to MJCF/URDF model
    dof: int = 7  # Degrees of freedom
    timestep: float = 0.002  # Simulation timestep (seconds)
    control_timestep: float = 0.02  # Control loop timestep (seconds)

    # PD control gains (per-joint or scalar)
    kp: list[float] | float = 100.0  # Position gain
    kd: list[float] | float = 10.0  # Velocity/damping gain

    # Joint limits (if not specified, read from model)
    joint_limits_lower: list[float] | None = None
    joint_limits_upper: list[float] | None = None

    # Velocity and acceleration limits
    max_velocity: float = 3.14  # rad/s (~180 deg/s)
    max_acceleration: float = 10.0  # rad/s^2

    # Gripper configuration
    has_gripper: bool = False
    gripper_joint_name: str | None = None

    # Rendering (offscreen)
    enable_rendering: bool = True
    render_width: int = 640
    render_height: int = 480

    # Viewer (interactive window)
    enable_viewer: bool = False  # Launch interactive MuJoCo viewer window


class MuJoCoManipulatorSDK(BaseManipulatorSDK):
    """MuJoCo implementation of the manipulator SDK interface.

    This SDK wrapper provides a simulation backend that implements the exact
    same interface as hardware SDK wrappers (XArmSDKWrapper, PiperSDKWrapper).
    Controllers using BaseManipulatorSDK work identically with this simulation.

    Standard Interface (BaseManipulatorSDK):
        - get_joint_positions(), set_joint_positions()
        - get_joint_velocities(), set_joint_velocities()
        - enable_servos(), disable_servos()
        - get_robot_state(), get_error_code(), etc.

    Simulation Extensions (not in BaseManipulatorSDK):
        - step_simulation() - advance physics
        - reset_to_state() - teleport to state
        - get_simulation_time() - get sim clock
        - render() - get camera image

    Example:
        # Create SDK (same pattern as hardware)
        sdk = MuJoCoManipulatorSDK(dof=7)
        sdk.connect({"model_path": "xarm7.xml"})

        # Use standard interface (hardware-compatible)
        positions = sdk.get_joint_positions()
        sdk.set_joint_positions([0, 0, 0, 0, 0, 0, 0])

        # Simulation-specific: step physics
        sdk.step_simulation(n_steps=10)
    """

    def __init__(self, dof: int = 7) -> None:
        """Initialize the MuJoCo SDK wrapper.

        Args:
            dof: Degrees of freedom for the manipulator
        """
        self.logger = logging.getLogger(self.__class__.__name__)
        self.dof = dof

        # MuJoCo objects
        self.model: mujoco.MjModel | None = None
        self.data: mujoco.MjData | None = None

        # Configuration
        self.config: SimulationConfig | None = None

        # Control state
        self._connected = False
        self._servos_enabled = True
        self._control_mode = "position"  # position, velocity, torque
        self._error_code = 0
        self._is_moving = False

        # PD control gains (will be set from config)
        self._kp: NDArray[np.floating[Any]] = np.ones(dof) * 100.0
        self._kd: NDArray[np.floating[Any]] = np.ones(dof) * 10.0

        # Target state for control
        self._target_positions: NDArray[np.floating[Any]] = np.zeros(dof)
        self._target_velocities: NDArray[np.floating[Any]] = np.zeros(dof)
        self._target_efforts: NDArray[np.floating[Any]] = np.zeros(dof)

        # Joint limits (default, updated from model)
        self._joint_limits_lower: list[float] = [-2 * math.pi] * dof
        self._joint_limits_upper: list[float] = [2 * math.pi] * dof
        self._velocity_limits: list[float] = [3.14] * dof
        self._acceleration_limits: list[float] = [10.0] * dof

        # Renderer (optional, for offscreen rendering)
        self._renderer: mujoco.Renderer | None = None

        # Viewer (optional, for interactive visualization)
        self._viewer: mujoco.viewer.Handle | None = None
        self._enable_viewer: bool = False

    # =========================================================================
    # Connection Management (BaseManipulatorSDK)
    # =========================================================================

    def connect(self, config: dict[str, Any]) -> bool:
        """Load MuJoCo model and initialize simulation.

        Args:
            config: Configuration dict with at least 'model_path'.
                   Can also include 'dof', 'kp', 'kd', etc.

        Returns:
            True if model loaded successfully
        """
        try:
            model_path = config.get("model_path")
            if not model_path:
                self.logger.error("No model_path specified in config")
                return False

            # Update DOF if specified
            if "dof" in config:
                self.dof = config["dof"]

            # Load MuJoCo model
            self.logger.info(f"Loading MuJoCo model from: {model_path}")
            self.model = mujoco.MjModel.from_xml_path(model_path)
            self.data = mujoco.MjData(self.model)

            # Reset to initial state
            mujoco.mj_resetData(self.model, self.data)

            # Set timestep if specified
            if "timestep" in config:
                self.model.opt.timestep = config["timestep"]

            # Configure PD gains
            kp = config.get("kp", 100.0)
            kd = config.get("kd", 10.0)
            if isinstance(kp, (int, float)):
                self._kp = np.ones(self.dof) * kp
            else:
                self._kp = np.array(kp[: self.dof])
            if isinstance(kd, (int, float)):
                self._kd = np.ones(self.dof) * kd
            else:
                self._kd = np.array(kd[: self.dof])

            # Extract joint limits from model
            self._extract_joint_limits()

            # Initialize target positions to current state
            self._target_positions = self.data.qpos[: self.dof].copy()

            # Initialize renderer if enabled (offscreen)
            if config.get("enable_rendering", False):
                width = config.get("render_width", 640)
                height = config.get("render_height", 480)
                self._renderer = mujoco.Renderer(self.model, height=height, width=width)

            # Mark as connected before launching viewer (viewer checks is_connected())
            self._connected = True

            # Initialize viewer if enabled (interactive window)
            self._enable_viewer = config.get("enable_viewer", False)
            if self._enable_viewer:
                self.launch_viewer()
            self.logger.info(
                f"MuJoCo simulation connected: {self.dof} DOF, timestep={self.model.opt.timestep}s"
            )
            return True

        except Exception as e:
            self.logger.error(f"Failed to load MuJoCo model: {e}")
            self._error_code = 1
            return False

    def disconnect(self) -> None:
        """Clean up simulation resources."""
        # Close viewer if open
        self.close_viewer()

        if self._renderer:
            self._renderer.close()
            self._renderer = None
        self.model = None
        self.data = None
        self._connected = False
        self.logger.info("MuJoCo simulation disconnected")

    def is_connected(self) -> bool:
        """Check if simulation is initialized.

        Returns:
            True if model is loaded
        """
        return self._connected and self.model is not None and self.data is not None

    # =========================================================================
    # Joint State Query (BaseManipulatorSDK)
    # =========================================================================

    def get_joint_positions(self) -> list[float]:
        """Get current joint positions from simulation.

        Returns:
            Joint positions in radians
        """
        if not self.is_connected():
            return [0.0] * self.dof
        return list(self.data.qpos[: self.dof])

    def get_joint_velocities(self) -> list[float]:
        """Get current joint velocities from simulation.

        Returns:
            Joint velocities in rad/s
        """
        if not self.is_connected():
            return [0.0] * self.dof
        return list(self.data.qvel[: self.dof])

    def get_joint_efforts(self) -> list[float]:
        """Get current joint efforts/torques from simulation.

        Returns:
            Joint torques in Nm
        """
        if not self.is_connected():
            return [0.0] * self.dof
        # qfrc_actuator contains actuator forces
        return list(self.data.qfrc_actuator[: self.dof])

    # =========================================================================
    # Joint Motion Control (BaseManipulatorSDK)
    # =========================================================================

    def set_joint_positions(
        self,
        positions: list[float],
        velocity: float = 1.0,
        acceleration: float = 1.0,
        wait: bool = False,
    ) -> bool:
        """Set target joint positions for PD control.

        The simulation uses PD control to track these positions.
        Call step_simulation() to advance physics.

        Args:
            positions: Target positions in radians
            velocity: Velocity scaling (0-1), affects PD tracking speed
            acceleration: Acceleration scaling (0-1), currently unused
            wait: If True, step simulation until reached (blocking)

        Returns:
            True if command accepted
        """
        if not self.is_connected() or not self._servos_enabled:
            self.logger.warning(
                f"set_joint_positions rejected: connected={self.is_connected()}, servos_enabled={self._servos_enabled}"
            )
            return False

        # Clip to joint limits
        positions_arr = np.array(positions[: self.dof])
        positions_arr = np.clip(positions_arr, self._joint_limits_lower, self._joint_limits_upper)
        self._target_positions = positions_arr

        self.logger.info(f"set_joint_positions: target={positions_arr[:3]}...")

        # Scale gains by velocity factor for smoother motion
        # (Higher velocity = higher effective gains)
        self._apply_pd_control(velocity_scale=velocity)

        self._is_moving = True
        self._control_mode = "position"

        if wait:
            # Step until converged
            self._wait_until_converged(positions_arr)

        return True

    def set_joint_velocities(self, velocities: list[float]) -> bool:
        """Set target joint velocities.

        Args:
            velocities: Target velocities in rad/s

        Returns:
            True if command accepted
        """
        if not self.is_connected() or not self._servos_enabled:
            return False

        velocities_arr = np.array(velocities[: self.dof])
        # Clip to velocity limits
        velocities_arr = np.clip(
            velocities_arr,
            [-v for v in self._velocity_limits],
            self._velocity_limits,
        )
        self._target_velocities = velocities_arr

        # For velocity control, set control directly
        # This uses velocity-based control: torque = kd * (v_target - v_current)
        self._apply_velocity_control()

        self._is_moving = np.any(np.abs(velocities_arr) > 0.01)
        self._control_mode = "velocity"

        return True

    def set_joint_efforts(self, efforts: list[float]) -> bool:
        """Set joint torques directly.

        Args:
            efforts: Target torques in Nm

        Returns:
            True if command accepted
        """
        if not self.is_connected() or not self._servos_enabled:
            return False

        efforts_arr = np.array(efforts[: self.dof])
        self._target_efforts = efforts_arr

        # Direct torque control
        self.data.ctrl[: self.dof] = efforts_arr

        self._is_moving = True
        self._control_mode = "torque"

        return True

    def stop_motion(self) -> bool:
        """Stop all motion by holding current position.

        Returns:
            True if stop successful
        """
        if not self.is_connected():
            return False

        # Set target to current position
        self._target_positions = self.data.qpos[: self.dof].copy()
        self._target_velocities = np.zeros(self.dof)
        self._apply_pd_control()

        self._is_moving = False
        return True

    # =========================================================================
    # Servo Control (BaseManipulatorSDK)
    # =========================================================================

    def enable_servos(self) -> bool:
        """Enable motor control (simulation always ready).

        Returns:
            True
        """
        self._servos_enabled = True
        self.logger.debug("Servos enabled (simulation)")
        return True

    def disable_servos(self) -> bool:
        """Disable motor control (zero torques).

        Returns:
            True
        """
        self._servos_enabled = False
        if self.is_connected():
            self.data.ctrl[: self.dof] = 0
        self.logger.debug("Servos disabled (simulation)")
        return True

    def are_servos_enabled(self) -> bool:
        """Check if servos are enabled.

        Returns:
            True if enabled
        """
        return self._servos_enabled

    # =========================================================================
    # System State (BaseManipulatorSDK)
    # =========================================================================

    def get_robot_state(self) -> dict[str, Any]:
        """Get current robot/simulation state.

        Returns:
            State dictionary
        """
        return {
            "state": 0 if self._error_code == 0 else 2,  # 0=ready, 2=error
            "mode": {"position": 0, "velocity": 1, "torque": 2}.get(self._control_mode, 0),
            "error_code": self._error_code,
            "is_moving": self._is_moving,
            "simulation_time": self.data.time if self.data else 0.0,
        }

    def get_error_code(self) -> int:
        """Get current error code.

        Returns:
            Error code (0 = no error)
        """
        return self._error_code

    def get_error_message(self) -> str:
        """Get human-readable error message.

        Returns:
            Error message string
        """
        error_messages = {
            0: "",
            1: "Failed to load model",
            2: "Simulation diverged (NaN detected)",
            3: "Joint limit exceeded",
        }
        return error_messages.get(self._error_code, f"Unknown error {self._error_code}")

    def clear_errors(self) -> bool:
        """Clear error state.

        Returns:
            True
        """
        self._error_code = 0
        return True

    def emergency_stop(self) -> bool:
        """Execute emergency stop (zero all torques, disable servos).

        Returns:
            True
        """
        self.disable_servos()
        self.stop_motion()
        return True

    # =========================================================================
    # Information (BaseManipulatorSDK)
    # =========================================================================

    def get_info(self) -> ManipulatorInfo:
        """Get manipulator information.

        Returns:
            ManipulatorInfo object
        """
        return ManipulatorInfo(
            vendor="MuJoCo Simulation",
            model=self.model.name if self.model else "Unknown",
            dof=self.dof,
            firmware_version=mujoco.__version__,
            serial_number="SIM-001",
        )

    def get_joint_limits(self) -> tuple[list[float], list[float]]:
        """Get joint position limits.

        Returns:
            Tuple of (lower_limits, upper_limits) in radians
        """
        return (self._joint_limits_lower.copy(), self._joint_limits_upper.copy())

    def get_velocity_limits(self) -> list[float]:
        """Get joint velocity limits.

        Returns:
            Maximum velocities in rad/s
        """
        return self._velocity_limits.copy()

    def get_acceleration_limits(self) -> list[float]:
        """Get joint acceleration limits.

        Returns:
            Maximum accelerations in rad/s^2
        """
        return self._acceleration_limits.copy()

    # =========================================================================
    # Optional Methods (BaseManipulatorSDK)
    # =========================================================================

    def get_cartesian_position(self) -> dict[str, float] | None:
        """Get end-effector pose via forward kinematics.

        Returns:
            Pose dict or None
        """
        if not self.is_connected():
            return None

        # Get end-effector body (assumes last body or named 'end_effector')
        try:
            # Try to find end-effector site or body
            ee_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_SITE, "end_effector")
            if ee_id < 0:
                ee_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, "end_effector")
            if ee_id < 0:
                # Use last body as end-effector
                ee_id = self.model.nbody - 1

            pos = self.data.xpos[ee_id]
            rot_mat = self.data.xmat[ee_id].reshape(3, 3)

            # Convert rotation matrix to euler angles (ZYX convention)
            roll = math.atan2(rot_mat[2, 1], rot_mat[2, 2])
            pitch = math.atan2(-rot_mat[2, 0], math.sqrt(rot_mat[2, 1] ** 2 + rot_mat[2, 2] ** 2))
            yaw = math.atan2(rot_mat[1, 0], rot_mat[0, 0])

            return {
                "x": float(pos[0]),
                "y": float(pos[1]),
                "z": float(pos[2]),
                "roll": roll,
                "pitch": pitch,
                "yaw": yaw,
            }
        except Exception as e:
            self.logger.warning(f"Failed to get cartesian position: {e}")
            return None

    def set_control_mode(self, mode: str) -> bool:
        """Set control mode.

        Args:
            mode: 'position', 'velocity', or 'torque'

        Returns:
            True if mode supported
        """
        if mode in ("position", "velocity", "torque"):
            self._control_mode = mode
            return True
        return False

    def get_control_mode(self) -> str | None:
        """Get current control mode.

        Returns:
            Mode string
        """
        return self._control_mode

    # =========================================================================
    # Simulation-Specific Extensions (NOT in BaseManipulatorSDK)
    # =========================================================================

    def step_simulation(self, n_steps: int = 1) -> None:
        """Advance physics simulation by n steps.

        This is simulation-specific - real hardware doesn't need this.

        Args:
            n_steps: Number of physics steps to take
        """
        if not self.is_connected():
            return

        for _ in range(n_steps):
            # Apply control based on current mode
            if self._servos_enabled:
                if self._control_mode == "position":
                    self._apply_pd_control()
                elif self._control_mode == "velocity":
                    self._apply_velocity_control()
                # torque mode: ctrl already set directly

            # Step physics
            mujoco.mj_step(self.model, self.data)

            # Check for simulation divergence
            if np.any(np.isnan(self.data.qpos)) or np.any(np.isnan(self.data.qvel)):
                self.logger.error("Simulation diverged (NaN detected)")
                self._error_code = 2
                break

    def reset_to_state(
        self,
        qpos: list[float] | None = None,
        qvel: list[float] | None = None,
    ) -> None:
        """Reset simulation to a specific state (teleport).

        This is simulation-specific - can't teleport real hardware!

        Args:
            qpos: Joint positions (or None to keep current)
            qvel: Joint velocities (or None to set to zero)
        """
        if not self.is_connected():
            return

        if qpos is not None:
            self.data.qpos[: len(qpos)] = qpos
        if qvel is not None:
            self.data.qvel[: len(qvel)] = qvel
        else:
            self.data.qvel[: self.dof] = 0

        # Update derived quantities
        mujoco.mj_forward(self.model, self.data)

        # Update target to match new state
        self._target_positions = self.data.qpos[: self.dof].copy()

    def reset_simulation(self) -> None:
        """Reset simulation to initial state."""
        if not self.is_connected():
            return
        mujoco.mj_resetData(self.model, self.data)
        self._target_positions = self.data.qpos[: self.dof].copy()
        self._error_code = 0

    def get_simulation_time(self) -> float:
        """Get current simulation time.

        Returns:
            Time in seconds
        """
        return self.data.time if self.data else 0.0

    def render(self, camera_name: str | None = None) -> NDArray[np.uint8] | None:
        """Render current frame from camera.

        Args:
            camera_name: Name of camera (or None for default view)

        Returns:
            RGB image as numpy array or None
        """
        if not self._renderer or not self.is_connected():
            return None

        try:
            if camera_name:
                camera_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_CAMERA, camera_name)
                self._renderer.update_scene(self.data, camera=camera_id)
            else:
                self._renderer.update_scene(self.data)

            return self._renderer.render()
        except Exception as e:
            self.logger.warning(f"Render failed: {e}")
            return None

    def get_contact_forces(self) -> list[dict[str, Any]]:
        """Get contact information from physics.

        Returns:
            List of contact dicts with position, force, bodies
        """
        if not self.is_connected():
            return []

        contacts = []
        for i in range(self.data.ncon):
            contact = self.data.contact[i]
            contacts.append(
                {
                    "pos": contact.pos.tolist(),
                    "force": self.data.efc_force[contact.efc_address]
                    if contact.efc_address >= 0
                    else 0.0,
                    "geom1": contact.geom1,
                    "geom2": contact.geom2,
                }
            )
        return contacts

    # =========================================================================
    # Viewer Methods (Interactive Window)
    # =========================================================================

    def launch_viewer(self) -> bool:
        """Launch interactive MuJoCo viewer window.

        Uses launch_passive() so the viewer runs in a background thread
        and doesn't block the simulation loop.

        Returns:
            True if viewer launched successfully
        """
        if not self.is_connected():
            self.logger.warning("Cannot launch viewer: not connected")
            return False

        if self._viewer is not None:
            self.logger.warning("Viewer already running")
            return True

        try:
            # Use passive viewer - runs in background thread, non-blocking
            self._viewer = mujoco.viewer.launch_passive(self.model, self.data)
            self.logger.info("MuJoCo viewer launched")
            return True
        except Exception as e:
            self.logger.error(f"Failed to launch viewer: {e}")
            return False

    def close_viewer(self) -> None:
        """Close the interactive viewer window."""
        if self._viewer is not None:
            try:
                self._viewer.close()
            except Exception as e:
                self.logger.warning(f"Error closing viewer: {e}")
            finally:
                self._viewer = None
                self.logger.info("MuJoCo viewer closed")

    def sync_viewer(self) -> None:
        """Sync viewer with current simulation state.

        Call this in the physics loop to update the viewer display.
        """
        if self._viewer is not None:
            try:
                self._viewer.sync()
            except Exception as e:
                # Viewer may have been closed by user
                self.logger.debug(f"Viewer sync failed (may be closed): {e}")
                self._viewer = None

    def is_viewer_running(self) -> bool:
        """Check if viewer is currently running.

        Returns:
            True if viewer window is open
        """
        if self._viewer is None:
            return False
        try:
            return self._viewer.is_running()
        except Exception:
            self._viewer = None
            return False

    # =========================================================================
    # Private Methods
    # =========================================================================

    def _extract_joint_limits(self) -> None:
        """Extract joint limits from MuJoCo model."""
        if not self.model:
            return

        # MuJoCo stores joint limits in model.jnt_range
        # Shape: (njnt, 2) where [:, 0] is lower and [:, 1] is upper
        n_joints = min(self.dof, self.model.njnt)

        lower = []
        upper = []
        for i in range(n_joints):
            if self.model.jnt_limited[i]:
                lower.append(float(self.model.jnt_range[i, 0]))
                upper.append(float(self.model.jnt_range[i, 1]))
            else:
                lower.append(-2 * math.pi)
                upper.append(2 * math.pi)

        # Pad if needed
        while len(lower) < self.dof:
            lower.append(-2 * math.pi)
            upper.append(2 * math.pi)

        self._joint_limits_lower = lower
        self._joint_limits_upper = upper

    def _apply_pd_control(self, velocity_scale: float = 1.0) -> None:
        """Apply position control by setting target positions directly.

        Note: This assumes the MuJoCo model uses position actuators,
        where data.ctrl expects target positions (not torques).
        MuJoCo's internal PD controller handles the actual control.
        """
        if not self.is_connected():
            return

        # For position actuators: ctrl = target position directly
        # MuJoCo handles PD control internally based on actuator gainprm
        self.data.ctrl[: self.dof] = self._target_positions

        # Debug: log occasionally (every ~100 calls)
        if hasattr(self, "_pd_call_count"):
            self._pd_call_count += 1
        else:
            self._pd_call_count = 0
        if self._pd_call_count % 500 == 0:
            self.logger.debug(
                f"_apply_pd_control: ctrl={self.data.ctrl[:3]}..., qpos={self.data.qpos[:3]}..."
            )

    def _apply_velocity_control(self) -> None:
        """Apply velocity control."""
        if not self.is_connected():
            return

        qd = self.data.qvel[: self.dof]
        qd_error = self._target_velocities - qd

        # Velocity control: tau = kd * (qd_target - qd)
        tau = self._kd * qd_error
        self.data.ctrl[: self.dof] = tau

    def _wait_until_converged(
        self,
        target: NDArray[np.floating[Any]],
        tolerance: float = 0.01,
        max_steps: int = 10000,
    ) -> bool:
        """Step simulation until position converges.

        Args:
            target: Target positions
            tolerance: Position error tolerance (rad)
            max_steps: Maximum steps before giving up

        Returns:
            True if converged
        """
        for _ in range(max_steps):
            self.step_simulation()

            error = np.abs(self.data.qpos[: self.dof] - target)
            if np.all(error < tolerance):
                self._is_moving = False
                return True

        self.logger.warning("Position convergence timeout")
        return False
