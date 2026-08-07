"""Launch file for Skill Runtime Node."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    """Generate launch description for skill runtime."""
    return LaunchDescription([
        Node(
            package="multi_arm_skill_runtime",
            executable="skill_node",
            name="skill_runtime_node",
            output="screen",
        ),
    ])