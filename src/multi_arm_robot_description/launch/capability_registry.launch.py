"""Launch file for capability registry node."""

from __future__ import annotations

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory
from pathlib import Path


def generate_launch_description() -> LaunchDescription:
    """Generate launch description for capability registry.

    Returns:
        LaunchDescription with capability registry node.

    """
    share_dir = get_package_share_directory("multi_arm_robot_description")
    default_yaml = str(Path(share_dir) / "config" / "capability.yaml")

    return LaunchDescription([
        DeclareLaunchArgument(
            "capability_yaml",
            default_value=default_yaml,
            description="Path to capability.yaml",
        ),
        DeclareLaunchArgument(
            "publish_rate",
            default_value="1.0",
            description="Capability publish rate in Hz",
        ),
        Node(
            package="multi_arm_robot_description",
            executable="capability_registry_node",
            name="capability_registry_node",
            parameters=[{
                "capability_yaml": LaunchConfiguration("capability_yaml"),
                "publish_rate": LaunchConfiguration("publish_rate"),
            }],
            output="screen",
        ),
    ])