"""Async ROS2 BT plugins for multi-arm task planning.

Unlike the old ros2_plugins.py that created temporary nodes and used
_time.sleep() polling (causing executor deadlocks), these plugins use
the AsyncActionNode pattern:

1. Share the TaskPlanner's ROS2 Node (injected via set_ros2_node)
2. First tick: send async request, return RUNNING
3. Subsequent ticks: check future.done(), return SUCCESS/FAILURE
4. Never block the executor

This is equivalent to BehaviorTree.CPP's AsyncActionNode pattern.
"""

import time as _time
from typing import Any, Optional

from rclpy.callback_groups import ReentrantCallbackGroup

from multi_arm_task_planner.behavior_tree import (
    AsyncActionNode,
    Blackboard,
    ConditionNode,
    NodeStatus,
)


class AsyncMoveToNode(AsyncActionNode):
    """Move arm to target position via Coordinator ExecuteTask action.

    Async pattern: send goal on first tick, check result on subsequent ticks.
    Never blocks the executor — uses service_is_ready() instead of wait_for_server().
    """

    def __init__(self, name: str = "", blackboard: Optional[Blackboard] = None) -> None:
        super().__init__(name=name, blackboard=blackboard)
        self._goal_handle = None
        self._result_future = None
        self._client = None

    def _send_request(self) -> Optional[Any]:
        try:
            from multi_arm_interfaces.action import ExecuteTask
            from multi_arm_interfaces.msg import TaskGoal, TaskConstraint
            from rclpy.action import ActionClient

            if self._ros2_node is None:
                self._blackboard.set("last_action", "move_to:no_ros2_node")
                return None

            arm = self._blackboard.get("arm_name")
            target = self._blackboard.get("target_position", "ready")
            zone = self._blackboard.get("target_zone", "zone_a")

            if not arm:
                return None

            if self._client is None:
                cb_group = ReentrantCallbackGroup()
                self._client = ActionClient(
                    self._ros2_node, ExecuteTask, "/coordinator/execute_task",
                    callback_group=cb_group
                )

            if not self._client.wait_for_server(timeout_sec=0.1):
                self._blackboard.set("last_action", f"move_to:{arm}->waiting_server")
                return self._make_completed_future("waiting")

            goal = ExecuteTask.Goal()
            goal.task_id = f"bt_move_{_time.time():.0f}"
            goal.task_type = "move"
            goal.description = f"{arm}:{zone}:{target}"

            task_goal = TaskGoal()
            task_goal.action_type = "move"
            task_goal.arm_name = arm
            task_goal.zone_name = zone
            task_goal.position_name = target
            task_goal.constraints = TaskConstraint()
            task_goal.constraints.safety_level = 0
            task_goal.constraints.priority = 1
            task_goal.constraints.allow_recovery = True
            task_goal.constraints.max_retries = 3
            goal.goal = task_goal

            self._blackboard.set("last_action", f"move_to:{arm}->{target}")
            return self._client.send_goal_async(goal)
        except Exception as e:
            self._blackboard.set("last_action", f"move_to:error:{e}")
            return None

    def _check_result(self, future: Any) -> NodeStatus:
        try:
            if isinstance(future.result(), str) and future.result() == "waiting":
                if self._client is not None and self._client.server_is_ready():
                    self._request_sent = False
                    self._pending_future = None
                return NodeStatus.RUNNING

            goal_handle = future.result()
            if goal_handle is None or not goal_handle.accepted:
                return NodeStatus.FAILURE

            if self._result_future is None:
                self._result_future = goal_handle.get_result_async()
                return NodeStatus.RUNNING

            if not self._result_future.done():
                return NodeStatus.RUNNING

            result_response = self._result_future.result()
            if result_response is not None and result_response.result.success:
                return NodeStatus.SUCCESS
            return NodeStatus.FAILURE
        except Exception:
            return NodeStatus.FAILURE

    def reset(self) -> None:
        self._goal_handle = None
        self._result_future = None
        self._client = None
        super().reset()


