"""Perception Node — object detection and pose estimation.

Publishes detected objects to /perception/object_poses (ObjectPose).
WorldModel subscribes to this topic for perception-cognition loop.
"""

from __future__ import annotations

import random
import sys
import time
from dataclasses import dataclass, field
from typing import Any

import yaml

import rclpy
from rclpy.node import Node
from std_msgs.msg import Header
from multi_arm_interfaces.msg import ObjectPose


@dataclass
class DetectedObject:
    """A detected object from perception."""

    object_id: str
    object_type: str
    position: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    orientation: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0, 1.0])
    confidence: float = 1.0


class ObjectDetector:
    """Object detector (placeholder for YOLOv8/Gazebo Ground Truth).

    In production, this would be replaced with:
    - Gazebo Ground Truth: query Gazebo for exact object poses
    - YOLOv8: real camera detection
    - Sim2Real: same interface, different backend
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """Initialize detector with configuration.

        Args:
            config: Detector configuration dict.

        """
        self._config = config or {}
        self._known_objects: dict[str, DetectedObject] = {}
        self._rng = random.Random(self._config.get("seed", 42))

    def register_object(
        self,
        object_id: str,
        object_type: str,
        position: list[float],
        orientation: list[float] | None = None,
    ) -> None:
        """Register a known object for detection.

        Args:
            object_id: Object unique ID.
            object_type: Object type (cube/cylinder/box).
            position: [x, y, z] position.
            orientation: [qx, qy, qz, qw] orientation.

        """
        self._known_objects[object_id] = DetectedObject(
            object_id=object_id,
            object_type=object_type,
            position=position,
            orientation=orientation or [0.0, 0.0, 0.0, 1.0],
        )

    def detect(self) -> list[DetectedObject]:
        """Detect all known objects.

        Returns:
            List of detected objects with confidence.

        """
        results: list[DetectedObject] = []
        for obj in self._known_objects.values():
            jitter = self._config.get("position_noise", 0.0)
            detected = DetectedObject(
                object_id=obj.object_id,
                object_type=obj.object_type,
                position=[
                    obj.position[0] + self._rng.uniform(-jitter, jitter),
                    obj.position[1] + self._rng.uniform(-jitter, jitter),
                    obj.position[2] + self._rng.uniform(-jitter, jitter),
                ],
                orientation=obj.orientation,
                confidence=self._config.get("confidence", 0.95),
            )
            results.append(detected)
        return results


class PerceptionNode(Node):
    """ROS2 node for object perception.

    Publishes:
        - /perception/object_poses (ObjectPose) — detected objects
        - /perception/scene_update (SceneState) — scene summary
    """

    def __init__(self) -> None:
        """Initialize perception node."""
        super().__init__("perception_node")

        self.declare_parameter("publish_rate", 10.0)
        self.declare_parameter("position_noise", 0.0)
        self.declare_parameter("confidence", 0.95)

        config = {
            "position_noise": self.get_parameter("position_noise").value,
            "confidence": self.get_parameter("confidence").value,
        }
        self._detector = ObjectDetector(config)

        self._publisher = self.create_publisher(
            ObjectPose, "/perception/object_poses", 10
        )

        rate = self.get_parameter("publish_rate").value
        self._timer = self.create_timer(1.0 / rate, self._publish_detections)

        self.get_logger().info("PerceptionNode started")

    def register_object(
        self,
        object_id: str,
        object_type: str,
        position: list[float],
        orientation: list[float] | None = None,
    ) -> None:
        """Register an object for detection.

        Args:
            object_id: Object ID.
            object_type: Object type.
            position: Position [x, y, z].
            orientation: Orientation [qx, qy, qz, qw].

        """
        self._detector.register_object(object_id, object_type, position, orientation)
        self.get_logger().info(f"Registered object: {object_id} ({object_type})")

    def _publish_detections(self) -> None:
        """Publish detected object poses."""
        detections = self._detector.detect()
        for det in detections:
            msg = ObjectPose()
            msg.object_id = det.object_id
            msg.object_type = det.object_type
            msg.position = det.position
            msg.orientation = det.orientation
            msg.confidence = det.confidence
            self._publisher.publish(msg)

    def load_objects_from_yaml(self, yaml_path: str) -> None:
        """Load object definitions from YAML.

        Args:
            yaml_path: Path to objects YAML file.

        """
        with open(yaml_path) as f:
            data = yaml.safe_load(f)

        for obj in data.get("objects", []):
            self.register_object(
                object_id=obj["id"],
                object_type=obj.get("type", "unknown"),
                position=obj.get("position", [0, 0, 0]),
                orientation=obj.get("orientation", [0, 0, 0, 1]),
            )


def main(args: list[str] | None = None) -> None:
    """Entry point for perception node.

    Args:
        args: Command line arguments.

    """
    rclpy.init(args=args)
    node = PerceptionNode()

    try:
        from ament_index_python.packages import get_package_share_directory
        share_dir = get_package_share_directory("multi_arm_perception")
        from pathlib import Path
        config_path = str(Path(share_dir) / "config" / "perception_config.yaml")
        node.load_objects_from_yaml(config_path)
    except Exception as e:
        node.get_logger().warn(f"Could not load config: {e}")

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main(sys.argv)