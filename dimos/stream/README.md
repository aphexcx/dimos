# Stream Plugin Architecture

The DIMOS Stream Plugin Architecture provides a modular, extensible system for managing perception and processing streams in robotic applications. This architecture decouples model dependencies from robot implementations, enabling flexible deployment across different hardware configurations.

## Overview

The stream plugin architecture consists of:

1. **StreamInterface**: Base abstract class that all stream plugins must implement
2. **StreamConfig**: Configuration dataclass for stream parameters
3. **StreamRegistry**: Central registry for managing stream plugins
4. **Stream Plugins**: Concrete implementations of perception capabilities

## Key Features

- **Modular Design**: Add or remove perception capabilities without modifying robot code
- **Hardware Flexibility**: Run on CPU, GPU, or mixed configurations
- **Dependency Management**: Automatic resolution of stream dependencies
- **Lazy Loading**: Models are only loaded when streams are initialized
- **Graceful Degradation**: System continues to function even if some streams fail

## Architecture Components

### StreamInterface

The base class that all stream plugins must inherit from:

```python
from dimos.stream import StreamInterface, StreamConfig
from reactivex import Observable

class MyStreamPlugin(StreamInterface):
    def initialize(self, dependencies=None) -> bool:
        """Initialize the stream and load any required models."""
        # Load models, setup resources
        return True
    
    def create_stream(self, input_stream: Observable) -> Observable:
        """Create the processing stream from video input."""
        # Return Observable that processes frames
        pass
    
    def cleanup(self):
        """Clean up resources when shutting down."""
        pass
```

### StreamConfig

Configuration for stream plugins:

```python
from dimos.stream import StreamConfig

config = StreamConfig(
    name="person_tracking",
    enabled=True,
    device="cuda",  # or "cpu", "cuda:0", etc.
    model_path="yolo11n.pt",
    parameters={
        "camera_intrinsics": [fx, fy, cx, cy],
        "camera_pitch": 0.0,
        "camera_height": 1.0,
    },
    dependencies=[],  # List of required stream names
    priority=10,  # Higher priority streams initialize first
)
```

### StreamRegistry

The central registry manages all stream plugins:

```python
from dimos.stream import stream_registry

# Register a stream class
stream_registry.register_stream_class("my_stream", MyStreamPlugin)

# Configure a stream
stream_registry.configure_stream(config)

# Initialize all configured streams
streams = stream_registry.initialize_streams(force_cpu=False)

# Get a specific stream
my_stream = stream_registry.get_stream("my_stream")
```

## Usage Examples

### Basic Usage with UnitreeGo2

```python
from dimos.robot.unitree import UnitreeGo2

# Create robot with default stream configuration
robot = UnitreeGo2(
    use_ros=True,
    force_cpu=False,  # Use GPU if available
)

# Access perception streams
streams = robot.get_perception_streams()
if "person_tracking" in streams:
    person_stream = streams["person_tracking"]
    # Subscribe to person tracking results
    person_stream.subscribe(lambda data: print(f"Detected {len(data['targets'])} people"))
```

### Custom Stream Configuration

```python
from dimos.stream import StreamConfig
from dimos.robot.unitree import UnitreeGo2

# Define custom stream configurations
configs = [
    StreamConfig(
        name="person_tracking",
        enabled=True,
        device="cuda:0",
        parameters={
            "camera_intrinsics": [819.5, 820.6, 625.3, 336.8],
            "camera_pitch": 0.0,
            "camera_height": 0.44,
            "model_path": "yolo11s.pt",  # Use larger model
        },
        priority=10,
    ),
    StreamConfig(
        name="object_tracking",
        enabled=True,
        device="cpu",  # Run on CPU to save GPU memory
        parameters={
            "camera_intrinsics": [819.5, 820.6, 625.3, 336.8],
            "use_depth_model": False,  # Disable depth for CPU
        },
        priority=5,
    ),
]

# Create robot with custom configuration
robot = UnitreeGo2(
    use_ros=True,
    stream_configs=configs,
)
```

### CPU-Only Deployment

```python
from dimos.robot.unitree import UnitreeGo2
from dimos.robot.unitree.stream_configs_example import get_cpu_minimal_config

# Get CPU-optimized configuration
camera_intrinsics = [819.5, 820.6, 625.3, 336.8]
configs = get_cpu_minimal_config(camera_intrinsics)

# Create robot for CPU-only environment
robot = UnitreeGo2(
    use_ros=True,
    stream_configs=configs,
    force_cpu=True,  # Force all streams to CPU
)
```

## Creating Custom Stream Plugins

To create a new stream plugin:

1. **Implement the StreamInterface**:

