# Codebase Analysis: m20-rosnav-migration

**Generated:** 2026-03-13
**Source:** 3-agent parallel exploration + synthesis

---

## Architecture Overview

### Project Structure

The codebase is organized by layer and robot:

```
/Users/afik_cohen/gt/dimos/crew/ace/
├── dimos/                  # Main Python package (all robot and nav code lives here)
│   ├── core/               # Framework infrastructure: modules, blueprints, transports, docker
│   ├── robot/              # Per-robot adapters (deeprobotics/, unitree/, etc.)
│   ├── navigation/         # Navigation modules: rosnav.py, rosnav_docker.py, a_star, frontier
│   ├── mapping/            # VoxelGridMapper, CostMapper, occupancy algos
│   ├── spec/               # Protocol/interface specs (Nav, Pointcloud, IMU, Odometry, etc.)
│   ├── msgs/               # DimOS message types (geometry_msgs, sensor_msgs, nav_msgs, etc.)
│   ├── visualization/      # RerunBridge and related
│   ├── web/                # websocket_vis_module (command center)
│   ├── agents/             # LLM agent infrastructure
│   ├── protocol/           # Low-level pubsub (LCM, ROS, SHM), RPC, TF
│   └── utils/              # Utilities including logging_config
├── docker/
│   ├── navigation/         # ROS2 Humble nav container (FASTLIO2 + CMU nav stack)
│   │   ├── Dockerfile      # Multi-stage, amd64/arm64; includes arise_slam + FASTLIO2
│   │   ├── build.sh
│   │   ├── start.sh
│   │   ├── config/         # fastdds.xml
│   │   └── ros-navigation-autonomy-stack/ # Submodule (CMU nav stack)
│   ├── ros/                # ROS-related docker utilities
│   └── dev/                # Dev container
├── plans/                  # Planning documents
├── pyproject.toml          # Build system: setuptools + pybind11; Python >=3.10
└── uv.lock                 # Dependency lock
```

### Robot-Specific Directory Structure

```
dimos/robot/deeprobotics/m20/
├── connection.py           # M20Connection (main robot module, dual ROS/UDP modes)
├── ros_sensors.py          # M20ROSSensors (wraps rclpy: /ODOM, /ALIGNED_POINTS, /IMU, /NAV_CMD)
├── camera.py               # M20RTSPCamera
├── lidar.py                # M20LidarDDS (CycloneDDS fallback)
├── odometry.py             # M20DeadReckonOdometry (UDP fallback)
├── velocity_controller.py  # M20VelocityController (UDP + /NAV_CMD)
├── mac_bridge_client.py    # Mac bridge TCP client
├── mac_bridge.py
├── skill_container.py
├── protocol/               # M20Protocol: UDP motion commands, gait, heartbeat
├── blueprints/
│   ├── basic/
│   │   └── m20_minimal.py  # m20_minimal blueprint (connection + vis, no nav)
│   ├── agentic/
│   └── smart/
└── docker/
    ├── Dockerfile           # Builds on Mac, runs on NOS (base: m20-deps:latest)
    ├── deploy.sh            # 600-line deploy script: push/pull/start/stop/dev/logs/status
    ├── entrypoint.sh        # Container init: ROS setup, topic wait, lidar health check
    ├── launch_nos.py        # Current blueprint: all-in-one ROS2 container on NOS
    ├── fastdds.xml
    ├── build_drdds_bindings.sh
    └── drdds_msgs/
```

### Navigation Module Structure

```
dimos/navigation/
├── rosnav.py               # ROSNav class: container-side rclpy node (ROS transport)
├── rosnav_docker.py        # ROSNavConfig (DockerModuleConfig) + ROSNav host-side class
├── base.py                 # NavigationInterface ABC + NavigationState enum
├── dimos_module_entrypoint.sh  # Container entrypoint for DockerModule pattern
├── entrypoint.sh           # Legacy entrypoint (Unity sim)
├── replanning_a_star/
│   └── module.py           # ReplanningAStarPlanner (host-side, no ROS)
├── frontier_exploration/
│   └── ...                 # WavefrontFrontierExplorer
├── bbox_navigation.py
└── visual/
```

### Core Framework

