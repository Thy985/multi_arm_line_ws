"""Launch LED status node."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    """Generate launch description for LED status node."""
    check_period_arg = DeclareLaunchArgument(
        "check_period",
        default_value="1.0",
        description="Period in seconds for checking system health.",
    )

    led_node = Node(
        package="multi_arm_runtime_api",
        executable="led_status_node",
        name="led_status_node",
        parameters=[{"check_period": LaunchConfiguration("check_period")}],
        output="screen",
    )

    return LaunchDescription([check_period_arg, led_node])