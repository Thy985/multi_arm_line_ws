"""Launch file for Experience Node."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    """Generate launch description for experience node."""
    return LaunchDescription([
        DeclareLaunchArgument(
            "db_path",
            default_value="experience.db",
            description="Path to SQLite database file",
        ),
        DeclareLaunchArgument(
            "json_dir",
            default_value="",
            description="Directory for JSON export (empty = no JSON)",
        ),
        Node(
            package="multi_arm_experience",
            executable="experience_node",
            name="experience_node",
            output="screen",
            parameters=[{
                "db_path": LaunchConfiguration("db_path"),
                "json_dir": LaunchConfiguration("json_dir"),
            }],
        ),
    ])