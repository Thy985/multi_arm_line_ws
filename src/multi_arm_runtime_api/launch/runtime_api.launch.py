"""Launch file for Robot Runtime API Node."""

from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    """Generate launch description for runtime API node."""
    return LaunchDescription([
        Node(
            package="multi_arm_runtime_api",
            executable="runtime_api_node",
            name="runtime_api_node",
            output="screen",
        ),
    ])