"""Skill Motion Bridge — connects Skill execution to real robot motion.

This bridge is the key piece that closes the M6 "mock → real" gap.

Previously, skills (pick_object/move_object/place_object) executed against a
pure-Python mock: SkillRuntime had no execution_functions, so a skill always
returned SUCCESS without ever moving a real (or simulated) robot.

This module provides:

1. A pure-Python parameter extraction layer (easily unit-testable):
   - extract_execution_params(task_goal, string_params)
   - normalize_target(params, default_position)
   - build_task_goal(params) -> TaskGoal (lazy import of ROS msg)

2. ``SkillMotionBridge`` — an ROS2 node with its own executor and background
   thread that forwards skills to the real Coordinator ``/coordinator/execute_task``
   action. The Coordinator then runs SafetyCheck → MoveIt2 → JTC → Gazebo, i.e.
   genuine robot motion.

Architecture note: the bridge talks only through ``multi_arm_interfaces``
(ExecuteTask.action / TaskGoal.msg) — it never imports Coordinator internals.
"""

from __future__ import annotations

import threading
import time
from typing import Any

from rclpy.action import ActionClient
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node

_execute_task = None


def _get_execute_task():
    """Lazily import the ExecuteTask action (avoids startup-time dependency)."""
    global _execute_task
    if _execute_task is None:
        from multi_arm_interfaces.action import ExecuteTask
        _execute_task = ExecuteTask
    return _execute_task


def _get_task_goal():
    """Lazily import the TaskGoal message."""
    from multi_arm_interfaces.msg import TaskGoal
    return TaskGoal


# Map a skill to a sensible default preset position when the caller did not
# provide one. Mirrors Coordinator's PRESET_POSITIONS vocabulary.
SKILL_DEFAULT_POSITION: dict[str, str] = {
    "pick_object": "scan",
    "move_object": "ready",
    "place_object": "place_high",
    "grasp_object": "scan",
}


def extract_execution_params(
    task_goal: Any = None,
    string_params: list[str] | None = None,
) -> dict[str, str]:
    """Extract a flat target dict from an ExecuteSkill goal.

    Prefers the structured ``task_goal`` (M6.3 domain model); falls back to the
    legacy string protocol ``"arm:zone:position[:object]"``.

    Args:
        task_goal: Optional TaskGoal message or object with arm_name/zone_name/
            position_name/object_id/action_type attributes.
        string_params: Legacy string list from ExecuteSkill.parameters.

    Returns:
        Dict with keys arm_name/zone_name/position_name/object_id (may be empty).
    """
    params: dict[str, str] = {
        "arm_name": "",
        "zone_name": "",
        "position_name": "",
        "object_id": "",
        "action_type": "",
    }

    if task_goal is not None:
        tg_arm = getattr(task_goal, "arm_name", "") or ""
        if tg_arm:
            params["arm_name"] = tg_arm
            params["zone_name"] = getattr(task_goal, "zone_name", "") or ""
            params["position_name"] = getattr(task_goal, "position_name", "") or ""
            params["object_id"] = getattr(task_goal, "object_id", "") or ""
            params["action_type"] = getattr(task_goal, "action_type", "") or ""
            return params

    # Legacy string protocol fallback: index 0 = arm, 1 = zone, 2 = position.
    consolidated = ";".join(string_params or [])
    parts = [p.strip() for p in consolidated.replace(":", ";").split(";") if p.strip()]
    if len(parts) >= 1:
        params["arm_name"] = parts[0]
    if len(parts) >= 2:
        params["zone_name"] = parts[1]
    if len(parts) >= 3:
        params["position_name"] = parts[2]
    if len(parts) >= 4:
        params["object_id"] = parts[3]

    return params


def normalize_target(
    params: dict[str, str],
    skill_name: str,
) -> dict[str, str]:
    """Normalize a target dict against a skill's expectations.

    Fills in a default preset position (by skill) when none is provided and logs
    a default arm when missing.

    Args:
        params: Flat target dict from extract_execution_params.
        skill_name: Skill name selecting the default position.

    Returns:
        Normalized dict with arm_name/zone_name/position_name/object_id.
    """
    out: dict[str, str] = dict(params)
    if not out.get("position_name"):
        out["position_name"] = SKILL_DEFAULT_POSITION.get(skill_name, "ready")
    if not out.get("arm_name"):
        out["arm_name"] = "left_arm"
    return out


