"""M6 Domain Randomization Benchmark E2E — Phase 4.

Runs random tasks against the M6 simulation stack and records
benchmark metrics. Tests whether the system generalizes across
different objects, locations, arms, and approaches.

Uses a single persistent ActionClient with retry on "Arm is WORKING".
Requires thorough process cleanup between test runs to avoid
multiple action server issues.

Usage:
    python3 m6_domain_randomization_e2e.py [--episodes N] [--timeout SEC]
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
from multi_arm_benchmark.random_task_generator import RandomTaskGenerator
from multi_arm_benchmark.benchmark_recorder import BenchmarkRecorder


class M6DomainRandomizationE2E(Node):
    """E2E runner for M6 domain randomization benchmark."""

    def __init__(self, episodes: int = 10, timeout: float = 30.0) -> None:
        super().__init__("m6_domain_randomization_e2e")
        self._cb_group = ReentrantCallbackGroup()
        self._episodes = episodes
        self._timeout = timeout
        self._generator = RandomTaskGenerator(seed=42)
        self._recorder = BenchmarkRecorder(
            db_path="/tmp/m6_domain_randomization.db"
        )
        self._results: list[dict] = []

        self._js_data: dict[str, float] = {}
        self._js_sub = self.create_subscription(
            JointState, "/joint_states", self._js_cb, 10,
            callback_group=self._cb_group,
        )

        self._client = ActionClient(
            self, ExecuteTask, "/coordinator/execute_task",
            callback_group=self._cb_group,
        )

    def _js_cb(self, msg: JointState) -> None:
        for i, name in enumerate(msg.name):
            self._js_data[name] = msg.position[i]

    def _spin_until_future(self, future, timeout_sec: float = 30.0) -> bool:
        deadline = time.time() + timeout_sec
        while not future.done() and time.time() < deadline:
            rclpy.spin_once(self, timeout_sec=0.05)
        return future.done()

    def wait_for_js(self, timeout: float = 30.0) -> bool:
        """Wait for joint states to arrive."""
        t0 = time.time()
        while time.time() - t0 < timeout:
            rclpy.spin_once(self, timeout_sec=0.5)
            if len(self._js_data) >= 6:
                return True
        return len(self._js_data) >= 6

    def execute_task(self, task_params: dict) -> dict:
        """Send ExecuteTask to Coordinator and return result.

        Retries on "Arm is WORKING" rejection with exponential backoff.

        Args:
            task_params: Dict from RandomTaskGenerator.

        Returns:
            Dict with success, planning_time, execution_time, message.
        """
        if not self._client.wait_for_server(timeout_sec=10.0):
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

        constraint = TaskConstraint()
        constraint.priority = 1
        constraint.max_time = self._timeout
        constraint.allow_recovery = True
        constraint.max_retries = 2
        task_goal.constraints = constraint

        goal.goal = task_goal

        max_retries = 3
        for attempt in range(max_retries):
            t_start = time.time()

            send_future = self._client.send_goal_async(goal)
            if not self._spin_until_future(send_future, timeout_sec=10.0):
                return {
                    "success": False, "planning_time": 0.0,
                    "execution_time": 0.0, "message": "goal_send_timeout",
                }

            goal_handle = send_future.result()
            if goal_handle is None or not goal_handle.accepted:
                t_now = time.time()
                return {
                    "success": False, "planning_time": 0.0,
                    "execution_time": t_now - t_start, "message": "goal_rejected",
                }

            t_accepted = time.time()
            planning_time = t_accepted - t_start

            result_future = goal_handle.get_result_async()
            if not self._spin_until_future(result_future, timeout_sec=self._timeout):
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
            msg = result.message

            if not result.success and "WORKING" in msg and attempt < max_retries - 1:
                wait = 2.0 * (attempt + 1)
                self.get_logger().info(f"  Arm busy, retry {attempt+1} after {wait}s")
                time.sleep(wait)
                continue

            return {
                "success": result.success,
                "planning_time": planning_time,
                "execution_time": execution_time,
                "message": msg,
            }

        return {
            "success": False, "planning_time": 0.0,
            "execution_time": 0.0, "message": "max_retries_exceeded",
        }

    def run_benchmark(self) -> dict:
        """Run domain randomization benchmark.

        Returns:
            Dict with benchmark results.
        """
        self.get_logger().info("Waiting for joint states...")
        if not self.wait_for_js(timeout=30.0):
            return {"overall_success": False, "reason": "no joint states"}

        self.get_logger().info(
            f"Joint states received: {len(self._js_data)} joints"
        )

        if not self._client.wait_for_server(timeout_sec=10.0):
            return {"overall_success": False, "reason": "no coordinator"}

        n = self._episodes
        self.get_logger().info(
            f"=== Domain Randomization Benchmark: {n} episodes ==="
        )

        run_id = self._recorder.start_run(
            "m6_domain_randomization",
            metadata={"episodes": n, "seed": 42},
        )

        tasks = self._generator.generate_batch(n)

        success_count = 0
        planning_times: list[float] = []
        execution_times: list[float] = []
        failure_reasons: list[str] = []

        for i, task in enumerate(tasks):
            task["arm_name"] = "left_arm"
            task["description"] = f"left_arm:{task['zone_name']}:{task['position_name']}"

            self.get_logger().info(
                f"  [{i+1}/{n}] {task['description']} "
                f"(pos={task['position_name']})"
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

            if result["success"]:
                success_count += 1
            else:
                failure_reasons.append(result["message"])

            planning_times.append(result["planning_time"])
            execution_times.append(result["execution_time"])

            self._results.append({
                "task_id": task["task_id"],
                "description": task["description"],
                "arm": task["arm_name"],
                "position": task["position_name"],
                "action_type": task["action_type"],
                "success": result["success"],
                "planning_time": result["planning_time"],
                "execution_time": result["execution_time"],
                "message": result["message"],
            })

            self.get_logger().info(
                f"    -> success={result['success']} "
                f"plan={result['planning_time']:.3f}s "
                f"exec={result['execution_time']:.3f}s "
                f"msg={result['message']}"
            )

            time.sleep(3.0)

        self._recorder.end_run(run_id)

        success_rate = success_count / n if n > 0 else 0.0
        avg_planning = sum(planning_times) / len(planning_times) if planning_times else 0.0
        avg_execution = sum(execution_times) / len(execution_times) if execution_times else 0.0

        self._recorder.get_run_summary(run_id)
        self._recorder.close()

        result = {
            "episodes": n,
            "success_count": success_count,
            "failure_count": n - success_count,
            "success_rate": success_rate,
            "avg_planning_time": avg_planning,
            "avg_execution_time": avg_execution,
            "failure_reasons": failure_reasons[:10],
            "run_id": run_id,
            "db_path": "/tmp/m6_domain_randomization.db",
            "per_task": self._results,
            "overall_success": success_rate >= 0.6,
        }

        self.get_logger().info(
            f"=== Benchmark Complete: {success_count}/{n} "
            f"({success_rate*100:.1f}%) ==="
        )

        return result


def main(args=None) -> int:
    """Entry point."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--episodes", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=30.0)
    parsed = parser.parse_args()

    rclpy.init(args=args)
    runner = M6DomainRandomizationE2E(
        episodes=parsed.episodes,
        timeout=parsed.timeout,
    )

    try:
        results = runner.run_benchmark()
    except Exception as e:
        results = {"overall_success": False, "error": str(e)}

    print("\n" + "=" * 60)
    print("M6 Domain Randomization Benchmark Results")
    print("=" * 60)
    if "error" in results:
        print(f"  ERROR: {results['error']}")
    else:
        print(f"  Episodes: {results['episodes']}")
        print(f"  Success: {results['success_count']}/{results['episodes']}")
        print(f"  Success Rate: {results['success_rate']*100:.1f}%")
        print(f"  Avg Planning Time: {results['avg_planning_time']:.3f}s")
        print(f"  Avg Execution Time: {results['avg_execution_time']:.3f}s")
        if results["failure_reasons"]:
            print(f"  Failure Reasons (first 10): {results['failure_reasons']}")
        print(f"  DB: {results['db_path']}")
    print("=" * 60)

    print(f"\nJSON: {json.dumps(results, indent=2)}")

    ret = 0 if results.get("overall_success", False) else 1
    runner.destroy_node()
    rclpy.shutdown()
    return ret


if __name__ == "__main__":
    sys.exit(main())
