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

"""Constants and default configurations for MuJoCo manipulation simulation."""

# =============================================================================
# Timing Constants
# =============================================================================

# Physics simulation rate (Hz)
# Higher = more accurate but slower
PHYSICS_RATE = 500

# Control loop rate (Hz) - matches hardware drivers
# Joint state feedback published at this rate
CONTROL_RATE = 100

# Robot state monitoring rate (Hz)
# Lower frequency for mode, errors, etc.
MONITOR_RATE = 10

# Default physics timestep (seconds)
# Should be 1/PHYSICS_RATE
DEFAULT_TIMESTEP = 0.002


# =============================================================================
# Control Parameters
# =============================================================================

# Default PD gains for position control
DEFAULT_KP = 100.0  # Position gain (Nm/rad)
DEFAULT_KD = 10.0  # Velocity/damping gain (Nm*s/rad)

# Velocity limits (rad/s) - approximately 180 deg/s
DEFAULT_MAX_VELOCITY = 3.14159

# Acceleration limits (rad/s^2)
DEFAULT_MAX_ACCELERATION = 10.0


# =============================================================================
# Rendering Constants
# =============================================================================

# Default camera image size
RENDER_WIDTH = 640
RENDER_HEIGHT = 480

# Default camera frame rate
RENDER_FPS = 30


# =============================================================================
# Robot Configurations
# =============================================================================

# Pre-configured robot settings
ROBOT_CONFIGS = {
    "xarm5": {
        "dof": 5,
        "kp": [100.0, 100.0, 80.0, 60.0, 40.0],
        "kd": [10.0, 10.0, 8.0, 6.0, 4.0],
        "has_gripper": True,
        "reach": 0.7,
        "payload_mass": 3.0,
    },
    "xarm6": {
        "dof": 6,
        "kp": [100.0, 100.0, 80.0, 60.0, 40.0, 30.0],
        "kd": [10.0, 10.0, 8.0, 6.0, 4.0, 3.0],
        "has_gripper": True,
        "reach": 0.7,
        "payload_mass": 5.0,
    },
    "xarm7": {
        "dof": 7,
        "kp": [100.0, 100.0, 80.0, 60.0, 40.0, 30.0, 20.0],
        "kd": [10.0, 10.0, 8.0, 6.0, 4.0, 3.0, 2.0],
        "has_gripper": True,
        "reach": 0.7,
        "payload_mass": 3.5,
    },
    "piper": {
        "dof": 6,
        "kp": [80.0, 80.0, 60.0, 40.0, 30.0, 20.0],
        "kd": [8.0, 8.0, 6.0, 4.0, 3.0, 2.0],
        "has_gripper": True,
        "reach": 0.5,
        "payload_mass": 1.5,
    },
    "generic_6dof": {
        "dof": 6,
        "kp": 100.0,
        "kd": 10.0,
        "has_gripper": False,
        "reach": 0.6,
        "payload_mass": 3.0,
    },
    "generic_7dof": {
        "dof": 7,
        "kp": 100.0,
        "kd": 10.0,
        "has_gripper": False,
        "reach": 0.8,
        "payload_mass": 5.0,
    },
}


def get_robot_config(robot_name: str) -> dict:
    """Get pre-configured robot settings.

    Args:
        robot_name: Name of robot (e.g., 'xarm7', 'piper')

    Returns:
        Configuration dict for that robot

    Raises:
        ValueError: If robot_name not found
    """
    if robot_name not in ROBOT_CONFIGS:
        available = ", ".join(ROBOT_CONFIGS.keys())
        raise ValueError(f"Unknown robot '{robot_name}'. Available: {available}")
    return ROBOT_CONFIGS[robot_name].copy()
