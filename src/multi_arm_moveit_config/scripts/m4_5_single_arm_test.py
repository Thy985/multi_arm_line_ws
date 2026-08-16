#!/usr/bin/env python3
"""M4.5 Test 1: MoveIt single-arm plan+execute via MoveGroup action.

Prerequisite: m4_5_motion.launch.py must be running with move_group active.
Run standalone: python3 m4_5_single_arm_test.py
"""

import sys
import time
import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
from moveit_msgs.action import MoveGroup
from moveit_msgs.msg import (
    PlanningOptions, RobotState, Constraints, JointConstraint
)
from sensor_msgs.msg import JointState


class MoveItSingleArmTest(Node):

    def __init__(self):
        super().__init__("m45_single_arm_test")
        self.js_data = {}
        self.js_sub = self.create_subscription(
            JointState, "/joint_states", self._js_cb, 10
        )
        self.move_client = ActionClient(self, MoveGroup, "/move_action")

    def _js_cb(self, msg):
        for i, name in enumerate(msg.name):
            self.js_data[name] = msg.position[i]

    def wait_for_js(self, timeout=15.0):
        t0 = time.time()
        while time.time() - t0 < timeout:
            rclpy.spin_once(self, timeout_sec=0.5)
            if len(self.js_data) >= 6:
                return True
        return len(self.js_data) >= 6

    def plan_and_execute(self, group_name, target_joints, label=""):
        self.get_logger().info(f"Planning {group_name} -> {label}")
        if not self.move_client.wait_for_server(timeout_sec=15.0):
            self.get_logger().error("MoveGroup action server not available!")
            return False, "no_server"

        goal = MoveGroup.Goal()
        goal.request.group_name = group_name
        goal.request.num_planning_attempts = 10
        goal.request.allowed_planning_time = 10.0
        goal.request.max_velocity_scaling_factor = 0.3
        goal.request.max_acceleration_scaling_factor = 0.3

        start_state = RobotState()
        start_state.joint_state.header.stamp = self.get_clock().now().to_msg()
        jnames = list(target_joints.keys())
        start_state.joint_state.name = jnames
        start_state.joint_state.position = [
            self.js_data.get(n, 0.0) for n in jnames
        ]
        goal.request.start_state = start_state

        constraints = Constraints()
        constraints.name = f"{group_name}_{label}"
        for jname, jval in target_joints.items():
            jc = JointConstraint()
            jc.joint_name = jname
            jc.position = jval
            jc.tolerance_above = 0.05
            jc.tolerance_below = 0.05
            jc.weight = 1.0
            constraints.joint_constraints.append(jc)
        goal.request.goal_constraints = [constraints]

        goal.planning_options = PlanningOptions()
        goal.planning_options.plan_only = False
        goal.planning_options.replan = True
        goal.planning_options.replan_attempts = 3

        future = self.move_client.send_goal_async(goal, feedback_callback=self._feedback_cb)
        rclpy.spin_until_future_complete(self, future, timeout_sec=30.0)

        if not future.result() or not future.result().accepted:
            return False, "goal_rejected"

        self.get_logger().info("Goal accepted, waiting for result...")
        result_future = future.result().get_result_async()
        rclpy.spin_until_future_complete(self, result_future, timeout_sec=60.0)

        if result_future.result() is None:
            return False, "action_timeout"

        err = result_future.result().result.error_code.val
        if err == 1:
            return True, "success"
        return False, f"error_{err}"

    def _feedback_cb(self, feedback):
        pass

    def verify_position(self, expected, tol=0.2):
        time.sleep(2.0)
        rclpy.spin_once(self, timeout_sec=1.0)
        all_ok = True
        for jname, exp_val in expected.items():
            actual = self.js_data.get(jname, None)
            if actual is None:
                self.get_logger().warn(f"  {jname}: NO DATA")
                all_ok = False
            elif abs(actual - exp_val) > tol:
                self.get_logger().warn(
                    f"  {jname}: exp={exp_val:.3f} act={actual:.3f} diff>{tol}"
                )
                all_ok = False
            else:
                self.get_logger().info(f"  {jname}: {actual:.3f} OK")
        return all_ok


def main():
    rclpy.init()
    node = MoveItSingleArmTest()
    results = {}

    node.get_logger().info("=== M4.5 Test 1: MoveIt Single-Arm ===")

    if not node.wait_for_js(timeout=15.0):
        node.get_logger().error("No joint_states! Is simulation running?")
        results["1.1_js_available"] = "FAIL"
        _print_results(results)
        rclpy.shutdown()
        sys.exit(1)

    results["1.1_js_available"] = "PASS"
    node.get_logger().info(f"JS received: {len(node.js_data)} joints")

    left_arm_ready = {
        "left_arm_shoulder_pan_joint": 0.0,
        "left_arm_shoulder_lift_joint": -1.57,
        "left_arm_elbow_joint": 1.57,
        "left_arm_wrist_1_joint": 0.0,
        "left_arm_wrist_2_joint": 0.0,
        "left_arm_wrist_3_joint": 0.0,
    }

    ok, msg = node.plan_and_execute("left_arm", left_arm_ready, "ready")
    results[f"1.2_left_arm_plan_ready"] = "PASS" if ok else "FAIL"
    node.get_logger().info(f"left_arm plan ready: {msg}")

    if ok:
        vok = node.verify_position(left_arm_ready)
        results["1.3_left_arm_verify_ready"] = "PASS" if vok else "FAIL"

    right_arm_ready = {
        "right_arm_shoulder_pan_joint": 0.0,
        "right_arm_shoulder_lift_joint": -1.57,
        "right_arm_elbow_joint": 1.57,
        "right_arm_wrist_1_joint": 0.0,
        "right_arm_wrist_2_joint": 0.0,
        "right_arm_wrist_3_joint": 0.0,
    }

    ok2, msg2 = node.plan_and_execute("right_arm", right_arm_ready, "ready")
    results["1.4_right_arm_plan_ready"] = "PASS" if ok2 else "FAIL"
    node.get_logger().info(f"right_arm plan ready: {msg2}")

    if ok2:
        vok2 = node.verify_position(right_arm_ready)
        results["1.5_right_arm_verify_ready"] = "PASS" if vok2 else "FAIL"

    _print_results(results)
    rclpy.shutdown()
    all_pass = all(v == "PASS" for v in results.values())
    sys.exit(0 if all_pass else 1)


def _print_results(results):
    print("\n=== M4.5 Test 1 Results ===")
    all_pass = True
    for k, v in results.items():
        print(f"  {k}: {v}")
        if v == "FAIL":
            all_pass = False
    print(f"Overall: {'ALL PASS' if all_pass else 'SOME FAILED'}")


if __name__ == "__main__":
    main()
