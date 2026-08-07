"""Skill Runtime ROS2 Node — exposes Skill Registry and Runtime via ROS2 services.

Services:
    - /skill/list (ListSkills.srv)
    - /skill/manage (ManageSkill.srv)

Actions:
    - /skill/execute (ExecuteSkill.action)
"""

from __future__ import annotations

import sys
from typing import Any

import rclpy
from rclpy.action import ActionServer
from rclpy.action.server import ServerGoalHandle
from rclpy.callback_group import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node

from multi_arm_interfaces.action import ExecuteSkill
from multi_arm_interfaces.msg import SkillDescription, SkillStatus
from multi_arm_interfaces.srv import ListSkills, ManageSkill

from multi_arm_skill_runtime.skill_registry import SkillRegistry
from multi_arm_skill_runtime.skill_runtime import SkillRuntime, ExecutionStatus
from multi_arm_skill_runtime.skill_manifest import SkillManifest


class SkillRuntimeNode(Node):
    """ROS2 node for Skill Runtime.

    Exposes Skill Registry and Runtime via ROS2 interfaces.
    """

    def __init__(self) -> None:
        """Initialize skill runtime node."""
        super().__init__("skill_runtime_node")

        self._callback_group = ReentrantCallbackGroup()

        self._registry = SkillRegistry()
        self._runtime = SkillRuntime(self._registry)

        self._list_srv = self.create_service(
            ListSkills,
            "/skill/list",
            self._handle_list,
            callback_group=self._callback_group,
        )

        self._manage_srv = self.create_service(
            ManageSkill,
            "/skill/manage",
            self._handle_manage,
            callback_group=self._callback_group,
        )

        self._execute_action = ActionServer(
            self,
            ExecuteSkill,
            "/skill/execute",
            self._handle_execute,
            callback_group=self._callback_group,
        )

        self.get_logger().info("Skill Runtime Node started")

    def _handle_list(
        self,
        request: ListSkills.Request,
        response: ListSkills.Response,
    ) -> ListSkills.Response:
        """Handle ListSkills service call.

        Args:
            request: ListSkills request.
            response: ListSkills response.

        Returns:
            ListSkills response.

        """
        caps = list(request.required_capabilities) if request.required_capabilities else None
        state = request.lifecycle_state if request.lifecycle_state else "ready"

        skills = self._registry.list_skills(
            required_capabilities=caps,
            lifecycle_state=state,
        )

        response.skills = []
        for skill_id, manifest in skills:
            desc = SkillDescription()
            desc.name = manifest.name
            desc.version = manifest.version
            desc.description = manifest.description
            desc.required_capabilities = manifest.required_capabilities
            desc.preconditions = manifest.preconditions
            desc.postconditions = manifest.postconditions
            desc.parameters = list(manifest.input_params.keys())
            desc.cost_time = manifest.cost.time
            desc.cost_risk = manifest.cost.risk
            desc.success_rate = manifest.cost.success_rate
            response.skills.append(desc)

        return response

    def _handle_manage(
        self,
        request: ManageSkill.Request,
        response: ManageSkill.Response,
    ) -> ManageSkill.Response:
        """Handle ManageSkill service call.

        Args:
            request: ManageSkill request.
            response: ManageSkill response.

        Returns:
            ManageSkill response.

        """
        action = request.action

        if action == "install":
            try:
                manifest = SkillManifest.from_yaml(request.skill_package)
                skill_id = self._registry.install_skill(manifest)
                self._registry.register_skill(skill_id)
                self._registry.validate_skill(skill_id)
                response.success = True
                response.message = f"Installed skill {manifest.name} as {skill_id}"
            except Exception as e:
                response.success = False
                response.message = f"Install failed: {e}"
        elif action == "remove":
            success = self._registry.remove_skill(request.skill_id)
            response.success = success
            response.message = "Removed" if success else "Remove failed"
        else:
            response.success = False
            response.message = f"Unknown action: {action}"

        status = self._registry.get_status(request.skill_id)
        if status:
            response.skill_status = self._dict_to_status(status)

        return response

    def _handle_execute(
        self,
        goal_handle: ServerGoalHandle,
    ) -> ExecuteSkill.Result:
        """Handle ExecuteSkill action call.

        Args:
            goal_handle: Action goal handle.

        Returns:
            ExecuteSkill result.

        """
        goal = goal_handle.goal
        skill_id = self._registry.find_by_name(goal.skill_name)

        result = ExecuteSkill.Result()

        if skill_id is None:
            result.success = False
            result.message = f"Skill not found or not READY: {goal.skill_name}"
            goal_handle.abort()
            return result

        goal_handle.execute()

        parameters = {}
        for i, param in enumerate(goal.parameters):
            parameters[f"param_{i}"] = param

        skill_result = self._runtime.execute(skill_id, parameters)

        result.success = skill_result.status in (
            ExecutionStatus.SUCCESS,
            ExecutionStatus.RECOVERED,
        )
        result.message = skill_result.message
        result.postcondition_results = skill_result.postcondition_results

        if result.success:
            goal_handle.succeed()
        else:
            goal_handle.abort()

        return result

    def _dict_to_status(self, status: dict[str, Any]) -> SkillStatus:
        """Convert status dict to SkillStatus msg.

        Args:
            status: Status dict.

        Returns:
            SkillStatus message.

        """
        msg = SkillStatus()
        msg.skill_id = status.get("skill_id", "")
        msg.name = status.get("name", "")
        msg.version = status.get("version", "")
        msg.lifecycle_state = status.get("lifecycle_state", "")
        msg.last_executed = status.get("last_executed", 0.0)
        msg.total_executions = status.get("total_executions", 0)
        msg.success_count = status.get("success_count", 0)
        return msg


def main(args: list[str] | None = None) -> None:
    """Entry point for skill runtime node.

    Args:
        args: Command line arguments.

    """
    rclpy.init(args=args)
    node = SkillRuntimeNode()
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