"""Launch file for simulation scenario with domain randomization."""

from __future__ import annotations

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory
from pathlib import Path


def generate_launch_description() -> LaunchDescription:
    """Generate launch description for simulation scenario.

    Returns:
        LaunchDescription with scene generator and dataset pipeline.

    """
    sim_share = get_package_share_directory("multi_arm_simulation")
    default_scenario = str(Path(sim_share) / "scenarios" / "dual_arm.yaml")
    default_dr = str(Path(sim_share) / "config" / "domain_randomization.yaml")

    return LaunchDescription([
        DeclareLaunchArgument(
            "scenario",
            default_value=default_scenario,
            description="Scenario YAML file",
        ),
        DeclareLaunchArgument(
            "domain_randomization",
            default_value=default_dr,
            description="Domain randomization config",
        ),
        DeclareLaunchArgument(
            "output_dir",
            default_value="/tmp/simulation_dataset",
            description="Dataset output directory",
        ),
        Node(
            package="multi_arm_simulation",
            executable="dataset_pipeline_node",
            name="dataset_pipeline_node",
            parameters=[{
                "output_dir": LaunchConfiguration("output_dir"),
                "scene_name": "simulation_scenario",
                "record_rate": 10.0,
            }],
            output="screen",
        ),
    ])