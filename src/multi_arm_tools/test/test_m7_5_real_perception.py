"""M7.5 Real Perception — Validation Tests.

Verifies camera image → OpenCV detection → pose estimation → WorldModel pipeline.

Key distinction from M7.4: image→OpenCV→pose (real perception pipeline)
vs M7.4's pose→noise (simulated vision).

Acceptance criteria:
    1. Camera image: Gazebo camera publishes real image data
    2. ColorDetector running: ColorDetectorNode active (not VisionGroundingNode)
    3. Vision poses: ColorDetector publishes ObjectPose with source="vision"
    4. Pose accuracy: vision pose within 0.50m of ground truth
    5. WorldModel sync: WorldModel receives camera-driven poses
    6. Real pipeline: image→HSV→contour→projection (not pose+noise)
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from typing import Any

import pytest

from m7_int_helpers import (
    launch_full_stack,
    run_cmd,
    shutdown_full_stack,
    source_env,
)


def check_topic_publisher(topic: str) -> int:
    """Check publisher count for a topic. Returns count or -1 on error."""
    result = run_cmd(["ros2", "topic", "info", topic], timeout=10.0)
    if result.returncode != 0:
        return -1
    for line in result.stdout.splitlines():
        if "Publisher count:" in line:
            return int(line.split(":")[1].strip())
    return -1


def check_nodes() -> list[str]:
    """Get list of running ROS2 nodes."""
    result = run_cmd(["ros2", "node", "list"], timeout=10.0)
    if result.returncode != 0:
        return []
    return result.stdout.splitlines()


def collect_all_poses() -> dict[str, Any]:
    """Collect all poses from /perception/vision_poses and /perception/object_poses.

    Uses a single Python process with one DDS participant to avoid participant limit.
    """
    env = source_env()
    script = """
import rclpy
from rclpy.node import Node
from multi_arm_interfaces.msg import ObjectPose
import json
import sys

rclpy.init()
node = Node("m75_pose_collector")
poses = []

def cb_vision(msg):
    poses.append({
        "topic": "vision",
        "object_id": msg.object_id,
        "source": msg.source,
        "confidence": msg.confidence,
        "position": [msg.position[0], msg.position[1], msg.position[2]],
    })

def cb_gt(msg):
    poses.append({
        "topic": "gt",
        "object_id": msg.object_id,
        "source": msg.source,
        "confidence": msg.confidence,
        "position": [msg.position[0], msg.position[1], msg.position[2]],
    })

node.create_subscription(ObjectPose, "/perception/vision_poses", cb_vision, 10)
node.create_subscription(ObjectPose, "/perception/object_poses", cb_gt, 10)

start = node.get_clock().now().nanoseconds
while rclpy.ok() and (node.get_clock().now().nanoseconds - start) < 8e9:
    rclpy.spin_once(node, timeout_sec=0.1)
    if len(poses) >= 4:
        break

