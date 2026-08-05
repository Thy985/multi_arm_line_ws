#!/usr/bin/env python3
"""
为多机械臂系统生成控制器配置文件。
每个机械臂需要独立的配置文件，关节名称带有前缀。
"""

import os
import sys

def generate_arm_config(tf_prefix, output_path):
    """为指定机械臂生成控制器配置文件。"""
    
    # 基础配置模板
    config = f"""controller_manager:
  ros__parameters:
    update_rate: 500

    joint_state_broadcaster:
      type: joint_state_broadcaster/JointStateBroadcaster

    joint_trajectory_controller:
      type: joint_trajectory_controller/JointTrajectoryController

joint_state_broadcaster:
  ros__parameters:
    state_publish_rate: 100.0

joint_trajectory_controller:
  ros__parameters:
    joints:
      - {tf_prefix}shoulder_pan_joint
      - {tf_prefix}shoulder_lift_joint
      - {tf_prefix}elbow_joint
      - {tf_prefix}wrist_1_joint
      - {tf_prefix}wrist_2_joint
      - {tf_prefix}wrist_3_joint
    command_interfaces:
      - position
    state_interfaces:
      - position
      - velocity
    state_publish_rate: 100.0
    action_monitor_rate: 20.0
    allow_partial_joints_goal: false
    constraints:
      stopped_velocity_tolerance: 0.2
      goal_time: 0.0
      {tf_prefix}shoulder_pan_joint: {{ trajectory: 0.2, goal: 0.1 }}
      {tf_prefix}shoulder_lift_joint: {{ trajectory: 0.2, goal: 0.1 }}
      {tf_prefix}elbow_joint: {{ trajectory: 0.2, goal: 0.1 }}
      {tf_prefix}wrist_1_joint: {{ trajectory: 0.2, goal: 0.1 }}
      {tf_prefix}wrist_2_joint: {{ trajectory: 0.2, goal: 0.1 }}
      {tf_prefix}wrist_3_joint: {{ trajectory: 0.2, goal: 0.1 }}
"""
    
    with open(output_path, 'w') as f:
        f.write(config)
    
    print(f"Generated config for {tf_prefix} at {output_path}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: generate_arm_config.py <tf_prefix> <output_path>")
        sys.exit(1)
    
    tf_prefix = sys.argv[1]
    output_path = sys.argv[2]
    generate_arm_config(tf_prefix, output_path)
