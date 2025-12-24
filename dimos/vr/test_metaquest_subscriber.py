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

import time

import dimos.core as core
from dimos.core import pLCMTransport
from dimos.vr.modules.controller_subscriber import VRControllerSubscriber
from dimos.vr.models import ControllerData, ControllerFrame


class LoggingControllerSubscriber(VRControllerSubscriber):
    """Controller subscriber with logging for testing and debugging."""

    def on_left_controller(self, data: ControllerData):
        """Callback for left controller data with logging."""
        super().on_left_controller(data)
        print("\n" + "=" * 60)
        print("LEFT CONTROLLER")
        print("=" * 60)
        self._print_controller_data(data)

    def on_right_controller(self, data: ControllerData):
        """Callback for right controller data with logging."""
        super().on_right_controller(data)
        print("\n" + "=" * 60)
        print("RIGHT CONTROLLER")
        print("=" * 60)
        self._print_controller_data(data)

    def on_both_controllers(self, frame: ControllerFrame):
        """Callback for complete controller frame with logging."""
        super().on_both_controllers(frame)
        print("\n" + "=" * 60)
        print(f"CONTROLLER FRAME - Timestamp: {frame.timestamp:.3f}")
        print("=" * 60)
        if frame.left and frame.left.connected:
            print("\nLEFT:")
            self._print_controller_data(frame.left)
        if frame.right and frame.right.connected:
            print("\nRIGHT:")
            self._print_controller_data(frame.right)

    def _print_controller_data(self, data: ControllerData):
        print(f"Connected: {data.connected}")

        if not data.connected:
            return

        print(
            f"\nPosition: ({data.position[0]:.3f}, {data.position[1]:.3f}, {data.position[2]:.3f})"
        )
        print(
            f"Rotation (quat): ({data.rotation[0]:.3f}, {data.rotation[1]:.3f}, {data.rotation[2]:.3f}, {data.rotation[3]:.3f})"
        )
        print(
            f"Rotation (euler): ({data.rotation_euler[0]:.1f}°, {data.rotation_euler[1]:.1f}°, {data.rotation_euler[2]:.1f}°)"
        )

        print("\nButtons:")
        print(
            f"  Trigger:    value={data.buttons.trigger.value:.3f}  pressed={data.buttons.trigger.pressed}  touched={data.buttons.trigger.touched}"
        )
        print(
            f"  Grip:       value={data.buttons.grip.value:.3f}  pressed={data.buttons.grip.pressed}  touched={data.buttons.grip.touched}"
        )
        print(
            f"  Menu:       value={data.buttons.menu.value:.3f}  pressed={data.buttons.menu.pressed}  touched={data.buttons.menu.touched}"
        )
        print(
            f"  Thumbstick: value={data.buttons.thumbstick.value:.3f}  pressed={data.buttons.thumbstick.pressed}  touched={data.buttons.thumbstick.touched}"
        )
        print(
            f"  X/A:        value={data.buttons.x_or_a.value:.3f}  pressed={data.buttons.x_or_a.pressed}  touched={data.buttons.x_or_a.touched}"
        )
        print(
            f"  Y/B:        value={data.buttons.y_or_b.value:.3f}  pressed={data.buttons.y_or_b.pressed}  touched={data.buttons.y_or_b.touched}"
        )

        print(f"\nThumbstick Axes:")
        print(f"  X: {data.axes.thumbstick_x:+.3f}")
        print(f"  Y: {data.axes.thumbstick_y:+.3f}")


def main():
    """Run the controller subscriber with logging."""
    dimos = core.start(1)

    # Create logging subscriber module
    subscriber = dimos.deploy(LoggingControllerSubscriber)
    # subscriber.controller_left_in.transport = pLCMTransport('/vr/left_controller')
    # subscriber.controller_right_in.transport = pLCMTransport('/vr/right_controller')
    subscriber.controller_both_in.transport = pLCMTransport("/vr/both_controller")

    subscriber.start()

    print("VR Controller Subscriber Started!")
    print("Listening for synchronized controller frames on:")
    print("  - /vr/both_controller")
    print("\nPress Ctrl+C to exit...\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\nShutting down subscriber...")
        subscriber.stop()


if __name__ == "__main__":
    main()
