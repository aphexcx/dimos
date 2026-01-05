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

"""MuJoCo simulation driver implementing the standard manipulator driver interface.

This driver provides a MuJoCo-based simulation backend that implements the exact
same interface as hardware drivers (XArmDriver, PiperDriver). Controllers using
ManipulatorDriverSpec work identically with this simulation.

Example:
    # Same usage pattern as hardware driver!
    driver = MuJoCoManipulatorDriver(config={
        "model_path": "path/to/xarm7.xml",
        "dof": 7,
    })
    driver.start()

    # Use standard interface
    driver.move_joint([0, 0, 0, 0, 0, 0, 0])

    # Or via pub/sub (same as hardware)
    driver.joint_position_command.publish(JointCommand(positions=[...]))
"""

from dataclasses import dataclass
import logging
from threading import Event, Thread
import time
from typing import Any

from dimos.core import rpc
from dimos.hardware.manipulators.base.components.motion import StandardMotionComponent
from dimos.hardware.manipulators.base.components.servo import StandardServoComponent
from dimos.hardware.manipulators.base.components.status import StandardStatusComponent
from dimos.hardware.manipulators.base.driver import BaseManipulatorDriver
from dimos.hardware.manipulators.base.spec import ManipulatorCapabilities

from .sdk_wrapper import MuJoCoManipulatorSDK


@dataclass
class SimDriverConfig:
    """Configuration for MuJoCo manipulator driver."""

    # Model
    model_path: str
    dof: int = 7

    # Control rates
    control_rate: int = 100  # Hz - joint feedback rate
    physics_rate: int = 500  # Hz - physics simulation rate
    monitor_rate: int = 10  # Hz - robot state monitoring

    # PD gains
    kp: float | list[float] = 100.0
    kd: float | list[float] = 10.0

    # Features
    has_gripper: bool = False
    has_force_torque: bool = False

    # Rendering (offscreen)
    enable_rendering: bool = False
    render_width: int = 640
    render_height: int = 480

    # Viewer (interactive window)
    enable_viewer: bool = False  # Launch interactive MuJoCo viewer window


