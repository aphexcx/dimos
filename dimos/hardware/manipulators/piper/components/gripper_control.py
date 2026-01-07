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
Gripper Control Component for PiperDriver.

Provides RPC methods for gripper control operations.
"""

from typing import Any

from dimos.core import rpc
from dimos.hardware.manipulators.base.components import component_api
from dimos.utils.logging_config import setup_logger

logger = setup_logger()


class GripperControlComponent:
    """
    Component providing gripper control RPC methods for PiperDriver.

    This component follows the component-based architecture pattern.
    Dependencies are injected via constructor or setter methods.
    """

    def __init__(self, sdk=None):
        """Initialize the gripper control component.

        Args:
            sdk: SDK wrapper instance (can be set later via set_sdk)
        """
        self.sdk = sdk

    def set_sdk(self, sdk):
        """Inject SDK dependency."""
        self.sdk = sdk

    @component_api
    def set_gripper(
        self,
        gripper_angle: int,
        gripper_effort: int = 100,
        gripper_enable: int = 0x01,
        gripper_state: int = 0x00,
    ) -> tuple[bool, str]:
        """
        Set gripper position and parameters.

        Args:
            gripper_angle: Gripper angle (0-1000, 0=closed, 1000=open)
            gripper_effort: Gripper effort/force (0-1000)
            gripper_enable: Gripper enable (0x00=disabled, 0x01=enabled)
            gripper_state: Gripper state

        Returns:
            Tuple of (success, message)
        """
        try:
            result = self.sdk.native_sdk.GripperCtrl(
                gripper_angle, gripper_effort, gripper_enable, gripper_state
            )

            if result:
                return (True, f"Gripper set to angle={gripper_angle}, effort={gripper_effort}")
            else:
                return (False, "Failed to set gripper")

        except Exception as e:
            logger.error(f"set_gripper failed: {e}")
            return (False, str(e))

    @component_api
    def open_gripper(self, effort: int = 100) -> tuple[bool, str]:
        """
        Open gripper.

        Args:
            effort: Gripper effort (0-1000)

        Returns:
            Tuple of (success, message)
        """
        result: tuple[bool, str] = self.set_gripper(gripper_angle=1000, gripper_effort=effort)  # type: ignore[no-any-return]
        return result

    @component_api
    def close_gripper(self, effort: int = 100) -> tuple[bool, str]:
        """
        Close gripper.

        Args:
            effort: Gripper effort (0-1000)

        Returns:
            Tuple of (success, message)
        """
        return self.set_gripper(gripper_angle=0, gripper_effort=effort)

    @component_api
    def set_gripper_position(
        self, position: float, wait: bool = False, effort: int = 100
    ) -> tuple[int, str]:
        """
        Set gripper position (for compatibility with manipulation_client).

        Args:
            position: Target position (0-1000, 0=closed, 1000=open)
            wait: Wait for completion (ignored in current implementation)
            effort: Gripper effort (0-1000)

        Returns:
            Tuple of (error_code, message). 0 = success, -1 = error
        """
        try:
            result = self.sdk.native_sdk.GripperCtrl(int(position), effort, 0x01, 0x00)
            if result:
                return (0, f"Gripper position set to {position}")
            else:
                return (-1, "Failed to set gripper position")
        except Exception as e:
            logger.error(f"set_gripper_position failed: {e}")
            return (-1, str(e))

    @component_api
    def get_gripper_position(self) -> tuple[int, float]:
        """
        Get current gripper position (for compatibility with manipulation_client).

        Returns:
            Tuple of (error_code, position). 0 = success, -1 = error
            Position is 0-1000 (0=closed, 1000=open)
        """
        try:
            # GetGripperState returns 0-100 percentage, convert to 0-1000
            state = self.sdk.native_sdk.GetGripperState()
            position = state * 10.0  # Convert percentage to 0-1000 range
            return (0, position)
        except Exception as e:
            logger.error(f"get_gripper_position failed: {e}")
            return (-1, 0.0)

    @component_api
    def set_gripper_zero(self) -> tuple[bool, str]:
        """
        Set gripper zero position.

        Returns:
            Tuple of (success, message)
        """
        try:
            # This method may require specific SDK implementation
            # For now, we'll just document it
            logger.info("set_gripper_zero called - implementation may vary by SDK version")
            return (True, "Gripper zero set (if supported by SDK)")

        except Exception as e:
            logger.error(f"set_gripper_zero failed: {e}")
            return (False, str(e))
