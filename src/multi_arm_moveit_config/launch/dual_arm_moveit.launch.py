"""Launch file for dual-arm MoveIt2 with Gazebo simulation."""

import os
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, DeclareLaunchArgument
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory


def generate_launch_description() -> LaunchDescription:
    """Generate launch description for dual-arm MoveIt2."""
    ur_simulation_dir = get_package_share_directory("ur_simulation_gz")
    moveit_config_dir = get_package_share_directory("multi_arm_moveit_config")

    use_sim = DeclareLaunchArgument(
        "use_sim",
        default_value="true",
        description="Use Gazebo simulation",
    )

    rviz_config = os.path.join(moveit_config_dir, "rviz", "moveit.rviz")

    rviz_node = Node(
        package="rviz2",
        executable="rviz2",
        name="rviz2",
        arguments=["-d", rviz_config] if os.path.exists(rviz_config) else [],
        output="screen",
    )

    return LaunchDescription([
        use_sim,
        rviz_node,
    ])