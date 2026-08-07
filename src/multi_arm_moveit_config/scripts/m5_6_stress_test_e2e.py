#!/usr/bin/env python3
"""M5.6 Gazebo E2E Stress Test.

Runs stress tests against a live Gazebo + MoveIt + Coordinator system.

Levels tested:
  L1: Random task parameter variation (N iterations, real motion)
  L3: Failure injection (unreachable target → RecoveryManager)
  L4: Multi-task priority scheduling

Prerequisite: m4_6_task_loop.launch.py must be running.

Run:
  ros2 launch multi_arm_moveit_config m4_6_task_loop.launch.py
  python3 m5_6_stress_test_e2e.py [--iterations N] [--level L]
"""

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
from multi_arm_core.robot_constants import ARM_JOINT_NAMES, PRESET_POSITIONS
from multi_arm_benchmark.benchmark_recorder import BenchmarkRecorder
from multi_arm_benchmark.random_task_generator import RandomTaskGenerator


class StressTestE2E(Node):

    def __init__(self, iterations=20, db_path=""):
        super().__init__("m56_stress_test_e2e")
        self._cb_group = ReentrantCallbackGroup()
        self._iterations = iterations
        self._recorder = BenchmarkRecorder(db_path=db_path)
        self._generator = RandomTaskGenerator(seed=42)
        self._results = {}

        self.js_data = {}
        self.js_sub = self.create_subscription(
            JointState, "/joint_states", self._js_cb, 10,
            callback_group=self._cb_group,
        )

        self._coordinator_client = ActionClient(
            self, ExecuteTask, "/coordinator/execute_task",
            callback_group=self._cb_group,
        )

    def _js_cb(self, msg):
        for i, name in enumerate(msg.name):
            self.js_data[name] = msg.position[i]

    def wait_for_js(self, timeout=30.0):
        t0 = time.time()
        while time.time() - t0 < timeout:
            rclpy.spin_once(self, timeout_sec=0.5)
            if len(self.js_data) >= 6:
                return True
        return len(self.js_data) >= 6

    def _spin_until_future(self, future, timeout_sec=120.0):
        deadline = time.time() + timeout_sec
        while not future.done() and time.time() < deadline:
            rclpy.spin_once(self, timeout_sec=0.1)
        return future.done()

    def execute_task(self, task_params):
        """Send ExecuteTask to Coordinator with structured TaskGoal.

        Args:
            task_params: Dict from RandomTaskGenerator.

        Returns:
            Dict with success, planning_time, execution_time, message.
        """
        if not self._coordinator_client.wait_for_server(timeout_sec=5.0):
            return {
                "success": False, "planning_time": 0.0,
                "execution_time": 0.0, "message": "no_server",
            }

        goal = ExecuteTask.Goal()
        goal.task_id = task_params["task_id"]
        goal.task_type = task_params["action_type"]
        goal.description = task_params["description"]

        task_goal = TaskGoal()
        task_goal.action_type = task_params["action_type"]
        task_goal.arm_name = task_params["arm_name"]
        task_goal.zone_name = task_params["zone_name"]
        task_goal.position_name = task_params["position_name"]
        task_goal.object_id = task_params.get("object_id", "")
        task_goal.approach = task_params.get("approach", "top")

        if "priority" in task_params:
            constraint = TaskConstraint()
            constraint.priority = task_params["priority"]
            constraint.max_time = task_params.get("timeout", 30.0)
            constraint.allow_recovery = True
            constraint.max_retries = 3
            task_goal.constraints = constraint

        goal.goal = task_goal

        self.get_logger().info(
            f"[{task_params['task_id']}] Sending: {goal.description}"
        )

        t_start = time.time()

        send_future = self._coordinator_client.send_goal_async(goal)
        if not self._spin_until_future(send_future, timeout_sec=15.0):
            return {
                "success": False, "planning_time": 0.0,
                "execution_time": 0.0, "message": "goal_send_timeout",
            }

        goal_handle = send_future.result()
        if goal_handle is None or not goal_handle.accepted:
            return {
                "success": False, "planning_time": 0.0,
                "execution_time": 0.0, "message": "goal_rejected",
            }

        t_accepted = time.time()
        planning_time = t_accepted - t_start

        result_future = goal_handle.get_result_async()
        if not self._spin_until_future(result_future, timeout_sec=120.0):
            return {
                "success": False, "planning_time": planning_time,
                "execution_time": 0.0, "message": "execution_timeout",
            }

        t_done = time.time()
        execution_time = t_done - t_accepted

        result_response = result_future.result()
        if result_response is None:
            return {
                "success": False, "planning_time": planning_time,
                "execution_time": execution_time, "message": "no_result",
            }

        result = result_response.result
        return {
            "success": result.success,
            "planning_time": planning_time,
            "execution_time": execution_time,
            "message": result.message,
        }

    def verify_position(self, arm_name, position_name, tol=0.3):
        """Verify arm joint positions match a preset position."""
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
                all_ok = False
            elif abs(actual - exp_val) > tol:
                all_ok = False
        return all_ok

    def run_level1(self, iterations=None):
        """Level 1: Random task parameter variation with real motion."""
        n = iterations or self._iterations
        self.get_logger().info(f"=== L1: Random tasks ({n} iterations) ===")

        run_id = self._recorder.start_run("e2e_stress_level1")
        tasks = self._generator.generate_batch(n)

        success_count = 0
        planning_times = []
        execution_times = []
        failure_reasons = []

        for i, task in enumerate(tasks):
            self.get_logger().info(f"L1 [{i+1}/{n}] {task['description']}")

            result = self.execute_task(task)

            record_id = self._recorder.record_task_start(
                run_id, task["task_id"], task["arm_name"],
                task["action_type"], task["description"],
            )
            self._recorder.record_task_end(
                record_id,
                success=result["success"],
                planning_time=result["planning_time"],
                execution_time=result["execution_time"],
                failure_reason="" if result["success"] else result["message"],
            )

            if result["success"]:
                success_count += 1
            else:
                failure_reasons.append(result["message"])

            planning_times.append(result["planning_time"])
            execution_times.append(result["execution_time"])

            self.get_logger().info(
                f"  → success={result['success']} "
                f"plan={result['planning_time']:.2f}s "
                f"exec={result['execution_time']:.2f}s "
                f"msg={result['message']}"
            )

            time.sleep(1.0)

        self._recorder.end_run(run_id)

        total = len(tasks)
        result = {
            "level": 1,
            "iterations": total,
            "success_count": success_count,
            "failure_count": total - success_count,
            "success_rate": success_count / total if total > 0 else 0.0,
            "avg_planning_time": (
                sum(planning_times) / len(planning_times) if planning_times else 0.0
            ),
            "avg_execution_time": (
                sum(execution_times) / len(execution_times) if execution_times else 0.0
            ),
            "failure_reasons": failure_reasons,
            "run_id": run_id,
        }
        self._results["level1"] = result
        self.get_logger().info(
            f"L1 done: {success_count}/{total} success "
            f"({result['success_rate']*100:.1f}%)"
        )
        return result

    def run_level3_planning_failure(self):
        """Level 3: Planning failure injection (unreachable target)."""
        self.get_logger().info("=== L3: Planning failure injection ===")

        run_id = self._recorder.start_run("e2e_stress_level3_planning")

        task = self._generator.generate_unreachable_task()
        self.get_logger().info(f"L3 planning: {task['description']}")

        result = self.execute_task(task)

        record_id = self._recorder.record_task_start(
            run_id, task["task_id"], task["arm_name"],
            task["action_type"], task["description"],
        )
        self._recorder.record_task_end(
            record_id,
            success=result["success"],
            planning_time=result["planning_time"],
            execution_time=result["execution_time"],
            failure_reason=result["message"],
            recovery_count=1 if not result["success"] else 0,
        )

        self._recorder.end_run(run_id)

        summary = {
            "level": 3,
            "failure_type": "planning_failure",
            "success": result["success"],
            "message": result["message"],
            "planning_time": result["planning_time"],
            "execution_time": result["execution_time"],
            "run_id": run_id,
        }
        self._results["level3_planning"] = summary
        self.get_logger().info(
            f"L3 planning: success={result['success']} msg={result['message']}"
        )
        return summary

    def run_level3_safety(self):
        """Level 3: Safety check verification (velocity scale test)."""
        self.get_logger().info("=== L3: Safety check verification ===")

        from multi_arm_interfaces.srv import SafetyCheck

        client = self.create_client(
            SafetyCheck, "/safety/safety_check",
            callback_group=self._cb_group,
        )

        for _ in range(10):
            if client.wait_for_service(timeout_sec=1.0):
                break
            rclpy.spin_once(self, timeout_sec=0.5)

        if not client.service_is_ready():
            self.get_logger().warn("SafetyCheck not ready, skipping L3 safety")
            self._results["level3_safety"] = {
                "level": 3, "failure_type": "safety_violation",
                "status": "skipped", "message": "service_not_ready",
            }
            return self._results["level3_safety"]

        request = SafetyCheck.Request()
        request.arm_names = ["arm1"]
        request.trajectory_joint_names = []
        request.trajectory_positions = []
        request.trajectory_duration = 3.0

        future = client.call_async(request)
        if not self._spin_until_future(future, timeout_sec=5.0):
            self._results["level3_safety"] = {
                "level": 3, "failure_type": "safety_violation",
                "status": "timeout", "message": "service_timeout",
            }
            return self._results["level3_safety"]

        resp = future.result()
        summary = {
            "level": 3,
            "failure_type": "safety_violation",
            "approved": resp.approved,
            "speed_scale": resp.speed_scale,
            "status": "verified",
        }
        self._results["level3_safety"] = summary
        self.get_logger().info(
            f"L3 safety: approved={resp.approved} scale={resp.speed_scale}"
        )
        return summary

    def run_level4_multi_task(self, task_count=3):
        """Level 4: Multi-task priority scheduling."""
        self.get_logger().info(f"=== L4: Multi-task scheduling ({task_count} tasks) ===")

        run_id = self._recorder.start_run("e2e_stress_level4_multi_task")

        tasks = self._generator.generate_multi_task_queue(task_count)
        expected_order = sorted(tasks, key=lambda t: t["priority"], reverse=True)

        execution_order = []
        for task in tasks:
            self.get_logger().info(
                f"L4: {task['task_id']} pri={task['priority']} "
                f"{task['description']}"
            )

            result = self.execute_task(task)

            record_id = self._recorder.record_task_start(
                run_id, task["task_id"], task["arm_name"],
                task["action_type"], task["description"],
            )
            self._recorder.record_task_end(
                record_id,
                success=result["success"],
                planning_time=result["planning_time"],
                execution_time=result["execution_time"],
                failure_reason="" if result["success"] else result["message"],
            )

            execution_order.append({
                "task_id": task["task_id"],
                "priority": task["priority"],
                "success": result["success"],
                "message": result["message"],
            })

            time.sleep(1.0)

        self._recorder.end_run(run_id)

        all_success = all(e["success"] for e in execution_order)
        summary = {
            "level": 4,
            "task_count": task_count,
            "all_success": all_success,
            "execution_order": execution_order,
            "expected_priority_order": [
                {"task_id": t["task_id"], "priority": t["priority"]}
                for t in expected_order
            ],
            "run_id": run_id,
        }
        self._results["level4"] = summary
        self.get_logger().info(
            f"L4 done: all_success={all_success}"
        )
        return summary

    def run_all_levels(self):
        """Run all E2E stress test levels."""
        self.run_level1()
        self.run_level3_planning_failure()
        self.run_level3_safety()
        self.run_level4_multi_task()
        return self._results

    @property
    def results(self):
        return self._results

    def close(self):
        self._recorder.close()


