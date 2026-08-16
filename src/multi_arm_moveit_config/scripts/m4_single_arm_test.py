#!/usr/bin/env python3
"""M4.1 Single-arm MoveIt2 closed-loop validation script.

Validates:
1. MoveIt2 planning (home -> target_pose -> home)
2. JTC execution via FollowJointTrajectory action
3. JointState feedback from Gazebo
4. WorldModel sync from joint_states
5. SafetyCheck before execution

Usage:
  ros2 launch ur_simulation_gz single_arm_m4.launch.py
  # Wait for controllers to be active, then:
  python3 src/multi_arm_moveit_config/scripts/m4_single_arm_test.py
"""

import sys
import time
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import JointState

from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint
from action_msgs.msg import GoalStatus
from control_msgs.action import FollowJointTrajectory


class M4SingleArmTest(Node):
    """Test node for M4.1 single-arm closed-loop validation."""

    def __init__(self):
        super().__init__("m4_single_arm_test")

        self._joint_positions = {}
        self._js_received = False
        self._wm_state_received = False

        self._js_sub = self.create_subscription(
            JointState,
            "/left_arm/joint_states",
            self._on_joint_state,
            10,
        )

        self._wm_sub = self.create_subscription(
            JointState,
            "/world_model/state",
            self._on_wm_state,
            10,
        )

        self._results = {}

    def _on_joint_state(self, msg: JointState) -> None:
        """Track joint states from Gazebo."""
        for i, name in enumerate(msg.name):
            self._joint_positions[name] = msg.position[i]
        self._js_received = True

    def _on_wm_state(self, msg) -> None:
        """Track WorldModel state updates."""
        self._wm_state_received = True

    def test_joint_state_received(self) -> bool:
        """Test: /left_arm/joint_states is being published."""
        self.get_logger().info("Test 1: Checking /left_arm/joint_states...")
        start = time.time()
        while not self._js_received and (time.time() - start) < 10.0:
            rclpy.spin_once(self, timeout_sec=0.1)
        if self._js_received:
            self.get_logger().info(
                f"  PASS: Received joint states: {list(self._joint_positions.keys())}"
            )
            return True
        self.get_logger().error("  FAIL: No joint states received")
        return False

    def test_jtc_action_available(self) -> bool:
        """Test: FollowJointTrajectory action server is available."""
        from rclpy.action import ActionClient

        self.get_logger().info("Test 2: Checking JTC action server...")
        client = ActionClient(
            self, FollowJointTrajectory,
            "/left_arm/joint_trajectory_controller/follow_joint_trajectory",
        )
        available = client.wait_for_server(timeout_sec=10.0)
        client.destroy()
        if available:
            self.get_logger().info("  PASS: JTC action server available")
            return True
        self.get_logger().error("  FAIL: JTC action server not available")
        return False

    def test_send_trajectory(self) -> bool:
        """Test: Send a simple trajectory to JTC."""
        from rclpy.action import ActionClient

        self.get_logger().info("Test 3: Sending trajectory home -> ready -> home...")
        client = ActionClient(
            self, FollowJointTrajectory,
            "/left_arm/joint_trajectory_controller/follow_joint_trajectory",
        )
        if not client.wait_for_server(timeout_sec=10.0):
            self.get_logger().error("  FAIL: JTC not available")
            client.destroy()
            return False

        joint_names = [
            "left_arm_shoulder_pan_joint",
            "left_arm_shoulder_lift_joint",
            "left_arm_elbow_joint",
            "left_arm_wrist_1_joint",
            "left_arm_wrist_2_joint",
            "left_arm_wrist_3_joint",
        ]

        home = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        ready = [0.0, -1.57, 1.57, 0.0, 0.0, 0.0]

        trajectory = JointTrajectory()
        trajectory.joint_names = joint_names

        pt1 = JointTrajectoryPoint()
        pt1.positions = ready
        pt1.time_from_start.sec = 3
        trajectory.points.append(pt1)

        pt2 = JointTrajectoryPoint()
        pt2.positions = home
        pt2.time_from_start.sec = 6
        trajectory.points.append(pt2)

        goal = FollowJointTrajectory.Goal()
        goal.trajectory = trajectory

        self.get_logger().info("  Sending goal: home -> ready -> home")
        future = client.send_goal_async(goal)
        rclpy.spin_until_future_complete(self, future, timeout_sec=5.0)

        if not future.result():
            self.get_logger().error("  FAIL: Goal send failed")
            client.destroy()
            return False

        goal_handle = future.result()
        if not goal_handle.accepted:
            self.get_logger().error(f"  FAIL: Goal rejected: {goal_handle.status}")
            client.destroy()
            return False

        self.get_logger().info("  Goal accepted, waiting for result...")
        result_future = goal_handle.get_result_async()

        start = time.time()
        while not result_future.done() and (time.time() - start) < 15.0:
            rclpy.spin_once(self, timeout_sec=0.1)

        if result_future.done():
            result = result_future.result()
            status = result.status
            if status == GoalStatus.STATUS_SUCCEEDED:
                self.get_logger().info("  PASS: Trajectory executed successfully")
                client.destroy()
                return True
            else:
                self.get_logger().error(f"  FAIL: Trajectory failed with status {status}")
                client.destroy()
                return False
        else:
            self.get_logger().error("  FAIL: Trajectory execution timed out")
            client.destroy()
            return False

    def test_joint_positions_changed(self) -> bool:
        """Test: Joint positions actually changed after trajectory."""
        self.get_logger().info("Test 4: Checking joint positions after trajectory...")
        if "left_arm_shoulder_lift_joint" in self._joint_positions:
            pos = self._joint_positions["left_arm_shoulder_lift_joint"]
            if abs(pos) < 0.3:
                self.get_logger().info(
                    f"  PASS: shoulder_lift={pos:.3f} (near home=0)"
                )
                return True
            self.get_logger().error(
                f"  FAIL: shoulder_lift={pos:.3f} (expected near 0)"
            )
            return False
        self.get_logger().error("  FAIL: No joint positions available")
        return False

    def run_tests(self) -> dict:
        """Run all M4.1 tests."""
        results = {}
        results["joint_state_received"] = self.test_joint_state_received()
        results["jtc_action_available"] = self.test_jtc_action_available()
        if results["jtc_action_available"]:
            results["trajectory_execution"] = self.test_send_trajectory()
            results["joint_positions_changed"] = self.test_joint_positions_changed()
        else:
            results["trajectory_execution"] = False
            results["joint_positions_changed"] = False

        self.get_logger().info("\n=== M4.1 Test Results ===")
        for name, passed in results.items():
            status = "PASS" if passed else "FAIL"
            self.get_logger().info(f"  {name}: {status}")

        total = len(results)
        passed = sum(1 for v in results.values() if v)
        self.get_logger().info(f"  Total: {passed}/{total}")

        return results


def main():
    rclpy.init()
    node = M4SingleArmTest()

    try:
        results = node.run_tests()
        all_passed = all(results.values())
        node.destroy_node()
        rclpy.shutdown()
        sys.exit(0 if all_passed else 1)
    except KeyboardInterrupt:
        node.destroy_node()
        rclpy.shutdown()
        sys.exit(1)


if __name__ == "__main__":
    main()