```
dimos/core/
├── module.py               # Module base class + ModuleConfig
├── blueprints.py           # Blueprint, autoconnect(), _BlueprintAtom
├── transport.py            # LCMTransport, pLCMTransport, ROSTransport, SHMTransport
├── docker_runner.py        # DockerModule, DockerModuleConfig, StandaloneModuleRunner
├── docker_build.py         # build_image(), image_exists()
├── stream.py               # In[T], Out[T] stream port types
├── module_coordinator.py   # ModuleCoordinator (deployment + lifecycle)
├── worker.py               # Worker (multiprocessing)
├── global_config.py        # GlobalConfig (robot_ip, n_workers, robot_width, etc.)
└── test_modules.py         # Auto-scan test enforcing start()/stop() on all Modules
```

---

## Integration Surface

### Files That Must Be Modified

#### 1.1 `dimos/robot/deeprobotics/m20/connection.py` — MODIFY

**Current state:** M20Connection has a dual ROS/UDP mode controlled by `enable_ros` parameter. The `_start_ros_path()` method subscribes to `/ODOM`, `/ALIGNED_POINTS`, `/IMU`.

**In ROSNav mode:**
- Pass `enable_ros=False` from the blueprint constructor to disable ROS subscriptions
- The `_start_udp_fallback_path()` method remains active, handling UDP heartbeats, camera, and motion control
- The `_on_cmd_vel` handler (line 397) routes velocity commands from `In[Twist]` → `M20VelocityController.set_twist()`

**Key issue identified:** M20Connection declares `pointcloud: Out[PointCloud2]` and `lidar: Out[PointCloud2]` at class level. These port annotations exist regardless of `enable_lidar` runtime state. In the ROSNav blueprint, both M20Connection and ROSNav will have `pointcloud: Out[PointCloud2]`. This creates a stream name conflict that `autoconnect()` will reject (two `Out` ports on same topic).

**Resolution:** The blueprint must use `.remappings()` to rename M20Connection's unused pointcloud outputs, or exclude them from the composition entirely.

#### 1.2 `dimos/navigation/rosnav_docker.py` — INSPECT/EXTEND

**Current `ROSNavConfig` fields (lines 98-239):**
```python
@dataclass
class ROSNavConfig(DockerModuleConfig):
    local_pointcloud_freq: float = 2.0
    global_map_freq: float = 1.0
    sensor_to_base_link_transform: Transform
    docker_image: str = "dimos_autonomy_stack:humble"
    docker_shm_size: str = "8g"
    docker_entrypoint: str = "/usr/local/bin/dimos_module_entrypoint.sh"
    docker_file: Path = Path(__file__).parent.parent.parent / "docker" / "navigation" / "Dockerfile"
    docker_build_context: Path = ...
    docker_gpus: str | None = None
    docker_extra_args: list = field(default_factory=lambda: ["--cap-add=NET_ADMIN"] + ...)
    docker_env: dict = field(default_factory=lambda: {"ROS_DISTRO": "humble", "ROS_DOMAIN_ID": "42", ...})
    docker_volumes: list = field(default_factory=lambda: [...])
    mode: str = "hardware"
    bagfile_path: str | Path = ""
    use_rviz: bool = False
```

**Note on `docker_memory`:** The spec mentions `docker_memory` as a new field, but `DockerModuleConfig` does not have this field. Memory limits must be passed via `docker_extra_args`:
```python
docker_extra_args: list = field(
    default_factory=lambda: ["--memory=1.5g", "--memory-swap=1.5g", "--cap-add=NET_ADMIN"]
)
```

**Critical pattern:** `ROSNavConfig.__post_init__()` (lines 147-248) performs significant work including setting MODE env var, adding docker_volumes (including Unity mesh paths and X11 sockets), and handling various mount points. Any M20 subclass MUST call `super().__post_init__()` then override fields as needed.

#### 1.3 `dimos/robot/deeprobotics/m20/docker/deploy.sh` — MODIFY

**Current structure (lines 385-599):** `case "${CMD}" in push|pull|dev|start|stop|restart|logs|shell|status|help`

