"""Robot Runtime API Node — unified aggregation layer for M6 runtime capabilities.

This node is the single entry point for M7 Agent to access all M6 runtime APIs.
It does NOT contain business logic — it routes requests to the appropriate backend nodes.

Action Server:
    - /runtime/submit_task_goals (SubmitTaskGoals.action) — submit TaskGoal list, routes to ExecuteSkill

Proxy Services (forward to backend nodes):
    - /runtime/query_world      → /world_model/query_world
    - /runtime/get_capability   → /capability/get_capability
    - /runtime/list_skills      → /skill/list
    - /runtime/manage_skill     → /skill/manage
    - /runtime/query_experience → /experience/query

Action Client:
    - /skill/execute (ExecuteSkill.action) — called by SubmitTaskGoals handler
"""

from __future__ import annotations

import sys
import time
from typing import Any

import rclpy
from rclpy.action import ActionClient, ActionServer
from rclpy.action.server import ServerGoalHandle
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node

from multi_arm_interfaces.action import ExecuteSkill, SubmitTaskGoals
from multi_arm_interfaces.srv import (
    GetCapability,
    ListSkills,
    ManageSkill,
    QueryExperience,
    QueryWorld,
)


ACTION_TYPE_TO_SKILL: dict[str, str] = {
    "pick_place": "pick_object",
    "pick": "pick_object",
    "place": "place_object",
    "move": "move_object",
    "grasp": "pick_object",
    "lift": "move_object",
    "retract": "move_object",
    "inspect": "move_object",
}


