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

from dimos_lcm.foxglove_msgs.ImageAnnotations import (
    ImageAnnotations,
    TextAnnotation,
)
from dimos_lcm.foxglove_msgs.Point2 import Point2
from reactivex import operators as ops
from reactivex.observable import Observable

from dimos.core import In, Module, ModuleConfig, Out, rpc
from dimos.msgs.foxglove_msgs.Color import Color
from dimos.msgs.sensor_msgs import Image
from dimos.msgs.vision_msgs import Detection2DArray
from dimos.perception.detection.reid.embedding_id_system import EmbeddingIDSystem
from dimos.perception.detection.reid.type import IDSystem
from dimos.perception.detection.type import ImageDetections2D
from dimos.types.timestamped import align_timestamped, to_ros_stamp
from dimos.utils.reactive import backpressure
from dimos.utils.logging_config import setup_logger

logger = setup_logger(__name__)


class Config(ModuleConfig):
    idsystem: IDSystem


class ReidModule(Module):
    default_config = Config

    detections: In[Detection2DArray] = None  # type: ignore
    image: In[Image] = None  # type: ignore
    annotations: Out[ImageAnnotations] = None  # type: ignore
    enriched_detections: Out[Detection2DArray] = None  # type: ignore

    def __init__(self, idsystem: IDSystem | None = None, embedding_frequency: int = 5, **kwargs):
        """Initialize ReID module.

        Args:
            idsystem: ID system for tracking. Defaults to EmbeddingIDSystem with TorchReIDModel.
            embedding_frequency: Only compute embeddings every N frames to reduce compute (default: 5)
        """
        super().__init__(**kwargs)
        if idsystem is None:
            try:
                from dimos.models.embedding import TorchReIDModel

                idsystem = EmbeddingIDSystem(model=TorchReIDModel, padding=0)
            except Exception as e:
                raise RuntimeError(
                    "TorchReIDModel not available. Please install with: pip install dimos[torchreid]"
                    f"\n\nERROR: {e}"
                ) from e

        self.idsystem = idsystem
        self.embedding_frequency = embedding_frequency
        self.frame_counter = 0
        self.last_known_ids = {}  # Cache track_id -> long_term_id mapping

    def detections_stream(self) -> Observable[tuple[ImageDetections2D, Detection2DArray]]:
        """Stream aligned image detections and raw Detection2DArray."""
        return backpressure(
            align_timestamped(
                self.image.pure_observable(),
                self.detections.pure_observable().pipe(
                    ops.filter(lambda d: d.detections_length > 0)  # type: ignore[attr-defined]
                ),
                match_tolerance=0.0,
                buffer_size=2.0,
            ).pipe(
                ops.map(
                    lambda pair: (
                        ImageDetections2D.from_ros_detection2d_array(*pair),  # type: ignore[misc]
                    )
                )
            )
        )

    @rpc
    def start(self):
        self.detections_stream().subscribe(self.ingress)

    @rpc
    def stop(self):
        super().stop()

    def ingress(self, data: tuple[ImageDetections2D, Detection2DArray]):
        imageDetections, raw_detections = data
        text_annotations = []

        # Create a copy of the raw Detection2DArray for enrichment
        enriched_array = Detection2DArray(
            header=raw_detections.header,
            detections=list(raw_detections.detections),  # Copy the detections list
            detections_length=raw_detections.detections_length,
        )

        self.frame_counter += 1
        compute_embeddings = (self.frame_counter % self.embedding_frequency) == 0

        if compute_embeddings:
            logger.info(f"ReID: Computing embeddings (frame {self.frame_counter})")
        else:
            logger.debug(f"ReID: Using cached IDs (frame {self.frame_counter})")

        for i, detection in enumerate(imageDetections):
            track_id = detection.track_id

            # Only compute expensive embeddings every N frames
            if compute_embeddings:
                # Register detection and get long-term ID (expensive - runs neural network)
                long_term_id = self.idsystem.register_detection(detection)
                # Cache the ID for this track
                if long_term_id != -1:
                    self.last_known_ids[track_id] = long_term_id
            else:
                # Use cached ID if available (cheap lookup)
                long_term_id = self.last_known_ids.get(track_id, -1)

            # Update the enriched array with ReID (even if -1)
            if i < len(enriched_array.detections):
                enriched_array.detections[i].id = str(long_term_id)

            # Skip annotation if not ready yet (long_term_id == -1)
            if long_term_id == -1:
                continue

            # Create text annotation for long_term_id above the detection
            x1, y1, _, _ = detection.bbox
            font_size = imageDetections.image.width / 60

            for detection in imageDetections:
                detection.id = self.idsystem.register_detection(detection)

            self.enriched_detections.publish(imageDetections.to_ros_detection2d_array())

            text_annotations.append(
                TextAnnotation(
                    timestamp=to_ros_stamp(detection.ts),
                    position=Point2(x=x1, y=y1 - font_size * 1.5),
                    text=f"PERSON: {long_term_id}",
                    font_size=font_size,
                    text_color=Color(r=0.0, g=1.0, b=1.0, a=1.0),  # Cyan
                    background_color=Color(r=0.0, g=0.0, b=0.0, a=0.8),
                )
            )

        # Publish annotations (even if empty to clear previous annotations)
        annotations = ImageAnnotations(
            texts=text_annotations,
            texts_length=len(text_annotations),
            points=[],
            points_length=0,
        )
        self.annotations.publish(annotations)