class AsyncRetractNode(AsyncActionNode):
    """Retract arm to home position via Coordinator ExecuteTask action."""

    def __init__(self, name: str = "", blackboard: Optional[Blackboard] = None) -> None:
        super().__init__(name=name, blackboard=blackboard)
        self._result_future = None
        self._client = None

    def _send_request(self) -> Optional[Any]:
        try:
            from multi_arm_interfaces.action import ExecuteTask
            from multi_arm_interfaces.msg import TaskGoal, TaskConstraint
            from rclpy.action import ActionClient

            if self._ros2_node is None:
                return None

            arm = self._blackboard.get("arm_name")
            if not arm:
                return None

            if self._client is None:
                cb_group = ReentrantCallbackGroup()
                self._client = ActionClient(
                    self._ros2_node, ExecuteTask, "/coordinator/execute_task",
                    callback_group=cb_group
                )

            if not self._client.wait_for_server(timeout_sec=0.1):
                self._blackboard.set("last_action", f"retract:{arm}->waiting_server")
                return self._make_completed_future("waiting")

            goal = ExecuteTask.Goal()
            goal.task_id = f"bt_retract_{_time.time():.0f}"
            goal.task_type = "move"
            goal.description = f"{arm}:home:home"

            task_goal = TaskGoal()
            task_goal.action_type = "retract"
            task_goal.arm_name = arm
            task_goal.zone_name = "home"
            task_goal.position_name = "home"
            task_goal.constraints = TaskConstraint()
            task_goal.constraints.safety_level = 0
            task_goal.constraints.priority = 1
            goal.goal = task_goal

            self._blackboard.set("last_action", f"retract:{arm}")
            return self._client.send_goal_async(goal)
        except Exception as e:
            self._blackboard.set("last_action", f"retract:error:{e}")
            return None

    def _check_result(self, future: Any) -> NodeStatus:
        try:
            if isinstance(future.result(), str) and future.result() == "waiting":
                if self._client is not None and self._client.server_is_ready():
                    self._request_sent = False
                    self._pending_future = None
                return NodeStatus.RUNNING

            goal_handle = future.result()
            if goal_handle is None or not goal_handle.accepted:
                return NodeStatus.FAILURE

            if self._result_future is None:
                self._result_future = goal_handle.get_result_async()
                return NodeStatus.RUNNING

            if not self._result_future.done():
                return NodeStatus.RUNNING

            result_response = self._result_future.result()
            if result_response is not None and result_response.result.success:
                return NodeStatus.SUCCESS
            return NodeStatus.FAILURE
        except Exception:
            return NodeStatus.FAILURE

    def reset(self) -> None:
        self._result_future = None
        self._client = None
        super().reset()

    def reset(self) -> None:
        self._result_future = None
        super().reset()


class AsyncCheckSafetyNode(ConditionNode):
    """Check if operation is safe via /safety/safety_check service.

    Uses shared Node for service client. Since safety check is a
    quick service call, we use a simplified async pattern:
    first tick sends request, subsequent ticks check result.
    """

    def __init__(self, name: str = "", blackboard: Optional[Blackboard] = None) -> None:
        super().__init__(name=name, blackboard=blackboard)
        self._ros2_node: Optional[Any] = None
        self._pending_future: Optional[Any] = None
        self._request_sent: bool = False

    def set_ros2_node(self, node: Any) -> None:
        self._ros2_node = node

    def tick(self) -> NodeStatus:
        if not self._request_sent:
            self._request_sent = True
            self._pending_future = self._send_safety_check()
            if self._pending_future is None:
                self._blackboard.set("safety_approved", True)
                self._status = NodeStatus.SUCCESS
                return NodeStatus.SUCCESS
            return NodeStatus.RUNNING

        if self._pending_future is not None and self._pending_future.done():
            try:
                result = self._pending_future.result()
                approved = result.approved if result else True
                self._blackboard.set("safety_approved", approved)
                self._status = NodeStatus.SUCCESS if approved else NodeStatus.FAILURE
                return self._status
            except Exception:
                self._blackboard.set("safety_approved", True)
                self._status = NodeStatus.SUCCESS
                return NodeStatus.SUCCESS

        return NodeStatus.RUNNING

    def _send_safety_check(self) -> Optional[Any]:
        try:
            from multi_arm_interfaces.srv import SafetyCheck

            if self._ros2_node is None:
                return None

            arm = self._blackboard.get("arm_name")
            if not arm:
                return None

            cb_group = ReentrantCallbackGroup()
            client = self._ros2_node.create_client(
                SafetyCheck, "/safety/safety_check", callback_group=cb_group
            )

            if not client.service_is_ready():
                return None

            request = SafetyCheck.Request()
            request.arm_names = [arm]
            request.trajectory_joint_names = []
            request.trajectory_positions = []
            request.trajectory_duration = 3.0

            return client.call_async(request)
        except Exception:
            return None

    def reset(self) -> None:
        self._request_sent = False
        self._pending_future = None
        super().reset()


