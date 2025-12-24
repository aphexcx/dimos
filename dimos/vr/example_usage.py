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
Example usage of VRControllerSubscriber.
Both direct connection and LCM transport patterns.
"""

import time
import dimos.core as core
from dimos.core import pLCMTransport
from dimos.vr.modules import MetaQuestModule, VRControllerSubscriber


def example_direct_connection():
    """Example: Direct connection without LCM (single process)."""
    dimos = core.start(1)

    quest = dimos.deploy(MetaQuestModule, port=8881, transform_to_ros=True)
    controller = dimos.deploy(VRControllerSubscriber)

    controller.controller_left_in.connect(quest.controller_left)
    controller.controller_right_in.connect(quest.controller_right)

    quest.start()
    controller.start()

    print("Direct connection established")
    print("Left controller data:", controller.left_state)
    print("Right controller data:", controller.right_state)


def example_lcm_transport():
    """Example: LCM transport for multi-process communication."""
    dimos = core.start(1)

    quest = dimos.deploy(MetaQuestModule, port=8881, transform_to_ros=True)
    quest.controller_left.transport = pLCMTransport("/vr/left_controller")
    quest.controller_right.transport = pLCMTransport("/vr/right_controller")
    quest.start()

    controller = dimos.deploy(VRControllerSubscriber)
    controller.controller_left_in.transport = pLCMTransport("/vr/left_controller")
    controller.controller_right_in.transport = pLCMTransport("/vr/right_controller")
    controller.start()

    print("LCM transport established")
    print("Listening on /vr/left_controller and /vr/right_controller")


def example_custom_subclass():
    """Example: Subclass VRControllerSubscriber for custom robot control."""
    from dimos.vr.modules import VRControllerSubscriber
    from dimos.vr.models import ControllerData

    class RobotControlModule(VRControllerSubscriber):
        def on_left_controller(self, data: ControllerData):
            super().on_left_controller(data)
            if data.connected:
                gripper = data.buttons.trigger.value
                grip_pressed = data.buttons.grip.pressed
                print(f"Gripper: {gripper:.2f}, Grip pressed: {grip_pressed}")

        def on_right_controller(self, data: ControllerData):
            super().on_right_controller(data)
            if data.connected:
                base_x = data.axes.thumbstick_x
                base_y = data.axes.thumbstick_y
                print(f"Base velocity: ({base_x:.2f}, {base_y:.2f})")

    dimos = core.start(1)
    robot = dimos.deploy(RobotControlModule)
    robot.controller_left_in.transport = pLCMTransport("/vr/left_controller")
    robot.controller_right_in.transport = pLCMTransport("/vr/right_controller")
    robot.start()

    print("Custom robot control module started")


if __name__ == "__main__":
    example_lcm_transport()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
