"""Ground Truth Node — extract exact poses from Gazebo simulation."""

from __future__ import annotations

import sys

import rclpy
from rclpy.node import Node
from multi_arm_interfaces.msg import ObjectPose

from .perception_node import ObjectDetector, DetectedObject


class GroundTruthNode(Node):
    """ROS2 node for Gazebo ground truth extraction.

    In simulation, this provides perfect object poses.
    In real robot, this node is not used (replaced by perception_node).
    """

    def __init__(self) -> None:
        """Initialize ground truth node."""
        super().__init__("ground_truth_node")

        self.declare_parameter("publish_rate", 30.0)

        self._detector = ObjectDetector({"position_noise": 0.0, "confidence": 1.0})

        self._publisher = self.create_publisher(
            ObjectPose, "/perception/object_poses", 10
        )

        rate = self.get_parameter("publish_rate").value
        self._timer = self.create_timer(1.0 / rate, self._publish_ground_truth)

        self.get_logger().info("GroundTruthNode started (perfect poses)")

    def register_object(
        self,
        object_id: str,
        object_type: str,
        position: list[float],
        orientation: list[float] | None = None,
    ) -> None:
        """Register an object for ground truth.

        Args:
            object_id: Object ID.
            object_type: Object type.
            position: Position [x, y, z].
            orientation: Orientation [qx, qy, qz, qw].

        """
        self._detector.register_object(object_id, object_type, position, orientation)

    def _publish_ground_truth(self) -> None:
        """Publish ground truth object poses."""
        detections = self._detector.detect()
        for det in detections:
            msg = ObjectPose()
            msg.object_id = det.object_id
            msg.object_type = det.object_type
            msg.position = det.position
            msg.orientation = det.orientation
            msg.confidence = det.confidence
            self._publisher.publish(msg)


def main(args: list[str] | None = None) -> None:
    """Entry point for ground truth node.

    Args:
        args: Command line arguments.

    """
    rclpy.init(args=args)
    node = GroundTruthNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main(sys.argv)