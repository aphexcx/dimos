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

"""Simple test script for FlowBase driver."""

import argparse
import time
import subprocess
import sys
import os
import numpy as np

from dimos.core import start, LCMTransport
from dimos.utils.logging_config import setup_logger
from dimos.msgs.geometry_msgs import Twist, Vector3
from dimos.msgs.nav_msgs import Odometry
from dimos.hardware.drive_trains.flow_base.flow_base_driver import FlowBaseDriver

logger = setup_logger(__name__)


def test_odometry(driver):
    """Test odometry functions."""
    logger.info("\n=== Testing odometry ===")

    # Get odometry
    odom = driver.get_odometry()
    if odom:
        logger.info(
            f"Current odometry: translation={odom['translation']}, rotation={odom['rotation']:.3f} rad"
        )
    else:
        logger.error("Failed to get odometry")

    # Reset odometry
    logger.info("Resetting odometry")
    success = driver.reset_odometry()
    if success:
        logger.info("Odometry reset successful")
    else:
        logger.error("Failed to reset odometry")

    # Check odometry after reset
    time.sleep(0.5)
    odom = driver.get_odometry()
    if odom:
        logger.info(
            f"Odometry after reset: translation={odom['translation']}, rotation={odom['rotation']:.3f} rad"
        )

    logger.info("Odometry test completed")


def main():
    parser = argparse.ArgumentParser(description="Test FlowBase driver")
    parser.add_argument(
        "--host", type=str, default="172.6.2.20", help="FlowBase controller IP address"
    )
    parser.add_argument("--port", type=int, default=11323, help="FlowBase controller port")
    parser.add_argument(
        "--lcm-channel",
        type=str,
        default="/flowbase/cmd_vel",
        help="LCM channel for twist commands",
    )
    parser.add_argument(
        "--odom-channel", type=str, default="/flowbase/odom", help="LCM channel for odometry output"
    )
    parser.add_argument(
        "--odom-rate",
        type=float,
        default=5.0,
        help="Odometry publishing rate in Hz (default: 20.0)",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    parser.add_argument("--test-odometry", action="store_true", help="Run odometry tests")

    # Teleop arguments
    parser.add_argument(
        "--teleop", action="store_true", help="Launch teleop_twist_keyboard for manual control"
    )
    parser.add_argument(
        "--teleop-speed",
        type=float,
        default=0.1,
        help="Initial teleop linear velocity (default: 0.1 m/s)",
    )
    parser.add_argument(
        "--teleop-turn",
        type=float,
        default=0.2,
        help="Initial teleop angular velocity (default: 0.3 rad/s)",
    )

    args = parser.parse_args()

    logger.info("Starting DIMOS")
    dimos = start(1)

    logger.info(f"Deploying FlowBase driver (host={args.host}, port={args.port})")
    driver = dimos.deploy(
        FlowBaseDriver,
        host=args.host,
        port=args.port,
        verbose=args.verbose,
        odom_rate=args.odom_rate,
    )

    # Setup LCM transport for twist commands
    logger.info(f"Setting up LCM transport on channel: {args.lcm_channel}")
    driver.twist_cmd.transport = LCMTransport(args.lcm_channel, Twist)

    # Setup LCM transport for odometry output
    logger.info(f"Setting up LCM transport for odometry on channel: {args.odom_channel}")
    driver.odom_out.transport = LCMTransport(args.odom_channel, Odometry)

    # Subscribe to odometry to print it
    odom_message_count = [0]  # Use list to allow modification in nested function

    def on_odom_received(msg: Odometry):
        """Callback to print received odometry messages."""
        odom_message_count[0] += 1

        # Only print every 10th message to avoid spam (2Hz if publishing at 20Hz)
        if odom_message_count[0] % 10 == 0:
            x = msg.pose.pose.position.x
            y = msg.pose.pose.position.y

            # Convert quaternion to theta (rotation around z-axis)
            qz = msg.pose.pose.orientation.z
            qw = msg.pose.pose.orientation.w
            theta = 2.0 * np.arctan2(qz, qw)

            print(
                f"[Odom #{odom_message_count[0]}] x={x:7.3f}m, y={y:7.3f}m, theta={theta:6.3f}rad ({np.degrees(theta):7.2f}°)"
            )

    odom_transport = LCMTransport(args.odom_channel, Odometry)
    odom_transport.subscribe(on_odom_received)
    logger.info(f"Subscribed to odometry on channel: {args.odom_channel}")

    # Start driver
    logger.info("Starting driver")
    if not driver.start():
        logger.error("Failed to start driver")
        return

    # Get status
    status = driver.get_status()
    logger.info(f"Driver status: {status}")

    # Launch teleop if requested
    teleop_process = None
    if args.teleop:
        logger.info("=" * 60)
        logger.info("Launching teleop_twist_keyboard...")
        logger.info(f"  Topic: {args.lcm_channel}")
        logger.info(f"  Initial speed: {args.teleop_speed} m/s")
        logger.info(f"  Initial turn: {args.teleop_turn} rad/s")

        # Find the teleop script path
        teleop_script = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "utils", "teleop_twist_keyboard.py"
        )
        teleop_script = os.path.abspath(teleop_script)

        if not os.path.exists(teleop_script):
            logger.error(f"Teleop script not found at: {teleop_script}")
            logger.error("Cannot launch teleop")
        else:
            # Launch teleop as subprocess
            teleop_cmd = [
                sys.executable,  # Use same Python interpreter
                teleop_script,
                "--topic",
                args.lcm_channel,
                "--speed",
                str(args.teleop_speed),
                "--turn",
                str(args.teleop_turn),
            ]

            try:
                teleop_process = subprocess.Popen(
                    teleop_cmd,
                    stdout=sys.stdout,
                    stderr=sys.stderr,
                )
                logger.info(f"Teleop launched (PID: {teleop_process.pid})")
                logger.info("=" * 60)
            except Exception as e:
                logger.error(f"Failed to launch teleop: {e}")

    # Run tests if requested
    if args.test_odometry:
        test_odometry(driver)

    # If no tests requested, just keep running
    if not args.test_odometry:
        logger.info("\nDriver is running. Press Ctrl+C to stop.")
        if args.teleop:
            logger.info("Use the teleop keyboard controls to move the base!")
        else:
            logger.info(
                f"You can publish Twist messages to LCM channel '{args.lcm_channel}' to control the base"
            )
            logger.info("Or use another terminal to run commands like:")
            logger.info(f"  python flow_base_simple_control.py --vx 0.3")
            logger.info("Or launch with --teleop flag for keyboard control")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("\nStopping...")

    # Cleanup teleop process if running
    if teleop_process is not None:
        logger.info("Stopping teleop...")
        try:
            teleop_process.terminate()
            teleop_process.wait(timeout=2)
            logger.info("Teleop stopped")
        except subprocess.TimeoutExpired:
            logger.warning("Teleop didn't terminate gracefully, killing...")
            teleop_process.kill()
            teleop_process.wait()
        except Exception as e:
            logger.error(f"Error stopping teleop: {e}")

    # Stop driver
    logger.info("Stopping driver")
    driver.stop()

    # Final status
    status = driver.get_status()
    logger.info(f"Final status: {status}")
    logger.info("Test completed")


if __name__ == "__main__":
    main()
