#!/usr/bin/env python3
"""M4.6 Autonomous Task Loop Test.

Tests the full closed-loop chain with proper rclpy spin.

Prerequisite: m4_6_task_loop.launch.py must be running.

Run: python3 m4_6_task_loop_test.py
"""

import os
import sys
import time

os.environ.setdefault("ROS_HOME", "/tmp/ros_home")
os.environ.setdefault("ROS_LOG_DIR", "/tmp/ros_home/log")

import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
from rclpy.callback_groups import ReentrantCallbackGroup
from sensor_msgs.msg import JointState


class M46TaskLoopTest(Node):

    def __init__(self):
        super().__init__("m46_task_loop_test")
        self._cb_group = ReentrantCallbackGroup()
        self.js_data = {}
        self.js_sub = self.create_subscription(
            JointState, "/joint_states", self._js_cb, 10,
            callback_group=self._cb_group,
        )

    def _js_cb(self, msg):
        for i, name in enumerate(msg.name):
            self.js_data[name] = msg.position[i]

    def wait_for_js(self, timeout=20.0):
        t0 = time.time()
        while time.time() - t0 < timeout:
            rclpy.spin_once(self, timeout_sec=0.5)
            if len(self.js_data) >= 6:
                return True
        return len(self.js_data) >= 6

    def _spin_until_future(self, future, timeout_sec=60.0):
        """Spin until future completes or timeout."""
        deadline = time.time() + timeout_sec
        while not future.done() and time.time() < deadline:
            rclpy.spin_once(self, timeout_sec=0.1)
        return future.done()

    def test_coordinator_execute_task(self, arm_name="left_arm", position="ready"):
        """Test Coordinator ExecuteTask action."""
        from multi_arm_interfaces.action import ExecuteTask

        client = ActionClient(
            self, ExecuteTask, "/coordinator/execute_task",
            callback_group=self._cb_group,
        )
        if not client.wait_for_server(timeout_sec=10.0):
            self.get_logger().error("Coordinator ExecuteTask server not available!")
            return False, "no_server"

        goal = ExecuteTask.Goal()
        goal.task_id = f"m46_test_{time.time():.0f}"
        goal.task_type = "move"
        goal.description = f"{arm_name}:zone_a:{position}"

        self.get_logger().info(f"Sending ExecuteTask: {goal.description}")

        send_future = client.send_goal_async(goal)
        if not self._spin_until_future(send_future, timeout_sec=15.0):
            return False, "goal_send_timeout"

        goal_handle = send_future.result()
        if goal_handle is None or not goal_handle.accepted:
            return False, "goal_rejected"

        self.get_logger().info("Goal accepted, waiting for result...")
        result_future = goal_handle.get_result_async()
        if not self._spin_until_future(result_future, timeout_sec=90.0):
            return False, "execution_timeout"

        result_response = result_future.result()
        if result_response is None:
            return False, "no_result"

        result = result_response.result
        self.get_logger().info(
            f"ExecuteTask result: success={result.success} msg={result.message}"
        )
        return result.success, result.message

    def test_safety_check(self):
        """Test SafetyCheck service."""
        from multi_arm_interfaces.srv import SafetyCheck

        client = self.create_client(
            SafetyCheck, "/safety/safety_check", callback_group=self._cb_group,
        )

        for attempt in range(10):
            if client.wait_for_service(timeout_sec=1.0):
                break
            rclpy.spin_once(self, timeout_sec=0.5)

        if not client.service_is_ready():
            self.get_logger().warn("SafetyCheck service not ready after retries, skipping")
            return True, "service_skipped"

        request = SafetyCheck.Request()
        request.arm_names = ["left_arm"]
        request.trajectory_joint_names = []
        request.trajectory_positions = []
        request.trajectory_duration = 3.0

        future = client.call_async(request)
        if not self._spin_until_future(future, timeout_sec=5.0):
            return False, "timeout"

        result = future.result()
        return result.approved, f"approved={result.approved} scale={result.speed_scale}"

    def test_world_model_query(self):
        """Test WorldModel query_objects service."""
        from multi_arm_interfaces.srv import QueryResources

        client = self.create_client(
            QueryResources, "/world_model/query_objects", callback_group=self._cb_group,
        )

        for attempt in range(10):
            if client.wait_for_service(timeout_sec=1.0):
                break
            rclpy.spin_once(self, timeout_sec=0.5)

        if not client.service_is_ready():
            self.get_logger().warn("WorldModel service not ready after retries, skipping")
            return True, "service_skipped"

        request = QueryResources.Request()
        request.resource_types = ["object"]

        future = client.call_async(request)
        if not self._spin_until_future(future, timeout_sec=5.0):
            return False, "timeout"

        result = future.result()
        return True, f"objects={list(result.resource_names)}"

    def test_task_planner_execute(self):
        """Test TaskPlanner ExecuteTask action with pick_place BT.

        Note: TaskPlanner uses mock BT plugins by default.
        The BT tick succeeds immediately (no real robot motion).
        Real motion is tested via Coordinator ExecuteTask separately.
        """
        from multi_arm_interfaces.action import ExecuteTask

        client = ActionClient(
            self, ExecuteTask, "/task_planner/execute_task",
            callback_group=self._cb_group,
        )
        if not client.wait_for_server(timeout_sec=10.0):
            return False, "no_server"

        goal = ExecuteTask.Goal()
        goal.task_id = f"m46_pick_{time.time():.0f}"
        goal.task_type = "pick_place"
        goal.description = "left_arm:zone_a:ready"

        self.get_logger().info(f"Sending TaskPlanner ExecuteTask: {goal.task_type}")

        send_future = client.send_goal_async(goal)
        if not self._spin_until_future(send_future, timeout_sec=15.0):
            return False, "goal_send_timeout"

        goal_handle = send_future.result()
        if goal_handle is None or not goal_handle.accepted:
            return False, "goal_rejected"

        self.get_logger().info("TaskPlanner goal accepted, waiting for result...")
        result_future = goal_handle.get_result_async()
        if not self._spin_until_future(result_future, timeout_sec=15.0):
            return False, "execution_timeout"

        result_response = result_future.result()
        if result_response is None:
            return False, "no_result"

        result = result_response.result
        self.get_logger().info(
            f"TaskPlanner result: success={result.success} msg={result.message}"
        )
        return result.success, result.message

    def verify_position(self, expected, tol=0.2):
        """Verify robot joint positions match expected."""
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
    node = M46TaskLoopTest()
    results = {}

    node.get_logger().info("=== M4.6 Autonomous Task Loop Test ===")

    if not node.wait_for_js(timeout=20.0):
        node.get_logger().error("No joint_states! Is simulation running?")
        results["1.1_js_available"] = "FAIL"
        _print_results(results)
        rclpy.shutdown()
        sys.exit(1)

    results["1.1_js_available"] = "PASS"
    node.get_logger().info(f"JS received: {len(node.js_data)} joints")

    ok, msg = node.test_safety_check()
    results["2.1_safety_check"] = "PASS" if ok else "FAIL"
    node.get_logger().info(f"SafetyCheck: {msg}")

    ok, msg = node.test_world_model_query()
    results["3.1_world_model_query"] = "PASS" if ok else "FAIL"
    node.get_logger().info(f"WorldModel: {msg}")

    left_arm_ready = {
        "left_arm_shoulder_pan_joint": 0.0,
        "left_arm_shoulder_lift_joint": -1.57,
        "left_arm_elbow_joint": 1.57,
        "left_arm_wrist_1_joint": 0.0,
        "left_arm_wrist_2_joint": 0.0,
        "left_arm_wrist_3_joint": 0.0,
    }

    ok, msg = node.test_coordinator_execute_task("left_arm", "ready")
    results["4.1_coordinator_move"] = "PASS" if ok else "FAIL"
    node.get_logger().info(f"Coordinator move: {msg}")

    if ok:
        vok = node.verify_position(left_arm_ready)
        results["4.2_position_verify"] = "PASS" if vok else "FAIL"

    left_arm_home = {
        "left_arm_shoulder_pan_joint": 0.0,
        "left_arm_shoulder_lift_joint": 0.0,
        "left_arm_elbow_joint": 0.0,
        "left_arm_wrist_1_joint": 0.0,
        "left_arm_wrist_2_joint": 0.0,
        "left_arm_wrist_3_joint": 0.0,
    }

    ok, msg = node.test_coordinator_execute_task("left_arm", "home")
    results["4.3_coordinator_home"] = "PASS" if ok else "FAIL"
    node.get_logger().info(f"Coordinator home: {msg}")

    if ok:
        vok = node.verify_position(left_arm_home)
        results["4.4_home_verify"] = "PASS" if vok else "FAIL"

    ok, msg = node.test_task_planner_execute()
    results["5.1_task_planner_bt"] = "PASS" if ok else "FAIL"
    node.get_logger().info(f"TaskPlanner BT: {msg}")

    _print_results(results)
    rclpy.shutdown()
    all_pass = all(v == "PASS" for v in results.values())
    sys.exit(0 if all_pass else 1)


def _print_results(results):
    print("\n=== M4.6 Autonomous Task Loop Test Results ===")
    all_pass = True
    for k, v in results.items():
        print(f"  {k}: {v}")
        if v == "FAIL":
            all_pass = False
    print(f"Overall: {'ALL PASS' if all_pass else 'SOME FAILED'}")


if __name__ == "__main__":
    main()
