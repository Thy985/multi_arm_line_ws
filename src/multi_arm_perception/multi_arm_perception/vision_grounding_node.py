"""Vision Grounding Node — simulates vision-based object detection.

Subscribes to Gazebo ground truth poses and adds configurable noise
to simulate real vision detection. Publishes to /perception/vision_poses
with source="vision" and confidence < 1.0.

In production, this would be replaced by YOLOv8 or similar detector
that processes head_camera/image_raw. In simulation, we use Gazebo GT
+ noise as a proxy.

Usage:
    ros2 run multi_arm_perception vision_grounding_node \
        --ros-args -p object_ids:=red_cube,blue_cylinder \
                   -p object_types:=cube,cylinder \
                   -p position_noise:=0.02 \
                   -p confidence:=0.85
"""

from __future__ import annotations

import random
from typing import Any

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Pose
from multi_arm_interfaces.msg import ObjectPose


class VisionGroundingNode(Node):
    """ROS2 node that simulates vision-based object detection.

    Subscribes to Gazebo bridged pose topics, adds Gaussian noise,
    and publishes as ObjectPose with source="vision".

    Attributes:
        _object_ids: List of object IDs to detect.
        _object_types: List of object types.
        _position_noise: Gaussian noise std-dev in meters.
        _confidence: Detection confidence (0.0-1.0).
    """

    def __init__(self) -> None:
        super().__init__("vision_grounding_node")

        object_ids_str = self.declare_parameter(
            "object_ids", "red_cube"
        ).value

        object_types_str = self.declare_parameter(
            "object_types", "cube"
        ).value

        self._object_ids = [
            s.strip() for s in str(object_ids_str).split(",") if s.strip()
        ]
        self._object_types = [
            s.strip() for s in str(object_types_str).split(",") if s.strip()
        ]

        while len(self._object_types) < len(self._object_ids):
            self._object_types.append("unknown")

        self._position_noise = self.declare_parameter(
            "position_noise", 0.02
        ).value

        self._confidence = self.declare_parameter(
            "confidence", 0.85
        ).value

        self._publisher = self.create_publisher(
            ObjectPose,
            "/perception/vision_poses",
            10,
        )

        self._latest_poses: dict[str, Pose | None] = {}

        for oid in self._object_ids:
            topic = f"/model/{oid}/pose"
            self._latest_poses[oid] = None
            self.create_subscription(
                Pose,
                topic,
                lambda msg, obj_id=oid: self._pose_callback(msg, obj_id),
                10,
            )

        publish_rate = self.declare_parameter("publish_rate", 10.0).value
        period = 1.0 / publish_rate if publish_rate > 0 else 0.1
        self._timer = self.create_timer(period, self._timer_callback)

        self.get_logger().info(
            f"VisionGroundingNode: {len(self._object_ids)} objects, "
            f"noise={self._position_noise}m, confidence={self._confidence}"
        )

    def _pose_callback(self, msg: Pose, object_id: str) -> None:
        self._latest_poses[object_id] = msg

    def _timer_callback(self) -> None:
        for i, oid in enumerate(self._object_ids):
            pose = self._latest_poses.get(oid)
            if pose is None:
                continue

            msg = ObjectPose()
            msg.object_id = oid
            msg.object_type = self._object_types[i]

            noise = self._position_noise
            msg.position = [
                pose.position.x + random.gauss(0, noise),
                pose.position.y + random.gauss(0, noise),
                pose.position.z + random.gauss(0, noise),
            ]
            msg.orientation = [
                pose.orientation.x,
                pose.orientation.y,
                pose.orientation.z,
                pose.orientation.w,
            ]
            msg.confidence = self._confidence
            msg.source = "vision"

            self._publisher.publish(msg)


def main(args: Any = None) -> None:
    rclpy.init(args=args)
    node = VisionGroundingNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()