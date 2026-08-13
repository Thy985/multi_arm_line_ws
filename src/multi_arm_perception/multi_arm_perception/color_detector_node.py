"""Color Detector Node — real camera image → object detection → 6DoF pose.

Subscribes to head_camera/image_raw, detects colored objects using OpenCV,
estimates 3D pose via ground plane projection, publishes ObjectPose.

This replaces the GazeboGroundTruthNode + VisionGroundingNode pipeline
with a real camera-driven perception pipeline (M7.5).

Pipeline:
    Camera Image → HSV color filter → contour detection
    → centroid (u,v) → ground plane projection → 3D pose
    → ObjectPose(source="vision") → /perception/vision_poses

Usage:
    ros2 run multi_arm_perception color_detector_node \
        --ros-args -p objects:=red_cube:cube:red,blue_cylinder:cylinder:blue
"""

from __future__ import annotations

import time
from typing import Any

import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
from multi_arm_interfaces.msg import ObjectPose

COLOR_RANGES = {
    "red": [
        (np.array([0, 80, 80]), np.array([10, 255, 255])),
        (np.array([170, 80, 80]), np.array([180, 255, 255])),
    ],
    "blue": [
        (np.array([100, 80, 80]), np.array([130, 255, 255])),
    ],
    "green": [
        (np.array([40, 80, 80]), np.array([80, 255, 255])),
    ],
}


class ColorDetectorNode(Node):
    """ROS2 node that detects colored objects from camera images.

    Subscribes to camera image, detects objects by color, estimates
    3D pose via ground plane projection, publishes ObjectPose.

    Attributes:
        _bridge: cv_bridge converter.
        _camera_x/y/z: Camera position in world frame.
        _fx, _fy, _cx, _cy: Camera intrinsics.
        _ground_z: Ground plane height.
    """

    def __init__(self) -> None:
        super().__init__("color_detector_node")

        self._bridge = CvBridge()

        objects_str = self.declare_parameter(
            "objects", "red_cube:cube:red,blue_cylinder:cylinder:blue"
        ).value
        self._objects = self._parse_objects(str(objects_str))

        self._camera_x = self.declare_parameter("camera_x", 0.56).value
        self._camera_y = self.declare_parameter("camera_y", 0.0).value
        self._camera_z = self.declare_parameter("camera_z", 0.9).value
        self._ground_z = self.declare_parameter("ground_z", 0.05).value

        img_width = self.declare_parameter("image_width", 1280).value
        img_height = self.declare_parameter("image_height", 720).value
        fov = self.declare_parameter("fov", 1.5708).value

        self._fx = (img_width / 2.0) / np.tan(fov / 2.0)
        self._fy = self._fx
        self._cx = img_width / 2.0
        self._cy = img_height / 2.0

        image_topic = self.declare_parameter(
            "image_topic", "/head_camera/image_raw"
        ).value

        self._publisher = self.create_publisher(
            ObjectPose, "/perception/vision_poses", 10
        )

        self._image_count = 0
        self._detection_count = 0

        self.create_subscription(
            Image, str(image_topic), self._on_image, 10
        )

        self.get_logger().info(
            f"ColorDetectorNode: {len(self._objects)} objects, "
            f"topic={image_topic}, fx={self._fx:.0f}"
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

    def _on_image(self, msg: Image) -> None:
        """Process camera image and detect objects."""
        self._image_count += 1

        try:
            cv_image = self._bridge.imgmsg_to_cv2(msg, "bgr8")
        except Exception as e:
            return

        hsv = cv2.cvtColor(cv_image, cv2.COLOR_BGR2HSV)

        for obj in self._objects:
            pose = self._detect_object(hsv, obj, msg.width, msg.height)
            if pose is not None:
                self._publisher.publish(pose)
                self._detection_count += 1

    def _detect_object(
        self, hsv: np.ndarray, obj: dict, width: int, height: int
    ) -> ObjectPose | None:
        """Detect object by color and estimate 3D pose."""
        color = obj["color"]
        if color not in COLOR_RANGES:
            return None

        mask = np.zeros(hsv.shape[:2], dtype=np.uint8)
        for lower, upper in COLOR_RANGES[color]:
            mask |= cv2.inRange(hsv, lower, upper)

        kernel = np.ones((5, 5), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

        contours, _ = cv2.findContours(
            mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        if not contours:
            return None

        largest = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(largest)
        if area < 100:
            return None

        m = cv2.moments(largest)
        if m["m00"] == 0:
            return None

        u = m["m10"] / m["m00"]
        v = m["m01"] / m["m00"]

        confidence = min(0.95, area / 5000.0)

        position = self._pixel_to_3d(u, v)
        if position is None:
            return None

        pose = ObjectPose()
        pose.object_id = obj["id"]
        pose.object_type = obj["type"]
        pose.position = [position[0], position[1], position[2]]
        pose.orientation = [0.0, 0.0, 0.0, 1.0]
        pose.confidence = float(confidence)
        pose.source = "vision"
        return pose

    def _pixel_to_3d(self, u: float, v: float) -> tuple[float, float, float] | None:
        """Project pixel to 3D world position via ground plane intersection.

        Camera at (cam_x, cam_y, cam_z) looking along x-axis.
        Ground plane at z = ground_z.
        """
        if v <= self._cy:
            return None

        ray_y = (u - self._cx) / self._fx
        ray_z = -(v - self._cy) / self._fy

        t = (self._camera_z - self._ground_z) / abs(ray_z)

        x = self._camera_x + t
        y = self._camera_y + t * ray_y
        z = self._ground_z

        return (x, y, z)

    @property
    def stats(self) -> str:
        return f"images={self._image_count}, detections={self._detection_count}"


def main(args: Any = None) -> None:
    rclpy.init(args=args)
    node = ColorDetectorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()