class RuntimeApiNode(Node):
    """Robot Runtime API unified node.

    Single entry point for M7 Agent to access all M6 capabilities.
    Routes requests to backend nodes, does not contain business logic.
    """

    def __init__(self) -> None:
        """Initialize runtime API node."""
        super().__init__("runtime_api_node")

        self._cb_group = ReentrantCallbackGroup()

        self._execute_skill_client = ActionClient(
            self,
            ExecuteSkill,
            "/skill/execute",
            callback_group=self._cb_group,
        )

        self._query_world_client = self.create_client(
            QueryWorld,
            "/world_model/query_world",
            callback_group=self._cb_group,
        )
        self._get_capability_client = self.create_client(
            GetCapability,
            "/capability/get_capability",
            callback_group=self._cb_group,
        )
        self._list_skills_client = self.create_client(
            ListSkills,
            "/skill/list",
            callback_group=self._cb_group,
        )
        self._manage_skill_client = self.create_client(
            ManageSkill,
            "/skill/manage",
            callback_group=self._cb_group,
        )
        self._query_experience_client = self.create_client(
            QueryExperience,
            "/experience/query",
            callback_group=self._cb_group,
        )

        self._submit_action = ActionServer(
            self,
            SubmitTaskGoals,
            "/runtime/submit_task_goals",
            self._handle_submit_task_goals,
            callback_group=self._cb_group,
        )

        self._proxy_query_world = self.create_service(
            QueryWorld,
            "/runtime/query_world",
            self._handle_proxy_query_world,
            callback_group=self._cb_group,
        )
        self._proxy_get_capability = self.create_service(
            GetCapability,
            "/runtime/get_capability",
            self._handle_proxy_get_capability,
            callback_group=self._cb_group,
        )
        self._proxy_list_skills = self.create_service(
            ListSkills,
            "/runtime/list_skills",
            self._handle_proxy_list_skills,
            callback_group=self._cb_group,
        )
        self._proxy_manage_skill = self.create_service(
            ManageSkill,
            "/runtime/manage_skill",
            self._handle_proxy_manage_skill,
            callback_group=self._cb_group,
        )
        self._proxy_query_experience = self.create_service(
            QueryExperience,
            "/runtime/query_experience",
            self._handle_proxy_query_experience,
            callback_group=self._cb_group,
        )

        self.get_logger().info("Robot Runtime API Node started")

    def _handle_submit_task_goals(
        self,
        goal_handle: ServerGoalHandle,
    ) -> SubmitTaskGoals.Result:
        """Handle SubmitTaskGoals action — route each TaskGoal to ExecuteSkill.

        Args:
            goal_handle: Action goal handle.

        Returns:
            SubmitTaskGoals result.

        """
        goals = goal_handle.request.goals
        total = len(goals)

        result = SubmitTaskGoals.Result()
        result.total_count = total
        result.results = []

        if total == 0:
            result.success = True
            result.success_count = 0
            goal_handle.succeed()
            return result


        success_count = 0

        for i, task_goal in enumerate(goals):
            skill_name = ACTION_TYPE_TO_SKILL.get(
                task_goal.action_type,
                task_goal.action_type,
            )

            feedback = SubmitTaskGoals.Feedback()
            feedback.current_goal = f"{task_goal.action_type}/{skill_name}"
            feedback.progress = float(i) / float(total)
            goal_handle.publish_feedback(feedback)

            skill_goal = ExecuteSkill.Goal()
            skill_goal.skill_name = skill_name
            skill_goal.task_goal = task_goal

            skill_result = self._call_execute_skill(skill_goal)

            if skill_result is not None and skill_result.success:
                result.results.append(
                    f"SUCCESS: {task_goal.action_type} -> {skill_result.message}"
                )
                success_count += 1
            else:
                msg = skill_result.message if skill_result else "ExecuteSkill unavailable"
                result.results.append(f"FAILURE: {task_goal.action_type} -> {msg}")

        feedback = SubmitTaskGoals.Feedback()
        feedback.current_goal = "done"
        feedback.progress = 1.0
        goal_handle.publish_feedback(feedback)

        result.success = success_count == total
        result.success_count = success_count

        if result.success:
            goal_handle.succeed()
        else:
            goal_handle.abort()

        self.get_logger().info(
            f"SubmitTaskGoals: {success_count}/{total} succeeded"
        )

        return result

    def _call_execute_skill(
        self,
        goal: ExecuteSkill.Goal,
        timeout_sec: float = 10.0,
    ) -> ExecuteSkill.Result | None:
        """Call ExecuteSkill action and wait for result.

        Args:
            goal: ExecuteSkill goal.
            timeout_sec: Timeout in seconds.

        Returns:
            ExecuteSkill result or None if unavailable.

        """
        if not self._execute_skill_client.wait_for_server(timeout_sec=10.0):
            return None

        future = self._execute_skill_client.send_goal_async(goal)
        if not self._wait_future(future, timeout_sec):
            return None

        goal_handle = future.result()
        if goal_handle is None or not goal_handle.accepted:
            return None

        result_future = goal_handle.get_result_async()
        if not self._wait_future(result_future, 120.0):
            return None

        return result_future.result().result

    def _handle_proxy_query_world(
        self,
        request: QueryWorld.Request,
        response: QueryWorld.Response,
    ) -> QueryWorld.Response:
        """Proxy QueryWorld request to /world_model/query_world.

        Args:
            request: QueryWorld request.
            response: QueryWorld response.

        Returns:
            QueryWorld response.

        """
        return self._proxy_call(
            self._query_world_client,
            request,
            response,
            "query_world",
        )

    def _handle_proxy_get_capability(
        self,
        request: GetCapability.Request,
        response: GetCapability.Response,
    ) -> GetCapability.Response:
        """Proxy GetCapability request to /capability/get_capability.

        Args:
            request: GetCapability request.
            response: GetCapability response.

        Returns:
            GetCapability response.

        """
        return self._proxy_call(
            self._get_capability_client,
            request,
            response,
            "get_capability",
        )

    def _handle_proxy_list_skills(
        self,
        request: ListSkills.Request,
        response: ListSkills.Response,
    ) -> ListSkills.Response:
        """Proxy ListSkills request to /skill/list.

        Args:
            request: ListSkills request.
            response: ListSkills response.

        Returns:
            ListSkills response.

        """
        return self._proxy_call(
            self._list_skills_client,
            request,
            response,
            "list_skills",
        )

    def _handle_proxy_manage_skill(
        self,
        request: ManageSkill.Request,
        response: ManageSkill.Response,
    ) -> ManageSkill.Response:
        """Proxy ManageSkill request to /skill/manage.

        Args:
            request: ManageSkill request.
            response: ManageSkill response.

        Returns:
            ManageSkill response.

        """
        return self._proxy_call(
            self._manage_skill_client,
            request,
            response,
            "manage_skill",
        )

    def _handle_proxy_query_experience(
        self,
        request: QueryExperience.Request,
        response: QueryExperience.Response,
    ) -> QueryExperience.Response:
        """Proxy QueryExperience request to /experience/query.

        Args:
            request: QueryExperience request.
            response: QueryExperience response.

        Returns:
            QueryExperience response.

        """
        return self._proxy_call(
            self._query_experience_client,
            request,
            response,
            "query_experience",
        )

    def _proxy_call(
        self,
        client: Any,
        request: Any,
        response: Any,
        name: str,
        timeout_sec: float = 5.0,
    ) -> Any:
        """Forward a service request to backend and return response.

        Args:
            client: Service client.
            request: Service request.
            response: Default response.
            name: Service name for logging.
            timeout_sec: Timeout in seconds.

        Returns:
            Service response from backend or default response.

        """
        if not client.wait_for_service(timeout_sec=1.0):
            self.get_logger().warn(f"Backend {name} unavailable")
            return response

        future = client.call_async(request)
        if not self._wait_future(future, timeout_sec):
            return response

        if future.done() and future.result() is not None:
            return future.result()

        return response

    @staticmethod
    def _wait_future(future: Any, timeout_sec: float) -> bool:
        """Wait for a future to complete by polling (non-blocking).

        Args:
            future: ROS2 future to wait for.
            timeout_sec: Timeout in seconds.

        Returns:
            True if future completed, False if timed out.

        """
        start = time.time()
        while not future.done() and (time.time() - start) < timeout_sec:
            time.sleep(0.01)
        return future.done()


def main(args: list[str] | None = None) -> None:
    """Entry point for runtime API node.

    Args:
        args: Command line arguments.

    """
    rclpy.init(args=args)
    node = RuntimeApiNode()
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main(sys.argv)