"""Runtime watcher — terminal real-time dashboard (like htop for robots)."""

import sys
import time
from typing import Any

import rclpy
from rclpy.node import Node

from sensor_msgs.msg import JointState


class Watcher:
    """Real-time terminal dashboard for robot runtime monitoring."""

    REFRESH_INTERVAL = 0.5

    def __init__(self, duration: float = 0.0) -> None:
        """Initialize watcher.

        Args:
            duration: Watch duration in seconds (0 = infinite until Ctrl+C)
        """
        self._duration = duration
        self._node: Node | None = None
        self._joint_states: dict[str, JointState] = {}
        self._running = True

    def watch(self) -> None:
        """Start real-time monitoring dashboard."""
        rclpy.init()
        self._node = Node("robot_watcher")
        self._node.create_subscription(
            JointState,
            "/joint_states",
            self._on_joint_states,
            10,
        )

        start_time = time.time()
        try:
            while self._running:
                elapsed = time.time() - start_time
                if self._duration > 0 and elapsed >= self._duration:
                    break
                self._render_dashboard(elapsed)
                rclpy.spin_once(self._node, timeout_sec=self.REFRESH_INTERVAL)
        except KeyboardInterrupt:
            pass
        finally:
            self._node.destroy_node()
            rclpy.shutdown()
            print("\nWatch stopped.")

    def _on_joint_states(self, msg: JointState) -> None:
        """JointState callback."""
        frame_id = msg.name[0].split("/")[0] if msg.name else "default"
        self._joint_states[frame_id] = msg

    def _render_dashboard(self, elapsed: float) -> None:
        """Render the dashboard."""
        sys.stdout.write("\033[2J\033[H")
        print("=== Robot Runtime Monitor ===")
        print(f"  Uptime: {elapsed:.1f}s  |  Press Ctrl+C to stop")
        print()

        if self._joint_states:
            print("  Robot State:")
            for arm_name, js_msg in sorted(self._joint_states.items()):
                print(f"    {arm_name}:")
                for i, (name, pos) in enumerate(
                    zip(js_msg.name, js_msg.position)
                ):
                    joint = name.split("/")[-1] if "/" in name else name
                    degrees = pos * 57.2958
                    bar = self._make_bar(degrees, -180, 180)
                    print(f"      {joint:<20} {degrees:>7.1f}deg {bar}")
            print()
        else:
            print("  Robot State: (waiting for /joint_states...)")
            print()

        print("  Legend: [#####-----] joint angle (-180 to +180)")
        print()

    @staticmethod
    def _make_bar(value: float, min_val: float, max_val: float) -> str:
        """Make a progress bar string."""
        range_val = max_val - min_val
        if range_val == 0:
            normalized = 0.5
        else:
            normalized = (value - min_val) / range_val
        normalized = max(0.0, min(1.0, normalized))
        filled = int(normalized * 10)
        return "[" + "#" * filled + "-" * (10 - filled) + "]"