```python
from dimos.stream import StreamInterface, StreamConfig
from reactivex import Observable, operators as ops
import logging

logger = logging.getLogger(__name__)

class SemanticSegmentationPlugin(StreamInterface):
    """Custom semantic segmentation stream plugin."""
    
    def __init__(self, config: StreamConfig):
        super().__init__(config)
        self.model = None
        
    def initialize(self, dependencies=None) -> bool:
        """Initialize the segmentation model."""
        try:
            # Import model only when initializing
            from my_models import SegmentationModel
            
            model_path = self.config.parameters.get("model_path")
            self.model = SegmentationModel(
                model_path=model_path,
                device=self.config.device,
            )
            
            self._initialized = True
            logger.info(f"Segmentation model loaded on {self.config.device}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize segmentation: {e}")
            return False
    
    def create_stream(self, input_stream: Observable) -> Observable:
        """Create segmentation stream."""
        if not self._initialized:
            raise RuntimeError("Plugin not initialized")
            
        def segment_frame(frame):
            # Run segmentation
            masks = self.model.segment(frame)
            return {
                "frame": frame,
                "masks": masks,
                "classes": self.model.get_classes(),
            }
        
        return input_stream.pipe(ops.map(segment_frame))
    
    def cleanup(self):
        """Clean up model resources."""
        if self.model:
            self.model.cleanup()
        self._initialized = False
```

2. **Register the Plugin**:

```python
from dimos.stream import stream_registry

# Register the plugin class
stream_registry.register_stream_class("semantic_segmentation", SemanticSegmentationPlugin)
```

3. **Configure and Use**:

```python
from dimos.stream import StreamConfig

# Configure the plugin
config = StreamConfig(
    name="semantic_segmentation",
    enabled=True,
    device="cuda",
    parameters={
        "model_path": "path/to/segmentation/model.pth",
        "num_classes": 80,
    },
    dependencies=["person_tracking"],  # Can depend on other streams
    priority=1,
)

# Add to robot configuration
configs = [person_config, object_config, config]
robot = UnitreeGo2(stream_configs=configs)
```

## Stream Dependencies

Streams can depend on other streams. The registry automatically:

1. Performs topological sorting to determine initialization order
2. Passes initialized dependencies to dependent streams
3. Detects circular dependencies

Example with dependencies:

```python
class EnhancedTrackingPlugin(StreamInterface):
    def initialize(self, dependencies=None) -> bool:
        # Access the person tracking stream
        if dependencies and "person_tracking" in dependencies:
            self.person_tracker = dependencies["person_tracking"]
        return True
```

## Best Practices

1. **Lazy Imports**: Import heavy dependencies (models) only in `initialize()` method
2. **Error Handling**: Gracefully handle missing dependencies or initialization failures
3. **Resource Management**: Properly clean up resources in `cleanup()` method
4. **Configuration Validation**: Validate parameters in plugin initialization
5. **Logging**: Use appropriate logging levels for debugging and monitoring

## Deployment Scenarios

### High-Performance GPU System

```python
from dimos.robot.unitree.stream_configs_example import get_gpu_full_config

configs = get_gpu_full_config(camera_intrinsics)
robot = UnitreeGo2(stream_configs=configs)
```

### Resource-Constrained Edge Device

```python
from dimos.robot.unitree.stream_configs_example import get_cpu_minimal_config

configs = get_cpu_minimal_config(camera_intrinsics)
robot = UnitreeGo2(stream_configs=configs, force_cpu=True)
```

### Hybrid Configuration

```python
from dimos.robot.unitree.stream_configs_example import get_hybrid_config

configs = get_hybrid_config(camera_intrinsics)
robot = UnitreeGo2(stream_configs=configs)
```

## Migration Guide

To migrate existing code to use the stream plugin architecture:

1. **Replace Direct Stream Creation**:

```python
# Old approach
self.person_tracker = PersonTrackingStream(...)
self.person_tracking_stream = self.person_tracker.create_stream(video_stream)

# New approach
configs = [StreamConfig(name="person_tracking", ...)]
robot = UnitreeGo2(stream_configs=configs)
streams = robot.get_perception_streams()
```

2. **Update Stream Access**:

```python
# Old approach
robot.person_tracking_stream.subscribe(...)

# New approach
streams = robot.get_perception_streams()
if "person_tracking" in streams:
    streams["person_tracking"].subscribe(...)
```

## Future Extensions

The architecture supports future extensions such as:

- Audio processing streams
- Sensor fusion streams
- Cloud-based processing streams
- Multi-robot coordination streams
- Custom hardware accelerator support

## Troubleshooting

### Stream Not Initializing

Check logs for initialization errors:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### GPU Memory Issues

Use CPU for some streams:
```python
configs[1].device = "cpu"  # Move specific stream to CPU
```

### Missing Dependencies

Install required packages:
```bash
pip install ultralytics  # For YOLO
pip install opencv-python  # For OpenCV tracking
```