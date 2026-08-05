#!/usr/bin/env python3
"""
Test launch file for multi-arm coordination.
"""

from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    IncludeLaunchDescription,
    OpaqueFunction,
    ExecuteProcess,
)
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import (
    LaunchConfiguration,
    PathJoinSubstitution,
)
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def launch_setup(context, *args, **kwargs):
    # Launch multi-arm simulation
    multi_arm_sim = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            [FindPackageShare("ur_simulation_gz"), "/launch/multi_arm_sim.launch.py"]
        ),
        launch_arguments={
            "ur_type": LaunchConfiguration("ur_type"),
            "world_file": LaunchConfiguration("world_file"),
        }.items(),
    )
    
    # Launch coordinator node
    coordinator_node = Node(
        package="order_manager",
        executable="multi_arm_coordinator",
        name="multi_arm_coordinator",
        output="screen",
    )
    
    return [
        multi_arm_sim,
        coordinator_node,
    ]


def generate_launch_description():
    declared_arguments = []
    
    declared_arguments.append(
        DeclareLaunchArgument(
            "ur_type",
            description="Type/series of used UR robot.",
            choices=[
                "ur3", "ur5", "ur10",
                "ur3e", "ur5e", "ur7e", "ur10e", "ur12e", "ur16e",
                "ur8long", "ur15", "ur18", "ur20", "ur30",
            ],
            default_value="ur5e",
        )
    )
    
    declared_arguments.append(
        DeclareLaunchArgument(
            "world_file",
            default_value="empty.sdf",
            description="Gazebo world file.",
        )
    )
    
    return LaunchDescription(declared_arguments + [OpaqueFunction(function=launch_setup)])