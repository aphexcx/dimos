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

"""Test manipulation processor with LCM topic subscription."""

import os
import sys
import cv2
import numpy as np
import time
import argparse
import threading
import matplotlib

# Try to use TkAgg backend for live display, fallback to Agg if not available
try:
    matplotlib.use("TkAgg")
except:
    try:
        matplotlib.use("Qt5Agg")
    except:
        matplotlib.use("Agg")  # Fallback to non-interactive
import matplotlib.pyplot as plt
import open3d as o3d
from typing import Dict, List, Optional

# LCM imports
import lcm
from lcm_msgs.sensor_msgs import Image as LCMImage
from lcm_msgs.sensor_msgs import CameraInfo as LCMCameraInfo

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dimos.perception.pointcloud.utils import visualize_clustered_point_clouds, visualize_voxel_grid
from dimos.perception.manip_aio_processer import ManipulationProcessor
from dimos.perception.grasp_generation.utils import visualize_grasps_3d
from dimos.perception.pointcloud.utils import visualize_pcd
from dimos.utils.logging_config import setup_logger

logger = setup_logger("test_pipeline_lcm")


class LCMDataCollector:
    """Collects one message from each required LCM topic."""
    
    def __init__(self, lcm_url: str = "udpm://239.255.76.67:7667?ttl=1"):
        self.lcm = lcm.LCM(lcm_url)
        
        # Data storage
        self.rgb_data: Optional[np.ndarray] = None
        self.depth_data: Optional[np.ndarray] = None
        self.camera_intrinsics: Optional[List[float]] = None
        
        # Synchronization
        self.data_lock = threading.Lock()
        self.data_ready_event = threading.Event()
        
        # Flags to track received messages
        self.rgb_received = False
        self.depth_received = False
        self.camera_info_received = False
        
        # Subscribe to topics
        self.lcm.subscribe("head_cam_rgb#sensor_msgs.Image", self._handle_rgb_message)
        self.lcm.subscribe("head_cam_depth#sensor_msgs.Image", self._handle_depth_message)
        self.lcm.subscribe("head_cam_info#sensor_msgs.CameraInfo", self._handle_camera_info_message)
        
        logger.info("LCM Data Collector initialized")
        logger.info("Subscribed to topics:")
        logger.info("  - head_cam_rgb#sensor_msgs.Image")
        logger.info("  - head_cam_depth#sensor_msgs.Image")
        logger.info("  - head_cam_info#sensor_msgs.CameraInfo")
    
    def _handle_rgb_message(self, channel: str, data: bytes):
        """Handle RGB image message."""
        if self.rgb_received:
            return  # Already got one, ignore subsequent messages
            
        try:
            msg = LCMImage.decode(data)
            
            # Convert message data to numpy array
            if msg.encoding == "rgb8":
                # RGB8 format: 3 bytes per pixel
                rgb_array = np.frombuffer(msg.data[:msg.data_length], dtype=np.uint8)
                rgb_image = rgb_array.reshape((msg.height, msg.width, 3))
                
                with self.data_lock:
                    self.rgb_data = rgb_image
                    self.rgb_received = True
                    logger.info(f"RGB message received: {msg.width}x{msg.height}, encoding: {msg.encoding}")
                    self._check_all_data_received()
                    
            else:
                logger.warning(f"Unsupported RGB encoding: {msg.encoding}")
                
        except Exception as e:
            logger.error(f"Error processing RGB message: {e}")
    
    def _handle_depth_message(self, channel: str, data: bytes):
        """Handle depth image message."""
        if self.depth_received:
            return  # Already got one, ignore subsequent messages
            
        try:
            msg = LCMImage.decode(data)
            
            # Convert message data to numpy array
            if msg.encoding == "32FC1":
                # 32FC1 format: 4 bytes (float32) per pixel
                depth_array = np.frombuffer(msg.data[:msg.data_length], dtype=np.float32)
                depth_image = depth_array.reshape((msg.height, msg.width))
                
                with self.data_lock:
                    self.depth_data = depth_image
                    self.depth_received = True
                    logger.info(f"Depth message received: {msg.width}x{msg.height}, encoding: {msg.encoding}")
                    logger.info(f"Depth range: {depth_image.min():.3f} - {depth_image.max():.3f} meters")
                    self._check_all_data_received()
                    
            else:
                logger.warning(f"Unsupported depth encoding: {msg.encoding}")
                
        except Exception as e:
            logger.error(f"Error processing depth message: {e}")
    
    def _handle_camera_info_message(self, channel: str, data: bytes):
        """Handle camera info message."""
        if self.camera_info_received:
            return  # Already got one, ignore subsequent messages
            
        try:
            msg = LCMCameraInfo.decode(data)
            
            # Extract intrinsics from K matrix: [fx, 0, cx, 0, fy, cy, 0, 0, 1]
            K = msg.K
            fx = K[0]  # K[0,0]
            fy = K[4]  # K[1,1] 
            cx = K[2]  # K[0,2]
            cy = K[5]  # K[1,2]
            
            intrinsics = [fx, fy, cx, cy]
            
            with self.data_lock:
                self.camera_intrinsics = intrinsics
                self.camera_info_received = True
                logger.info(f"Camera info received: {msg.width}x{msg.height}")
                logger.info(f"Intrinsics: fx={fx:.1f}, fy={fy:.1f}, cx={cx:.1f}, cy={cy:.1f}")
                self._check_all_data_received()
                
        except Exception as e:
            logger.error(f"Error processing camera info message: {e}")
    
    def _check_all_data_received(self):
        """Check if all required data has been received."""
        if self.rgb_received and self.depth_received and self.camera_info_received:
            logger.info("✅ All required data received!")
            self.data_ready_event.set()
    
    def wait_for_data(self, timeout: float = 30.0) -> bool:
        """Wait for all data to be received."""
        logger.info("Waiting for RGB, depth, and camera info messages...")
        
        # Start LCM handling in a separate thread
        lcm_thread = threading.Thread(target=self._lcm_handle_loop, daemon=True)
        lcm_thread.start()
        
        # Wait for data with timeout
        return self.data_ready_event.wait(timeout)
    
    def _lcm_handle_loop(self):
        """LCM message handling loop."""
        try:
            while not self.data_ready_event.is_set():
                self.lcm.handle_timeout(100)  # 100ms timeout
        except Exception as e:
            logger.error(f"Error in LCM handling loop: {e}")
    
    def get_data(self):
        """Get the collected data."""
        with self.data_lock:
            return self.rgb_data, self.depth_data, self.camera_intrinsics


