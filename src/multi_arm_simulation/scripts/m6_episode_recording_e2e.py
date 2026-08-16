"""M6 Episode Recording E2E — Phase 5.

Runs tasks against the M6 simulation stack, records complete Episodes
(robot experience), and exports to SQLite + JSON dataset.

This proves the full M6 Experience Infrastructure works in simulation:
    Task → Coordinator → JTC → Gazebo → Episode recorded → Dataset exported

Usage:
    python3 m6_episode_recording_e2e.py [--episodes N] [--timeout SEC]
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
from multi_arm_interfaces.srv import QueryWorld
from multi_arm_benchmark.random_task_generator import RandomTaskGenerator
from multi_arm_experience.experience_recorder import ExperienceRecorder
from multi_arm_experience.dataset_exporter import DatasetExporter


class M6EpisodeRecordingE2E(Node):
    """E2E runner that records robot experience as Episodes."""

    def __init__(self, episodes: int = 5, timeout: float = 30.0) -> None:
        super().__init__("m6_episode_recording_e2e")
        self._cb_group = ReentrantCallbackGroup()
        self._episodes = episodes
        self._timeout = timeout
        self._generator = RandomTaskGenerator(seed=42)
        self._recorder = ExperienceRecorder()

        self._js_data: dict[str, float] = {}
        self._js_sub = self.create_subscription(
            JointState, "/joint_states", self._js_cb, 10,
            callback_group=self._cb_group,
        )

        self._client = ActionClient(
            self, ExecuteTask, "/coordinator/execute_task",
            callback_group=self._cb_group,
        )

        self._world_client = self.create_client(
            QueryWorld, "/world_model/query_world",
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

    def capture_world_snapshot(self) -> dict:
        """Capture current world state from WorldModel."""
        if not self._world_client.service_is_ready():
            return {"objects": {}, "relations": []}

        req = QueryWorld.Request()
        future = self._world_client.call_async(req)
        if not self._spin_until_future(future, timeout_sec=5.0):
            return {"objects": {}, "relations": []}

        resp = future.result()
        if resp is None:
            return {"objects": {}, "relations": []}

        objects = {}
        for obj in resp.scene_state.objects:
            objects[obj.object_id] = {
                "type": obj.object_type,
                "position": list(obj.position),
                "orientation": list(obj.orientation),
            }

        relations = []
        for rel in resp.relations:
            relations.append({
                "subject": rel.subject,
                "predicate": rel.predicate,
                "object": rel.object,
            })

        return {"objects": objects, "relations": relations}

    def execute_task_with_episode(self, task_params: dict) -> dict:
        """Execute a task and record it as an Episode.

        Args:
            task_params: Task parameters dict.

        Returns:
            Dict with episode result info.
        """
        if not self._client.wait_for_server(timeout_sec=10.0):
            return {"success": False, "message": "no_server", "episode_id": ""}

        initial_world = self.capture_world_snapshot()

        skill_name = task_params.get("action_type", "move")
        episode = self._recorder.start_episode(
            task_type=task_params["action_type"],
            skill_name=skill_name,
            robot_id=task_params["arm_name"],
            initial_world=self._recorder.capture_world_snapshot(
                objects=initial_world["objects"],
                relations=initial_world["relations"],
            ),
        )

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

        self._recorder.record_step(
            episode, "send_goal", success=True, duration=0.0,
            task_id=task_params["task_id"],
        )

        t_start = time.time()

        send_future = self._client.send_goal_async(goal)
        if not self._spin_until_future(send_future, timeout_sec=10.0):
            self._recorder.record_step(
                episode, "goal_send", success=False, duration=time.time() - t_start,
            )
            self._recorder.finish_episode(
                episode, result="failure", duration=time.time() - t_start,
            )
            return {"success": False, "message": "goal_send_timeout",
                    "episode_id": episode.episode_id}

        goal_handle = send_future.result()
        if goal_handle is None or not goal_handle.accepted:
            self._recorder.record_step(
                episode, "goal_accepted", success=False, duration=time.time() - t_start,
            )
            self._recorder.finish_episode(
                episode, result="failure", duration=time.time() - t_start,
            )
            return {"success": False, "message": "goal_rejected",
                    "episode_id": episode.episode_id}

        t_accepted = time.time()
        self._recorder.record_step(
            episode, "goal_accepted", success=True, duration=t_accepted - t_start,
        )

        result_future = goal_handle.get_result_async()
        if not self._spin_until_future(result_future, timeout_sec=self._timeout):
            self._recorder.record_step(
                episode, "execution", success=False, duration=time.time() - t_accepted,
                reason="timeout",
            )
            self._recorder.finish_episode(
                episode, result="failure", duration=time.time() - t_start,
            )
            return {"success": False, "message": "execution_timeout",
                    "episode_id": episode.episode_id}

        t_done = time.time()
        exec_duration = t_done - t_accepted

        result_response = result_future.result()
        if result_response is None:
            self._recorder.record_step(
                episode, "execution", success=False, duration=exec_duration,
            )
            self._recorder.finish_episode(
                episode, result="failure", duration=t_done - t_start,
            )
            return {"success": False, "message": "no_result",
                    "episode_id": episode.episode_id}

        result = result_response.result
        msg = result.message

        self._recorder.record_step(
            episode, "execution", success=result.success,
            duration=exec_duration, message=msg,
        )

        if not result.success and "recovery" in msg.lower():
            self._recorder.record_recovery(
                episode, "execution_failure", "recovery_attempted",
                success=False,
            )

        final_world = self.capture_world_snapshot()
        result_str = "success" if result.success else "failure"
        self._recorder.finish_episode(
            episode, result=result_str, duration=t_done - t_start,
            final_world=self._recorder.capture_world_snapshot(
                objects=final_world["objects"],
                relations=final_world["relations"],
            ),
        )

        return {
            "success": result.success,
            "message": msg,
            "episode_id": episode.episode_id,
            "duration": t_done - t_start,
        }

    def run(self) -> dict:
        """Run episode recording E2E.

        Returns:
            Dict with results.
        """
        self.get_logger().info("Waiting for joint states...")
        if not self.wait_for_js(timeout=30.0):
            return {"overall_success": False, "reason": "no joint states"}

        if not self._client.wait_for_server(timeout_sec=10.0):
            return {"overall_success": False, "reason": "no coordinator"}

        n = self._episodes
        self.get_logger().info(f"=== Episode Recording E2E: {n} episodes ===")

        tasks = self._generator.generate_batch(n)

        success_count = 0
        task_results = []

        for i, task in enumerate(tasks):
            task["arm_name"] = "left_arm"
            task["description"] = f"left_arm:{task['zone_name']}:{task['position_name']}"

            self.get_logger().info(
                f"  [{i+1}/{n}] {task['description']} (pos={task['position_name']})"
            )

            result = self.execute_task_with_episode(task)

            if result["success"]:
                success_count += 1

            task_results.append({
                "task_id": task["task_id"],
                "description": task["description"],
                "position": task["position_name"],
                "success": result["success"],
                "message": result["message"],
                "episode_id": result["episode_id"],
                "duration": result.get("duration", 0.0),
            })

            self.get_logger().info(
                f"    -> success={result['success']} "
                f"episode={result['episode_id']} "
                f"msg={result['message']}"
            )

            time.sleep(2.0)

        db_path = "/tmp/m6_episode_recording.db"
        json_dir = "/tmp/m6_episode_dataset"
        exporter = DatasetExporter(db_path=db_path, json_dir=json_dir)
        exported_count = exporter.export_recorder(self._recorder)

        db_episode_count = exporter.get_episode_count()
        db_failure_count = exporter.get_failure_count()
        json_path = os.path.join(json_dir, "experience_dataset.json")
        json_exists = os.path.exists(json_path)

        episodes = self._recorder.get_all_episodes()
        episodes_with_steps = sum(1 for ep in episodes if len(ep.execution_steps) >= 2)
        episodes_with_world = sum(
            1 for ep in episodes
            if ep.initial_world.objects or ep.final_world.objects
        )

        result = {
            "episodes_run": n,
            "success_count": success_count,
            "failure_count": n - success_count,
            "success_rate": success_count / n if n > 0 else 0.0,
            "episodes_recorded": self._recorder.episode_count,
            "failures_recorded": self._recorder.failure_count,
            "episodes_with_steps": episodes_with_steps,
            "episodes_with_world_snapshot": episodes_with_world,
            "exported_to_sqlite": exported_count,
            "db_episode_count": db_episode_count,
            "db_failure_count": db_failure_count,
            "db_path": db_path,
            "json_exported": json_exists,
            "json_path": json_path if json_exists else "",
            "per_task": task_results,
            "overall_success": (
                self._recorder.episode_count == n
                and exported_count == n
                and db_episode_count == n
                and json_exists
                and episodes_with_steps >= n * 0.5
            ),
        }

        self.get_logger().info(
            f"=== Episode Recording Complete: {success_count}/{n} ==="
        )
        self.get_logger().info(
            f"  Episodes recorded: {self._recorder.episode_count}"
        )
        self.get_logger().info(f"  Exported to SQLite: {exported_count}")
        self.get_logger().info(f"  JSON exported: {json_exists}")

        return result


def main(args=None) -> int:
    """Entry point."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--episodes", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=30.0)
    parsed = parser.parse_args()

    rclpy.init(args=args)
    runner = M6EpisodeRecordingE2E(
        episodes=parsed.episodes,
        timeout=parsed.timeout,
    )

    try:
        results = runner.run()
    except Exception as e:
        results = {"overall_success": False, "error": str(e)}

    print("\n" + "=" * 60)
    print("M6 Episode Recording E2E Results")
    print("=" * 60)
    if "error" in results:
        print(f"  ERROR: {results['error']}")
    else:
        print(f"  Episodes Run: {results['episodes_run']}")
        print(f"  Success: {results['success_count']}/{results['episodes_run']}")
        print(f"  Episodes Recorded: {results['episodes_recorded']}")
        print(f"  Failures Recorded: {results['failures_recorded']}")
        print(f"  Episodes with Steps: {results['episodes_with_steps']}")
        print(f"  Episodes with World Snapshot: {results['episodes_with_world_snapshot']}")
        print(f"  Exported to SQLite: {results['exported_to_sqlite']}")
        print(f"  DB Episode Count: {results['db_episode_count']}")
        print(f"  DB Failure Count: {results['db_failure_count']}")
        print(f"  JSON Exported: {results['json_exported']}")
        print(f"  DB Path: {results['db_path']}")
    print("=" * 60)

    print(f"\nJSON: {json.dumps(results, indent=2)}")

    ret = 0 if results.get("overall_success", False) else 1
    runner.destroy_node()
    rclpy.shutdown()
    return ret


if __name__ == "__main__":
    sys.exit(main())