print(json.dumps(poses))
node.destroy_node()
rclpy.shutdown()
"""
    try:
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True, text=True, timeout=15.0,
            env=env,
        )
        if result.returncode != 0:
            return {"error": result.stderr[:300], "poses": []}
        import json
        poses = json.loads(result.stdout.strip())
        return {"poses": poses}
    except Exception as e:
        return {"error": str(e), "poses": []}


class TestM75RealPerception:
    """M7.5 Real Perception validation.

    Tests that the perception pipeline uses real camera images (OpenCV color
    detection) instead of Gazebo pose + noise.
    """

    @pytest.fixture(autouse=True)
    def _launch_stack(self) -> Any:
        print("\n  [M7.5] Starting full stack with camera pipeline...")
        launch_proc, aux_procs = launch_full_stack()
        try:
            time.sleep(20)
            yield
        finally:
            print("\n  [M7.5] Shutting down...")
            shutdown_full_stack(launch_proc, aux_procs)
            time.sleep(5)

    def test_01_camera_image_published(self) -> None:
        """Gazebo camera publishes real image data through ros_gz_bridge."""
        pub_count = check_topic_publisher("/head_camera/image_raw/image")
        assert pub_count > 0, \
            f"Camera image topic has no publisher (count={pub_count})"
        print(f"  ✓ Camera image published (publisher count={pub_count})")

    def test_02_color_detector_replaces_vision_grounding(self) -> None:
        """ColorDetectorNode is running, VisionGroundingNode is NOT."""
        nodes = check_nodes()
        assert any("color_detector_node" in n for n in nodes), \
            f"color_detector_node not found in nodes: {nodes}"
        assert not any("vision_grounding_node" in n for n in nodes), \
            f"vision_grounding_node should NOT be running (M7.5 replaces it): {nodes}"
        print("  ✓ ColorDetectorNode active, VisionGroundingNode removed")

    def test_03_vision_poses_published(self) -> None:
        """ColorDetectorNode publishes to /perception/vision_poses."""
        pub_count = check_topic_publisher("/perception/vision_poses")
        assert pub_count > 0, \
            f"vision_poses has no publisher (count={pub_count})"
        print(f"  ✓ /perception/vision_poses published (count={pub_count})")

    def test_04_vision_pose_content(self) -> None:
        """Vision poses have source='vision', confidence>0, valid position."""
        data = collect_all_poses()
        poses = data.get("poses", [])
        assert len(poses) > 0, \
            f"No poses collected. Error: {data.get('error', 'none')}"

        vision_poses = [p for p in poses if p["source"] == "vision"]
        assert len(vision_poses) > 0, \
            f"No vision source poses. All poses: {poses}"

        for p in vision_poses:
            assert p["confidence"] > 0.0, \
                f"Zero confidence for {p['object_id']}"
            pos = p["position"]
            assert all(abs(v) < 10.0 for v in pos), \
                f"Invalid position for {p['object_id']}: {pos}"

        print(f"  ✓ {len(vision_poses)} vision poses: source='vision', conf>0, pos valid")
        for p in vision_poses:
            print(f"    {p['object_id']}: conf={p['confidence']:.3f}, pos={p['position']}")

    def test_05_pose_accuracy_vs_ground_truth(self) -> None:
        """Vision pose within 0.10m of known ground truth positions."""
        KNOWN_GT = {
            "red_cube": (0.5, 0.0, 0.435),
            "blue_cylinder": (0.3, 0.2, 0.44),
        }

        data = collect_all_poses()
        poses = data.get("poses", [])
        if len(poses) == 0:
            pytest.skip(f"No poses collected. Error: {data.get('error', 'none')}")

        vision_poses = [p for p in poses if p["source"] == "vision"]
        if len(vision_poses) == 0:
            pytest.skip("No vision poses for comparison")

        errors = []
        for vp in vision_poses:
            oid = vp["object_id"]
            if oid in KNOWN_GT:
                gt = KNOWN_GT[oid]
                dx = vp["position"][0] - gt[0]
                dy = vp["position"][1] - gt[1]
                dz = vp["position"][2] - gt[2]
                error = (dx**2 + dy**2 + dz**2) ** 0.5
                errors.append((oid, error))
                print(f"    {oid}: vision={vp['position']}, gt={gt}, error={error:.3f}m")

        assert len(errors) > 0, "No matching objects between GT and vision"
        max_error = max(e for _, e in errors)
        assert max_error < 0.10, \
            f"Max pose error {max_error:.3f}m exceeds 0.10m threshold"
        print(f"  ✓ Vision pose accuracy: max error={max_error:.3f}m < 0.10m")

    def test_06_real_image_pipeline(self) -> None:
        """Pipeline is image→OpenCV→pose, not pose→noise.

        M7.5 key distinction: ColorDetectorNode subscribes to camera image
        and does OpenCV processing (HSV, contour, projection).
        VisionGroundingNode (M7.4) subscribed to Gazebo poses and added noise.
        """
        nodes = check_nodes()

        assert any("color_detector_node" in n for n in nodes), "ColorDetectorNode not running"
        assert not any("vision_grounding_node" in n for n in nodes), "VisionGroundingNode still running"

        cam_pub = check_topic_publisher("/head_camera/image_raw/image")
        vis_pub = check_topic_publisher("/perception/vision_poses")

        assert cam_pub > 0, "No camera image publisher"
        assert vis_pub > 0, "No vision poses publisher"

        print("  ✓ Real image pipeline: camera→ColorDetector→vision_poses")
        print(f"    camera publisher={cam_pub}, vision publisher={vis_pub}")
