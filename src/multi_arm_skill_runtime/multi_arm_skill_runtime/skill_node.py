"""Skill Runtime ROS2 Node — exposes Skill Registry and Runtime via ROS2 services.

Services:
    - /skill/list (ListSkills.srv)
    - /skill/manage (ManageSkill.srv)

Actions:
    - /skill/execute (ExecuteSkill.action)
"""

from __future__ import annotations

import os
import sys
import time
from typing import Any

import rclpy
from rclpy.action import ActionServer
from rclpy.action.server import ServerGoalHandle
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup, ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node

from multi_arm_interfaces.action import ExecuteSkill
from multi_arm_interfaces.msg import SkillDescription, SkillStatus
from multi_arm_interfaces.srv import ListSkills, ManageSkill

from multi_arm_skill_runtime.skill_registry import SkillRegistry
from multi_arm_skill_runtime.skill_runtime import SkillRuntime, ExecutionStatus
from multi_arm_skill_runtime.skill_manifest import SkillManifest
from multi_arm_skill_runtime.skill_motion_bridge import (
    SkillMotionBridge,
    build_task_goal,
    extract_execution_params,
    normalize_target,
)

# Skills that drive the real robot by forwarding to the Coordinator.
REAL_MOTION_SKILLS = ("pick_object", "move_object", "place_object")


class SkillRuntimeNode(Node):
    """ROS2 node for Skill Runtime.

    Exposes Skill Registry and Runtime via ROS2 interfaces.
    """

    def __init__(self) -> None:
        """Initialize skill runtime node."""
        super().__init__("skill_runtime_node")

        self._callback_group = ReentrantCallbackGroup()
        self._action_callback_group = MutuallyExclusiveCallbackGroup()

        self._registry = SkillRegistry()
        self._runtime = SkillRuntime(self._registry)
        self._auto_install_default_skills()

        self.declare_parameter("use_real_motion", True)

        self._bridge: SkillMotionBridge | None = None
        if bool(self.get_parameter("use_real_motion").value):
            try:
                self._bridge = SkillMotionBridge()
            except Exception as e:  # pragma: no cover - rclpy env dependent
                self.get_logger().warn(f"SkillMotionBridge init failed: {e}")
                self._bridge = None
            if self._bridge is not None:
                for skill_name in REAL_MOTION_SKILLS:
                    self._runtime.register_execution_function(
                        skill_name,
                        self._make_real_execution(skill_name),
                    )
                self.get_logger().info(
                    "Registered real-motion execution for skills: "
                    + ", ".join(REAL_MOTION_SKILLS)
                )
        else:
            self.get_logger().info("use_real_motion=false: skills run against defaults")

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
            callback_group=self._action_callback_group,
        )

        self.get_logger().info("Skill Runtime Node started")

    def _auto_install_default_skills(self) -> None:
        """Install the bundled skill manifests shipped in config/skills.

        Puts pick_object / move_object / place_object into the READY state at
        startup so the M6 Skill Showcase works out of the box. Dynamic skill
        management remains available through the ManageSkill service.
        """
        skills_dir = None
        try:
            from ament_index_python.packages import get_package_share_directory

            skills_dir = os.path.join(
                get_package_share_directory("multi_arm_skill_runtime"),
                "config",
                "skills",
            )
        except Exception:  # pragma: no cover - source-tree fallback
            skills_dir = os.path.join(
                os.path.dirname(__file__), "..", "..", "config", "skills"
            )

        if not skills_dir or not os.path.isdir(skills_dir):
            self.get_logger().warn(f"Skill manifests dir not found: {skills_dir}")
            return

        installed: list[str] = []
        for fname in sorted(os.listdir(skills_dir)):
            if not fname.endswith(".yaml"):
                continue
            path = os.path.join(skills_dir, fname)
            try:
                manifest = SkillManifest.from_yaml(path)
                if self._registry.find_by_name(manifest.name) is None:
                    skill_id = self._registry.install_skill(manifest)
                    self._registry.register_skill(skill_id)
                    if self._registry.validate_skill(skill_id):
                        self._registry.lifecycle.make_ready(skill_id)
                    installed.append(manifest.name)
            except Exception as e:
                self.get_logger().warn(f"Auto-install {fname} failed: {e}")

        if installed:
            self.get_logger().info(
                "Auto-installed default skills: " + ", ".join(installed)
            )

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
        goal = goal_handle.request
        skill_id = self._registry.find_by_name(goal.skill_name)

        result = ExecuteSkill.Result()

        if skill_id is None:
            result.success = False
            result.message = f"Skill not found or not READY: {goal.skill_name}"
            goal_handle.abort()
            return result

        # Goal is already EXECUTING (rclpy transitions before the callback).
        # Build real motion parameters from the structured task_goal (preferred)
        # with a fallback to the legacy string protocol via execute/parameters.
        task_goal = getattr(goal, "task_goal", None)
        params = extract_execution_params(task_goal, tuple(goal.parameters))
        params = normalize_target(params, goal.skill_name)
        params["action_type"] = params.get("action_type") or goal.skill_name
        params["task_id"] = f"skill_{goal.skill_name}_{time.time():.0f}"

        context = {
            "skill_name": goal.skill_name,
            "task_goal": build_task_goal(params),
        }

        skill_result = self._runtime.execute(skill_id, params, context)

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

    def _make_real_execution(self, skill_name: str) -> Any:
        """Build a SkillRuntime execution function that forwards to Coordinator.

        Args:
            skill_name: Skill name to forward.

        Returns:
            Callable(*, arm_name=..., zone_name=..., ...) -> bool that drives
            the real robot via SkillMotionBridge. Raises on failed motion so
            SkillRuntime reports a genuine FAILURE instead of a mock SUCCESS.
        """
        assert self._bridge is not None

        def execute(
            arm_name: str = "",
            zone_name: str = "",
            position_name: str = "",
            object_id: str = "",
            action_type: str = "",
            task_id: str = "",
            **kwargs: Any,
        ) -> bool:
            params: dict[str, str] = {
                "arm_name": arm_name,
                "zone_name": zone_name,
                "position_name": position_name,
                "object_id": object_id,
                "action_type": action_type or skill_name,
            }
            params = normalize_target(params, skill_name)
            goal = build_task_goal(params)
            ok, msg = self._bridge.execute_task_goal(
                goal,
                task_id=task_id or f"skill_{skill_name}_{time.time():.0f}",
                skill_name=skill_name,
            )
            if not ok:
                raise RuntimeError(f"{skill_name} motion failed: {msg}")
            return True

        return execute

    def shutdown(self) -> None:
        """Stop any background motion bridge before node teardown."""
        if self._bridge is not None:
            self._bridge.shutdown()
            self._bridge = None

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
        node.shutdown()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main(sys.argv)