def create_point_cloud(color_img, depth_img, intrinsics):
    """Create Open3D point cloud."""
    fx, fy, cx, cy = intrinsics
    height, width = depth_img.shape

    o3d_intrinsics = o3d.camera.PinholeCameraIntrinsic(width, height, fx, fy, cx, cy)
    color_o3d = o3d.geometry.Image(color_img)
    depth_o3d = o3d.geometry.Image((depth_img * 1000).astype(np.uint16))

    rgbd = o3d.geometry.RGBDImage.create_from_color_and_depth(
        color_o3d, depth_o3d, depth_scale=1000.0, convert_rgb_to_intensity=False
    )

    return o3d.geometry.PointCloud.create_from_rgbd_image(rgbd, o3d_intrinsics)


def run_processor(color_img, depth_img, intrinsics):
    """Run processor and collect results."""
    # Create processor
    processor = ManipulationProcessor(
        camera_intrinsics=intrinsics,
        grasp_server_url="ws://10.0.0.125:8000/ws/grasp",
        enable_grasp_generation=False,
        enable_segmentation=True,
        segmentation_model="FastSAM-x.pt",
    )

    # Process single frame directly
    results = processor.process_frame(color_img, depth_img)

    # Debug: print available results
    print(f"Available results: {list(results.keys())}")

    processor.cleanup()

    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lcm-url", default="udpm://239.255.76.67:7667?ttl=1", 
                       help="LCM URL for subscription")
    parser.add_argument("--timeout", type=float, default=30.0, 
                       help="Timeout in seconds to wait for messages")
    parser.add_argument("--save-images", action="store_true", 
                       help="Save received RGB and depth images to files")
    args = parser.parse_args()

    # Create data collector
    collector = LCMDataCollector(args.lcm_url)
    
    # Wait for data
    if not collector.wait_for_data(args.timeout):
        logger.error(f"Timeout waiting for data after {args.timeout} seconds")
        logger.error("Make sure Unity is running and publishing to the LCM topics")
        return
    
    # Get the collected data
    color_img, depth_img, intrinsics = collector.get_data()
    
    logger.info(f"Loaded images: color {color_img.shape}, depth {depth_img.shape}")
    logger.info(f"Intrinsics: {intrinsics}")
    
    # Save images if requested
    if args.save_images:
        try:
            cv2.imwrite("received_rgb.png", cv2.cvtColor(color_img, cv2.COLOR_RGB2BGR))
            # Save depth as 16-bit for visualization
            depth_viz = (np.clip(depth_img * 1000, 0, 65535)).astype(np.uint16)
            cv2.imwrite("received_depth.png", depth_viz)
            logger.info("Saved received_rgb.png and received_depth.png")
        except Exception as e:
            logger.warning(f"Failed to save images: {e}")

    # Run processor
    results = run_processor(color_img, depth_img, intrinsics)

    # Debug: Print what we received
    print(f"\n✅ Processor Results:")
    print(f"   Available results: {list(results.keys())}")
    print(f"   Processing time: {results.get('processing_time', 0):.3f}s")

    # Show timing breakdown if available
    if "timing_breakdown" in results:
        breakdown = results["timing_breakdown"]
        print(f"   Timing breakdown:")
        print(f"     - Detection: {breakdown.get('detection', 0):.3f}s")
        print(f"     - Segmentation: {breakdown.get('segmentation', 0):.3f}s")
        print(f"     - Point cloud: {breakdown.get('pointcloud', 0):.3f}s")
        print(f"     - Misc extraction: {breakdown.get('misc_extraction', 0):.3f}s")

    # Print object information
    detected_count = len(results.get("detected_objects", []))
    all_count = len(results.get("all_objects", []))

    print(f"   Detection objects: {detected_count}")
    print(f"   All objects processed: {all_count}")

    # Print misc clusters information
    if "misc_clusters" in results and results["misc_clusters"]:
        cluster_count = len(results["misc_clusters"])
        total_misc_points = sum(
            len(np.asarray(cluster.points)) for cluster in results["misc_clusters"]
        )
        print(f"   Misc clusters: {cluster_count} clusters with {total_misc_points} total points")
    else:
        print(f"   Misc clusters: None")

    # Print grasp summary
    if "grasps" in results and results["grasps"]:
        total_grasps = 0
        best_score = 0
        for grasp in results["grasps"]:
            score = grasp.get("score", 0)
            if score > best_score:
                best_score = score
            total_grasps += 1
        print(f"   Grasps generated: {total_grasps} (best score: {best_score:.3f})")
    else:
        print("   Grasps: None generated")

    # Determine number of subplots based on what results we have
    num_plots = 0
    plot_configs = []

    if "detection_viz" in results and results["detection_viz"] is not None:
        plot_configs.append(("detection_viz", "Object Detection"))
        num_plots += 1

    if "segmentation_viz" in results and results["segmentation_viz"] is not None:
        plot_configs.append(("segmentation_viz", "Semantic Segmentation"))
        num_plots += 1

    if "pointcloud_viz" in results and results["pointcloud_viz"] is not None:
        plot_configs.append(("pointcloud_viz", "All Objects Point Cloud"))
        num_plots += 1

    if "detected_pointcloud_viz" in results and results["detected_pointcloud_viz"] is not None:
        plot_configs.append(("detected_pointcloud_viz", "Detection Objects Point Cloud"))
        num_plots += 1

    if "misc_pointcloud_viz" in results and results["misc_pointcloud_viz"] is not None:
        plot_configs.append(("misc_pointcloud_viz", "Misc/Background Points"))
        num_plots += 1

    if "grasp_overlay" in results and results["grasp_overlay"] is not None:
        plot_configs.append(("grasp_overlay", "Grasp Overlay"))
        num_plots += 1

    if num_plots == 0:
        print("No visualization results to display")
        return

    # Create subplot layout
    if num_plots <= 3:
        fig, axes = plt.subplots(1, num_plots, figsize=(6 * num_plots, 5))
    else:
        rows = 2
        cols = (num_plots + 1) // 2
        fig, axes = plt.subplots(rows, cols, figsize=(6 * cols, 5 * rows))

    # Ensure axes is always a list for consistent indexing
    if num_plots == 1:
        axes = [axes]
    elif num_plots > 2:
        axes = axes.flatten()

    # Plot each result
    for i, (key, title) in enumerate(plot_configs):
        axes[i].imshow(results[key])
        axes[i].set_title(title)
        axes[i].axis("off")

    # Hide unused subplots if any
    if num_plots > 3:
        for i in range(num_plots, len(axes)):
            axes[i].axis("off")

    plt.tight_layout()

    # Save and show the plot
    output_path = "manipulation_results_lcm.png"
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    print(f"Results visualization saved to: {output_path}")

    # Show plot live as well
    plt.show(block=True)
    plt.close()

    # 3D visualization with grasps (if enabled)
    if "grasps" in results and results["grasps"]:
        pcd = create_point_cloud(color_img, depth_img, intrinsics)
        all_grasps = results["grasps"]

        if all_grasps:
            logger.info(f"Visualizing {len(all_grasps)} grasps in 3D")
            visualize_grasps_3d(pcd, all_grasps)
    else:
        logger.info("Grasp generation disabled - skipping 3D grasp visualization")

    # Visualize full point cloud if available
    if "full_pointcloud" in results and results["full_pointcloud"] is not None:
        full_pcd = results["full_pointcloud"]
        print(f"Visualizing full point cloud with {len(np.asarray(full_pcd.points))} points")

        try:
            visualize_pcd(
                full_pcd,
                window_name="Full Scene Point Cloud",
                point_size=2.0,
                show_coordinate_frame=True,
            )
        except (KeyboardInterrupt, EOFError):
            print("\nSkipping full point cloud visualization")
    else:
        print("No full point cloud available for visualization")

    # Visualize misc/background clusters if available
    if "misc_clusters" in results and results["misc_clusters"]:
        misc_clusters = results["misc_clusters"]
        cluster_count = len(misc_clusters)
        total_misc_points = sum(len(np.asarray(cluster.points)) for cluster in misc_clusters)
        print(
            f"Visualizing {cluster_count} misc/background clusters with {total_misc_points} total points"
        )

        try:
            visualize_clustered_point_clouds(
                misc_clusters,
                window_name="Misc/Background Clusters (DBSCAN)",
                point_size=3.0,
                show_coordinate_frame=True,
            )
        except (KeyboardInterrupt, EOFError):
            print("\nSkipping misc clusters visualization")
    else:
        print("No misc clusters available for visualization")

    # Visualize voxel grid separately
    if "misc_voxel_grid" in results and results["misc_voxel_grid"] is not None:
        misc_voxel_grid = results["misc_voxel_grid"]
        misc_clusters = results.get("misc_clusters", [])

        voxel_count = len(misc_voxel_grid.get_voxels())
        print(f"Visualizing voxel grid with {voxel_count} voxels")

        try:
            visualize_voxel_grid(
                misc_voxel_grid,
                window_name="Misc/Background Voxel Grid",
                show_coordinate_frame=True,
            )
        except (KeyboardInterrupt, EOFError):
            print("\nSkipping voxel grid visualization")
        except Exception as e:
            print(f"Error in voxel grid visualization: {e}")
    else:
        print("No voxel grid available for visualization")


if __name__ == "__main__":
    main()