**Required changes:**
- Add `setup` subcommand: SSH to NOS, install uv, create Python 3.10 venv, install dimos, rebuild drdds for Python 3.10
- Modify `start` subcommand: In ROSNav mode, dimos runs natively on NOS host; DockerModule manages nav container. Remove `docker run` call and replace with SSH execution of launch script.
- Replace `ensure_lio_enabled()` with `ensure_lio_disabled()` that stops lio_perception on AOS and verifies rsdriver publishes `/lidar_points`
- Update `status` case: Check host dimos process + nav container + rsdriver status instead of lio_ddsnode
- Modify `dev` subcommand: rsync to NOS host venv in addition to container

**SSH/remote execution pattern (already implemented):**
- ControlMaster socket: `~/.ssh/ctl-%C` with `-o ControlMaster=auto`
- NOS sudo password handling: `SUDO_PASS="${SUDO_PASS:-"'"}"` (single quote password already supported)
- Remote execution: `ssh $SSH_OPTS user@$NOS_IP "command"` with pre-existing session

#### 1.4 `dimos/robot/deeprobotics/m20/docker/entrypoint.sh` — MODIFY

**Current behavior (lines 33-103):**
- Waits for `/ODOM` and `/IMU`
- Checks `/ALIGNED_POINTS` (lio_perception output)
- Restarts lio_perception if `/ALIGNED_POINTS` missing

**In ROSNav mode:**
- Remove wait for `/ODOM` (no longer provided by lio_perception)
- Keep wait for `/IMU` (still needed by FASTLIO2)
- Change lidar health check: check `/lidar_points` (rsdriver output) instead of `/ALIGNED_POINTS`
- Remove restart logic for lio_perception (disabled in ROSNav mode)

**Note:** The entrypoint currently runs inside the old monolithic Docker container. In ROSNav mode, the NOS host runs dimos natively; the nav container uses `dimos_module_entrypoint.sh` from `dimos/navigation/`. The M20-specific entrypoint becomes a host-side startup script.

#### 1.5 `dimos/robot/deeprobotics/m20/docker/launch_nos.py` — REPLACE

**Current:** Builds an all-in-one pipeline inside the old monolithic Docker container.

**In ROSNav mode:** `launch_nos.py` becomes the NOS host launcher that runs natively (outside Docker). It imports and executes the `m20_rosnav` blueprint. The ROSNav container is managed by DockerModule inside dimos, not externally by deploy.sh.

**New structure:**
```python
from dimos.robot.deeprobotics.m20.blueprints.rosnav.m20_rosnav import m20_rosnav_bp
coordinator = m20_rosnav_bp.build()
# wait loop
```

#### 1.6 `dimos/navigation/dimos_module_entrypoint.sh` — INSPECT

**Current behavior (lines 239-278):**
- `LOCALIZATION_METHOD="${LOCALIZATION_METHOD:-arise_slam}"` — default is arise_slam
- `use_fastlio2:=true` launch arg when `LOCALIZATION_METHOD=fastlio`
- `ROS_DOMAIN_ID` comes from env (default set by ROSNavConfig to 42)

**For M20 Phase 1:** No changes needed. The env var `ROS_DOMAIN_ID=0` set by `M20ROSNavConfig` will override correctly. FASTLIO2 mode already supported via `LOCALIZATION_METHOD=fastlio` env var.

---

### New Files to Create

#### 2.1 `dimos/robot/deeprobotics/m20/rosnav_docker.py` — NEW

A new `@dataclass` extending `ROSNavConfig` with M20-specific overrides:

