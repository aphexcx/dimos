# Copyright 2026 Dimensional Inc.
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

from dataclasses import dataclass
import os
from threading import Event, Thread
import time
from typing import Any

import cv2
import numpy as np
import rerun as rr
from scipy.spatial.transform import Rotation

from dimos.core import In, Module, ModuleConfig, Out, rpc
from dimos.core.rpc_client import RpcCall
from dimos.dashboard.rerun_init import connect_rerun
from dimos.msgs.geometry_msgs import Quaternion, Transform, Vector3
from dimos.msgs.sensor_msgs.CameraInfo import CameraInfo
from dimos.msgs.sensor_msgs.Image import Image
from dimos.utils.logging_config import setup_logger
from dimos.utils.transform_utils import euler_to_quaternion

logger = setup_logger()


@dataclass
class ArucoTrackerConfig(ModuleConfig):
    """Configuration for ArUco tracker."""

    marker_size: float = 0.1
    aruco_dict: int = cv2.aruco.DICT_4X4_50
    camera_frame_id: str = "camera_color_optical_frame"  # Frame ID for the camera
    rate: float = 1  # Rate in Hz - defines speed of execution (process loop then sleep)
    max_loops: int = 5  # Maximum number of loops to process
    move_robot_to_aruco: bool = True  # Whether to move the robot to the ArUco marker
    move_robot_to_aruco_rotation: bool = (
        False  # Whether to follow ArUco rotation (False = fixed orientation)
    )
    safety_max_delta: float = 0.10  # Max allowed 3D distance (meters) between commands
    safety_max_rot_delta: float = (
        0.2  # Max allowed rotation delta (radians) per axis between commands
    )
    hardware_id: str = "arm"  # Hardware ID for ControlOrchestrator EE pose lookup
    robot_connected: bool = True  # Whether robot is connected (False = use dummy EE transform)
    expected_marker_count: int = 4  # Expected number of ArUco markers (±1 tolerance)


