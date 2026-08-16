"""MoveItInterface - MoveIt2 planning and execution interface for Coordinator.

Provides a synchronous interface to MoveIt2's /move_action for planning
and executing joint-space trajectories. Falls back to preset positions
when MoveIt2 is unavailable.

Used by Coordinator to translate task-level commands into robot motion.
"""

import time as _time
from typing import Dict, List, Optional, Tuple

from rclpy.action import ActionClient
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.node import Node

from multi_arm_core.robot_constants import ARM_JOINT_NAMES, PRESET_POSITIONS


class MoveItInterface:
    """Interface to MoveIt2 move_group for planning and execution.

    Uses /move_action (MoveGroup action) for integrated plan+execute.
    Falls back to direct JTC trajectory sending when MoveIt2 is unavailable.
    """

    def __init__(
        self,
        node: Node,
        cb_group: Optional[ReentrantCallbackGroup] = None,
    ) -> None:
        """Initialize the MoveIt2 interface.

        Args:
            node: The ROS2 node that owns this interface.
            cb_group: Optional callback group for async calls.
        """
        self._node = node
        self._cb_group = cb_group or ReentrantCallbackGroup()
        self._move_client: Optional[ActionClient] = None
        self._js_data: Dict[str, float] = {}

        self._init_moveit_client()

    def _init_moveit_client(self) -> None:
        """Initialize MoveIt2 MoveGroup action client."""
        try:
            from moveit_msgs.action import MoveGroup

            self._move_client = ActionClient(
                self._node,
                MoveGroup,
                "/move_action",
                callback_group=self._cb_group,
            )
            self._node.get_logger().info("MoveIt2 MoveGroup action client initialized")
        except ImportError:
            self._node.get_logger().warn(
                "moveit_msgs not available, MoveIt2 planning disabled"
            )
            self._move_client = None

    def update_joint_states(self, joint_data: Dict[str, float]) -> None:
        """Update cached joint state data.

        Args:
            joint_data: Dictionary of joint_name -> position.
        """
        self._js_data.update(joint_data)

    def plan_and_execute(
        self,
        group_name: str,
        target_joints: Dict[str, float],
        label: str = "",
        max_velocity_scaling: float = 0.3,
        max_accel_scaling: float = 0.3,
        planning_time: float = 10.0,
        planning_attempts: int = 10,
        timeout: float = 60.0,
    ) -> Tuple[bool, str]:
        """Plan and execute a motion via MoveIt2.

        Args:
            group_name: MoveIt planning group name (e.g. 'left_arm', 'right_arm').
            target_joints: Dict of joint_name -> target_position.
            label: Human-readable label for logging.
            max_velocity_scaling: Velocity scaling factor (0-1).
            max_accel_scaling: Acceleration scaling factor (0-1).
            planning_time: Max planning time in seconds.
            planning_attempts: Number of planning attempts.
            timeout: Total timeout for the action call.

        Returns:
            Tuple of (success, message).
        """
        if self._move_client is None:
            return False, "moveit_unavailable"

        if not self._move_client.wait_for_server(timeout_sec=5.0):
            return False, "move_group_not_ready"

        self._node.get_logger().info(
            f"[MoveIt] Planning {group_name} -> {label or 'target'}"
        )

        from moveit_msgs.action import MoveGroup
        from moveit_msgs.msg import (
            PlanningOptions,
            RobotState,
            Constraints,
            JointConstraint,
        )

        goal = MoveGroup.Goal()
        goal.request.group_name = group_name
        goal.request.num_planning_attempts = planning_attempts
        goal.request.allowed_planning_time = planning_time
        goal.request.max_velocity_scaling_factor = max_velocity_scaling
        goal.request.max_acceleration_scaling_factor = max_accel_scaling

        start_state = RobotState()
        start_state.joint_state.header.stamp = (
            self._node.get_clock().now().to_msg()
        )
        jnames = list(target_joints.keys())
        start_state.joint_state.name = jnames
        start_state.joint_state.position = [
            self._js_data.get(n, 0.0) for n in jnames
        ]
        goal.request.start_state = start_state

        constraints = Constraints()
        constraints.name = f"{group_name}_{label}"
        for jname, jval in target_joints.items():
            jc = JointConstraint()
            jc.joint_name = jname
            jc.position = float(jval)
            jc.tolerance_above = 0.05
            jc.tolerance_below = 0.05
            jc.weight = 1.0
            constraints.joint_constraints.append(jc)
        goal.request.goal_constraints = [constraints]

        goal.planning_options = PlanningOptions()
        goal.planning_options.plan_only = False
        goal.planning_options.replan = True
        goal.planning_options.replan_attempts = 3

        future = self._move_client.send_goal_async(goal)
        deadline = _time.time() + timeout

        while not future.done() and _time.time() < deadline:
            _time.sleep(0.05)

        if not future.done():
            return False, "goal_send_timeout"

        goal_handle = future.result()
        if goal_handle is None or not goal_handle.accepted:
            return False, "goal_rejected"

        self._node.get_logger().info(
            f"[MoveIt] Goal accepted for {group_name}, waiting for result..."
        )

        result_future = goal_handle.get_result_async()
        while not result_future.done() and _time.time() < deadline:
            _time.sleep(0.05)

        if not result_future.done():
            return False, "execution_timeout"

        result_response = result_future.result()
        if result_response is None:
            return False, "no_result"

        error_code = result_response.result.error_code.val
        if error_code == 1:
            self._node.get_logger().info(
                f"[MoveIt] {group_name} -> {label}: SUCCESS"
            )
            return True, "success"

        self._node.get_logger().warn(
            f"[MoveIt] {group_name} -> {label}: FAILED (error_code={error_code})"
        )
        return False, f"moveit_error_{error_code}"

    def move_to_preset(
        self,
        arm_name: str,
        position_name: str,
        timeout: float = 60.0,
    ) -> Tuple[bool, str]:
        """Move arm to a preset position via MoveIt2.

        Args:
            arm_name: Arm name (e.g. 'left_arm', 'right_arm').
            position_name: Preset position name (e.g. 'home', 'ready').
            timeout: Execution timeout.

        Returns:
            Tuple of (success, message).
        """
        positions = PRESET_POSITIONS.get(position_name)
        if positions is None:
            return False, f"unknown_preset:{position_name}"

        joint_names = ARM_JOINT_NAMES.get(arm_name, [])
        if not joint_names:
            return False, f"unknown_arm:{arm_name}"

        target_joints = dict(zip(joint_names, positions))
        return self.plan_and_execute(
            group_name=arm_name,
            target_joints=target_joints,
            label=position_name,
            timeout=timeout,
        )

    def is_available(self) -> bool:
        """Check if MoveIt2 action server is available."""
        if self._move_client is None:
            return False
        return self._move_client.wait_for_server(timeout_sec=1.0)
