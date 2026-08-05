#!/usr/bin/env python3
"""
Launch file for rqt_robot_monitor with multi-arm diagnostics visualization.

Starts the multi-arm coordinator and rqt_robot_monitor panel.
"""

from launch import LaunchDescription
from launch.actions import ExecuteProcess
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        Node(
            package='order_manager',
            executable='enhanced_multi_arm_coordinator',
            name='enhanced_multi_arm_coordinator',
            output='screen',
        ),
        ExecuteProcess(
            cmd=['rqt', '--force-discover', '--standalone',
                 'rqt_robot_monitor.robot_monitor_plugin.RobotMonitorPlugin'],
            output='screen',
        ),
    ])