```python
@dataclass
class M20ROSNavConfig(ROSNavConfig):
    # Docker resource settings for NOS (RAM-constrained)
    docker_image: str = "ghcr.io/aphexcx/m20-nav:latest"
    docker_shm_size: str = "1g"                    # from 8g default
    docker_extra_args: list = field(default_factory=lambda: [
        "--cap-add=NET_ADMIN",
        "--memory=1.5g",
        "--memory-swap=1.5g",
    ])
    docker_env: dict = field(default_factory=lambda: {
        "ROS_DISTRO": "humble",
        "ROS_DOMAIN_ID": "0",              # CRITICAL: match rsdriver's domain
        "RMW_IMPLEMENTATION": "rmw_fastrtps_cpp",
        "FASTRTPS_DEFAULT_PROFILES_FILE": "/ros2_ws/config/fastdds.xml",
        "MODE": "hardware",
        "USE_ROUTE_PLANNER": "true",
        "LOCALIZATION_METHOD": "fastlio",
        "USE_RVIZ": "false",
    })

    # M20-specific SLAM/sensor configuration
    localization_method: str = "fastlio"
    lidar_topic: str = "/lidar_points"
    imu_topic: str = "/IMU"
    nav_cmd_topic: str = "/NAV_CMD"
    robot_width: float = 0.45
    lidar_height: float = 0.47

    def __post_init__(self) -> None:
        # Call parent to set up base config
        super().__post_init__()

        # Override docker_volumes with M20-minimal list (base includes Unity paths that don't exist on NOS)
        self.docker_volumes = [
            (dimos_root, "/workspace/dimos", "rw"),
            (fastdds_xml_path, "/ros2_ws/config/fastdds.xml", "ro"),
            (entrypoint_sh_path, "/usr/local/bin/dimos_module_entrypoint.sh", "ro"),
            # Phase 2: ("/var/opt/robot/data/maps", "/maps", "rw")
        ]

        # Ensure ROS domain is set correctly
        self.docker_env["ROS_DOMAIN_ID"] = "0"
```

**Critical detail:** The `__post_init__` must NOT call `super().__post_init__()` blindly without reviewing what it does. It adds Unity mesh paths, X11 sockets, and other mounts that don't exist on NOS and will cause bind-mount failures. The safest approach is to call `super().__post_init__()` then immediately replace `docker_volumes` with the M20-specific minimal list.

#### 2.2 `dimos/robot/deeprobotics/m20/blueprints/rosnav/m20_rosnav.py` — NEW

Blueprint file following the G1 pattern:

```python
from dimos.core.blueprints import autoconnect
from dimos.navigation.rosnav_docker import ros_nav  # DockerModule-backed version
from dimos.robot.deeprobotics.m20.rosnav_docker import M20ROSNavConfig
from dimos.robot.deeprobotics.m20.connection import m20_connection
from dimos.mapping.voxels import voxel_mapper
from dimos.mapping.costmapper import cost_mapper
from dimos.mapping.pointclouds.occupancy import HeightCostConfig
from dimos.web.websocket_vis.websocket_vis_module import websocket_vis
from dimos.visualization.rerun.bridge import rerun_bridge

m20_rosnav = autoconnect(
    m20_connection(enable_ros=False, lidar_height=0.47),
    voxel_mapper(voxel_size=0.05, publish_interval=1.0, max_height=0.7),
    cost_mapper(config=HeightCostConfig(
        max_height=0.7,
        resolution=0.05,
        ignore_noise=0.05,
        can_climb=0.25,
        smoothing=5.0
    )),
    websocket_vis(),
    rerun_bridge(memory_limit="512MB"),
    ros_nav(config=M20ROSNavConfig()),
).remappings([
    # Disambiguate pointcloud outputs between M20Connection and ROSNav
    (M20Connection, "pointcloud", "m20_pointcloud_unused"),
    (M20Connection, "lidar", "m20_lidar_unused"),
]).transports({
    # Explicit routing for lidar data
    ("lidar", PointCloud2): LCMTransport("/lidar", PointCloud2),
    ("pointcloud", PointCloud2): LCMTransport("/lidar", PointCloud2),
}).global_config(
    robot_ip="10.21.33.103",
    robot_model="deeprobotics_m20",
    robot_width=0.45,
    robot_rotation_diameter=0.6,
    n_workers=2,
)
```

**Critical stream conflict issues identified:**

| Stream | M20Connection | ROSNav | VoxelGridMapper | Resolution |
|--------|---------------|--------|-----------------|------------|
| `pointcloud: Out[PointCloud2]` | YES | YES | — | Remap M20 to unused name |
| `lidar: Out[PointCloud2]` | YES | — | — | Remap M20 to unused name |
| `lidar: In[PointCloud2]` | — | — | YES | Expects input from `/lidar` topic |
| `global_map: Out[PointCloud2]` | — | YES | YES | Both M20's voxel mapper + ROSNav publish this |
| `cmd_vel: In[Twist]` | YES | — | — | Receives from ROSNav |
| `cmd_vel: Out[Twist]` | — | YES | — | Sends to M20Connection |