def build_task_goal(params: dict[str, str]) -> Any:
    """Build a TaskGoal ROS message from a normalized target dict.

    Args:
        params: Normalized dict from normalize_target.

    Returns:
        A multi_arm_interfaces.msg.TaskGoal instance.
    """
    TaskGoal = _get_task_goal()
    goal = TaskGoal()
    goal.action_type = params.get("action_type", "")
    goal.arm_name = params.get("arm_name", "")
    goal.zone_name = params.get("zone_name", "")
    goal.position_name = params.get("position_name", "")
    goal.object_id = params.get("object_id", "")
    goal.approach = params.get("approach") or "top"
    return goal
class SkillMotionBridge:
    """Forward Skill executions to the real Coordinator for actual motion.

    Runs its own rclpy node + MultiThreadedExecutor on a background thread so
    the (blocking) skill execution never starves the skill_node executor. The
    Coordinator action server handles SafetyCheck → MoveIt → JTC → Gazebo.

    Args:
        node_name: Name for the internal bridge node.
        action_timeout: Per-call action timeout in seconds.
    """

    def __init__(self, node_name: str = "skill_motion_bridge", action_timeout: float = 90.0) -> None:
        """Initialize the bridge node, executor and action client."""
        self._action_timeout = action_timeout
        self._node = Node(node_name)
        self._cb_group = ReentrantCallbackGroup()
        ExecuteTask = _get_execute_task()
        self._client = ActionClient(
            self._node,
            ExecuteTask,
            "/coordinator/execute_task",
            callback_group=self._cb_group,
        )
        self._executor = MultiThreadedExecutor(num_threads=2)
        self._executor.add_node(self._node)
        self._thread = threading.Thread(
            target=self._executor.spin,
            name="skill_motion_bridge_spin",
            daemon=True,
        )
        self._thread.start()
        self._node.get_logger().info(
            f"SkillMotionBridge started (action={self._action_timeout}s)"
        )

    def is_available(self, timeout: float = 10.0) -> bool:
        """Return True once the Coordinator ExecuteTask server is discovered.

        Args:
            timeout: Discovery wait in seconds.

        Returns:
            Whether the server is reachable.
        """
        deadline = time.time() + timeout
        while not self._client.server_is_ready() and time.time() < deadline:
            time.sleep(0.05)
        ready = self._client.server_is_ready()
        if not ready:
            self._node.get_logger().warn("Coordinator /execute_task not available")
        return ready

    def execute_task_goal(
        self,
        task_goal: Any,
        task_id: str,
        skill_name: str = "",
    ) -> tuple[bool, str]:
        """Send a TaskGoal to the real Coordinator and wait for the result.

        Args:
            task_goal: TaskGoal message describing the target.
            task_id: Unique task identifier.
            skill_name: Skill name for the description string.

        Returns:
            Tuple of (success, message).
        """
        ExecuteTask = _get_execute_task()
        goal = ExecuteTask.Goal()
        goal.task_id = task_id
        goal.task_type = task_goal.action_type or skill_name
        goal.description = (
            f"{task_goal.arm_name}:{task_goal.zone_name}:"
            f"{task_goal.position_name}:{task_goal.object_id}"
        )
        goal.goal = task_goal

        if not self.is_available(timeout=5.0):
            return False, "coordinator_unavailable"

        send_future = self._client.send_goal_async(goal)
        if not self._wait_future(send_future, 15.0):
            return False, "goal_send_timeout"

        goal_handle = send_future.result()
        if goal_handle is None or not goal_handle.accepted:
            self._node.get_logger().warn("ExecuteTask goal rejected by Coordinator")
            return False, "goal_rejected"

        result_future = goal_handle.get_result_async()
        if not self._wait_future(result_future, self._action_timeout):
            return False, "execution_timeout"

        result = result_future.result()
        if result is None:
            return False, "no_result"
        outcome = result.result
        self._node.get_logger().info(
            f"[{task_id}] Coordinator -> success={outcome.success} msg={outcome.message}"
        )
        return bool(outcome.success), outcome.message

    @staticmethod
    def _wait_future(future: Any, timeout_sec: float) -> bool:
        """Poll a future until done or timeout (background executor spins).

        Args:
            future: rclpy future.
            timeout_sec: Timeout in seconds.

        Returns:
            True if completed.
        """
        deadline = time.time() + timeout_sec
        while not future.done() and time.time() < deadline:
            time.sleep(0.02)
        return future.done()

    def shutdown(self) -> None:
        """Gracefully stop the background executor and node."""
        try:
            self._executor.shutdown()
        except Exception:
            pass
        if self._thread.is_alive():
            self._thread.join(timeout=5.0)
        try:
            self._node.destroy_node()
        except Exception:
            pass