class ArucoTracker(Module[ArucoTrackerConfig]):
    """
    ArUco marker tracker that detects markers in camera images and computes their transforms.

    Subscribes to camera images and camera info, detects ArUco markers,
    and publishes their transforms relative to the camera frame.
    """

    # Transport ports
    color_image: In[Image]
    camera_info: In[CameraInfo]
    annotated_image: Out[Image]

    config: ArucoTrackerConfig
    default_config = ArucoTrackerConfig

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

        # ArUco detector
        self._aruco_dict = cv2.aruco.getPredefinedDictionary(self.config.aruco_dict)
        self._aruco_params = cv2.aruco.DetectorParameters()
        self._detector = cv2.aruco.ArucoDetector(self._aruco_dict, self._aruco_params)

        # params from callback
        self._camera_matrix: np.ndarray | None = None
        self._dist_coeffs: np.ndarray | None = None
        self._latest_image: Image | None = None

        # Threading for processing loop
        self._stop_event = Event()
        self._processing_thread: Thread | None = None
        self._loop_count = 0

        # RPC calls to ControlOrchestrator
        self._get_ee_positions_rpc: RpcCall | None = None
        self._move_to_cartesian_pose_rpc: RpcCall | None = None

        # Safety: track last commanded pose for delta check
        self._last_commanded_pos: tuple[float, float, float] | None = None
        self._last_commanded_rot: tuple[float, float, float] | None = None

    @rpc
    def start(self) -> None:
        """Start the ArUco tracker by subscribing to camera streams."""
        super().start()

        connect_rerun()
        self._disposables.add(self.camera_info.observable().subscribe(self._update_camera_info))
        self._disposables.add(self.color_image.observable().subscribe(self._store_latest_image))

        self._loop_count = 0
        self._stop_event.clear()
        self._processing_thread = Thread(
            target=self._processing_loop, daemon=True, name="ArucoTracker"
        )
        self._processing_thread.start()

    @rpc
    def stop(self) -> None:
        """Stop the ArUco tracker."""
        self._stop_event.set()

        if self._processing_thread is not None and self._processing_thread.is_alive():
            self._processing_thread.join(timeout=2.0)
        super().stop()

    def _store_latest_image(self, image: Image) -> None:
        """Store the latest image for processing."""
        self._latest_image = image

    def _update_camera_info(self, camera_info: CameraInfo) -> None:
        """Update camera intrinsics from CameraInfo message."""
        if len(camera_info.K) == 9:
            fx, _, cx, _, fy, cy, _, _, _ = camera_info.K
            self._camera_matrix = np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1]], dtype=np.float32)
            self._dist_coeffs = (
                np.array(camera_info.D, dtype=np.float32) if camera_info.D else np.zeros(5)
            )

    @rpc
    def set_ControlOrchestrator_get_ee_positions(self, rpc_call: RpcCall) -> None:
        """Wire get_ee_positions RPC from ControlOrchestrator."""
        self._get_ee_positions_rpc = rpc_call
        self._get_ee_positions_rpc.set_rpc(self.rpc)

    @rpc
    def set_ControlOrchestrator_move_to_cartesian_pose(self, rpc_call: RpcCall) -> None:
        """Wire move_to_cartesian_pose RPC from ControlOrchestrator."""
        self._move_to_cartesian_pose_rpc = rpc_call
        self._move_to_cartesian_pose_rpc.set_rpc(self.rpc)

    def _log_transform_to_rerun(self, transform: Transform) -> None:
        """Log a transform to Rerun without named frame references (avoids duplicate entries)."""
        rr.log(
            f"world/tf/{transform.child_frame_id}",
            rr.Transform3D(
                translation=[
                    transform.translation.x,
                    transform.translation.y,
                    transform.translation.z,
                ],
                rotation=rr.Quaternion(
                    xyzw=[
                        transform.rotation.x,
                        transform.rotation.y,
                        transform.rotation.z,
                        transform.rotation.w,
                    ]
                ),
            ),
        )

    def _check_safety_delta(
        self, x: float, y: float, z: float, roll: float, pitch: float, yaw: float
    ) -> bool:
        """Check if the new pose is within safety limits of the last commanded pose."""
        # Check position delta
        if self._last_commanded_pos is not None:
            dx = x - self._last_commanded_pos[0]
            dy = y - self._last_commanded_pos[1]
            dz = z - self._last_commanded_pos[2]
            pos_delta = (dx**2 + dy**2 + dz**2) ** 0.5

            if pos_delta > self.config.safety_max_delta:
                logger.warning(
                    f"Safety check failed: position delta {pos_delta:.3f}m exceeds limit {self.config.safety_max_delta:.3f}m"
                )
                return False

        # Check orientation delta
        if self._last_commanded_rot is not None:
            d_roll = abs(roll - self._last_commanded_rot[0])
            d_pitch = abs(pitch - self._last_commanded_rot[1])
            d_yaw = abs(yaw - self._last_commanded_rot[2])

            # Handle wrap-around for roll (can go from π to -π)
            if d_roll > 3.14159:
                d_roll = 2 * 3.14159 - d_roll

            for name, delta in [("roll", d_roll), ("pitch", d_pitch), ("yaw", d_yaw)]:
                if delta > self.config.safety_max_rot_delta:
                    logger.warning(
                        f"Safety check failed: {name} delta {delta:.3f}rad exceeds limit {self.config.safety_max_rot_delta:.3f}rad"
                    )
                    return False

        return True

    def _processing_loop(self) -> None:
        """Processing loop that runs at the configured rate."""
        period = 1.0 / self.config.rate
        logger.info(f"ArUco processing loop started at {self.config.rate}Hz")

        while not self._stop_event.is_set() and self._loop_count < self.config.max_loops:
            loop_start = time.time()
            try:
                if self._latest_image is None:
                    time.sleep(period)
                    continue

                self._process_image(self._latest_image)
                self._loop_count += 1
                logger.debug(f"Processed image {self._loop_count}/{self.config.max_loops}")

            except Exception as e:
                logger.error(f"Error in processing loop: {e}")

            # Sleep for the remainder of the period
            elapsed = time.time() - loop_start
            logger.debug(f"Processing loop took {elapsed:.3f}s")
            sleep_time = period - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)
        logger.info(f"ArUco processing loop completed after {self._loop_count} iterations")

    def _process_image(self, image: Image) -> None:
        """Process image to detect ArUco markers and average their poses."""
        if self._camera_matrix is None or self._dist_coeffs is None:
            return  # Skip if camera info not ready yet

        # Convert image for visualization (keep original format)
        if image.format.name == "RGB":
            display_image = image.data.copy()
            gray = cv2.cvtColor(image.data, cv2.COLOR_RGB2GRAY)
        elif image.format.name == "BGR":
            display_image = image.data.copy()
            gray = cv2.cvtColor(image.data, cv2.COLOR_BGR2GRAY)
        else:
            display_image = image.data.copy()
            gray = image.data

        corners, ids, _ = self._detector.detectMarkers(gray)
        # If no markers detected, publish bare frame and return
        if ids is None or len(ids) == 0:
            logger.debug("No ArUco markers detected")
            self._publish_annotated_image(display_image, image.format.name)
            return

        num_detected = len(ids)
        expected = self.config.expected_marker_count
        # Check if detected count is within ±1 of expected
        if abs(num_detected - expected) > 1:
            logger.error(
                f"Detected {num_detected} ArUco markers, expected {expected} (±1 tolerance)"
            )
            self._publish_annotated_image(display_image, image.format.name)
            return
        # Estimate pose for all detected markers
        rvecs, tvecs, _ = cv2.aruco.estimatePoseSingleMarkers(
            corners, self.config.marker_size, self._camera_matrix, self._dist_coeffs
        )

        # Collect all rotations and positions for averaging
        rotations = []
        positions = []
        for i in range(num_detected):
            rvec = rvecs[i][0]
            tvec = tvecs[i][0]
            rot_matrix, _ = cv2.Rodrigues(rvec)
            rotations.append(Rotation.from_matrix(rot_matrix))
            positions.append(tvec)

        # Average position (simple mean)
        avg_position = np.mean(positions, axis=0)

        # Average rotation using scipy's mean (proper quaternion averaging)
        avg_rotation = Rotation.concatenate(rotations).mean()
        avg_quat = avg_rotation.as_quat()  # [x, y, z, w]

        logger.debug(
            f"Averaged {num_detected} markers: pos=({avg_position[0]:.3f}, {avg_position[1]:.3f}, {avg_position[2]:.3f})"
        )

        # Create and publish transforms using averaged pose
        # Use "aruco_avg" as the frame ID for the averaged marker
        transform = self._set_transforms("avg", avg_position, avg_quat, image.ts)
        if transform is None:
            logger.error("Failed to create transform")
            self._publish_annotated_image(display_image, image.format.name)
            return

        aruco_wrt_robot_base = self.tf.get("base_link", "aruco_avg")
        if aruco_wrt_robot_base is not None:
            aruco_rpy = aruco_wrt_robot_base.rotation.to_euler()
            logger.debug(
                f"ArUco (avg) wrt base_link: x={aruco_wrt_robot_base.translation.x:.3f}, y={aruco_wrt_robot_base.translation.y:.3f}, z={aruco_wrt_robot_base.translation.z:.3f}, "
                f"roll={aruco_rpy.x:.3f}, pitch={aruco_rpy.y:.3f}, yaw={aruco_rpy.z:.3f}"
            )
        else:
            logger.error("Failed to lookup aruco_avg wrt base_link")

        if aruco_wrt_robot_base is not None:
            self._move_to_aruco(aruco_wrt_robot_base)

        # Draw markers on display image (show all detected markers)
        self._draw_markers(
            display_image,
            corners,
            ids,
            rvecs,
            tvecs,
            image.format.name,
        )

    def _move_to_aruco(self, aruco_wrt_robot_base: Transform) -> None:
        """Move the robot to the ArUco marker position with offset."""
        import math

        # Calculate reach pose: position offset
        reach_x = aruco_wrt_robot_base.translation.x - 0.05  # 5cm offset in x
        reach_y = aruco_wrt_robot_base.translation.y
        reach_z = aruco_wrt_robot_base.translation.z + 0.20  # 20cm offset in z

        # Always compute rotation values for logging
        aruco_rpy = aruco_wrt_robot_base.rotation.to_euler()
        aruco_roll = aruco_rpy.x
        aruco_pitch = aruco_rpy.y
        aruco_yaw = aruco_rpy.z

        # Map ArUco orientation to robot EE orientation
        # ArUco home: roll=0, pitch=0, yaw≈-π/2 -> Robot home: roll=π, pitch=0, yaw=0
        # Robot roll = π + ArUco roll (wrap to ±π)
        computed_roll = math.pi + aruco_roll
        if computed_roll > math.pi:
            computed_roll -= 2 * math.pi
        elif computed_roll < -math.pi:
            computed_roll += 2 * math.pi

        # Robot pitch = ArUco pitch (clamp to ±π/2)
        computed_pitch = max(-math.pi / 2, min(math.pi / 2, aruco_pitch))

        # Robot yaw = ArUco yaw + π/2 (offset from -π/2 home, clamp to ±π/2)
        computed_yaw = aruco_yaw + math.pi / 2
        computed_yaw = max(-math.pi / 2, min(math.pi / 2, computed_yaw))

        # Log computed rotation values
        logger.debug(
            f"Computed rotation: roll={computed_roll:.3f}, pitch={computed_pitch:.3f}, yaw={computed_yaw:.3f}"
        )

        # Use computed rotation or fixed default based on config
        if self.config.move_robot_to_aruco_rotation:
            reach_roll = computed_roll
            reach_pitch = computed_pitch
            reach_yaw = computed_yaw
        else:
            # Use fixed default orientation (robot home: roll=π, pitch=0, yaw=0)
            reach_roll = math.pi
            reach_pitch = 0.0
            reach_yaw = 0.0

        logger.debug(
            f"Reach pose: x={reach_x:.3f}, y={reach_y:.3f}, z={reach_z:.3f}, "
            f"roll={reach_roll:.3f}, pitch={reach_pitch:.3f}, yaw={reach_yaw:.3f}"
        )

        # Safety check: ensure delta is within limits
        if not self._check_safety_delta(
            reach_x, reach_y, reach_z, reach_roll, reach_pitch, reach_yaw
        ):
            logger.warning("Skipping move command due to safety check failure")
            return

        if self._move_to_cartesian_pose_rpc is None:
            logger.warning("move_to_cartesian_pose RPC not available")
            return

        if not self.config.move_robot_to_aruco:
            logger.info("move_robot_to_aruco is False, skipping move command")
            return

        try:
            success = self._move_to_cartesian_pose_rpc(
                hardware_id=self.config.hardware_id,
                x=reach_x,
                y=reach_y,
                z=reach_z,
                roll=reach_roll,
                pitch=reach_pitch,
                yaw=reach_yaw,
                velocity=0.2,
                wait=True,
            )
            if not success:
                logger.warning("Failed to move to pose, stopping processing loop")
                self._loop_count = self.config.max_loops
            else:
                self._last_commanded_pos = (reach_x, reach_y, reach_z)
                self._last_commanded_rot = (reach_roll, reach_pitch, reach_yaw)
                logger.debug("Successfully commanded move to pose")
        except Exception as e:
            logger.error(f"Error calling move_to_cartesian_pose: {e}")
            self._loop_count = self.config.max_loops

    def _set_transforms(
        self, marker_id: int | str, tvec: np.ndarray, quat: np.ndarray, timestamp: float
    ) -> Transform | None:
        # Create ArUco marker transform (camera_optical -> aruco_{marker_id})
        aruco_transform = Transform(
            translation=Vector3(float(tvec[0]), float(tvec[1]), float(tvec[2])),
            rotation=Quaternion(float(quat[0]), float(quat[1]), float(quat[2]), float(quat[3])),
            frame_id="camera_color_optical_frame",
            child_frame_id=f"aruco_{marker_id}",
            ts=timestamp,
        )

        # Publish ArUco marker transform to TF buffer (for graph lookups)
        self.tf.publish(aruco_transform)
        self._log_transform_to_rerun(aruco_transform)

        # Publish world -> base_link transform (static, but republish for TF polling)
        robot_base_to_world_transform = Transform(
            translation=Vector3(0.0, 0.0, 0.0),
            rotation=Quaternion(0.0, 0.0, 0.0, 1.0),
            frame_id="world",
            child_frame_id="base_link",
            ts=timestamp,
        )
        self.tf.publish(robot_base_to_world_transform)
        self._log_transform_to_rerun(robot_base_to_world_transform)

        if self.config.robot_connected and self._get_ee_positions_rpc is not None:
            # Get EE pose from ControlOrchestrator via RPC
            try:
                ee_positions = self._get_ee_positions_rpc()
                if ee_positions is not None:
                    hw_pose = ee_positions.get(self.config.hardware_id)
                    if hw_pose is not None:
                        x, y, z = hw_pose["x"], hw_pose["y"], hw_pose["z"]
                        roll, pitch, yaw = hw_pose["roll"], hw_pose["pitch"], hw_pose["yaw"]
                        orientation = euler_to_quaternion(Vector3(roll, pitch, yaw))
                        ee_transform = Transform(
                            translation=Vector3(float(x), float(y), float(z)),
                            rotation=orientation,
                            frame_id="base_link",
                            child_frame_id="ee_link",
                            ts=timestamp,
                        )
                        self.tf.publish(ee_transform)
                        self._log_transform_to_rerun(ee_transform)
                    else:
                        logger.warning(f"No EE pose for hardware_id '{self.config.hardware_id}'")
            except Exception as e:
                logger.error(f"Error getting EE pose from ControlOrchestrator: {e}")
        else:
            import math

            orientation = euler_to_quaternion(Vector3(math.pi, 0.0, 0.0))
            ee_transform = Transform(
                translation=Vector3(0.4, 0.0, 0.4),
                rotation=orientation,
                frame_id="base_link",
                child_frame_id="ee_link",
                ts=timestamp,
            )
            self.tf.publish(ee_transform)
            self._log_transform_to_rerun(ee_transform)

        return aruco_transform

    def _publish_annotated_image(self, display_image: np.ndarray, image_format: str) -> None:
        """Publish the annotated image to subscribers and Rerun."""
        from dimos.msgs.sensor_msgs.Image import ImageFormat

        if image_format == "BGR":
            publish_image = cv2.cvtColor(display_image, cv2.COLOR_BGR2RGB)
        else:
            publish_image = display_image

        annotated_msg = Image(
            data=publish_image,
            format=ImageFormat.RGB,
            frame_id=self.config.camera_frame_id,
            ts=time.time(),
        )
        self.annotated_image.publish(annotated_msg)
        rr.log("aruco/annotated", rr.Image(publish_image))

    def _draw_markers(
        self,
        display_image: np.ndarray,
        corners: list[np.ndarray],
        ids: np.ndarray,
        rvecs: np.ndarray,
        tvecs: np.ndarray,
        image_format: str,
    ) -> None:
        """Draw detected markers and axes on the image, then publish."""
        # Draw all detected markers
        cv2.aruco.drawDetectedMarkers(display_image, corners, ids)

        # Draw axes for each marker
        for i in range(len(ids)):
            rvec = rvecs[i][0]
            tvec = tvecs[i][0]

            axis_length = self.config.marker_size * 0.5
            cv2.drawFrameAxes(
                display_image,
                self._camera_matrix,
                self._dist_coeffs,
                rvec,
                tvec,
                axis_length,
            )

        self._publish_annotated_image(display_image, image_format)


aruco_tracker = ArucoTracker.blueprint

__all__ = ["ArucoTracker", "ArucoTrackerConfig", "aruco_tracker"]