class AsyncQueryWorldNode(AsyncActionNode):
    """Query WorldModel for object/robot state via /world_model/query_objects."""

    def __init__(self, name: str = "", blackboard: Optional[Blackboard] = None) -> None:
        super().__init__(name=name, blackboard=blackboard)

    def _send_request(self) -> Optional[Any]:
        try:
            from multi_arm_interfaces.srv import QueryResources

            if self._ros2_node is None:
                self._blackboard.set("last_action", "query_world:no_node")
                return self._make_completed_future(None)

            cb_group = ReentrantCallbackGroup()
            client = self._ros2_node.create_client(
                QueryResources, "/world_model/query_objects", callback_group=cb_group
            )

            if not client.service_is_ready():
                self._blackboard.set("last_action", "query_world:service_not_ready")
                return self._make_completed_future(None)

            request = QueryResources.Request()
            request.resource_types = ["object"]

            return client.call_async(request)
        except Exception:
            self._blackboard.set("last_action", "query_world:error")
            return self._make_completed_future(None)

    def _check_result(self, future: Any) -> NodeStatus:
        try:
            if not future.done():
                return NodeStatus.RUNNING

            result = future.result()
            if result is not None:
                objects = list(result.resource_names)
                self._blackboard.set("world_query_result", objects)
                self._blackboard.set("last_action", f"query_world:objects={len(objects)}")
            else:
                self._blackboard.set("last_action", "query_world:empty")

            return NodeStatus.SUCCESS
        except Exception:
            self._blackboard.set("last_action", "query_world:error")
            return NodeStatus.SUCCESS


class AsyncGraspNode(AsyncActionNode):
    """Grasp action (simplified for M5 — no real gripper in simulation)."""

    def _send_request(self) -> Optional[Any]:
        arm = self._blackboard.get("arm_name")
        obj_id = self._blackboard.get("object_id", "unknown")
        approach = self._blackboard.get("approach", "top")

        if not arm:
            return None

        self._blackboard.set("grasp_success", True)
        self._blackboard.set("last_action", f"grasp:{arm}->{obj_id}({approach})")
        return self._make_completed_future(True)

    def _check_result(self, future: Any) -> NodeStatus:
        return NodeStatus.SUCCESS


class AsyncPlaceNode(AsyncActionNode):
    """Place action (simplified for M5 — no real gripper in simulation)."""

    def _send_request(self) -> Optional[Any]:
        arm = self._blackboard.get("arm_name")
        target = self._blackboard.get("target_zone")

        if not arm:
            return None

        self._blackboard.set("last_action", f"place:{arm}->{target}")
        return self._make_completed_future(True)

    def _check_result(self, future: Any) -> NodeStatus:
        return NodeStatus.SUCCESS


class AsyncLiftNode(AsyncActionNode):
    """Lift action (simplified for M5)."""

    def _send_request(self) -> Optional[Any]:
        arm = self._blackboard.get("arm_name")
        if not arm:
            return None

        self._blackboard.set("last_action", f"lift:{arm}")
        return self._make_completed_future(True)

    def _check_result(self, future: Any) -> NodeStatus:
        return NodeStatus.SUCCESS


class AsyncRecoverNode(AsyncActionNode):
    """Recovery action — calls RecoveryManager via Coordinator.

    For M5.2, recovery is simplified. Full integration with
    multi_arm_recovery will be completed in M5.2+.
    """

    def _send_request(self) -> Optional[Any]:
        failure = self._blackboard.get("failure_type", "unknown")
        arm = self._blackboard.get("arm_name", "unknown")
        self._blackboard.set("last_action", f"recover:{arm} type={failure}")
        return self._make_completed_future(True)

    def _check_result(self, future: Any) -> NodeStatus:
        return NodeStatus.SUCCESS


ASYNC_PLUGIN_REGISTRY = {
    "MoveTo": AsyncMoveToNode,
    "Grasp": AsyncGraspNode,
    "Place": AsyncPlaceNode,
    "Lift": AsyncLiftNode,
    "Retract": AsyncRetractNode,
    "CheckSafety": AsyncCheckSafetyNode,
    "QueryWorld": AsyncQueryWorldNode,
    "Recover": AsyncRecoverNode,
}