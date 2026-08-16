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

    Singleton pattern: one ROS2 context per process. This avoids the
    'rclpy.init() has already been called' error when the client is
    recreated in a loop (e.g. Robot OS Shell).

    The first instantiation initializes rclpy + node + clients. Subsequent
    instantiations return the cached instance with just a timeout update.
    """

    _instance: "RuntimeClient | None" = None
    _initialized: bool = False

    def __new__(cls, *args: Any, **kwargs: Any) -> "RuntimeClient":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, timeout_sec: float = 10.0) -> None:
        if RuntimeClient._initialized:
            self._timeout = timeout_sec
            return
        if not rclpy.ok():
            rclpy.init()
        self._node = Node(f"runtime_cli_{int(time.time() * 1000000)}")
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
        RuntimeClient._initialized = True

    def shutdown(self) -> None:
        """No-op for singleton — rclpy context stays alive across commands.

        The RuntimeClient singleton persists for the process lifetime.
        Python's atexit handler cleans up rclpy on exit.
        """
        pass

    def _safe_spin(self, future: Any) -> Any:
        """Spin until future complete, handling shutdown exceptions."""
        try:
            rclpy.spin_until_future_complete(
                self._node, future, timeout_sec=self._timeout
            )
        except Exception:
            return None
        try:
            return future.result()
        except Exception:
            return None

    def _wait_for_service(self, client: Any, name: str) -> bool:
        """Wait for a service to be available."""
        import sys as _sys
        try:
            if not client.wait_for_service(self._timeout):
                print(f"ERROR: Service {name} not available", flush=True)
                _sys.stdout.flush()
                return False
            return True
        except Exception as e:
            print(f"ERROR: Service {name} context invalid: {e}", flush=True)
            _sys.stdout.flush()
            return False

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
        return self._safe_spin(future)

    def list_skills(
        self, lifecycle_state: str = ""
    ) -> ListSkills.Response | None:
        """List registered skills."""
        if not self._wait_for_service(self._list_skills, "/runtime/list_skills"):
            return None
        req = ListSkills.Request()
        req.lifecycle_state = lifecycle_state
        future = self._list_skills.call_async(req)
        return self._safe_spin(future)

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
        return self._safe_spin(future)

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
        return self._safe_spin(future)

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

        latest_feedback = []
        def _feedback_cb(feedback_msg):
            latest_feedback.append(feedback_msg.feedback)

        if on_feedback:
            send_future = self._submit_task.send_goal_async(
                goal_msg, feedback_callback=_feedback_cb
            )
        else:
            send_future = self._submit_task.send_goal_async(goal_msg)
        self._safe_spin(send_future)
        goal_handle: ClientGoalHandle = send_future.result()
        if goal_handle is None:
            print("ERROR: Task goal not accepted (timeout or service unavailable)")
            return None
        if not goal_handle.accepted:
            print("ERROR: Task goal rejected")
            return None

        result_future = goal_handle.get_result_async()
        while not result_future.done():
            rclpy.spin_once(self._node, timeout_sec=0.1)
            if on_feedback and latest_feedback:
                on_feedback(latest_feedback[-1])
                latest_feedback.clear()

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
        goal.arm_name = arm_name if arm_name else "left_arm"
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

    def emergency_stop(self) -> tuple[bool, str]:
        """Call SafetySupervisor emergency stop directly.

        Bypasses RuntimeApiNode/Coordinator — Safety has final stop authority.

        Returns:
            (success, message) tuple.

        """
        from multi_arm_interfaces.srv import EmergencyStop

        client = self._node.create_client(EmergencyStop, "/safety/emergency_stop")
        if not client.wait_for_service(self._timeout):
            return False, "Safety service not available"

        req = EmergencyStop.Request()
        req.emergency = True
        future = client.call_async(req)
        self._safe_spin(future)
        result = future.result()
        client.destroy()

        if result is None:
            return False, "No response from SafetySupervisor"
        return result.success, result.message

    def safety_check(
        self, arm_names: list[str] | None = None
    ) -> tuple[bool, float, str]:
        """Call SafetySupervisor safety check directly.

        Returns:
            (approved, speed_scale, message) tuple.

        """
        from multi_arm_interfaces.srv import SafetyCheck

        client = self._node.create_client(SafetyCheck, "/safety/safety_check")
        if not client.wait_for_service(self._timeout):
            return False, 0.0, "Safety service not available"

        req = SafetyCheck.Request()
        if arm_names:
            req.arm_names = arm_names
        future = client.call_async(req)
        self._safe_spin(future)
        result = future.result()
        client.destroy()

        if result is None:
            return False, 0.0, "No response from SafetySupervisor"
        return result.approved, result.speed_scale, result.message

    def spin_once(self, timeout_sec: float = 0.1) -> None:
        """Spin once for callback processing."""
        rclpy.spin_once(self._node, timeout_sec=timeout_sec)