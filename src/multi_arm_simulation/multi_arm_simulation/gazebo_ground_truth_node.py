"""Gazebo Ground Truth Node — extracts object poses from Gazebo simulation.

Subscribes to ROS2 topics bridged from Gazebo PosePublisher plugin
and republishes as ObjectPose messages to /perception/object_poses.

This replaces the placeholder PerceptionNode for simulation E2E.
In production (real robot), this would be replaced by YOLOv8 or similar.

Bridge setup (in launch file):
    /model/<model_name>/pose @ geometry_msgs/msg/Pose [gz.msgs.Pose

Usage:
    ros2 run multi_arm_simulation gazebo_ground_truth_node \
        --ros-args -p object_ids:=red_cube,blue_cylinder \
                   -p object_types:=cube,cylinder
"""

from __future__ import annotations

from typing import Any

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Pose
from multi_arm_interfaces.msg import ObjectPose


class GazeboGroundTruthNode(Node):
    """ROS2 node that publishes ground truth object poses from Gazebo.

    Subscribes to bridged pose topics (/model/<name>/pose) and
    republishes as ObjectPose messages to /perception/object_poses.

    Attributes:
        _world_name: Gazebo world name.
        _object_ids: List of object IDs to track.
        _object_types: List of object types.
    """

    def __init__(self) -> None:
        """Initialize ground truth node."""
        super().__init__("gazebo_ground_truth_node")

        self._world_name = self.declare_parameter(
            "world_name", "m6_test_world"
        ).value

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

        self._publisher = self.create_publisher(
            ObjectPose,
            "/perception/object_poses",
            10,
        )

        self._pose_subscriptions: dict[str, Any] = {}
        self._latest_poses: dict[str, Pose | None] = {}

        for i, oid in enumerate(self._object_ids):
            topic = f"/model/{oid}/pose"
            self._latest_poses[oid] = None

            sub = self.create_subscription(
                Pose,
                topic,
                lambda msg, obj_id=oid: self._pose_callback(msg, obj_id),
                10,
            )
            self._pose_subscriptions[oid] = sub
            self.get_logger().info(
                f"Tracking {oid} ({self._object_types[i]}) on {topic}"
            )

        publish_rate = self.declare_parameter("publish_rate", 10.0).value
        period = 1.0 / publish_rate if publish_rate > 0 else 0.1
        self._timer = self.create_timer(period, self._timer_callback)

        self.get_logger().info(
            f"GazeboGroundTruthNode: {len(self._object_ids)} objects, "
            f"rate={publish_rate}Hz"
        )

    def _pose_callback(self, msg: Pose, object_id: str) -> None:
        """Store latest pose from bridged topic.

        Args:
            msg: Pose message from Gazebo bridge.
            object_id: Object identifier.

        """
        self._latest_poses[object_id] = msg

    def _timer_callback(self) -> None:
        """Publish all latest poses as ObjectPose messages."""
        for i, oid in enumerate(self._object_ids):
            pose = self._latest_poses.get(oid)
            if pose is None:
                continue

            msg = ObjectPose()
            msg.object_id = oid
            msg.object_type = self._object_types[i]
            msg.position = [
                pose.position.x,
                pose.position.y,
                pose.position.z,
            ]
            msg.orientation = [
                pose.orientation.x,
                pose.orientation.y,
                pose.orientation.z,
                pose.orientation.w,
            ]
            msg.confidence = 1.0

            self._publisher.publish(msg)

    @property
    def tracked_object_count(self) -> int:
        """Number of tracked objects."""
        return len(self._object_ids)

    @property
    def received_pose_count(self) -> int:
        """Number of objects with received poses."""
        return sum(1 for p in self._latest_poses.values() if p is not None)


def main(args: Any = None) -> None:
    """Entry point for gazebo_ground_truth_node."""
    rclpy.init(args=args)
    node = GazeboGroundTruthNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