class MuJoCoManipulatorDriver(BaseManipulatorDriver):
    """MuJoCo simulation driver with same interface as hardware drivers.

    This driver extends BaseManipulatorDriver and uses MuJoCoManipulatorSDK
    instead of a hardware SDK. It provides:

    1. Same pub/sub interface (joint_state, robot_state, etc.)
    2. Same RPC methods (move_joint, enable_servo, etc.)
    3. Same component system (StandardMotionComponent, etc.)

    The key difference is that it also runs the physics simulation loop.

    Architecture:
        - Inherits threading model from BaseManipulatorDriver
        - Adds physics stepping thread
        - Uses same standard components as hardware

    Usage:
        # Create driver (same as hardware)
        driver = MuJoCoManipulatorDriver({
            "model_path": "xarm7.xml",
            "dof": 7,
        })

        # Start driver (same as hardware)
        driver.start()

        # Use pub/sub (same as hardware)
        driver.joint_state.subscribe(callback)
        driver.joint_position_command.publish(cmd)

        # Use RPC (same as hardware)
        driver.move_joint([0, 0, 0, 0, 0, 0, 0])
        state = driver.get_joint_state()

    With Controllers:
        # Controllers work identically with simulation!
        controller = CartesianMotionController(arm_driver=driver)
        controller.start()
        controller.set_target_pose(position=[0.3, 0, 0.4], orientation=[0, 0, 0, 1])
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize the MuJoCo simulation driver.

        Args:
            config: Configuration dict with at least 'model_path' and 'dof'
        """
        self.logger = logging.getLogger(self.__class__.__name__)

        # Extract config
        dof = config.get("dof", 7)
        model_path = config.get("model_path")

        if not model_path:
            raise ValueError("model_path is required in config")

        # Create MuJoCo SDK wrapper
        sdk = MuJoCoManipulatorSDK(dof=dof)

        # Create capabilities from config
        ManipulatorCapabilities(
            dof=dof,
            has_gripper=config.get("has_gripper", False),
            has_force_torque=config.get("has_force_torque", False),
            has_impedance_control=False,
            has_cartesian_control=True,
            max_joint_velocity=[3.14] * dof,  # ~180 deg/s
            max_joint_acceleration=[10.0] * dof,
            joint_limits_lower=[-2 * 3.14159] * dof,
            joint_limits_upper=[2 * 3.14159] * dof,
            payload_mass=config.get("payload_mass", 5.0),
            reach=config.get("reach", 0.7),
        )

        # Create standard components (same as hardware drivers!)
        components = [
            StandardMotionComponent(),
            StandardServoComponent(),
            StandardStatusComponent(),
        ]

        # Initialize base driver
        super().__init__(
            sdk=sdk,
            components=components,
            config=config,
            name=config.get("name", "MuJoCoManipulatorDriver"),
        )

        # Store typed SDK reference for simulation-specific methods
        self._sim_sdk: MuJoCoManipulatorSDK = sdk

        # Physics thread
        self._physics_thread: Thread | None = None
        self._physics_rate = config.get("physics_rate", 500)

        # Compute substeps: how many physics steps per control step
        self._control_rate = config.get("control_rate", 100)
        self._substeps = max(1, self._physics_rate // self._control_rate)

        self.logger.info(
            f"MuJoCo driver initialized: {dof} DOF, "
            f"physics={self._physics_rate}Hz, control={self._control_rate}Hz, "
            f"substeps={self._substeps}"
        )

    # =========================================================================
    # Lifecycle (Override base class)
    # =========================================================================

    @rpc
    def start(self) -> None:
        """Start driver threads including physics simulation."""
        # Start base driver threads (control loop, state monitor)
        super().start()

        # Start physics simulation thread
        self._physics_thread = Thread(
            target=self._physics_loop,
            name=f"{self.name}-PhysicsLoop",
            daemon=True,
        )
        self._physics_thread.start()
        self.logger.info("Physics simulation thread started")

    @rpc
    def stop(self) -> None:
        """Stop all threads and cleanup."""
        self.logger.info("Stopping MuJoCo driver...")

        # Signal stop (inherited from base)
        self.stop_event.set()

        # Wait for physics thread
        if self._physics_thread and self._physics_thread.is_alive():
            self._physics_thread.join(timeout=2.0)

        # Stop base driver
        super().stop()

    # =========================================================================
    # Physics Loop (Simulation-specific)
    # =========================================================================

    def _physics_loop(self) -> None:
        """Physics simulation loop running at physics_rate Hz.

        This thread advances the MuJoCo simulation at a fixed rate,
        separate from the control loop that reads state.
        """
        period = 1.0 / self._physics_rate
        next_time = time.perf_counter() + period

        self.logger.debug(f"Physics loop started at {self._physics_rate}Hz")

        while not self.stop_event.is_set():
            try:
                # Step physics (single step)
                self._sim_sdk.step_simulation(n_steps=1)

                # Note: Don't call sync_viewer() here - the passive viewer
                # auto-syncs at its own rate. Calling sync() at physics rate
                # (500Hz) causes race conditions with the viewer thread.

            except Exception as e:
                self.logger.error(f"Physics loop error: {e}")

            # Rate control
            next_time += period
            sleep_time = next_time - time.perf_counter()
            if sleep_time > 0:
                time.sleep(sleep_time)
            else:
                # Fell behind - reset timing
                next_time = time.perf_counter() + period
                if sleep_time < -period * 10:
                    self.logger.warning(f"Physics loop fell behind by {-sleep_time * 1000:.1f}ms")

        self.logger.debug("Physics loop stopped")

    # =========================================================================
    # Simulation-Specific RPC Methods
    # =========================================================================

    @rpc
    def reset_simulation(self) -> None:
        """Reset simulation to initial state.

        Simulation-only method - not available on hardware.
        """
        self._sim_sdk.reset_simulation()
        self.logger.info("Simulation reset to initial state")

    @rpc
    def reset_to_state(
        self,
        qpos: list[float] | None = None,
        qvel: list[float] | None = None,
    ) -> None:
        """Teleport robot to a specific state.

        Simulation-only method - not available on hardware.

        Args:
            qpos: Target joint positions (or None to keep current)
            qvel: Target joint velocities (or None to set to zero)
        """
        self._sim_sdk.reset_to_state(qpos, qvel)
        self.logger.debug(f"State reset: qpos={qpos}, qvel={qvel}")

    @rpc
    def get_simulation_time(self) -> float:
        """Get current simulation time.

        Returns:
            Time in seconds since simulation start
        """
        return self._sim_sdk.get_simulation_time()

    @rpc
    def get_contact_forces(self) -> list[dict[str, Any]]:
        """Get contact information from physics.

        Returns:
            List of contact dicts
        """
        return self._sim_sdk.get_contact_forces()

    @rpc
    def render(self, camera_name: str | None = None) -> Any:
        """Render current frame.

        Args:
            camera_name: Camera to render from

        Returns:
            RGB image as numpy array or None
        """
        return self._sim_sdk.render(camera_name)

    # =========================================================================
    # Viewer Control (Interactive Window)
    # =========================================================================

    @rpc
    def launch_viewer(self) -> bool:
        """Launch interactive MuJoCo viewer window.

        Simulation-only method. Opens a 3D visualization window showing
        the robot and environment. The viewer runs in a background thread
        and updates automatically with the simulation.

        Returns:
            True if viewer launched successfully
        """
        success = self._sim_sdk.launch_viewer()
        if success:
            self.logger.info("Viewer launched")
        return success

    @rpc
    def close_viewer(self) -> None:
        """Close the interactive viewer window.

        Simulation-only method.
        """
        self._sim_sdk.close_viewer()
        self.logger.info("Viewer closed")

    @rpc
    def is_viewer_running(self) -> bool:
        """Check if viewer window is currently open.

        Returns:
            True if viewer is running
        """
        return self._sim_sdk.is_viewer_running()

    # =========================================================================
    # Factory Method
    # =========================================================================

    @classmethod
    def create(
        cls,
        model_path: str,
        dof: int = 7,
        **kwargs: Any,
    ) -> "MuJoCoManipulatorDriver":
        """Factory method to create a simulation driver.

        Args:
            model_path: Path to MJCF/URDF model file
            dof: Degrees of freedom
            **kwargs: Additional config options

        Returns:
            Configured driver instance

        Example:
            driver = MuJoCoManipulatorDriver.create(
                model_path="xarm7.xml",
                dof=7,
                control_rate=100,
            )
        """
        config = {
            "model_path": model_path,
            "dof": dof,
            **kwargs,
        }
        return cls(config)