The blueprint must handle:
1. **Pointcloud conflict:** M20Connection and ROSNav both declare `pointcloud: Out[PointCloud2]`. Remap M20's to avoid collision.
2. **Global map conflict:** Both VoxelGridMapper and ROSNav publish `global_map`. Blueprint needs remapping or transport override.
3. **Lidar input routing:** VoxelGridMapper's `lidar: In[PointCloud2]` must connect to ROSNav's `pointcloud: Out[PointCloud2]` on the same LCM topic `/lidar`.

#### 2.3 `dimos/robot/deeprobotics/m20/blueprints/rosnav/__init__.py` — NEW

Empty init file for the new blueprint subpackage.

#### 2.4 `dimos/robot/deeprobotics/m20/docker/launch_nos_rosnav.py` — NEW (Optional)

If needed separate from `launch_nos.py`. Minimal launcher:

```python
import signal
from dimos.robot.deeprobotics.m20.blueprints.rosnav.m20_rosnav import m20_rosnav_bp

bp = m20_rosnav_bp.build()
coordinator = bp.coordinator()

def signal_handler(sig, frame):
    coordinator.stop()
    exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

coordinator.start()
while True:
    signal.pause()
```

---

## Patterns & Conventions

### Module Structure

Every module follows this exact pattern:

```python
class MyModule(Module, spec.SomeSpec, spec.AnotherSpec):
    """Docstring: one-liner + longer explanation.

    Streams:
        input_name (In):  Description
        output_name (Out): Description
    """
    # Input streams declared at class level
    cmd_vel: In[Twist]

    # Output streams declared at class level
    color_image: Out[Image]
    pointcloud: Out[PointCloud2]

    # Private state with type annotations
    _protocol: M20Protocol
    _thread: Thread | None = None
    _running: bool = False

    def __init__(self, param1: Type = default, *args: Any, **kwargs: Any) -> None:
        # 1. Store parameters
        self._param1 = param1
        # 2. Initialize sub-objects (protocols, sensors, etc.)
        self._protocol = M20Protocol(...)
        # 3. Conditional initialization with graceful fallback
        try:
            self._optional = OptionalComponent()
        except (ImportError, RuntimeError) as e:
            logger.warning(f"Optional component unavailable: {e}")
            self._optional = None
        # 4. Module.__init__ MUST be called LAST
        Module.__init__(self, *args, **kwargs)

    @rpc
    def start(self) -> None:
        super().start()
        try:
            self._service.start()
            self._disposables.add(Disposable(self.input_stream.subscribe(self._on_input)))
        except Exception:
            logger.exception("MyModule.start() failed")
            self.stop()
            raise

    @rpc
    def stop(self) -> None:
        # Stop each component in a separate try/except
        try:
            self._service.stop()
        except Exception:
            logger.exception("Failed to stop service")
        super().stop()
```

**Critical rules:**
- `Module.__init__()` must be called LAST
- Both `start()` and `stop()` methods required and decorated with `@rpc`
- Each stop-time operation in its own try/except block for graceful cleanup
- Forbidden method names (enforced by `test_modules.py`): `acquire`, `release`, `open`, `close`, `shutdown`, `clean`, `cleanup`
- Reactive subscriptions stored in `self._disposables` (CompositeDisposable) for cleanup on stop

### DockerModuleConfig Pattern

```python
@dataclass
class M20ROSNavConfig(ROSNavConfig):
    # Override Docker resource settings
    docker_shm_size: str = "1g"
    docker_image: str = "ghcr.io/aphexcx/m20-nav:latest"

    # Add custom fields for M20-specific behavior
    localization_method: str = "fastlio"
    lidar_topic: str = "/lidar_points"

    def __post_init__(self) -> None:
        super().__post_init__()
        # M20-specific post-init logic
        self.docker_env["LOCALIZATION_METHOD"] = self.localization_method
```

**Key rules:**
- Extend `ROSNavConfig` (which extends `DockerModuleConfig`)
- Non-`docker_*` fields are passed to the container module via JSON payload
- `docker_*` fields control the `docker run` command
- Memory limits must use `docker_extra_args: ["--memory=1.5g"]` (no `docker_memory` field exists)
- Call `super().__post_init__()` to set up base config, then override as needed

### Blueprint Factory Pattern

