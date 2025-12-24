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

from dimos.core import Module, In, rpc
from dimos.vr.models import ControllerData, ControllerFrame
from reactivex.disposable import Disposable


class VRControllerSubscriber(Module):
    """Subscriber module for receiving VR controller data"""

    controller_left_in: In[ControllerData] = None
    controller_right_in: In[ControllerData] = None
    controller_both_in: In[ControllerFrame] = None

    def __init__(self, **kwargs):
        """Initialize VR controller module."""
        super().__init__(**kwargs)
        self.left_state = None
        self.right_state = None

    def _has_config(self, input_port):
        """Check if input port has transport or connection configured."""
        if input_port.connection is not None:
            return True
        try:
            return input_port.transport is not None
        except AttributeError:
            return False

    @rpc
    def start(self):
        super().start()

        if self._has_config(self.controller_left_in):
            unsub = self.controller_left_in.subscribe(self.on_left_controller)
            self._disposables.add(Disposable(unsub))

        if self._has_config(self.controller_right_in):
            unsub = self.controller_right_in.subscribe(self.on_right_controller)
            self._disposables.add(Disposable(unsub))

        if self._has_config(self.controller_both_in):
            unsub = self.controller_both_in.subscribe(self.on_both_controllers)
            self._disposables.add(Disposable(unsub))

    def on_left_controller(self, data: ControllerData):
        """Callback for left controller data. Override in subclass."""
        if data.connected:
            self.left_state = data

    def on_right_controller(self, data: ControllerData):
        """Callback for right controller data. Override in subclass."""
        if data.connected:
            self.right_state = data

    def on_both_controllers(self, frame: ControllerFrame):
        """Callback for complete controller frame. Override in subclass."""
        if frame.left and frame.left.connected:
            self.left_state = frame.left
        if frame.right and frame.right.connected:
            self.right_state = frame.right
