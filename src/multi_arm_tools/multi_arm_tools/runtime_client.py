"""Runtime API client for robot CLI.

Encapsulates all ROS2 service/action calls to the Runtime API (M6.5).
"""

import json
import time
from typing import Any

import rclpy
from rclpy.action import ActionClient
from rclpy.action.client import ClientGoalHandle
from rclpy.node import Node

from multi_arm_interfaces.action import SubmitTaskGoals
from multi_arm_interfaces.msg import TaskConstraint, TaskGoal
from multi_arm_interfaces.srv import (
    GetCapability,
    ListSkills,
    QueryExperience,
    QueryWorld,
)

ACTION_TYPE_TO_SKILL = {
    "pick_place": "pick_object",
    "pick": "pick_object",
    "place": "place_object",
    "move": "move_object",
    "grasp": "pick_object",
    "lift": "move_object",
    "retract": "move_object",
    "inspect": "move_object",
}


class RuntimeClient:
    """ROS2 client for Runtime API (M6.5).

    Wraps all service/action calls with synchronous wait semantics
    suitable for CLI usage.
    """

    def __init__(self, timeout_sec: float = 5.0) -> None:
        rclpy.init()
        self._node = Node("runtime_cli")
        self._timeout = timeout_sec
        self._query_world = self._node.create_client(
            QueryWorld, "/runtime/query_world"
        )
        self._list_skills = self._node.create_client(
            ListSkills, "/runtime/list_skills"
        )
        self._get_capability = self._node.create_client(
            GetCapability, "/runtime/get_capability"
        )
        self._query_experience = self._node.create_client(
            QueryExperience, "/runtime/query_experience"
        )
        self._submit_task = ActionClient(
            self._node, SubmitTaskGoals, "/runtime/submit_task_goals"
        )

    def shutdown(self) -> None:
        """Shutdown ROS2."""
        self._submit_task.destroy()
        self._node.destroy_node()
        rclpy.shutdown()

    def _wait_for_service(self, client: Any, name: str) -> bool:
        """Wait for a service to be available."""
        if not client.wait_for_service(self._timeout):
            print(f"ERROR: Service {name} not available")
            return False
        return True

    def query_world(
        self, entity_id: str = "", relation_predicate: str = ""
    ) -> QueryWorld.Response | None:
        """Query world model state."""
        if not self._wait_for_service(self._query_world, "/runtime/query_world"):
            return None
        req = QueryWorld.Request()
        req.entity_id = entity_id
        req.relation_predicate = relation_predicate
        future = self._query_world.call_async(req)
        rclpy.spin_until_future_complete(self._node, future, timeout_sec=self._timeout)
        return future.result()

    def list_skills(
        self, lifecycle_state: str = ""
    ) -> ListSkills.Response | None:
        """List registered skills."""
        if not self._wait_for_service(self._list_skills, "/runtime/list_skills"):
            return None
        req = ListSkills.Request()
        req.lifecycle_state = lifecycle_state
        future = self._list_skills.call_async(req)
        rclpy.spin_until_future_complete(self._node, future, timeout_sec=self._timeout)
        return future.result()

    def get_capability(
        self, include_dynamic: bool = True
    ) -> GetCapability.Response | None:
        """Query three-layer capability."""
        if not self._wait_for_service(
            self._get_capability, "/runtime/get_capability"
        ):
            return None
        req = GetCapability.Request()
        req.include_dynamic = include_dynamic
        future = self._get_capability.call_async(req)
        rclpy.spin_until_future_complete(self._node, future, timeout_sec=self._timeout)
        return future.result()

    def query_experience(
        self, data_type: str = "episodes", filter_json: str = ""
    ) -> QueryExperience.Response | None:
        """Query episode/experience history."""
        if not self._wait_for_service(
            self._query_experience, "/runtime/query_experience"
        ):
            return None
        req = QueryExperience.Request()
        req.data_type = data_type
        req.filter_json = filter_json
        future = self._query_experience.call_async(req)
        rclpy.spin_until_future_complete(self._node, future, timeout_sec=self._timeout)
        return future.result()

    def submit_task(
        self,
        task_type: str,
        args: list[str],
        arm_name: str = "",
        on_feedback: Any = None,
    ) -> SubmitTaskGoals.Result | None:
        """Submit a task goal and wait for completion.

        Args:
            task_type: Action type (pick_place, move, etc.)
            args: Positional args [object_id, zone_name, ...]
            arm_name: Optional arm name override
            on_feedback: Callback(feedback_msg) for progress updates

        Returns:
            SubmitTaskGoals.Result or None on failure
        """
        if not self._submit_task.wait_for_server(self._timeout):
            print("ERROR: Action /runtime/submit_task_goals not available")
            return None

        goal = self._build_task_goal(task_type, args, arm_name)
        goal_msg = SubmitTaskGoals.Goal()
        goal_msg.goals = [goal]

        send_future = self._submit_task.send_goal_async(goal_msg)
        rclpy.spin_until_future_complete(self._node, send_future, timeout_sec=self._timeout)
        goal_handle: ClientGoalHandle = send_future.result()
        if not goal_handle.accepted:
            print("ERROR: Task goal rejected")
            return None

        result_future = goal_handle.get_result_async()
        while not result_future.done():
            rclpy.spin_once(self._node, timeout_sec=0.1)
            if on_feedback:
                feedback = goal_handle.feedback
                if feedback:
                    on_feedback(feedback)

        return result_future.result().result

    def _build_task_goal(
        self, task_type: str, args: list[str], arm_name: str
    ) -> TaskGoal:
        """Build TaskGoal from CLI args.

        Parsing convention:
            robot run pick_place red_cube zone_b
            robot run move ready
            robot run grasp red_cube
        """
        goal = TaskGoal()
        goal.action_type = task_type
        goal.arm_name = arm_name if arm_name else "arm1"
        goal.constraints = TaskConstraint()
        goal.constraints.allow_recovery = True
        goal.constraints.max_retries = 3
        goal.constraints.priority = 1

        if task_type in ("pick_place", "pick", "grasp"):
            if len(args) >= 1:
                goal.object_id = args[0]
            if len(args) >= 2:
                goal.zone_name = args[1]
            goal.approach = "top"
        elif task_type == "place":
            if len(args) >= 1:
                goal.zone_name = args[0]
            if len(args) >= 2:
                goal.object_id = args[1]
        elif task_type in ("move", "lift", "retract", "inspect"):
            if len(args) >= 1:
                goal.position_name = args[0]
            if len(args) >= 2:
                goal.zone_name = args[1]

        return goal

    def spin_once(self, timeout_sec: float = 0.1) -> None:
        """Spin once for callback processing."""
        rclpy.spin_once(self._node, timeout_sec=timeout_sec)