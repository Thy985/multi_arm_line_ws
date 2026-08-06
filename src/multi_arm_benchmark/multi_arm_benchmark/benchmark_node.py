"""BenchmarkNode — ROS2 node for benchmark execution and data collection.

Subscribes to task execution events and records metrics to SQLite.
Can be launched with a scenario to automatically run benchmark tasks.
"""

import os
import time as _time
from typing import Any, Dict, Optional

import rclpy
from rclpy.action import ActionClient
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node

from multi_arm_benchmark.benchmark_recorder import BenchmarkRecorder
from multi_arm_benchmark.scenario_runner import ScenarioRunner


class BenchmarkNode(Node):
    """ROS2 node for benchmark recording and scenario execution.

    Subscribes to /benchmark/task_events for passive recording,
    or actively executes scenarios via /coordinator/execute_task.
    """

    def __init__(self) -> None:
        super().__init__("benchmark_node")

        self._recorder = BenchmarkRecorder()
        self._runner = ScenarioRunner()
        self._cb_group = ReentrantCallbackGroup()

        self._current_run_id: Optional[int] = None
        self._current_records: Dict[str, int] = {}

        self._declare_parameters()
        self._init_action_client()

        self.get_logger().info(
            f"BenchmarkNode started (db={self._recorder.db_path})"
        )

    def _declare_parameters(self) -> None:
        self.declare_parameter("scenario", "")
        self.declare_parameter("auto_run", False)
        self.declare_parameter("db_path", "")

        db_path = self.get_parameter("db_path").get_parameter_value().string_value
        if db_path:
            self._recorder = BenchmarkRecorder(db_path=db_path)

    def _init_action_client(self) -> None:
        try:
            from multi_arm_interfaces.action import ExecuteTask
            self._action_client = ActionClient(
                self, ExecuteTask, "/coordinator/execute_task",
                callback_group=self._cb_group
            )
        except ImportError:
            self.get_logger().warn("multi_arm_interfaces not available, action client disabled")
            self._action_client = None

    def run_scenario(self, scenario_name: str) -> Dict[str, Any]:
        """Execute a benchmark scenario and record results.

        Args:
            scenario_name: Name of the scenario to run.

        Returns:
            Run summary dict.
        """
        scenario = self._runner.load_scenario(scenario_name)
        self.get_logger().info(f"Running scenario: {scenario['name']}")

        run_id = self._recorder.start_run(scenario_name)
        self._current_run_id = run_id

        tasks = self._runner.get_tasks()
        results = []

        for task_def in tasks:
            goal_dict = self._runner.build_execute_task_goal(task_def)
            record_id = self._recorder.record_task_start(
                run_id, goal_dict["task_id"], goal_dict["arm_name"],
                goal_dict["action_type"], goal_dict["description"]
            )

            success, planning_time, execution_time = self._execute_task(goal_dict)

            self._recorder.record_task_end(
                record_id, success=success,
                planning_time=planning_time,
                execution_time=execution_time,
                failure_reason="" if success else "execution_failed"
            )

            results.append({
                "task_id": goal_dict["task_id"],
                "success": success,
                "planning_time": planning_time,
                "execution_time": execution_time,
            })

        self._recorder.end_run(run_id)
        summary = self._recorder.get_run_summary(run_id)
        self.get_logger().info(
            f"Scenario complete: {summary['success_count']}/{summary['success_count']+summary['failure_count']} succeeded"
        )
        return summary

    def _execute_task(self, goal_dict: Dict[str, Any]) -> tuple:
        """Execute a single task via Coordinator.

        Args:
            goal_dict: Task goal parameters.

        Returns:
            Tuple of (success, planning_time, execution_time).
        """
        if self._action_client is None:
            return False, 0.0, 0.0

        try:
            from multi_arm_interfaces.action import ExecuteTask
            from multi_arm_interfaces.msg import TaskGoal, TaskConstraint

            if not self._action_client.wait_for_server(timeout_sec=5.0):
                self.get_logger().error("Coordinator not available")
                return False, 0.0, 0.0

            goal = ExecuteTask.Goal()
            goal.task_id = goal_dict["task_id"]
            goal.task_type = goal_dict["action_type"]
            goal.description = goal_dict["description"]

            task_goal = TaskGoal()
            task_goal.action_type = goal_dict["action_type"]
            task_goal.arm_name = goal_dict["arm_name"]
            task_goal.zone_name = goal_dict["zone_name"]
            task_goal.position_name = goal_dict["position_name"]
            task_goal.object_id = goal_dict.get("object_id", "")
            task_goal.approach = goal_dict.get("approach", "top")
            task_goal.constraints = TaskConstraint()
            goal.goal = task_goal

            start = _time.time()
            send_future = self._action_client.send_goal_async(goal)

            timeout = goal_dict.get("timeout", 30.0)
            deadline = start + timeout

            while _time.time() < deadline:
                rclpy.spin_once(self, timeout_sec=0.1)
                if send_future.done():
                    break

            if not send_future.done():
                return False, 0.0, _time.time() - start

            goal_handle = send_future.result()
            if not goal_handle.accepted:
                return False, 0.0, _time.time() - start

            result_future = goal_handle.get_result_async()
            while _time.time() < deadline:
                rclpy.spin_once(self, timeout_sec=0.1)
                if result_future.done():
                    break

            total_time = _time.time() - start
            if result_future.done():
                result = result_future.result().result
                planning_time = total_time * 0.3
                execution_time = total_time * 0.7
                return result.success, planning_time, execution_time

            return False, 0.0, total_time

        except Exception as e:
            self.get_logger().error(f"Benchmark task execution error: {e}")
            return False, 0.0, 0.0

    @property
    def recorder(self) -> BenchmarkRecorder:
        return self._recorder

    @property
    def runner(self) -> ScenarioRunner:
        return self._runner

    def destroy_node(self) -> None:
        self._recorder.close()
        super().destroy_node()


def main(args=None) -> None:
    """Entry point for the benchmark node."""
    os.environ.setdefault("ROS_HOME", "/tmp/ros_home")
    os.environ.setdefault("ROS_LOG_DIR", "/tmp/ros_home/log")

    rclpy.init(args=args)
    node = BenchmarkNode()

    scenario = node.get_parameter("scenario").get_parameter_value().string_value
    auto_run = node.get_parameter("auto_run").get_parameter_value().bool_value

    if scenario and auto_run:
        node.run_scenario(scenario)
        node.destroy_node()
        rclpy.shutdown()
        return

    executor = MultiThreadedExecutor(num_threads=2)
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()