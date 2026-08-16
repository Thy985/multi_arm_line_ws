#!/usr/bin/env python3
"""
Simple test script for multi-arm control.
Sends trajectory commands to both arms.
"""

import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
from control_msgs.action import FollowJointTrajectory
from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint
from builtin_interfaces.msg import Duration
import sys


class ArmTestNode(Node):
    """Test node for controlling a single arm."""
    
    def __init__(self, arm_name):
        super().__init__(f'{arm_name}_test_node')
        self.arm_name = arm_name
        
        # Action client
        self.client = ActionClient(
            self,
            FollowJointTrajectory,
            f'/{arm_name}/joint_trajectory_controller/follow_joint_trajectory'
        )
        
        self.get_logger().info(f'Test node for {arm_name} started')
        self.get_logger().info('Waiting for action server...')
        
        self.client.wait_for_server()
        self.get_logger().info('Action server available')
    
    def send_test_trajectory(self):
        """Send a test trajectory."""
        trajectory = JointTrajectory()
        trajectory.joint_names = [
            'shoulder_pan_joint',
            'shoulder_lift_joint',
            'elbow_joint',
            'wrist_1_joint',
            'wrist_2_joint',
            'wrist_3_joint'
        ]
        
        # Create a simple movement
        point = JointTrajectoryPoint()
        point.positions = [0.0, -1.57, 1.57, 0.0, 0.0, 0.0]
        point.velocities = [0.0] * 6
        point.accelerations = [0.0] * 6
        point.time_from_start = Duration(sec=3)
        
        trajectory.points = [point]
        
        goal = FollowJointTrajectory.Goal()
        goal.trajectory = trajectory
        
        self.get_logger().info(f'Sending trajectory to {self.arm_name}')
        future = self.client.send_goal_async(goal)
        return future


def main(args=None):
    rclpy.init(args=args)
    
    if len(sys.argv) < 2:
        print("Usage: test_arm_control.py <arm_name>")
        print("Example: test_arm_control.py left_arm")
        return
    
    arm_name = sys.argv[1]
    
    node = ArmTestNode(arm_name)
    
    try:
        future = node.send_test_trajectory()
        rclpy.spin_until_future_complete(node, future)
        node.get_logger().info(f'Trajectory sent to {arm_name}')
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()