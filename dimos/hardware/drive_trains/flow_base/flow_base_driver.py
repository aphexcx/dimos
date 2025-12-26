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

"""Simple FlowBase driver module for DIMOS."""

import numpy as np
import portal
import threading
import time
from typing import Optional, Dict, Any

from dimos.core import Module, In, Out, rpc
from dimos.msgs.geometry_msgs import Twist, Vector3, Pose, Quaternion
from dimos.msgs.nav_msgs import Odometry
from dimos.utils.logging_config import setup_logger

logger = setup_logger(__name__)


class FlowBaseDriver(Module):
    """Simple FlowBase driver that interfaces with FlowBase controller via Portal RPC.

    Subscribes to Twist commands via LCM and forwards x, y, theta velocities to FlowBase.
    Publishes odometry data continuously.
    Provides RPC methods to get and reset odometry.
    """

    twist_cmd: In[Twist] = None  # Input port for velocity commands
    odom_out: Out[Odometry] = None  # Output port for odometry

    def __init__(
        self,
        host: str = "172.6.2.20",
        port: int = 11323,
        verbose: bool = False,
        odom_rate: float = 20.0,
    ):
        """Initialize FlowBase driver.

        Args:
            host: FlowBase controller IP address
            port: FlowBase controller port (default: 11323)
            verbose: Enable verbose logging
            odom_rate: Odometry publishing rate in Hz (default: 20.0)
        """
        super().__init__()
        self.host = host
        self.port = port
        self.verbose = verbose
        self.odom_rate = odom_rate

        # Portal client (initialized in start())
        self.client = None
        self.connected = False

        # Statistics
        self.command_count = 0
        self.error_count = 0

        # Odometry publishing thread
        self._odom_thread = None
        self._odom_stop_event = threading.Event()

        # Thread safety
        self._lock = threading.Lock()

    def _on_twist_received(self, msg: Twist):
        """Handle incoming Twist messages and forward to FlowBase.
            Note: FlowBase uses an inverted Y-axis compared to standard ROS convention.
            We negate the Y velocity to convert from ROS frame to FlowBase frame.

          ROS (right-hand):   FlowBase (inverted Y):
              +Y                  -Y
              ↑                   ↑
           ───┼──→ +X          ───┼──→ +X
              |                   |
              ↓                   ↓
             -Y                  +Y
        Args:
            msg: Twist message with linear and angular velocities
        """
        print(f"[CALLBACK] _on_twist_received called! msg={msg}")
        logger.info(f"[CALLBACK] _on_twist_received called! msg type={type(msg)}")

        if not self.connected or not self.client:
            logger.warning("Not connected to FlowBase, ignoring twist command")
            return

        try:
            # Extract velocities from Twist message
            vx = msg.linear.x
            vy = -msg.linear.y
            vtheta = -msg.angular.z

            # Create velocity command as numpy array
            target_velocity = np.array([vx, vy, vtheta])

            # Send to FlowBase via Portal RPC
            # Note: FlowBaseClient expects dict with 'target_velocity' and 'frame' keys
            command = {"target_velocity": target_velocity, "frame": "local"}

            # Call set_target_velocity RPC (non-blocking, FlowBase client handles the 50Hz loop)
            with self._lock:
                self.client.set_target_velocity(command).result()
                self.command_count += 1

            if self.verbose:
                logger.debug(f"Sent velocity command: x={vx:.3f}, y={vy:.3f}, theta={vtheta:.3f}")

        except Exception as e:
            logger.error(f"Error sending velocity command: {e}")
            self.error_count += 1

    def _odometry_publisher_loop(self):
        """Background thread that continuously publishes odometry."""
        logger.info(f"Odometry publisher thread started at {self.odom_rate} Hz")

        publish_period = 1.0 / self.odom_rate

        while not self._odom_stop_event.is_set():
            try:
                if not self.connected or not self.client:
                    time.sleep(publish_period)
                    continue

                # Get odometry from FlowBase controller
                odom_data = self.client.get_odometry({}).result()

                if odom_data is None:
                    time.sleep(publish_period)
                    continue

                # Get translation and rotation
                translation = odom_data["translation"]  # [x, y]
                rotation = odom_data["rotation"]  # theta in radians

                # Convert theta to quaternion (rotation around z-axis)
                half_theta = rotation / 2.0
                orientation = Quaternion(
                    0.0,  # x
                    0.0,  # y
                    np.sin(half_theta),  # z
                    np.cos(half_theta),  # w
                )

                position = Vector3(
                    float(translation[0]),  # x
                    float(translation[1]),  # y
                    0.0,  # z
                )

                pose = Pose(position=position, orientation=orientation)

                # Create Odometry message with timestamp
                current_time = time.time()
                odom_msg = Odometry(
                    ts=current_time,
                    frame_id="odom",
                    child_frame_id="base_link",
                    pose=pose,
                    twist=None,  # We don't have velocity info from get_odometry
                )

                # Publish odometry
                if self.odom_out:
                    self.odom_out.publish(odom_msg)

                    if self.verbose and (int(current_time * 10) % 10 == 0):  # Log every 1 second
                        logger.debug(
                            f"Published odom: x={translation[0]:.3f}, y={translation[1]:.3f}, theta={rotation:.3f}"
                        )

            except Exception as e:
                logger.error(f"Error in odometry publisher: {e}")

            time.sleep(publish_period)

        logger.info("Odometry publisher thread stopped")

    @rpc
    def connect(self) -> bool:
        """Connect to the FlowBase controller via Portal RPC.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            logger.info(f"Connecting to FlowBase at {self.host}:{self.port}")
            self.client = portal.Client(f"{self.host}:{self.port}")
            self.connected = True
            logger.info(f"Successfully connected to FlowBase at {self.host}:{self.port}")
            return True

        except Exception as e:
            logger.error(f"Failed to connect to FlowBase: {e}")
            self.connected = False
            return False

    @rpc
    def start(self) -> bool:
        """Start the driver.

        Returns:
            True if started successfully, False otherwise
        """
        # Connect to FlowBase
        if not self.connect():
            logger.error("Failed to connect to FlowBase during start()")
            return False

        # Subscribe to twist commands
        if self.twist_cmd:
            logger.info(f"twist_cmd port exists: {self.twist_cmd}")
            logger.info(f"twist_cmd transport: {self.twist_cmd.transport}")
            logger.info(f"twist_cmd transport type: {type(self.twist_cmd.transport)}")
            unsubscribe = self.twist_cmd.subscribe(self._on_twist_received)
            logger.info(f"Subscribed to twist commands, unsubscribe function: {unsubscribe}")
        else:
            logger.warning("No twist_cmd input port configured")

        # Start odometry publishing thread
        if self.odom_out:
            logger.info(f"odom_out port exists: {self.odom_out}")
            logger.info(f"odom_out transport: {self.odom_out.transport}")
            logger.info(f"odom_out transport type: {type(self.odom_out.transport)}")
            self._odom_stop_event.clear()
            self._odom_thread = threading.Thread(target=self._odometry_publisher_loop, daemon=True)
            self._odom_thread.start()
            logger.info(f"Odometry publishing started at {self.odom_rate} Hz")
        else:
            logger.info("No odom_out port configured, odometry will not be published")

        logger.info("FlowBase driver started successfully")
        return True

    @rpc
    def stop(self) -> bool:
        """Stop the driver and close connection.

        Returns:
            True if stopped successfully
        """
        logger.info("Stopping FlowBase driver")

        # Stop odometry publishing thread
        if self._odom_thread is not None:
            logger.info("Stopping odometry publisher thread...")
            self._odom_stop_event.set()
            self._odom_thread.join(timeout=2.0)
            if self._odom_thread.is_alive():
                logger.warning("Odometry thread did not stop gracefully")
            else:
                logger.info("Odometry publisher stopped")

        # Send zero velocity command before stopping
        if self.connected and self.client:
            try:
                zero_cmd = {"target_velocity": np.array([0.0, 0.0, 0.0]), "frame": "local"}
                with self._lock:
                    self.client.set_target_velocity(zero_cmd).result()
                logger.info("Sent zero velocity command")
            except Exception as e:
                logger.error(f"Error sending zero velocity: {e}")

        # Close portal client
        if self.client:
            try:
                self.client.close()
                logger.info("Portal client closed")
            except Exception as e:
                logger.error(f"Error closing portal client: {e}")

        self.connected = False
        logger.info("FlowBase driver stopped")
        return True

    @rpc
    def get_odometry(self) -> dict:
        """Get current odometry from FlowBase.

        Returns:
            Dictionary with 'translation' [x, y] and 'rotation' (theta) keys
            Returns None if not connected or error occurs
        """
        if not self.connected or not self.client:
            logger.warning("Not connected to FlowBase, cannot get odometry")
            return None

        try:
            with self._lock:
                # Call get_odometry RPC with empty dict as parameter
                odom = self.client.get_odometry({}).result()

            if self.verbose:
                logger.debug(
                    f"Odometry: translation={odom['translation']}, rotation={odom['rotation']:.3f}"
                )

            return odom

        except Exception as e:
            logger.error(f"Error getting odometry: {e}")
            return None

    @rpc
    def reset_odometry(self) -> bool:
        """Reset odometry to zero.

        Returns:
            True if reset successful, False otherwise
        """
        if not self.connected or not self.client:
            logger.warning("Not connected to FlowBase, cannot reset odometry")
            return False

        try:
            with self._lock:
                # Call reset_odometry RPC with empty dict as parameter
                self.client.reset_odometry({}).result()

            logger.info("Odometry reset to zero")
            return True

        except Exception as e:
            logger.error(f"Error resetting odometry: {e}")
            return False

    @rpc
    def get_status(self) -> dict:
        """Get driver status.

        Returns:
            Dictionary with connection status and statistics
        """
        return {
            "connected": self.connected,
            "host": self.host,
            "port": self.port,
            "command_count": self.command_count,
            "error_count": self.error_count,
        }
