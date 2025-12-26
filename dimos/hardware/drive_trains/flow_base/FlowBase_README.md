# Hardware Drivers

## FlowBase Driver

Omnidirectional mobile robot driver interfacing with FlowBase controller via Portal RPC.

### Quick Start

```python
from dimos.core import start, LCMTransport
from dimos.hardware.drive_trains.flow_base.flow_base_driver import FlowBaseDriver
from dimos.msgs.geometry_msgs import Twist
from dimos.msgs.nav_msgs import Odometry

dimos = start(1)
driver = dimos.deploy(FlowBaseDriver, host="172.6.2.20", port=11323)
driver.twist_cmd.transport = LCMTransport("/flowbase/cmd_vel", Twist)
driver.odom_out.transport = LCMTransport("/flowbase/odom", Odometry)
driver.start()
```

### Test Script

```bash
# Basic test
python flow_base_test.py --host 172.6.2.20 --odom-rate 20.0

# With keyboard control
python flow_base_test.py --host 172.6.2.20 --teleop --teleop-speed 0.1

# With odometry tests
python flow_base_test.py --test-odometry --verbose
```

### API

**Constructor:**
```python
FlowBaseDriver(host="172.6.2.20", port=11323, verbose=False, odom_rate=20.0)
```

**Ports:**
- `twist_cmd: In[Twist]` - Velocity commands
- `odom_out: Out[Odometry]` - Odometry output

**RPC Methods:**
- `start() -> bool` - Start driver
- `stop() -> bool` - Stop driver
- `get_odometry() -> dict` - Get odometry `{"translation": [x, y], "rotation": theta}`
- `reset_odometry() -> bool` - Reset odometry
- `get_status() -> dict` - Get driver status

### Coordinate Frames

**Note:** FlowBase uses inverted Y-axis compared to ROS standard. The driver automatically converts:
```
ROS (right-hand):    FlowBase (inverted Y):
    +Y                   -Y
    ↑                    ↑
 ───┼──→ +X          ───┼──→ +X
    |                    |
    ↓                    ↓
   -Y                   +Y
```

### Requirements

- Python 3.8+
- DIMOS framework
- Portal RPC library
- NumPy
- FlowBase controller at `172.6.2.20:11323`

### Troubleshooting

| Issue | Solution |
|-------|----------|
| Cannot connect | Check controller power, ping 172.6.2.20, verify port 11323 |
| No commands sent | Verify LCM channel names match, check transport config |
| No odometry | Verify `odom_out` has transport, check logs |

### Files

- [flow_base_driver.py](flow_base_driver.py) - Driver implementation
- [flow_base_test.py](flow_base_test.py) - Test/example script


Copyright 2025 Dimensional Inc. - Licensed under Apache 2.0