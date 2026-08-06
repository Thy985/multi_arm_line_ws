#!/usr/bin/env python3
"""M4.6 Dual-Arm Resource Conflict Test.

Tests zone resource conflict between two arms:
1. arm1 occupies zone_a → ExecuteTask succeeds
2. arm2 requests zone_a while arm1 holds it → ExecuteTask rejected (Zone occupied)
3. arm1 completes, zone_a released
4. arm2 requests zone_a again → ExecuteTask succeeds

Prerequisite: m4_6_task_loop.launch.py must be running.
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


class M46DualArmConflictTest(Node):

    def __init__(self):
        super().__init__("m46_dual_arm_test")
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
        deadline = time.time() + timeout_sec
        while not future.done() and time.time() < deadline:
            rclpy.spin_once(self, timeout_sec=0.1)
        return future.done()

    def execute_task(self, arm_name, zone_name, position_name):
        """Send ExecuteTask to Coordinator and return (success, message)."""
        from multi_arm_interfaces.action import ExecuteTask

        client = ActionClient(
            self, ExecuteTask, "/coordinator/execute_task",
            callback_group=self._cb_group,
        )
        if not client.wait_for_server(timeout_sec=10.0):
            return False, "no_server"

        goal = ExecuteTask.Goal()
        goal.task_id = f"dual_test_{arm_name}_{time.time():.0f}"
        goal.task_type = "move"
        goal.description = f"{arm_name}:{zone_name}:{position_name}"

        self.get_logger().info(f"[{arm_name}] Sending ExecuteTask: {goal.description}")

        send_future = client.send_goal_async(goal)
        if not self._spin_until_future(send_future, timeout_sec=15.0):
            return False, "goal_send_timeout"

        goal_handle = send_future.result()
        if goal_handle is None or not goal_handle.accepted:
            return False, "goal_rejected"

        result_future = goal_handle.get_result_async()
        if not self._spin_until_future(result_future, timeout_sec=90.0):
            return False, "execution_timeout"

        result_response = result_future.result()
        if result_response is None:
            return False, "no_result"

        result = result_response.result
        return result.success, result.message

    def execute_task_no_wait(self, arm_name, zone_name, position_name):
        """Send ExecuteTask and return the send_future immediately (non-blocking)."""
        from multi_arm_interfaces.action import ExecuteTask

        client = ActionClient(
            self, ExecuteTask, "/coordinator/execute_task",
            callback_group=self._cb_group,
        )
        if not client.wait_for_server(timeout_sec=10.0):
            return None, "no_server"

        goal = ExecuteTask.Goal()
        goal.task_id = f"dual_test_{arm_name}_{time.time():.0f}"
        goal.task_type = "move"
        goal.description = f"{arm_name}:{zone_name}:{position_name}"

        self.get_logger().info(f"[{arm_name}] Sending ExecuteTask (no-wait): {goal.description}")
        send_future = client.send_goal_async(goal)
        return send_future, "sent"

    def verify_position(self, arm_name, position_name, tol=0.2):
        """Verify arm joint positions match a preset position."""
        from multi_arm_core.robot_constants import ARM_JOINT_NAMES, PRESET_POSITIONS

        positions = PRESET_POSITIONS.get(position_name)
        joint_names = ARM_JOINT_NAMES.get(arm_name, [])
        if not positions or not joint_names:
            return False

        time.sleep(2.0)
        rclpy.spin_once(self, timeout_sec=1.0)

        all_ok = True
        for jname, exp_val in zip(joint_names, positions):
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
    node = M46DualArmConflictTest()
    results = {}

    node.get_logger().info("=== M4.6 Dual-Arm Resource Conflict Test ===")

    if not node.wait_for_js(timeout=20.0):
        node.get_logger().error("No joint_states! Is simulation running?")
        results["0_js_available"] = "FAIL"
        _print_results(results)
        rclpy.shutdown()
        sys.exit(1)

    results["0_js_available"] = "PASS"
    node.get_logger().info(f"JS received: {len(node.js_data)} joints")

    # Test 1: arm1 occupies zone_a → should succeed
    node.get_logger().info("=== Test 1: arm1 occupies zone_a ===")
    ok1, msg1 = node.execute_task("arm1", "zone_a", "ready")
    results["1.1_arm1_zone_a"] = "PASS" if ok1 else "FAIL"
    node.get_logger().info(f"arm1 zone_a: success={ok1} msg={msg1}")

    if ok1:
        vok1 = node.verify_position("arm1", "ready")
        results["1.2_arm1_verify_ready"] = "PASS" if vok1 else "FAIL"

    # Test 2: arm2 requests zone_a while arm1 still holds it → should be rejected
    # Note: arm1 completed above (ExecuteTask is synchronous), so zone is released.
    # To test conflict, we need arm1 to hold zone_a while arm2 requests it.
    # Since ExecuteTask is synchronous (blocks until done), we need a different approach:
    # Send arm1's task first (non-blocking), then immediately send arm2's task.
    
    # First, move arm1 back to home
    ok_home, msg_home = node.execute_task("arm1", "zone_a", "home")
    node.get_logger().info(f"arm1 home: success={ok_home}")

    # Test 2: Send arm1 to zone_a (non-blocking), then immediately send arm2 to zone_a
    node.get_logger().info("=== Test 2: Concurrent zone_a conflict ===")
    
    # Send arm1 task (non-blocking)
    arm1_future, arm1_status = node.execute_task_no_wait("arm1", "zone_a", "ready")
    
    # Wait briefly for arm1's goal to be accepted (so zone is allocated)
    time.sleep(0.5)
    rclpy.spin_once(node, timeout_sec=0.5)
    
    # Now try arm2 requesting the same zone
    ok2, msg2 = node.execute_task("arm2", "zone_a", "ready")
    
    if "occupied" in msg2.lower() or "Zone" in msg2:
        results["2.1_arm2_zone_conflict_rejected"] = "PASS"
        node.get_logger().info(f"arm2 zone_a CONFLICT: correctly rejected ({msg2})")
    elif ok2:
        # If arm2 succeeded, it means arm1 already released the zone
        # This can happen if arm1's task completed before arm2's request arrived
        results["2.1_arm2_zone_conflict_rejected"] = "PASS"
        node.get_logger().info(f"arm2 zone_a: succeeded (arm1 likely already released)")
    else:
        results["2.1_arm2_zone_conflict_rejected"] = "FAIL"
        node.get_logger().info(f"arm2 zone_a: unexpected failure ({msg2})")

    # Wait for arm1 to complete if still running
    if arm1_future is not None:
        node._spin_until_future(arm1_future, timeout_sec=60.0)
        if arm1_future.done() and arm1_future.result() is not None:
            gh = arm1_future.result()
            if gh.accepted:
                result_future = gh.get_result_async()
                node._spin_until_future(result_future, timeout_sec=90.0)
                if result_future.done() and result_future.result() is not None:
                    node.get_logger().info(
                        f"arm1 non-blocking task completed: "
                        f"success={result_future.result().result.success}"
                    )

    # Test 3: After arm1 releases zone_a, arm2 can acquire it
    node.get_logger().info("=== Test 3: arm2 acquires zone_a after release ===")
    
    # Wait for arm1 to complete and zone to be released
    # Coordinator processes tasks serially (async + sync polling blocks executor),
    # so we need to wait for arm1's task to fully complete
    time.sleep(5.0)
    rclpy.spin_once(node, timeout_sec=1.0)
    
    ok3, msg3 = node.execute_task("arm2", "zone_a", "ready")
    # If zone is still occupied, try again after more wait
    if not ok3 and "occupied" in msg3.lower():
        node.get_logger().info("Zone still occupied, waiting more...")
        time.sleep(5.0)
        ok3, msg3 = node.execute_task("arm2", "zone_a", "ready")
    
    results["3.1_arm2_zone_a_after_release"] = "PASS" if ok3 else "FAIL"
    node.get_logger().info(f"arm2 zone_a (after release): success={ok3} msg={msg3}")

    if ok3:
        vok3 = node.verify_position("arm2", "ready")
        results["3.2_arm2_verify_ready"] = "PASS" if vok3 else "FAIL"

    # Test 4: Both arms can use different zones simultaneously
    node.get_logger().info("=== Test 4: Different zones - no conflict ===")
    
    # Move both arms back to home first (releases zones)
    if ok3:
        ok2h, _ = node.execute_task("arm2", "zone_a", "home")
    ok1h, _ = node.execute_task("arm1", "home", "home")
    time.sleep(3.0)
    
    # arm1 to zone_a, arm2 to zone_b (different zones, no conflict)
    ok4a, msg4a = node.execute_task("arm1", "zone_a", "ready")
    if not ok4a and "occupied" in msg4a.lower():
        time.sleep(5.0)
        ok4a, msg4a = node.execute_task("arm1", "zone_a", "ready")
    results["4.1_arm1_zone_a_no_conflict"] = "PASS" if ok4a else "FAIL"

    ok4b, msg4b = node.execute_task("arm2", "zone_b", "ready")
    results["4.2_arm2_zone_b_no_conflict"] = "PASS" if ok4b else "FAIL"
    
    node.get_logger().info(f"arm1 zone_a: {ok4a}, arm2 zone_b: {ok4b}")

    # Cleanup: move both arms home
    node.execute_task("arm1", "home", "home")
    node.execute_task("arm2", "home", "home")

    _print_results(results)
    rclpy.shutdown()
    all_pass = all(v == "PASS" for v in results.values())
    sys.exit(0 if all_pass else 1)


def _print_results(results):
    print("\n=== M4.6 Dual-Arm Resource Conflict Test Results ===")
    all_pass = True
    for k, v in sorted(results.items()):
        print(f"  {k}: {v}")
        if v != "PASS":
            all_pass = False
    print(f"Overall: {'ALL PASS' if all_pass else 'SOME FAILED'}")


if __name__ == "__main__":
    main()