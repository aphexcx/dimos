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

"""Grasp Visualization with Open3D (Debug Tool).

Visualizes generated grasp poses on object point clouds using Open3D.

Usage:
    python -m dimos.grasping.visualize_grasps [-f FILE] [-m MAX_GRASPS]

Examples:
    python -m dimos.grasping.visualize_grasps
    python -m dimos.grasping.visualize_grasps -f /path/to/grasps.json
    python -m dimos.grasping.visualize_grasps -m 10
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

try:
    import open3d as o3d
except ImportError:
    o3d = None

# Gripper dimensions: (width, finger_length, palm_depth)
GRIPPER_DIMENSIONS: dict[str, tuple[float, float, float]] = {
    "ufactory_xarm": (0.086, 0.052, 0.04),
    "robotiq_2f_140": (0.140, 0.06, 0.05),
}


def create_gripper_geometry(
    transform: np.ndarray,
    gripper_width: float = 0.086,
    finger_length: float = 0.052,
    palm_depth: float = 0.04,
    color: list[float] | None = None,
    gripper_type: str = "ufactory_xarm",
    style: str = "arrows",
) -> list:
    """Create Open3D geometry for a grasp pose (lines only)."""
    if o3d is None:
        return []

    if color is None:
        color = [0.0, 1.0, 0.0]

    dims = GRIPPER_DIMENSIONS.get(gripper_type, GRIPPER_DIMENSIONS["ufactory_xarm"])
    gripper_width, finger_length, palm_depth = dims

    w = gripper_width / 2.0
    fl = finger_length
    pd = palm_depth

    wrist = np.array([0.0, 0.0, -(pd + fl)])
    palm = np.array([0.0, 0.0, -fl])
    l_base = np.array([-w, 0.0, -fl])
    r_base = np.array([w, 0.0, -fl])
    l_tip = np.array([-w, 0.0, 0.0])
    r_tip = np.array([w, 0.0, 0.0])

    extend = 0.25 * fl
    l_tip2 = np.array([-w, 0.0, extend])
    r_tip2 = np.array([w, 0.0, extend])

    if style == "arrows":
        points = np.vstack([wrist, palm, l_base, r_base, l_tip2, r_tip2])
        lines = [
            [0, 1],
            [1, 2],
            [1, 3],
            [2, 4],
            [3, 5],
        ]
    else:
        points = np.vstack([wrist, palm, l_base, r_base, l_tip, r_tip])
        lines = [
            [0, 1],
            [1, 2],
            [1, 3],
            [2, 4],
            [3, 5],
            [2, 3],
        ]

    points_h = np.hstack([points, np.ones((len(points), 1))])
    points_world = (transform @ points_h.T).T[:, :3]

    line_set = o3d.geometry.LineSet()
    line_set.points = o3d.utility.Vector3dVector(points_world)
    line_set.lines = o3d.utility.Vector2iVector(lines)
    line_set.colors = o3d.utility.Vector3dVector([color] * len(lines))

    wrist_dot = o3d.geometry.PointCloud()
    wrist_dot.points = o3d.utility.Vector3dVector(points_world[[0]])
    wrist_dot.colors = o3d.utility.Vector3dVector(np.array([color], dtype=np.float64))

    return [line_set, wrist_dot]


def visualize_grasps(
    point_cloud: np.ndarray,
    grasps: list,
    scores: list | None = None,
    max_grasps: int = 100,
    window_name: str = "GraspGen Visualization",
    gripper_type: str = "ufactory_xarm",
    style: str = "arrows",
) -> None:
    """Visualize grasps using Open3D.

    Args:
        point_cloud: Nx3 point cloud array
        grasps: List of 4x4 grasp transformation matrices
        scores: Optional list of grasp quality scores
        max_grasps: Maximum number of grasps to display (default 100)
        window_name: Window title
        gripper_type: Gripper type for visualization dimensions
        style: Visualization style - "arrows" (clean) or "gripper" (detailed)
    """
    if o3d is None:
        print("Error: Open3D is required for visualization")
        print("Install with: pip install open3d")
        return

    if scores is None:
        scores = [1.0] * len(grasps)

    geometries = []

    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(point_cloud)
    pcd.paint_uniform_color([0.0, 0.8, 0.8])
    geometries.append(pcd)

    coord_frame = o3d.geometry.TriangleMesh.create_coordinate_frame(size=0.1)
    geometries.append(coord_frame)

    num_to_show = min(len(grasps), max_grasps)
    for i in range(num_to_show):
        # Color gradient: green (best) -> yellow -> red (worst)
        t = i / max(num_to_show - 1, 1) if i > 0 else 0.0
        color = [min(1.0, 2 * t), max(0.0, 1.0 - t), 0.0]

        gripper_geoms = create_gripper_geometry(
            grasps[i], color=color, gripper_type=gripper_type, style=style
        )
        geometries.extend(gripper_geoms)

    print(f"\nVisualizing {num_to_show} grasps on {len(point_cloud)} points")
    print(f"Gripper type: {gripper_type}, Style: {style}")
    print("\nVisualization Convention:")
    print("  - Lines point FROM wrist TOWARD grasp point (on object)")
    print("  - Dot = Wrist position (where arm connects)")
    print("  - V-shape at tip = Finger opening direction")
    print("  - Color: Green=best, Yellow=medium, Red=worst")
    print("\nControls:")
    print("  Left mouse:   Rotate")
    print("  Middle mouse: Pan")
    print("  Scroll:       Zoom")
    print("  Q:            Quit")

    o3d.visualization.draw_geometries(
        geometries,
        window_name=window_name,
        width=1280,
        height=720,
    )


def save_grasps_for_visualization(
    point_cloud: np.ndarray,
    grasps: list,
    scores: list | None = None,
    filepath: str = "/tmp/grasp_visualization.json",
) -> str:
    """Save grasp data to JSON file for later visualization.

    Args:
        point_cloud: Nx3 point cloud array
        grasps: List of 4x4 grasp transformation matrices
        scores: Optional list of grasp quality scores
        filepath: Output file path

    Returns:
        Path to saved file
    """
    if scores is None:
        scores = [1.0] * len(grasps)

    data = {
        "point_cloud": point_cloud.tolist(),
        "grasps": [np.asarray(g).tolist() for g in grasps],
        "scores": scores if isinstance(scores, list) else list(scores),
        "timestamp": time.time(),
        "num_grasps": len(grasps),
    }

    Path(filepath).parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w") as f:
        json.dump(data, f)

    print(f"Saved visualization data to: {filepath}")
    return filepath


def load_and_visualize(
    filepath: str,
    max_grasps: int = 100,
    gripper_type: str = "ufactory_xarm",
    style: str = "arrows",
) -> None:
    """Load grasp data from JSON and visualize.

    Args:
        filepath: Path to JSON file with grasp data
        max_grasps: Maximum number of grasps to display
        gripper_type: Gripper type for visualization dimensions
        style: Visualization style - "arrows" or "gripper"
    """
    with open(filepath) as f:
        data = json.load(f)

    point_cloud = np.array(data["point_cloud"])
    grasps = [np.array(g).reshape(4, 4) for g in data["grasps"]]
    scores = data.get("scores", [1.0] * len(grasps))

    print(f"Loaded {len(grasps)} grasps from {filepath}")
    visualize_grasps(
        point_cloud,
        grasps,
        scores,
        max_grasps=max_grasps,
        gripper_type=gripper_type,
        style=style,
    )


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Visualize grasp poses with Open3D",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m dimos.grasping.visualize_grasps
  python -m dimos.grasping.visualize_grasps -f /path/to/grasps.json
  python -m dimos.grasping.visualize_grasps -m 100 -s arrows
  python -m dimos.grasping.visualize_grasps -g ufactory_xarm -s gripper

Visualization Styles:
  arrows  - Clean lines pointing toward grasp point (like GraspGen reference)
  gripper - Detailed gripper geometry with fingers

Coordinate Convention:
  - GraspGen outputs grasp poses where the TCP (origin) is at the grasp point
  - The dot shows the WRIST position (where arm connects)
  - Lines/fingers extend toward the object
  - Color: Green=best grasp, Yellow=medium, Red=worst
        """,
    )
    parser.add_argument(
        "-f",
        "--file",
        type=str,
        default="/tmp/grasp_visualization.json",
        help="Path to grasp data JSON file (default: /tmp/grasp_visualization.json)",
    )
    parser.add_argument(
        "-m",
        "--max-grasps",
        type=int,
        default=100,
        help="Maximum number of grasps to visualize (default: 100)",
    )
    parser.add_argument(
        "-g",
        "--gripper",
        type=str,
        default="ufactory_xarm",
        choices=["ufactory_xarm", "robotiq_2f_140"],
        help="Gripper type for visualization dimensions (default: ufactory_xarm)",
    )
    parser.add_argument(
        "-s",
        "--style",
        type=str,
        default="arrows",
        choices=["arrows", "gripper"],
        help="Visualization style: 'arrows' (clean) or 'gripper' (detailed). Default: arrows",
    )

    args = parser.parse_args()

    if o3d is None:
        print("Error: Open3D is required for visualization")
        print("Install with: pip install open3d")
        return 1

    filepath = Path(args.file)
    if not filepath.exists():
        print(f"Error: File not found: {filepath}")
        print("\nTo generate visualization data, run grasp generation first.")
        print("Enable visualization with: graspgen(save_visualization_data=True)")
        return 1

    load_and_visualize(
        str(filepath),
        max_grasps=args.max_grasps,
        gripper_type=args.gripper,
        style=args.style,
    )
    return 0


if __name__ == "__main__":
    exit(main())
