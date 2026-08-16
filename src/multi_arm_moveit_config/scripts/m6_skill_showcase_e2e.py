"""M6 Skill Showcase E2E — drive real motion through the M6 Skill layer.

Issues a SubmitTaskGoals request to the Robot Runtime API and reports the
outcome. This exercises the CURRENT (M6) architecture path end-to-end:

    SubmitTaskGoals -> RuntimeApi -> ExecuteSkill -> skill_node
      -> SkillMotionBridge -> ExecuteTask -> Coordinator -> SafetyCheck
      -> MoveIt2 -> JTC -> Gazebo -> Joint States -> WorldModel

Usage:
    python3 m6_skill_showcase_e2e.py [arm] [action_type] [position]
"""

from __future__ import annotations

import sys

import rclpy
from rclpy.action import ActionClient
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.node import Node

from multi_arm_interfaces.action import SubmitTaskGoals
from multi_arm_interfaces.msg import TaskGoal


def build_goals(arm: str, action_type: str, position: str) -> list[TaskGoal]:
    """Construct the TaskGoal list for the showcase.

    Args:
        arm: Target arm name (e.g. left_arm).
        action_type: Skill action type (move/place/pick).
        position: Destination preset name (e.g. ready).

    Returns:
        List of TaskGoal messages.
    """
    goals: list[TaskGoal] = []
    for zone in ("zone_a", "zone_b"):
        goal = TaskGoal()
        goal.action_type = action_type
        goal.arm_name = arm
        goal.zone_name = zone
        goal.position_name = position
        goal.approach = "top"
        goals.append(goal)
    return goals


def main(args: list[str] | None = None) -> int:
    """Run the showcase and return 0 on success (all goals completed)."""
    argv = sys.argv[1:]
    arm = argv[0] if len(argv) > 0 else "left_arm"
    action_type = argv[1] if len(argv) > 1 else "move"
    position = argv[2] if len(argv) > 2 else "ready"

    rclpy.init(args=args)
    node = Node("m6_skill_showcase_e2e")
    cb_group = ReentrantCallbackGroup()
    client = ActionClient(
        node, SubmitTaskGoals, "/runtime/submit_task_goals",
        callback_group=cb_group,
    )

    node.get_logger().info("Waiting for Runtime API /submit_task_goals server...")
    if not client.wait_for_server(timeout_sec=30.0):
        node.get_logger().error(
            "Runtime API not available — is the full stack up?"
        )
        rclpy.shutdown()
        return 2

    goals = build_goals(arm, action_type, position)
    request = SubmitTaskGoals.Goal()
    request.goals = goals

    node.get_logger().info(
        f"Submitting {len(goals)} goal(s): arm={arm} "
        f"action={action_type} position={position}"
    )

    future = client.send_goal_async(request)
    rclpy.spin_until_future_complete(node, future, timeout_sec=30.0)
    goal_handle = future.result()

    if goal_handle is None or not goal_handle.accepted:
        node.get_logger().error("SubmitTaskGoals goal rejected.")
        rclpy.shutdown()
        return 3

    node.get_logger().info("Goal accepted, waiting for result...")
    result_future = goal_handle.get_result_async()
    rclpy.spin_until_future_complete(node, result_future, timeout_sec=120.0)
    outcome = result_future.result().result if result_future.done() else None

    if outcome is None:
        node.get_logger().error("Timeout waiting for SubmitTaskGoals result.")
        node.destroy_node()
        rclpy.shutdown()
        return 4

    node.get_logger().info(
        "=== M6 Skill Showcase RESULT ==="
    )
    node.get_logger().info(
        f"success={outcome.success} "
        f"success_count={outcome.success_count}/{outcome.total_count}"
    )
    for idx, r in enumerate(outcome.results):
        node.get_logger().info(f"  task[{idx}] -> {r}")

    node.destroy_node()
    rclpy.shutdown()
    return 0 if outcome.success else 1


if __name__ == "__main__":
    sys.exit(main())