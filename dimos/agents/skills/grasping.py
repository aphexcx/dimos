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

from __future__ import annotations
import threading
from dimos.core.skill_module import SkillModule
from dimos.core.stream import In, Out
from dimos.msgs.geometry_msgs import PoseArray
from dimos.protocol.skill.skill import rpc, skill
from dimos.utils.logging_config import setup_logger
from dimos.utils.transform_utils import quaternion_to_euler

logger = setup_logger()


class GraspingSkillContainer(SkillModule):
    """Core grasping skill - model and sensor agnostic.

    Streams:
        trigger (Out): Object name to trigger grasp generation for
        grasps (In): Receives generated grasp poses from any provider
    """

    trigger: Out[str]  # Object name to grasp
    grasps: In[PoseArray]

    _latest_grasps: PoseArray | None = None
    _grasps_received: threading.Event

    @rpc
    def start(self) -> None:
        self._grasps_received = threading.Event()
        self._disposables.add(self.grasps.subscribe(self._on_grasps))
        logger.info("GraspingSkillContainer started")

    @rpc
    def stop(self) -> None:
        self._latest_grasps = None
        self._grasps_received.set()  # Unblock any waiting calls
        super().stop()
        logger.info("GraspingSkillContainer stopped")

    def _on_grasps(self, grasps: PoseArray) -> None:
        self._latest_grasps = grasps
        self._grasps_received.set()  # Signal that grasps have arrived
        logger.info(f"Received {len(grasps.poses)} grasps")

    @rpc
    def get_grasp_poses(self) -> PoseArray | None:
        return self._latest_grasps

    @rpc
    def signal_no_grasps(self, reason: str = "unknown") -> None:
        """Signal that grasp generation failed (e.g., no pointcloud)."""
        logger.warning(f"Grasp generation failed: {reason}")
        self._latest_grasps = None
        self._grasps_received.set()  # Unblock waiting skill

    @skill()
    def generate_grasps(self, object_name: str = "object", timeout: float = 120.0) -> str:
        """Generate grasp poses for the specified object.
        This waits for the grasp generator to finish before returning.
        object_name is the name of the object to generate grasps.
        """
        # Clear previous grasps and reset event
        self._latest_grasps = None
        self._grasps_received.clear()

        # Trigger grasp generation
        self.trigger.publish(object_name)
        logger.info(f"Grasp generation triggered for '{object_name}', waiting for response (timeout={timeout}s)...")

        # Wait for grasps to arrive with timeout
        if not self._grasps_received.wait(timeout=timeout):
            logger.error(f"Grasp generation timed out after {timeout}s for '{object_name}'")
            return f"Grasp generation timed out after {timeout}s for '{object_name}'"

        # Return result with best grasp position
        if self._latest_grasps is None or len(self._latest_grasps.poses) == 0:
            return f"No grasps generated for '{object_name}'"

        best = self._latest_grasps.poses[0]
        pos = best.position
        rpy = quaternion_to_euler(best.orientation, degrees=True)
        return (
            f"Generated {len(self._latest_grasps.poses)} grasps for '{object_name}'. "
            f"Best grasp: pos=({pos.x:.4f}, {pos.y:.4f}, {pos.z:.4f}), "
            f"rpy=({rpy.x:.1f}, {rpy.y:.1f}, {rpy.z:.1f}) degrees"
        )

grasping_skill = GraspingSkillContainer.blueprint

__all__ = ["GraspingSkillContainer", "grasping_skill"]
