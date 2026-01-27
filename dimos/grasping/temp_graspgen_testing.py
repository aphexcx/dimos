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

"""Temporary testing module for grasp generation pipeline.

Wires: GraspingSkill → GraspPipeline → Perception + GraspGen
"""

from __future__ import annotations

from dimos.core.module import Module, rpc
from dimos.core.stream import In, Out
from dimos.msgs.geometry_msgs import PoseArray
from dimos.msgs.std_msgs import Header
from dimos.utils.logging_config import setup_logger

logger = setup_logger()


class GraspPipeline(Module):
    """Wires perception → grasp generation via RPC calls."""

    trigger: In[str]  # Object name to grasp
    grasps: Out[PoseArray]  # Output for failure signaling (empty PoseArray)

    rpc_calls: list[str] = [
        "ObjectSceneRegistrationModule.get_object_pointcloud_by_name",
        "ObjectSceneRegistrationModule.get_full_scene_pointcloud",
        "GraspGenModule.generate_grasps",
        "GraspingSkillContainer.signal_no_grasps",
    ]

    _default_object_name: str = "object"

    def __init__(self, object_name: str = "object") -> None:
        super().__init__()
        self._default_object_name = object_name

    @rpc
    def start(self) -> None:
        super().start()
        self._disposables.add(self.trigger.subscribe(self._on_trigger))
        logger.info(f"GraspPipeline started (default_object={self._default_object_name})")

    @rpc
    def stop(self) -> None:
        super().stop()
        logger.info("GraspPipeline stopped")

    def _on_trigger(self, object_name: str) -> None:
        # Use provided object name, or fall back to default
        target = object_name if object_name else self._default_object_name
        logger.info(f"Grasp trigger received for '{target}'")

        try:
            get_pc = self.get_rpc_calls(
                "ObjectSceneRegistrationModule.get_object_pointcloud_by_name"
            )
            pc = get_pc(target)
        except Exception as e:
            logger.error(f"Failed to get pointcloud: {e}")
            self._signal_failure(f"Failed to get pointcloud: {e}")
            return

        if pc is None:
            logger.warning(f"No pointcloud for '{target}'")
            self._signal_failure(f"No pointcloud available for '{target}'")
            return

        try:
            get_scene = self.get_rpc_calls(
                "ObjectSceneRegistrationModule.get_full_scene_pointcloud"
            )
            scene = get_scene(target)
        except Exception:
            scene = None

        try:
            generate = self.get_rpc_calls("GraspGenModule.generate_grasps")
            result = generate(pc, scene)

            if not result or len(result.poses) == 0:
                logger.warning(f"No grasps generated for '{target}'")
        except Exception as e:
            logger.error(f"Grasp generation failed: {e}")

    def _signal_failure(self, reason: str) -> None:
        """Signal to the grasping skill that grasp generation failed."""
        signal = self.get_rpc_calls("GraspingSkillContainer.signal_no_grasps")
        signal(reason)


def grasp_pipeline(object_name: str = "object"):
    return GraspPipeline.blueprint(object_name=object_name)


__all__ = ["GraspPipeline", "grasp_pipeline"]
