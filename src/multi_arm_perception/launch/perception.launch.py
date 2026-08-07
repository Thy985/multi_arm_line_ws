"""Launch file for perception node."""

from __future__ import annotations

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    """Generate launch description for perception.

    Returns:
        LaunchDescription with perception node.

    """
    return LaunchDescription([
        DeclareLaunchArgument("publish_rate", default_value="10.0"),
        DeclareLaunchArgument("use_ground_truth", default_value="true"),
        Node(
            package="multi_arm_perception",
            executable="ground_truth_node",
            name="ground_truth_node",
            parameters=[{"publish_rate": LaunchConfiguration("publish_rate")}],
            output="screen",
        ),
    ])