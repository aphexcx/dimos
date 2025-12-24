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
from dimos.vr.modules import MetaQuestModule
from dimos.core import LCMTransport
from dimos.core import pLCMTransport
from dimos.msgs.geometry_msgs import PoseStamped


def main():
    dimos = core.start(1)
    quest = dimos.deploy(MetaQuestModule, port=8881, transform_to_ros=True)
    quest.generate_certificate()

    quest.controller_left.transport = pLCMTransport("/vr/left_controller")
    quest.controller_right.transport = pLCMTransport("/vr/right_controller")
    quest.controller_both.transport = pLCMTransport("/vr/both_controller")

    quest.controller_left_pose.transport = LCMTransport("/vr/left_arm", PoseStamped)
    quest.controller_right_pose.transport = LCMTransport("/vr/right_arm", PoseStamped)

    quest.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        quest.stop()
        print("Shutting down...")


if __name__ == "__main__":
    main()