Every module file ends with:
```python
m20_connection = M20Connection.blueprint
ros_nav = ROSNav.blueprint
```

This is declared in `Module` base class (module.py lines 350-355) and inherited automatically. Blueprint files are minimal — compose via `autoconnect()` and call `.global_config()`:

```python
m20_minimal = autoconnect(
    with_vis,
    m20_connection(),
    websocket_vis(),
).global_config(
    n_workers=4,
    robot_model="deeprobotics_m20",
    robot_width=0.45,
    robot_rotation_diameter=0.6,
)
```

### Two ROSNav Classes (Critical Distinction)

There are TWO different classes both named `ROSNav`:

1. **`dimos/navigation/rosnav.py` — ROSNav (rclpy-based, ROS transport)**
   - Uses `rclpy` directly (spins a ROS2 node, creates ROS2 pub/sub)
   - Runs INSIDE the Docker container
   - Streams wired via `ROSTransport` (connects to actual ROS2 topics)
   - Exports: `ros_nav = ROSNav.blueprint`

2. **`dimos/navigation/rosnav_docker.py` — ROSNav (host-side, DockerModule-backed)**
   - Uses direct `rclpy` node in `__init__`
   - Runs INSIDE the Docker container BUT managed by DockerModule on host
   - Host-side: `DockerModuleConfig`-backed proxy
   - Exports: `ros_nav = ROSNav.blueprint`

**For M20 ROSNav, the correct import is:**
```python
from dimos.navigation.rosnav_docker import ros_nav  # DockerModule-backed
```

NOT:
```python
from dimos.navigation.rosnav import ros_nav  # Wrong — in-process ROS transport
```

The G1 integration imports from `rosnav_docker.py` (confirmed by analyzing unitree blueprint patterns).

### Error Handling

**Import guard for optional dependencies:**
```python
try:
    from .ros_sensors import M20ROSSensors
    _ROS_AVAILABLE = True
except (ImportError, RuntimeError):
    _ROS_AVAILABLE = False
```

Then check at runtime:
```python
if self._ros_sensors is None and enable_ros and _ROS_AVAILABLE:
    try:
        self._ros_sensors = M20ROSSensors()
    except RuntimeError as e:
        logger.warning(f"M20ROSSensors init failed: {e}")
```

**For ROS message types (container-only imports):**
```python
try:
    from geometry_msgs.msg import PoseStamped as ROSPoseStamped
except ModuleNotFoundError:
    class _Stub:
        def __init__(self, *args, **kwargs) -> None:
            pass
    ROSPoseStamped = _Stub
```

### Logging Pattern

**In navigation/ROS modules:**
```python
from dimos.utils.logging_config import setup_logger
logger = setup_logger(level=logging.INFO)
```

**In robot/connection modules:**
```python
import logging
logger = logging.getLogger(__name__)
```

Both output through structlog. The `setup_logger()` variant gets richer formatting with callsite info.

### RxPY / Reactive Observable Pattern

Observable streams use RxPY `Subject` for internal state, exposed as `Observable`:

```python
self._odom_subject: Subject[PoseStamped] = Subject()

def odom_stream(self) -> Observable[PoseStamped]:
    return self._odom_subject

# Publishing
self._odom_subject.on_next(pose)

# Subscription
self._disposables.add(
    self._ros_sensors.odom_stream().subscribe(self._publish_tf)
)
```

### Naming Conventions

- **Files:** `snake_case.py` matching class name; config files `{robot}_docker.py`; blueprint files `{robot}_{variant}.py`
- **Classes:** `PascalCase` with spec mixins (`M20Connection(Module, spec.Camera, spec.Pointcloud, ...)`)
- **Config classes:** `PascalCase + Config` (`M20ROSNavConfig`, `ROSNavConfig`)
- **Blueprint factories:** snake_case of class: `m20_connection = M20Connection.blueprint`
- **Private members:** Leading underscore: `_protocol`, `_ros_sensors`, `_running`
- **Constants:** `ALL_CAPS` for module-level constants; `_LEADING_UNDERSCORE` for flags

---

## Key Files Reference

### Files to Modify