def _print_results(results):
    print("\n" + "=" * 60)
    print("M5.6 Gazebo E2E Stress Test Results")
    print("=" * 60)

    for level_key, data in sorted(results.items()):
        level = data.get("level", "?")
        print(f"\n--- Level {level} ({level_key}) ---")

        if level_key == "level1":
            print(f"  Iterations: {data['iterations']}")
            print(f"  Success: {data['success_count']}/{data['iterations']}")
            print(f"  Success Rate: {data['success_rate']*100:.1f}%")
            print(f"  Avg Planning Time: {data['avg_planning_time']:.3f}s")
            print(f"  Avg Execution Time: {data['avg_execution_time']:.3f}s")
            if data["failure_reasons"]:
                print(f"  Failure Reasons: {data['failure_reasons'][:5]}")

        elif level_key == "level3_planning":
            print(f"  Failure Type: {data['failure_type']}")
            print(f"  Success: {data['success']}")
            print(f"  Message: {data['message']}")

        elif level_key == "level3_safety":
            print(f"  Failure Type: {data['failure_type']}")
            print(f"  Status: {data['status']}")
            if "approved" in data:
                print(f"  Approved: {data['approved']}")
                print(f"  Speed Scale: {data['speed_scale']}")

        elif level_key == "level4":
            print(f"  Task Count: {data['task_count']}")
            print(f"  All Success: {data['all_success']}")
            for entry in data["execution_order"]:
                print(f"    {entry['task_id']} pri={entry['priority']} "
                      f"success={entry['success']}")

    print("\n" + "=" * 60)
    overall_pass = True
    if "level1" in results and results["level1"]["success_rate"] < 0.5:
        overall_pass = False
    if "level3_planning" in results and results["level3_planning"]["success"]:
        overall_pass = False
    if "level4" in results and not results["level4"]["all_success"]:
        overall_pass = False
    print(f"Overall: {'PASS' if overall_pass else 'NEEDS REVIEW'}")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="M5.6 Gazebo E2E Stress Test")
    parser.add_argument(
        "--iterations", type=int, default=20,
        help="Number of L1 random task iterations (default: 20)",
    )
    parser.add_argument(
        "--level", type=str, default="all",
        choices=["all", "1", "3", "3p", "3s", "4"],
        help="Which level to run (default: all)",
    )
    parser.add_argument(
        "--db-path", type=str, default="",
        help="Path to benchmark SQLite DB (default: auto)",
    )
    args = parser.parse_args()

    rclpy.init()
    node = StressTestE2E(iterations=args.iterations, db_path=args.db_path)

    node.get_logger().info("=== M5.6 Gazebo E2E Stress Test ===")
    node.get_logger().info(f"Waiting for joint_states (Gazebo must be running)...")

    if not node.wait_for_js(timeout=30.0):
        node.get_logger().error(
            "No joint_states received! Is Gazebo simulation running?"
        )
        node.get_logger().error(
            "Start with: ros2 launch multi_arm_moveit_config "
            "m4_6_task_loop.launch.py"
        )
        rclpy.shutdown()
        sys.exit(1)

    node.get_logger().info(f"JS received: {len(node.js_data)} joints")

    if not node._coordinator_client.wait_for_server(timeout_sec=10.0):
        node.get_logger().error("Coordinator ExecuteTask server not available!")
        rclpy.shutdown()
        sys.exit(1)

    node.get_logger().info("Coordinator available, starting stress tests...")

    if args.level == "all":
        node.run_all_levels()
    elif args.level == "1":
        node.run_level1()
    elif args.level == "3":
        node.run_level3_planning_failure()
        node.run_level3_safety()
    elif args.level == "3p":
        node.run_level3_planning_failure()
    elif args.level == "3s":
        node.run_level3_safety()
    elif args.level == "4":
        node.run_level4_multi_task()

    _print_results(node.results)
    node.close()
    rclpy.shutdown()


if __name__ == "__main__":
    main()