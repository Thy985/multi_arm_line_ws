"""Synthetic Camera Node — generates camera images from ground truth poses.

In headless environments without GPU, Gazebo's ogre2 rendering engine cannot
generate camera sensor data. This node creates synthetic camera images by
projecting known object positions into a 2D image, simulating what a real
camera would see.

The synthetic image is a valid camera image (BGR8, 1280x720) with colored
objects rendered at their projected positions. ColorDetectorNode processes
this image through the full OpenCV pipeline (HSV → contour → pose).

This tests the real perception pipeline (image → detection → pose) without
requiring GPU rendering.

Pipeline:
    Gazebo Pose → 3D→2D projection → draw colored rectangle → Image
    → /head/rgb/image_raw/image → ColorDetectorNode → ObjectPose
"""

from __future__ import annotations

import math
from typing import Any

import cv2
import numpy as np
import rclpy
from geometry_msgs.msg import Pose as PoseMsg
from rclpy.node import Node
from sensor_msgs.msg import Image


COLOR_BGR = {
    "red": (0, 0, 255),
    "blue": (255, 0, 0),
    "green": (0, 255, 0),
}

OBJECT_SIZES = {
    "cube": (0.05, 0.05),
    "cylinder": (0.06, 0.06),
    "box": (0.05, 0.05),
}


class SyntheticCameraNode(Node):
    """ROS2 node that generates synthetic camera images from object poses.

    Subscribes to Gazebo pose topics, projects 3D positions to 2D pixel
    coordinates, draws colored objects on a blank image, publishes as Image.

    Attributes:
        _camera_x/y/z: Camera position in world frame.
        _fx, _fy, _cx, _cy: Camera intrinsics (pinhole model).
        _img_width, _img_height: Image dimensions.
        _objects: List of (id, type, color, pose_topic) tuples.
        _poses: Current poses keyed by object_id.
    """

    def __init__(self) -> None:
        super().__init__("synthetic_camera_node")

        self._camera_x = self.declare_parameter("camera_x", 0.56).value
        self._camera_y = self.declare_parameter("camera_y", 0.0).value
        self._camera_z = self.declare_parameter("camera_z", 0.9).value

        self._img_width = self.declare_parameter("image_width", 1280).value
        self._img_height = self.declare_parameter("image_height", 720).value
        fov = self.declare_parameter("fov", 1.5708).value

        self._fx = (self._img_width / 2.0) / math.tan(fov / 2.0)
        self._fy = self._fx
        self._cx = self._img_width / 2.0
        self._cy = self._img_height / 2.0

        objects_str = self.declare_parameter(
            "objects", "red_cube:cube:red,blue_cylinder:cylinder:blue"
        ).value
        self._objects = self._parse_objects(str(objects_str))

        self._poses: dict[str, tuple[float, float, float]] = {
            "red_cube": (0.5, 0.0, 0.435),
            "blue_cylinder": (0.3, 0.2, 0.44),
        }
        self._use_gazebo_poses = False

        image_topic = self.declare_parameter(
            "image_topic", "/head/rgb/image_raw/image"
        ).value
        publish_rate = self.declare_parameter("publish_rate", 10.0).value

        self._publisher = self.create_publisher(Image, str(image_topic), 10)

        for obj in self._objects:
            pose_topic = f"/model/{obj['id']}/pose"
            self.create_subscription(
                PoseMsg, pose_topic,
                lambda msg, oid=obj["id"]: self._on_pose(msg, oid),
                10,
            )

        self.create_timer(1.0 / publish_rate, self._publish_image)

        self.get_logger().info(
            f"SyntheticCameraNode: {len(self._objects)} objects, "
            f"topic={image_topic}, {self._img_width}x{self._img_height}"
        )

    def _parse_objects(self, s: str) -> list[dict[str, str]]:
        result = []
        for entry in s.split(","):
            parts = entry.strip().split(":")
            if len(parts) >= 3:
                result.append({
                    "id": parts[0].strip(),
                    "type": parts[1].strip(),
                    "color": parts[2].strip(),
                })
        return result

    def _on_pose(self, msg: PoseMsg, object_id: str) -> None:
        """Store object pose from Gazebo."""
        self._poses[object_id] = (
            msg.position.x,
            msg.position.y,
            msg.position.z,
        )
        self._use_gazebo_poses = True

    def _project_3d_to_2d(
        self, x: float, y: float, z: float
    ) -> tuple[float, float] | None:
        """Project 3D world position to 2D pixel coordinates.

        Camera at (cam_x, cam_y, cam_z) looking along +x axis.
        """
        dx = x - self._camera_x
        dy = y - self._camera_y
        dz = z - self._camera_z

        if dx <= 0.1:
            return None

        u = self._fx * dy / dx + self._cx
        v = -self._fy * dz / dx + self._cy

        if 0 <= u < self._img_width and 0 <= v < self._img_height:
            return (u, v)
        return None

    def _publish_image(self) -> None:
        """Generate and publish synthetic camera image."""
        img = np.zeros(
            (self._img_height, self._img_width, 3), dtype=np.uint8
        )
        img[:] = (200, 200, 200)

        cv2.rectangle(img, (0, int(self._cy)), (self._img_width, self._img_height),
                      (100, 100, 100), -1)

        for obj in self._objects:
            oid = obj["id"]
            if oid not in self._poses:
                continue

            x, y, z = self._poses[oid]
            pixel = self._project_3d_to_2d(x, y, z)
            if pixel is None:
                continue

            u, v = int(pixel[0]), int(pixel[1])
            color = COLOR_BGR.get(obj["color"], (0, 0, 0))
            size = OBJECT_SIZES.get(obj["type"], (0.05, 0.05))

            dx = x - self._camera_x
            pixel_w = max(10, int(self._fx * size[0] / dx))
            pixel_h = max(10, int(self._fy * size[1] / dx))

            x1 = max(0, u - pixel_w // 2)
            y1 = max(0, v - pixel_h // 2)
            x2 = min(self._img_width, u + pixel_w // 2)
            y2 = min(self._img_height, v + pixel_h // 2)

            cv2.rectangle(img, (x1, y1), (x2, y2), color, -1)

        msg = Image()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = "head_rgb_link"
        msg.height = self._img_height
        msg.width = self._img_width
        msg.encoding = "bgr8"
        msg.step = self._img_width * 3
        msg.data = img.tobytes()

        self._publisher.publish(msg)

    @property
    def stats(self) -> str:
        return f"objects_tracked={len(self._poses)}"


def main(args: Any = None) -> None:
    rclpy.init(args=args)
    node = SyntheticCameraNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()