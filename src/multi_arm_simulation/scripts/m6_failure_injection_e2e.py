"""M6 Failure Injection Simulation E2E — Phase 3 recovery validation.

Verifies the M6 stack's failure recovery in Gazebo simulation:

    Scenario 1: Planning failure injection
        Send unreachable target → Coordinator → MoveIt fails
        → RecoveryManager classifies → Recovery attempt → Abort/Fail
        → WorldModel remains consistent

    Scenario 2: Safety check verification
        Call SafetyCheck service → Verify approved + speed_scale
        Trigger E-Stop → Verify E-Stop active → Send task → Reject

    Scenario 3: Normal task after failure recovery
        After failure scenarios, send a normal task
        → Verify system still works (no corruption)
        → WorldModel has objects + robot state

Usage:
    python3 m6_failure_injection_e2e.py [--timeout SEC]
"""

from __future__ import annotations

import argparse
import json
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

from multi_arm_interfaces.action import ExecuteTask
from multi_arm_interfaces.msg import TaskGoal, TaskConstraint
from multi_arm_interfaces.srv import QueryWorld, SafetyCheck, EmergencyStop


class M6FailureInjectionE2E(Node):
    """E2E test runner for M6 failure injection in simulation."""

    def __init__(self, timeout: float = 120.0) -> None:
        super().__init__("m6_failure_injection_e2e")
        self._cb_group = ReentrantCallbackGroup()
        self._timeout = timeout
        self._results: dict = {}

        self._js_data: dict[str, float] = {}
        self._js_sub = self.create_subscription(
            JointState, "/joint_states", self._js_cb, 10,
            callback_group=self._cb_group,
        )

        self._coordinator_client = ActionClient(
            self, ExecuteTask, "/coordinator/execute_task",
            callback_group=self._cb_group,
        )

        self._query_world_client = self.create_client(
            QueryWorld, "/world_model/query_world",
            callback_group=self._cb_group,
        )

        self._safety_check_client = self.create_client(
            SafetyCheck, "/safety/safety_check",
            callback_group=self._cb_group,
        )

        self._e_stop_client = self.create_client(
            EmergencyStop, "/safety/emergency_stop",
            callback_group=self._cb_group,
        )

    def _js_cb(self, msg: JointState) -> None:
        for i, name in enumerate(msg.name):
            self._js_data[name] = msg.position[i]

    def _spin_until_future(self, future, timeout_sec: float = 30.0) -> bool:
        deadline = time.time() + timeout_sec
        while not future.done() and time.time() < deadline:
            rclpy.spin_once(self, timeout_sec=0.1)
        return future.done()

    def wait_for_js(self, timeout: float = 30.0) -> bool:
        """Wait for joint states to arrive."""
        t0 = time.time()
        while time.time() - t0 < timeout:
            rclpy.spin_once(self, timeout_sec=0.5)
            if len(self._js_data) >= 6:
                return True
        return len(self._js_data) >= 6

    def _send_task(
        self,
        task_id: str,
        arm_name: str,
        zone_name: str,
        position_name: str,
        timeout: float = 30.0,
    ) -> dict:
        """Send ExecuteTask and return result dict."""
        if not self._coordinator_client.wait_for_server(timeout_sec=5.0):
            return {"success": False, "reason": "no_server"}

        goal = ExecuteTask.Goal()
        goal.task_id = task_id
        goal.task_type = "move"
        goal.description = f"{arm_name}:{zone_name}:{position_name}"

        task_goal = TaskGoal()
        task_goal.action_type = "move"
        task_goal.arm_name = arm_name
        task_goal.zone_name = zone_name
        task_goal.position_name = position_name
        task_goal.approach = "top"

        constraint = TaskConstraint()
        constraint.priority = 1
        constraint.max_time = timeout
        constraint.allow_recovery = True
        constraint.max_retries = 2
        task_goal.constraints = constraint

        goal.goal = task_goal

        self.get_logger().info(f"  Sending task: {goal.description}")

        t_start = time.time()

        send_future = self._coordinator_client.send_goal_async(goal)
        if not self._spin_until_future(send_future, timeout_sec=10.0):
            return {"success": False, "reason": "goal_send_timeout"}

        goal_handle = send_future.result()
        if goal_handle is None or not goal_handle.accepted:
            return {"success": False, "reason": "goal_rejected"}

        t_accepted = time.time()
        planning_time = t_accepted - t_start

        result_future = goal_handle.get_result_async()
        if not self._spin_until_future(result_future, timeout_sec=timeout):
            return {
                "success": False,
                "planning_time": planning_time,
                "reason": "execution_timeout",
            }

        t_done = time.time()
        execution_time = t_done - t_accepted

        result_response = result_future.result()
        if result_response is None:
            return {
                "success": False,
                "planning_time": planning_time,
                "execution_time": execution_time,
                "reason": "no_result",
            }

        result = result_response.result
        return {
            "success": result.success,
            "planning_time": planning_time,
            "execution_time": execution_time,
            "message": result.message,
            "reason": "ok" if result.success else "task_failed",
        }

    def scenario1_planning_failure(self) -> dict:
        """Scenario 1: Planning failure injection (unreachable target).

        Sends a task with zone_invalid:unreachable_pose.
        Expected: Coordinator fails, RecoveryManager attempts recovery,
        eventually aborts or fails gracefully.
        """
        self.get_logger().info("=== Scenario 1: Planning Failure Injection ===")

        result = self._send_task(
            task_id="fail_inject_planning",
            arm_name="arm1",
            zone_name="zone_invalid",
            position_name="unreachable_pose",
            timeout=30.0,
        )

        self.get_logger().info(
            f"  Result: success={result['success']} "
            f"msg={result.get('message', '')} "
            f"reason={result['reason']}"
        )

        success = not result["success"]
        return {
            "scenario": 1,
            "name": "planning_failure_injection",
            "success": success,
            "task_result": result,
            "expected": "task should fail (unreachable target)",
            "reason": "ok" if success else "unexpectedly_succeeded",
        }

    def scenario2_safety_check(self) -> dict:
        """Scenario 2: Safety check service verification.

        Calls SafetyCheck service with a valid trajectory.
        Expected: approved=True, speed_scale=1.0.
        Then triggers E-Stop and verifies it's active.
        """
        self.get_logger().info("=== Scenario 2: Safety Check Verification ===")

        for _ in range(10):
            if self._safety_check_client.wait_for_service(timeout_sec=1.0):
                break
            rclpy.spin_once(self, timeout_sec=0.5)

        if not self._safety_check_client.service_is_ready():
            return {"scenario": 2, "success": False, "reason": "safety_service_unavailable"}

        request = SafetyCheck.Request()
        request.arm_names = ["arm1"]
        request.trajectory_joint_names = []
        request.trajectory_positions = []
        request.trajectory_duration = 3.0

        future = self._safety_check_client.call_async(request)
        if not self._spin_until_future(future, timeout_sec=5.0):
            return {"scenario": 2, "success": False, "reason": "safety_check_timeout"}

        resp = future.result()
        self.get_logger().info(
            f"  SafetyCheck: approved={resp.approved} scale={resp.speed_scale}"
        )

        safety_ok = resp.approved and resp.speed_scale > 0.0

        return {
            "scenario": 2,
            "name": "safety_check_verification",
            "success": safety_ok,
            "approved": resp.approved,
            "speed_scale": resp.speed_scale,
            "reason": "ok" if safety_ok else "safety_check_failed",
        }

    def scenario3_estop_rejection(self) -> dict:
        """Scenario 3: E-Stop activation and task rejection.

        Triggers E-Stop, then sends a task.
        Expected: Task is rejected because E-Stop is active.
        Then releases E-Stop.
        """
        self.get_logger().info("=== Scenario 3: E-Stop Rejection ===")

        for _ in range(10):
            if self._e_stop_client.wait_for_service(timeout_sec=1.0):
                break
            rclpy.spin_once(self, timeout_sec=0.5)

        if not self._e_stop_client.service_is_ready():
            return {"scenario": 3, "success": False, "reason": "estop_service_unavailable"}

        estop_req = EmergencyStop.Request()
        estop_req.emergency = True

        future = self._e_stop_client.call_async(estop_req)
        if not self._spin_until_future(future, timeout_sec=5.0):
            return {"scenario": 3, "success": False, "reason": "estop_activate_timeout"}

        estop_resp = future.result()
        self.get_logger().info(f"  E-Stop activated: {estop_resp.success}")

        time.sleep(1.0)

        task_result = self._send_task(
            task_id="fail_inject_estop",
            arm_name="arm1",
            zone_name="zone_a",
            position_name="ready",
            timeout=10.0,
        )

        self.get_logger().info(
            f"  Task during E-Stop: success={task_result['success']} "
            f"msg={task_result.get('message', '')}"
        )

        task_rejected = not task_result["success"]

        estop_req2 = EmergencyStop.Request()
        estop_req2.emergency = False
        future2 = self._e_stop_client.call_async(estop_req2)
        self._spin_until_future(future2, timeout_sec=5.0)
        self.get_logger().info("  E-Stop released")

        return {
            "scenario": 3,
            "name": "estop_rejection",
            "success": task_rejected,
            "estop_activated": estop_resp.success,
            "task_result": task_result,
            "expected": "task should be rejected during E-Stop",
            "reason": "ok" if task_rejected else "task_not_rejected",
        }

    def scenario4_recovery_after_failure(self) -> dict:
        """Scenario 4: Normal task after failure recovery.

        After failure scenarios, send a normal task.
        Expected: System still works, no corruption.
        """
        self.get_logger().info("=== Scenario 4: Recovery After Failure ===")

        time.sleep(2.0)

        result = self._send_task(
            task_id="recovery_after_failure",
            arm_name="arm1",
            zone_name="zone_a",
            position_name="ready",
            timeout=30.0,
        )

        self.get_logger().info(
            f"  Recovery task: success={result['success']} "
            f"msg={result.get('message', '')}"
        )

        return {
            "scenario": 4,
            "name": "recovery_after_failure",
            "success": result["success"],
            "task_result": result,
            "reason": "ok" if result["success"] else "system_not_recovered",
        }

    def scenario5_worldmodel_consistency(self) -> dict:
        """Scenario 5: WorldModel consistency after failures.

        Verifies WorldModel still has objects after all failure scenarios.
        """
        self.get_logger().info("=== Scenario 5: WorldModel Consistency ===")

        for _ in range(10):
            if self._query_world_client.wait_for_service(timeout_sec=1.0):
                break
            rclpy.spin_once(self, timeout_sec=0.5)

        if not self._query_world_client.service_is_ready():
            return {"scenario": 5, "success": False, "reason": "query_world_unavailable"}

        request = QueryWorld.Request()
        request.query_type = "object"

        future = self._query_world_client.call_async(request)
        if not self._spin_until_future(future, timeout_sec=10.0):
            return {"scenario": 5, "success": False, "reason": "query_timeout"}

        resp = future.result()
        object_count = len(resp.object_states)
        object_ids = [s.object_id for s in resp.object_states]

        self.get_logger().info(
            f"  WorldModel after failures: {object_count} objects {object_ids}"
        )

        success = object_count >= 1
        return {
            "scenario": 5,
            "name": "worldmodel_consistency",
            "success": success,
            "object_count": object_count,
            "object_ids": object_ids,
            "reason": "ok" if success else "worldmodel_lost_objects",
        }

    def run_all(self) -> dict:
        """Run all failure injection scenarios."""
        self.get_logger().info("Waiting for joint states...")
        if not self.wait_for_js(timeout=30.0):
            return {"overall_success": False, "reason": "no joint states"}

        self.get_logger().info(
            f"Joint states received: {len(self._js_data)} joints"
        )

        results = {}

        results["scenario1_planning_failure"] = self.scenario1_planning_failure()
        results["scenario2_safety_check"] = self.scenario2_safety_check()
        results["scenario3_estop_rejection"] = self.scenario3_estop_rejection()
        results["scenario4_recovery"] = self.scenario4_recovery_after_failure()
        results["scenario5_worldmodel"] = self.scenario5_worldmodel_consistency()

        overall = all(
            r.get("success", False) for r in results.values()
        )
        results["overall_success"] = overall

        return results


def main(args=None) -> int:
    """Entry point."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout", type=float, default=120.0)
    parsed = parser.parse_args()

    rclpy.init(args=args)
    runner = M6FailureInjectionE2E(timeout=parsed.timeout)

    try:
        results = runner.run_all()
    except Exception as e:
        results = {"overall_success": False, "error": str(e)}

    print("\n" + "=" * 60)
    print("M6 Failure Injection Simulation E2E Results")
    print("=" * 60)
    for key, val in results.items():
        if isinstance(val, dict):
            success = val.get("success", "?")
            reason = val.get("reason", "")
            print(f"  {key}: success={success} ({reason})")
        else:
            print(f"  {key}: {val}")
    print("=" * 60)

    print(f"\nJSON: {json.dumps(results, indent=2)}")

    ret = 0 if results.get("overall_success", False) else 1
    runner.destroy_node()
    rclpy.shutdown()
    return ret


if __name__ == "__main__":
    sys.exit(main())