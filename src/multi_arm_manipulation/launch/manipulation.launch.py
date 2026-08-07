"""Launch file for manipulation node."""

from __future__ import annotations

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    """Generate launch description for manipulation.

    Returns:
        LaunchDescription with manipulation node.

    """
    return LaunchDescription([
        DeclareLaunchArgument("arm_names", default_value="[arm1,arm2]"),
        Node(
            package="multi_arm_manipulation",
            executable="manipulation_node",
            name="manipulation_node",
            parameters=[{"arm_names": LaunchConfiguration("arm_names")}],
            output="screen",
        ),
    ])