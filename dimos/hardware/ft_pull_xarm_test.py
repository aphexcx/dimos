#!/usr/bin/env python3
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
Force-Torque Pull Module Test with xArm Driver Integration

This script integrates the FT sensor door opening system with the new xArm driver.
Instead of directly calling the xArm SDK, it sends joint position commands via LCM
to the xArm driver module.
"""

import time
import argparse
from pathlib import Path

from dimos.core import start, LCMTransport
from dimos.utils.logging_config import setup_logger
from dimos.msgs.geometry_msgs import Vector3
from dimos.msgs.sensor_msgs import JointCommand, JointState
from dimos.hardware.ft_driver_module import FTDriverModule
from dimos.hardware.ft_pull_xarm_skill import FTPullXArmModule
from dimos.hardware.ft_visualizer_module import FTVisualizerModule
from dimos.hardware.manipulators.xarm.xarm_driver import XArmDriver, XArmDriverConfig
from dimos.agents2.agent import Agent
from dimos.agents2.cli.human import HumanInput

logger = setup_logger(__name__)


def main():
    """Main deployment function for FT pull system with xArm driver."""
    parser = argparse.ArgumentParser(
        description="Deploy Force-Torque sensor driver, xArm driver, and pull skill modules",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run with default settings (requires xArm at $XARM_IP or 192.168.1.235)
  python ft_pull_xarm_test.py

  # Run with custom xArm IP
  python ft_pull_xarm_test.py --xarm 192.168.1.210

  # Run with custom calibration file
  python ft_pull_xarm_test.py --calibration ft_calibration.json --xarm 192.168.1.210

  # Run with custom parameters and auto-execute
  python ft_pull_xarm_test.py --xarm 192.168.1.210 --auto-run --force-threshold 5.0

  # Run in interactive mode with agent
  python ft_pull_xarm_test.py --xarm 192.168.1.210 --interactive
        """,
    )

    # FT Driver arguments
    parser.add_argument(
        "--port",
        default="/dev/ttyACM0",
        help="Serial port for sensor (default: /dev/ttyACM0)",
    )
    parser.add_argument(
        "--baud", type=int, default=115200, help="Serial baud rate (default: 115200)"
    )
    parser.add_argument(
        "--window", type=int, default=3, help="Moving average window size (default: 3)"
    )
    parser.add_argument(
        "--calibration",
        type=str,
        default="dimos/hardware/ft_calibration.json",
        help="Path to calibration file (default: dimos/hardware/ft_calibration.json)",
    )

    # xARM connection
    parser.add_argument(
        "--xarm",
        type=str,
        default="192.168.1.235",
        help="xARM IP address (default: 192.168.1.235)",
    )
    parser.add_argument(
        "--servo-speed",
        type=float,
        default=0.3,
        help="Servo joint speed in rad/s (0.1=very slow, 1.0=fast, default: 0.3)",
    )
    parser.add_argument(
        "--control-rate",
        type=float,
        default=5.0,
        help="Control loop rate in Hz (1=very smooth, 10=responsive, default: 5.0)",
    )

    # Pull skill parameters (for auto-run mode)
    parser.add_argument(
        "--force-threshold",
        type=float,
        default=7.0,
        help="Target force threshold in Newtons (default: 7.0)",
    )
    parser.add_argument(
        "--rotation-gain", type=float, default=0.01, help="Rotation gain (rad/N) (default: 0.01)"
    )
    parser.add_argument(
        "--pull-speed",
        type=float,
        default=0.015,
        help="Pull speed in meters per step (default: 0.015)",
    )
    parser.add_argument(
        "--pivot-distance",
        type=float,
        default=0.2,
        help="Distance to virtual pivot point in meters (default: 0.2)",
    )
    parser.add_argument(
        "--door-opens-clockwise",
        action="store_true",
        help="Door opens clockwise (default: counter-clockwise)",
    )
    parser.add_argument(
        "--rotation-axis",
        type=str,
        default="z",
        choices=["x", "y", "z"],
        help="Rotation axis (default: z)",
    )
    parser.add_argument(
        "--max-duration",
        type=float,
        default=45.0,
        help="Maximum duration in seconds (default: 45.0)",
    )
    parser.add_argument(
        "--end-angle", type=float, default=None, help="Maximum rotation angle in degrees (optional)"
    )

    # LCM transport arguments
    parser.add_argument(
        "--lcm-force-channel",
        default="/ft/force",
        help="LCM channel for force Vector3 data (default: /ft/force)",
    )
    parser.add_argument(
        "--lcm-torque-channel",
        default="/ft/torque",
        help="LCM channel for torque Vector3 data (default: /ft/torque)",
    )
    parser.add_argument(
        "--lcm-joint-cmd-channel",
        default="/xarm/joint_position_command",
        help="LCM channel for joint commands (default: /xarm/joint_position_command)",
    )
    parser.add_argument(
        "--lcm-joint-state-channel",
        default="/xarm/joint_state",
        help="LCM channel for joint state (default: /xarm/joint_state)",
    )

    # Visualizer arguments
    parser.add_argument(
        "--dash-port", type=int, default=8052, help="Port for Dash web server (default: 8052)"
    )
    parser.add_argument(
        "--dash-host", default="0.0.0.0", help="Host for Dash web server (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--history", type=int, default=500, help="Max history points to keep (default: 500)"
    )
    parser.add_argument(
        "--update-interval",
        type=int,
        default=100,
        help="Dashboard update interval in ms (default: 100)",
    )
    parser.add_argument(
        "--no-visualizer", action="store_true", help="Run without visualizer dashboard"
    )

    # Execution mode
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Run in interactive mode with agent and human input",
    )
    parser.add_argument(
        "--auto-run", action="store_true", help="Automatically start the continuous pull on startup"
    )

    # System arguments
    parser.add_argument(
        "--processes", type=int, default=4, help="Number of Dimos processes (default: 4)"
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")

    args = parser.parse_args()

    # Check if calibration file exists
    if args.calibration:
        cal_path = Path(args.calibration)
        if not cal_path.exists():
            logger.warning(f"Calibration file {cal_path} not found")
            logger.warning("Will run without calibration (raw sensor values only)")
            args.calibration = None

    # Start Dimos
    logger.info("=" * 60)
    logger.info("Force-Torque Pull System with xArm Driver")
    logger.info("=" * 60)
    logger.info(f"Starting Dimos with {args.processes} processes...")
    dimos = start(args.processes)

    # Deploy xArm driver module
    logger.info("=" * 60)
    logger.info("Deploying xArm driver module...")
    logger.info(f"  xARM IP: {args.xarm}")
    logger.info("=" * 60)

    xarm_driver = dimos.deploy(
        XArmDriver,
        ip_address=args.xarm,
        is_radian=True,
        control_frequency=100.0,
        joint_state_rate=100.0,
        robot_state_rate=10.0,
        report_type="normal",
        enable_on_start=True,
        num_joints=6,
        servo_j_speed=args.servo_speed,  # Speed for smoother motion (0.1-1.0 rad/s)
    )
    logger.info(f"  Servo speed: {args.servo_speed} rad/s")

    # Set up LCM transports for xArm driver
    logger.info("Setting up xArm driver LCM transports...")
    xarm_driver.joint_position_command.transport = LCMTransport(
        args.lcm_joint_cmd_channel, JointCommand
    )
    logger.info(f"  Joint command channel: {args.lcm_joint_cmd_channel}")

    xarm_driver.joint_state.transport = LCMTransport(args.lcm_joint_state_channel, JointState)
    logger.info(f"  Joint state channel: {args.lcm_joint_state_channel}")

    # Start xArm driver
    logger.info("Starting xArm driver...")
    xarm_driver.start()
    logger.info("xArm driver started")

    # Wait for driver to initialize
    time.sleep(1)

    # Deploy FT driver module
    logger.info("=" * 60)
    logger.info("Deploying FT driver module...")
    logger.info(f"  Serial port: {args.port}")
    logger.info(f"  Baud rate: {args.baud}")
    logger.info(f"  Moving average window: {args.window}")
    logger.info(f"  Calibration file: {args.calibration or 'None (raw data only)'}")
    logger.info("=" * 60)

    driver = dimos.deploy(
        FTDriverModule,
        serial_port=args.port,
        baud_rate=args.baud,
        window_size=args.window,
        calibration_file=args.calibration,
        verbose=True,
        frame_id="ft_sensor",
    )
    logger.info("FT driver deployment complete")

    # Set up LCM transport for driver outputs
    logger.info("Setting up FT driver LCM transports...")
    driver.force.transport = LCMTransport(args.lcm_force_channel, Vector3)
    logger.info(f"  Force Vector3 channel: {args.lcm_force_channel}")

    driver.torque.transport = LCMTransport(args.lcm_torque_channel, Vector3)
    logger.info(f"  Torque Vector3 channel: {args.lcm_torque_channel}")

    # Deploy FT pull module (with xArm driver integration)
    logger.info("=" * 60)
    logger.info("Deploying FT pull module with xArm driver integration...")
    logger.info("  Using new xArm driver (NOT direct SDK)")
    logger.info("=" * 60)

    ft_pull = dimos.deploy(
        FTPullXArmModule,
        xarm_ip=args.xarm,
        joint_command_channel=args.lcm_joint_cmd_channel,
        joint_state_channel=args.lcm_joint_state_channel,
        control_rate=args.control_rate,
        verbose=args.verbose,
    )
    logger.info("FT pull module deployment complete")
    logger.info(
        f"  Control rate: {args.control_rate}Hz (sends commands every {1000 / args.control_rate:.1f}ms)"
    )

    # Set up LCM transports for FT pull module (xArm driver communication)
    logger.info("Setting up FT pull module LCM transports...")
    ft_pull.joint_state_input.transport = LCMTransport(args.lcm_joint_state_channel, JointState)
    logger.info(f"  Joint state input channel: {args.lcm_joint_state_channel}")

    ft_pull.joint_command_output.transport = LCMTransport(args.lcm_joint_cmd_channel, JointCommand)
    logger.info(f"  Joint command output channel: {args.lcm_joint_cmd_channel}")

    # Connect FT pull inputs to driver outputs
    ft_pull.force.connect(driver.force)
    ft_pull.torque.connect(driver.torque)
    logger.info("Connected FT pull module to driver force and torque streams")

    # Start modules
    logger.info("=" * 60)
    logger.info("Starting modules...")
    logger.info("=" * 60)

    # Start FT driver first (starts serial reading loop)
    if not driver.start():
        logger.error("CRITICAL: FT driver failed to start!")
        logger.error("Check that:")
        logger.error(f"  1. Serial port {args.port} exists and is accessible")
        logger.error("  2. No other process is using the serial port")
        logger.error("  3. You have permission to access the serial port")
        logger.error("  4. The sensor is connected and powered on")
        logger.info("\nTry running: ls -la /dev/tty* | grep ACM")
        logger.info("Or: sudo chmod 666 /dev/ttyACM0")
        dimos.shutdown()
        return
    logger.info("FT driver started - reading sensor data")

    # Wait a moment for data to start flowing
    logger.info("Waiting for sensor data to start flowing...")
    time.sleep(1)

    # Check driver stats to verify it's working
    stats = driver.get_stats()
    logger.info(f"Driver initial stats: {stats}")

    if stats["message_count"] == 0:
        logger.warning("No messages received from sensor yet")
        logger.warning("Waiting additional time for sensor to start...")
        time.sleep(3)
        stats = driver.get_stats()
        if stats["message_count"] == 0:
            logger.error("Still no data from sensor after 4 seconds!")
            logger.error("Check sensor connection and power")

    # Start FT pull module
    ft_pull.start()
    logger.info("FT pull module started - subscribed to force/torque streams")

    # Deploy and start visualizer if requested
    visualizer = None
    if not args.no_visualizer and args.calibration:
        logger.info("=" * 60)
        logger.info("Deploying FT visualizer module...")
        logger.info(f"  Dashboard port: {args.dash_port}")
        logger.info(f"  Dashboard host: {args.dash_host}")
        logger.info(f"  History points: {args.history}")
        logger.info(f"  Update interval: {args.update_interval}ms")
        logger.info("=" * 60)

        visualizer = dimos.deploy(
            FTVisualizerModule,
            max_history=args.history,
            update_interval_ms=args.update_interval,
            dash_port=args.dash_port,
            dash_host=args.dash_host,
            verbose=args.verbose,
        )

        # Connect visualizer inputs to driver outputs
        visualizer.force.connect(driver.force)
        visualizer.torque.connect(driver.torque)
        logger.info("Connected visualizer to force and torque streams")

        # Start visualizer
        visualizer.start()
        logger.info(
            f"Dashboard running at http://{'127.0.0.1' if args.dash_host == '0.0.0.0' else args.dash_host}:{args.dash_port}"
        )
    elif not args.no_visualizer and not args.calibration:
        logger.warning("Visualizer requires calibration file to run")
        logger.warning("  Skipping visualizer deployment")

    # Setup interactive mode if requested
    if args.interactive:
        logger.info("=" * 60)
        logger.info("Setting up interactive agent mode...")
        logger.info("=" * 60)

        # Deploy human input module
        human_input = dimos.deploy(HumanInput)

        # Deploy agent
        agent = dimos.deploy(
            Agent,
            system_prompt="""You are a helpful robotic assistant that can control a force-based door opening system.
            You have access to skills for controlling the door opening process:

            1. 'continuous_pull': Start continuous adaptive door pulling with these parameters:
               - pivot_distance: Distance to virtual pivot (meters, default 0.2)
               - force_threshold: Target force in Newtons (default 7.0)
               - rotation_gain: Rotation speed per Newton of error (default 0.01)
               - pull_speed: Pull distance per step in meters (default 0.015)
               - door_opens_clockwise: True if door opens clockwise
               - rotation_axis: 'x', 'y', or 'z' axis to rotate around
               - max_duration: Maximum duration in seconds
               - end_angle: Maximum rotation angle in degrees (optional)

            2. 'stop_pull': Stop the continuous pull operation

            Be helpful and explain what you're doing when executing skills.""",
        )

        # Register skills
        agent.register_skills(ft_pull)
        agent.register_skills(human_input)

        # Start agent
        agent.run_implicit_skill("human")
        agent.start()

        logger.info("Interactive agent ready!")
        logger.info("You can now interact with the system through the agent.")
        logger.info("Example commands:")
        logger.info('  "Start pulling the door with 5N of force"')
        logger.info('  "Pull the door open slowly"')
        logger.info('  "Stop the pull operation"')
        logger.info('  "Open the door clockwise with 10N force"')

        # Keep agent running
        agent.loop_thread()

        # Keep running indefinitely
        while True:
            time.sleep(1)

    # Auto-run mode if requested
    elif args.auto_run:
        logger.info("=" * 60)
        logger.info("Auto-running continuous pull skill...")
        logger.info("=" * 60)

        # Wait for sensor data to start flowing
        time.sleep(2)

        # Execute the skill
        result = ft_pull.continuous_pull(
            pivot_distance=args.pivot_distance,
            force_threshold=args.force_threshold,
            rotation_gain=args.rotation_gain,
            pull_speed=args.pull_speed,
            door_opens_clockwise=args.door_opens_clockwise,
            rotation_axis=args.rotation_axis,
            max_duration=args.max_duration,
            end_angle=args.end_angle,
        )

        logger.info(f"Skill result: {result}")

        # Keep running for a bit to allow cleanup
        time.sleep(5)

    # Default mode - manual control
    else:
        logger.info("=" * 60)
        logger.info("Modules running. Skills available for RPC calls:")
        logger.info("  - continuous_pull: Start adaptive door pulling")
        logger.info("  - stop_pull: Stop the pull operation")
        logger.info("Use --auto-run to automatically start pulling")
        logger.info("Use --interactive for agent-based control")
        logger.info("Press Ctrl+C to stop...")
        logger.info("=" * 60)

        try:
            # Main loop - print statistics periodically
            last_print_time = time.time()
            while True:
                time.sleep(1)

                # Print stats every 5 seconds
                if time.time() - last_print_time > 5:
                    driver_stats = driver.get_stats()
                    logger.info(
                        f"Driver Stats: Messages={driver_stats['message_count']}, "
                        f"Errors={driver_stats['error_count']}, "
                        f"Calibrated={driver_stats['calibrated_count']}"
                    )

                    if driver_stats["calibration_loaded"]:
                        logger.info(
                            f"  Latest |F|={driver_stats['latest_force_magnitude']:.2f} N, "
                            f"|T|={driver_stats['latest_torque_magnitude']:.4f} N⋅m"
                        )

                    ft_pull_stats = ft_pull.get_stats()
                    if ft_pull_stats["has_force_data"]:
                        logger.info(
                            f"Pull Stats: Force={ft_pull_stats['lateral_force']:.1f}N, "
                            f"Rotation={ft_pull_stats['total_rotation_deg']:.1f}°, "
                            f"Pull={ft_pull_stats['total_pull_cm']:.1f}cm, "
                            f"Motions={ft_pull_stats['motion_count']}"
                        )
                        if ft_pull_stats["running"]:
                            logger.info("  Status: PULLING")
                        else:
                            logger.info("  Status: IDLE")

                    if visualizer:
                        viz_stats = visualizer.get_stats()
                        logger.info(
                            f"Visualizer Stats: Force msgs={viz_stats['force_count']}, "
                            f"Torque msgs={viz_stats['torque_count']}, "
                            f"Data points={viz_stats['data_points']}"
                        )

                    last_print_time = time.time()

        except KeyboardInterrupt:
            logger.info("\n" + "=" * 60)
            logger.info("Shutting down...")
            logger.info("=" * 60)

    # Cleanup
    if not args.interactive:
        # Stop modules
        driver.stop()
        ft_pull.cleanup()
        xarm_driver.stop()
        if visualizer:
            visualizer.stop()

        # Shutdown Dimos
        time.sleep(0.5)
        dimos.shutdown()

        logger.info("Shutdown complete")


if __name__ == "__main__":
    main()
