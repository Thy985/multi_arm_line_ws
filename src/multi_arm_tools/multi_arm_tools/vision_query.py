"""Vision query module — display perception layer state.

Distinct from WorldQuery: Vision shows what the sensor currently sees,
WorldModel shows what the robot currently believes about the world.
"""

import json
import time
from typing import Any

import rclpy
from rclpy.node import Node

from multi_arm_interfaces.msg import ObjectPose


class VisionQuery:
    """Terminal viewer for vision/perception state."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def print_status(self, json_output: bool = False) -> dict[str, Any]:
        """Print vision pipeline status.

        Returns dict for --json mode.
        """
        poses = self._collect_vision_poses(duration=3.0)

        camera_pub = self._check_topic("/head_camera/image_raw/image")
        vision_pub = self._check_topic("/perception/vision_poses")

        high_conf = [p for p in poses if p["confidence"] >= 0.8]
        uncertain = [p for p in poses if 0.3 <= p["confidence"] < 0.8]
        rejected = [p for p in poses if p["confidence"] < 0.3]

        status_data = {
            "camera": {
                "topic": "/head_camera/image_raw/image",
                "publisher_count": camera_pub,
                "active": camera_pub > 0,
            },
            "detector": {
                "topic": "/perception/vision_poses",
                "publisher_count": vision_pub,
                "active": vision_pub > 0,
            },
            "objects": poses,
            "quality": {
                "high_confidence": len(high_conf),
                "uncertain": len(uncertain),
                "rejected": len(rejected),
            },
        }

        if json_output:
            return status_data

        print("\nVISION STATUS")
        print("-" * 40)
        print()
        print("Camera")
        print(f"  topic:    /head_camera/image_raw/image")
        print(f"  status:   {'● ACTIVE' if camera_pub > 0 else '○ INACTIVE'}")
        print()
        print("Detector")
        print(f"  topic:    /perception/vision_poses")
        print(f"  status:   {'● READY' if vision_pub > 0 else '○ OFFLINE'}")
        print()

        if poses:
            print("Objects")
            for p in poses:
                print(f"  {p['object_id']:<20} conf={p['confidence']:.2f}")
            print()

        print("Quality")
        print(f"  high confidence    {len(high_conf)}")
        print(f"  uncertain          {len(uncertain)}")
        print(f"  rejected           {len(rejected)}")
        print()

        return status_data

    def print_objects(self, json_output: bool = False) -> dict[str, Any]:
        """Print detected objects from vision only."""
        poses = self._collect_vision_poses(duration=3.0)

        if json_output:
            return {"objects": poses}

        if not poses:
            print("No vision detections.")
            return {"objects": []}

        print("\nVISION DETECTIONS")
        print("-" * 60)
        print()
        print(f"{'OBJECT':<20} {'POSITION':<30} {'CONF':<8} {'SOURCE'}")
        for p in poses:
            pos_str = f"({p['position'][0]:.2f}, {p['position'][1]:.2f}, {p['position'][2]:.2f})"
            print(f"  {p['object_id']:<18} {pos_str:<30} {p['confidence']:<8.2f} {p.get('source', 'vision')}")
        print()

        return {"objects": poses}

    @staticmethod
    def _check_topic(topic: str) -> int:
        """Check publisher count for a topic."""
        import subprocess
        try:
            result = subprocess.run(
                ["ros2", "topic", "info", topic],
                capture_output=True, text=True, timeout=5.0,
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if "Publisher count:" in line:
                        return int(line.split(":")[1].strip())
        except Exception:
            pass
        return 0

    @staticmethod
    def _collect_vision_poses(duration: float = 3.0) -> list[dict[str, Any]]:
        """Collect vision poses from /perception/vision_poses."""
        import subprocess
        import sys

        script = """
import rclpy
from rclpy.node import Node
from multi_arm_interfaces.msg import ObjectPose
import json

rclpy.init()
node = Node("vision_collector")
poses = []

def cb(msg):
    poses.append({
        "object_id": msg.object_id,
        "object_type": msg.object_type,
        "position": [msg.position[0], msg.position[1], msg.position[2]],
        "confidence": msg.confidence,
        "source": msg.source if msg.source else "vision",
    })

node.create_subscription(ObjectPose, "/perception/vision_poses", cb, 10)

start = node.get_clock().now().nanoseconds
while rclpy.ok() and (node.get_clock().now().nanoseconds - start) < {dur}e9:
    rclpy.spin_once(node, timeout_sec=0.1)

seen = {{}}
for p in poses:
    seen[p["object_id"]] = p
print(json.dumps(list(seen.values())))
node.destroy_node()
rclpy.shutdown()
""".replace("{dur}", str(duration)).replace("{{}}", "{}")

        try:
            result = subprocess.run(
                [sys.executable, "-c", script],
                capture_output=True, text=True, timeout=duration + 5.0,
            )
            if result.returncode == 0 and result.stdout.strip():
                return json.loads(result.stdout.strip())
        except Exception:
            pass
        return []