| File | Change | Why |
|------|--------|-----|
| `dimos/robot/deeprobotics/m20/connection.py` | Pass `enable_ros=False` from new blueprint | Disable ROS subscriptions in ROSNav mode |
| `dimos/robot/deeprobotics/m20/docker/deploy.sh` | Add `setup` subcommand; modify `start`/`stop`/`status`/`dev` | Host+container split, native dimos execution |
| `dimos/robot/deeprobotics/m20/docker/entrypoint.sh` | Adapt for host use; check `/lidar_points` not `/ODOM` | Align with ROSNav data flow |
| `dimos/robot/deeprobotics/m20/docker/launch_nos.py` | Replace with ROSNav host launcher | Entry point for native dimos on NOS |

### New Files to Create

| File | Purpose |
|------|---------|
| `dimos/robot/deeprobotics/m20/rosnav_docker.py` | `M20ROSNavConfig(ROSNavConfig)` dataclass with M20 overrides |
| `dimos/robot/deeprobotics/m20/blueprints/rosnav/m20_rosnav.py` | `m20_rosnav` blueprint: mapping modules + ROSNav DockerModule |
| `dimos/robot/deeprobotics/m20/blueprints/rosnav/__init__.py` | Package init for new blueprint subpackage |

### Referenced (Unchanged) Files

| File | Why Unchanged |
|------|--------------|
| `dimos/core/docker_runner.py` | `DockerModule` is ready for M20 use |
| `dimos/core/blueprints.py` | `autoconnect()` handles `.remappings()` already |
| `dimos/navigation/rosnav.py` | Container-side module unchanged; M20 uses same class |
| `dimos/navigation/dimos_module_entrypoint.sh` | Already handles hardware mode + FASTLIO2 |
| `docker/navigation/Dockerfile` | Already arm64-compatible, already has FASTLIO2 support |
| `dimos/mapping/voxels.py` | VoxelGridMapper used as-is |
| `dimos/mapping/costmapper.py` | CostMapper used as-is |
| `dimos/robot/deeprobotics/m20/velocity_controller.py` | Unchanged; handles both UDP and NAV_CMD |
| `dimos/robot/deeprobotics/m20/blueprints/basic/m20_minimal.py` | `m20_minimal` unchanged; still valid for teleop |

---

## Constraints & Considerations

### Architectural Boundaries

1. **No rclpy on the host.** M20Connection in ROSNav mode must NOT use rclpy. The ROS path was for running inside a ROS container. The new host is Python 3.10 native with no ROS sourced.

2. **DDS domain isolation.** Run FASTLIO2 on domain 0 (same as rsdriver). The `ROSNavConfig` default is `ROS_DOMAIN_ID=42`. The `M20ROSNavConfig.__post_init__()` must override to `ROS_DOMAIN_ID=0`.

3. **Stream name/type must match exactly.** `autoconnect()` wires by (name, type) pairs. The M20 blueprint must not introduce duplicate stream names with conflicting types. Current M20Connection publishes `pointcloud: Out[PointCloud2]` and ROSNav also publishes `pointcloud: Out[PointCloud2]` — these will conflict. The blueprint must use `.remappings()` to resolve.

4. **`m20_minimal` as optional base.** The new ROSNav blueprint CAN compose on top of `m20_minimal` or build from scratch. The current `m20_minimal` sets `n_workers=2, robot_model, robot_width, robot_rotation_diameter` via `.global_config()`. The new blueprint must NOT re-set conflicting values or should replace the base entirely.

5. **VoxelGridMapper input routing.** `VoxelGridMapper` declares `lidar: In[PointCloud2]`. `ROSNav` declares `pointcloud: Out[PointCloud2]`. The names differ, so autoconnect won't auto-wire them. The blueprint must use explicit `.transports()` or `.remappings()` to route ROSNav's `pointcloud` output to the same LCM topic that VoxelGridMapper's `lidar` input expects.

### Build & Deploy

- **Python package:** `pyproject.toml` with setuptools + pybind11. `pip install -e .` or `uv pip install -e .`
- **C++ extension:** `dimos/navigation/replanning_a_star/min_cost_astar_cpp.cpp` (pybind11). Built during `pip install`.
- **drdds rebuild:** Mandatory for Python 3.10 ABI compatibility on NOS
- **Nav container:** `docker/navigation/Dockerfile` — multi-stage, ARM64-compatible. Push to `ghcr.io/aphexcx/m20-nav:latest` (new distinct tag from current `m20-nos:latest`)

