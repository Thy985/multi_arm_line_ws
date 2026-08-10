"""ROS2 node for dynamic Capability Registry."""

from __future__ import annotations

import sys
from pathlib import Path

import rclpy
from rclpy.node import Node
from ament_index_python.packages import get_package_share_directory

from multi_arm_interfaces.msg import CapabilityInfo
from multi_arm_interfaces.srv import GetCapability

from .capability_registry import CapabilityRegistry


class CapabilityRegistryNode(Node):
    """ROS2 node providing dynamic Capability Registry service.

    Provides:
        - /capability/get_capability (GetCapability.srv)
        - /capability/updates (CapabilityInfo topic)
    """

    def __init__(self) -> None:
        """Initialize capability registry node."""
        super().__init__("capability_registry_node")

        self.declare_parameter("capability_yaml", "")
        self.declare_parameter("publish_rate", 1.0)

        yaml_param = self.get_parameter("capability_yaml").value
        if yaml_param:
            yaml_path = yaml_param
        else:
            share_dir = get_package_share_directory("multi_arm_robot_description")
            yaml_path = str(Path(share_dir) / "config" / "capability.yaml")

        self._registry = CapabilityRegistry(yaml_path)
        self.get_logger().info(f"Loaded capabilities from: {yaml_path}")

        self._service = self.create_service(
            GetCapability, "/capability/get_capability", self._handle_get_capability
        )

        self._publisher = self.create_publisher(
            CapabilityInfo, "/capability/updates", 10
        )

        rate = self.get_parameter("publish_rate").value
        self._timer = self.create_timer(1.0 / rate, self._publish_capabilities)

        self.get_logger().info("CapabilityRegistryNode started")

    def _handle_get_capability(
        self,
        request: GetCapability.Request,
        response: GetCapability.Response,
    ) -> GetCapability.Response:
        """Handle GetCapability service request.

        Args:
            request: Service request with capability_name and include_dynamic.
            response: Service response.

        Returns:
            Filled service response.

        """
        name = request.capability_name
        include_dynamic = request.include_dynamic

        if name == "all" or name == "":
            infos = self._registry.get_all_capabilities(include_dynamic=include_dynamic)
            response.capabilities = [self._dict_to_msg(info) for info in infos]
        else:
            cap = self._registry.get_capability(name)
            if cap is not None:
                info = cap.to_info_dict()
                response.capabilities = [self._dict_to_msg(info)]
            else:
                response.capabilities = []

        return response

    def _publish_capabilities(self) -> None:
        """Publish current capabilities on /capability/updates topic."""
        infos = self._registry.get_all_capabilities(include_dynamic=True)
        for info in infos:
            msg = self._dict_to_msg(info)
            self._publisher.publish(msg)

    @staticmethod
    def _dict_to_msg(info: dict) -> CapabilityInfo:
        """Convert dict to CapabilityInfo message.

        Args:
            info: Capability info dict.

        Returns:
            CapabilityInfo message.

        """
        msg = CapabilityInfo()
        msg.name = info.get("name", "")
        msg.category = info.get("category", "")
        msg.available = info.get("available", True)
        msg.value = info.get("value", "")
        msg.reason = info.get("reason", "")
        msg.requires = info.get("requires", [])
        msg.composed_of = info.get("composed_of", [])
        msg.conflicts_with = info.get("conflicts_with", [])
        return msg


def main(args: list[str] | None = None) -> None:
    """Entry point for capability registry node.

    Args:
        args: Command line arguments.

    """
    rclpy.init(args=args)
    node = CapabilityRegistryNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main(sys.argv)