"""LED Status Node — binds status_led color to runtime state.

Phase 2.5: Subscribes to system health signals and publishes LED status
on /led/status (std_msgs/String). States:

    READY       — green  (all services available)
    RUNNING     — blue   (task in progress)
    FAILED      — red    (service unavailable)
    SAFETY_STOP — red flashing (emergency stop active)
"""

from __future__ import annotations

import rclpy
from rclpy.node import Node
from std_msgs.msg import String, ColorRGBA
from geometry_msgs.msg import Point
from multi_arm_interfaces.srv import SafetyCheck


LED_COLORS: dict[str, tuple[float, float, float]] = {
    "READY": (0.0, 0.8, 0.0),
    "RUNNING": (0.0, 0.0, 0.8),
    "FAILED": (0.8, 0.0, 0.0),
    "SAFETY_STOP": (0.8, 0.0, 0.0),
    "INITIALIZING": (0.8, 0.6, 0.0),
}

FLASH_STATES = {"SAFETY_STOP"}


class LedStatusNode(Node):
    """Monitor system health and publish LED status."""

    def __init__(self) -> None:
        super().__init__("led_status_node")

        self._state = "INITIALIZING"
        self._flash_on = True
        self._safety_available = False
        self._coordinator_available = False

        self._safety_client = self.create_client(
            SafetyCheck, "/safety/check"
        )

        self._status_pub = self.create_publisher(String, "/led/status", 10)
        self._color_pub = self.create_publisher(ColorRGBA, "/led/color", 10)

        check_period = self.declare_parameter("check_period", 1.0).value
        self._timer = self.create_timer(check_period, self._tick)

        self.get_logger().info("LED status node started")

    def _tick(self) -> None:
        """Check system health and update LED state."""
        self._check_services()
        new_state = self._determine_state()

        if new_state != self._state:
            self.get_logger().info(f"LED state: {self._state} -> {new_state}")
            self._state = new_state

        self._flash_on = not self._flash_on
        self._publish_status()

    def _check_services(self) -> None:
        """Probe service and action server availability."""
        self._safety_available = self._safety_client.service_is_ready()

        try:
            from rclpy.action import ActionClient
            from multi_arm_interfaces.action import ExecuteTask

            if not hasattr(self, "_coord_client"):
                self._coord_client = ActionClient(self, ExecuteTask, "/execute_task")
            self._coordinator_available = self._coord_client.wait_for_server(
                timeout_sec=0.1
            )
        except Exception:
            self._coordinator_available = False

    def _determine_state(self) -> str:
        """Determine LED state from service availability."""
        if not self._safety_available and not self._coordinator_available:
            return "INITIALIZING"
        if not self._safety_available or not self._coordinator_available:
            return "FAILED"
        return "READY"

    def _publish_status(self) -> None:
        """Publish LED status and color."""
        display_state = self._state
        if self._state in FLASH_STATES and not self._flash_on:
            display_state = "OFF"

        msg = String()
        msg.data = display_state
        self._status_pub.publish(msg)

        color = LED_COLORS.get(self._state, (0.1, 0.1, 0.1))
        if self._state in FLASH_STATES and not self._flash_on:
            color = (0.1, 0.1, 0.1)

        color_msg = ColorRGBA()
        color_msg.r = color[0]
        color_msg.g = color[1]
        color_msg.b = color[2]
        color_msg.a = 1.0
        self._color_pub.publish(color_msg)

    def destroy_node(self) -> bool:
        """Clean up action client."""
        if hasattr(self, "_coord_client"):
            self._coord_client.destroy()
        return super().destroy_node()


def main(args=None) -> None:
    """Entry point for led_status_node."""
    rclpy.init(args=args)
    node = LedStatusNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()