### Docker Considerations

- **NOS Docker storage:** `/var/opt/robot/data/docker` (non-default path, set via daemon.json). Docker binary is at standard `/usr/bin/docker`. No changes needed.
- **NOS Docker image size:** Existing nav container potentially > 10GB. NOS has 46GB free. Initial pull over GOS 5G will be slow but one-time.
- **arise_slam in Phase 1 image:** Included but not started (LOCALIZATION_METHOD=fastlio env var switches runtime). Acceptable for Phase 1; Phase 2 can optimize.

### ROS Domain ID Critical Issue

The spec requires running FASTLIO2 on domain 0 to match rsdriver. The base `ROSNavConfig.docker_env` sets `ROS_DOMAIN_ID=42`. The `M20ROSNavConfig.__post_init__()` MUST override this:

```python
def __post_init__(self) -> None:
    super().__post_init__()
    self.docker_env["ROS_DOMAIN_ID"] = "0"  # Match AOS rsdriver
```

This ensures FASTLIO2 container discovers `/lidar_points` and `/IMU` on the correct DDS domain.

### Volume Mounts for M20 Container

The base `ROSNavConfig.__post_init__()` adds large volumes including X11 socket, Unity mesh paths, and ros_tcp_endpoint patch. Most are irrelevant on NOS. The M20 override should define a minimal list:

```python
docker_volumes = [
    (dimos_root, "/workspace/dimos", "rw"),
    (fastdds_xml_path, "/ros2_ws/config/fastdds.xml", "ro"),
    (entrypoint_sh_path, "/usr/local/bin/dimos_module_entrypoint.sh", "ro"),
    # Phase 2: ("/var/opt/robot/data/maps", "/maps", "rw")
]
```

### Known Stream Wiring Gaps

**The `odom` stream gap:** In current architecture, `M20Connection` publishes `odom: Out[PoseStamped]`. `ReplanningAStarPlanner` consumes it. In ROSNav architecture, odometry comes from FASTLIO2 in the container. The `ROSNav` class in `rosnav_docker.py` does NOT publish an `odom` output port.

**Resolution:** The new `m20_rosnav` blueprint should NOT include `replanning_a_star_planner` — that is the whole point of ROSNav (CMU stack handles all planning internally).

### Module Compliance & Blueprint Registration

- Auto-scan test `dimos/core/test_modules.py` enforces `start()`/`stop()` on all Modules
- Auto-import test `dimos/robot/test_all_blueprints.py` requires registration in `dimos/robot/all_blueprints.py`
- Generate registry by running: `pytest dimos/robot/test_all_blueprints_generation.py`

### Testing

- **Framework:** pytest with standard discovery
- **Location:** Co-located test files (`test_*.py` in same directory as module)
- **For M20 ROSNav:** Write tests for config defaults, `__post_init__` behavior, Twist→NavCmd translation, message conversions
- **Blueprint smoke tests:** Auto-covered once registered in `all_blueprints.py`

---

## Implementation Order (Phase 1)

1. **`dimos/robot/deeprobotics/m20/rosnav_docker.py`** — Create `M20ROSNavConfig` with all fields, `__post_init__()` handling volumes + ROS_DOMAIN_ID
2. **`dimos/robot/deeprobotics/m20/blueprints/rosnav/__init__.py`** — Create package init
3. **`dimos/robot/deeprobotics/m20/blueprints/rosnav/m20_rosnav.py`** — Create blueprint with explicit `.remappings()` + `.transports()` for stream conflicts
4. **`dimos/robot/all_blueprints.py`** — Register new `m20_rosnav` blueprint
5. **Build M20 nav container** — New Dockerfile based on `docker/navigation/Dockerfile` with robosense_fast_lio; push to `ghcr.io/aphexcx/m20-nav:latest`
6. **`dimos/robot/deeprobotics/m20/docker/launch_nos.py`** — Replace with ROSNav host launcher
7. **`dimos/robot/deeprobotics/m20/docker/deploy.sh`** — Add `setup`, modify `start`/`stop`/`status`/`dev`
8. **`dimos/robot/deeprobotics/m20/docker/entrypoint.sh`** — Adapt for host-side use
9. **End-to-end test** on robot hardware
