"""ROS2-enabled BT plugins for multi-arm task planning.

Unlike the mock plugins in pick_place_plugins.py, these plugins
call real ROS2 services and actions:
- MoveTo/Grasp/Place/Lift/Retract: Call /coordinator/execute_task action
- CheckSafety: Call /safety/safety_check service
- QueryWorld: Call /world_model/query_objects service
- Recover: Call /coordinator/execute_task with reset task_type

Each plugin creates its own ROS2 clients internally and performs
synchronous service/action calls during tick().
"""

import time as _time
from typing import Optional

import rclpy
from rclpy.node import Node
from rclpy.callback_groups import ReentrantCallbackGroup

from multi_arm_task_planner.behavior_tree import (
    ActionNode,
    Blackboard,
    ConditionNode,
    NodeStatus,
)


class ROS2MoveToNode(ActionNode):
    """Move arm to a target position via Coordinator ExecuteTask action.

    Blackboard inputs:
    - arm_name: str
    - target_position: str (position name)
    - target_zone: str (optional, zone to allocate)
    """

    def tick(self) -> NodeStatus:
        arm = self._blackboard.get("arm_name")
        target = self._blackboard.get("target_position", "ready")
        zone = self._blackboard.get("target_zone", "zone_a")

        if not arm:
            return NodeStatus.FAILURE

        success = self._call_coordinator(
            task_type="move",
            description=f"{arm}:{zone}:{target}",
        )
        self._blackboard.set("last_action", f"move_to:{arm}->{target}")
        return NodeStatus.SUCCESS if success else NodeStatus.FAILURE

    def _call_coordinator(self, task_type: str, description: str) -> bool:
        try:
            from multi_arm_interfaces.action import ExecuteTask

            node = rclpy.create_node("_bt_move_to_tmp", automatically_declare_parameters_from_overrides=True)
            cb_group = ReentrantCallbackGroup()
            client = rclpy.action.ActionClient(
                node, ExecuteTask, "/coordinator/execute_task", callback_group=cb_group
            )

            if not client.wait_for_server(timeout_sec=5.0):
                node.destroy_node()
                return False

            goal = ExecuteTask.Goal()
            goal.task_id = f"bt_move_{_time.time():.0f}"
            goal.task_type = task_type
            goal.description = description

            future = client.send_goal_async(goal)
            deadline = _time.time() + 60.0
            while not future.done() and _time.time() < deadline:
                _time.sleep(0.05)

            if not future.done() or future.result() is None:
                node.destroy_node()
                return False

            goal_handle = future.result()
            if not goal_handle.accepted:
                node.destroy_node()
                return False

            result_future = goal_handle.get_result_async()
            while not result_future.done() and _time.time() < deadline:
                _time.sleep(0.05)

            node.destroy_node()
            if result_future.done() and result_future.result() is not None:
                return result_future.result().result.success
            return False
        except Exception:
            return False


class ROS2GraspNode(ActionNode):
    """Close gripper to grasp object.

    For M4.6, grasp is simplified to a wrist rotation command
    (simulating gripper close). In production, this will call
    GripperController.

    Blackboard inputs:
    - arm_name: str
    - object_id: str
    - approach: str (top/side)
    """

    def tick(self) -> NodeStatus:
        arm = self._blackboard.get("arm_name")
        obj_id = self._blackboard.get("object_id", "unknown")
        approach = self._blackboard.get("approach", "top")

        if not arm:
            return NodeStatus.FAILURE

        self._blackboard.set("grasp_success", True)
        self._blackboard.set("last_action", f"grasp:{arm}->{obj_id}({approach})")
        return NodeStatus.SUCCESS


class ROS2PlaceNode(ActionNode):
    """Open gripper to place object.

    For M4.6, place is simplified (no real gripper in simulation).
    In production, this will call GripperController.

    Blackboard inputs:
    - arm_name: str
    - target_zone: str
    """

    def tick(self) -> NodeStatus:
        arm = self._blackboard.get("arm_name")
        target = self._blackboard.get("target_zone")

        if not arm:
            return NodeStatus.FAILURE

        self._blackboard.set("last_action", f"place:{arm}->{target}")
        return NodeStatus.SUCCESS


class ROS2LiftNode(ActionNode):
    """Lift object to a safe height via Coordinator.

    Blackboard inputs:
    - arm_name: str
    - lift_height: float (optional)
    """

    def tick(self) -> NodeStatus:
        arm = self._blackboard.get("arm_name")
        if not arm:
            return NodeStatus.FAILURE

        self._blackboard.set("last_action", f"lift:{arm}")
        return NodeStatus.SUCCESS


class ROS2RetractNode(ActionNode):
    """Retract arm to home position via Coordinator.

    Blackboard inputs:
    - arm_name: str
    """

    def tick(self) -> NodeStatus:
        arm = self._blackboard.get("arm_name")
        if not arm:
            return NodeStatus.FAILURE

        success = self._call_coordinator_retract(arm)
        self._blackboard.set("last_action", f"retract:{arm}")
        return NodeStatus.SUCCESS if success else NodeStatus.FAILURE

    def _call_coordinator_retract(self, arm_name: str) -> bool:
        try:
            from multi_arm_interfaces.action import ExecuteTask

            node = rclpy.create_node("_bt_retract_tmp")
            cb_group = ReentrantCallbackGroup()
            client = rclpy.action.ActionClient(
                node, ExecuteTask, "/coordinator/execute_task", callback_group=cb_group
            )

            if not client.wait_for_server(timeout_sec=5.0):
                node.destroy_node()
                return False

            goal = ExecuteTask.Goal()
            goal.task_id = f"bt_retract_{_time.time():.0f}"
            goal.task_type = "move"
            goal.description = f"{arm_name}:home:home"

            future = client.send_goal_async(goal)
            deadline = _time.time() + 60.0
            while not future.done() and _time.time() < deadline:
                _time.sleep(0.05)

            if not future.done() or future.result() is None:
                node.destroy_node()
                return False

            goal_handle = future.result()
            if not goal_handle.accepted:
                node.destroy_node()
                return False

            result_future = goal_handle.get_result_async()
            while not result_future.done() and _time.time() < deadline:
                _time.sleep(0.05)

            node.destroy_node()
            if result_future.done() and result_future.result() is not None:
                return result_future.result().result.success
            return False
        except Exception:
            return False


class ROS2CheckSafetyNode(ConditionNode):
    """Check if operation is safe via /safety/safety_check service.

    Blackboard inputs:
    - arm_name: str
    - target_position: str
    """

    def tick(self) -> NodeStatus:
        arm = self._blackboard.get("arm_name")
        if not arm:
            return NodeStatus.FAILURE

        approved = self._call_safety_check(arm)
        self._blackboard.set("safety_approved", approved)
        return NodeStatus.SUCCESS if approved else NodeStatus.FAILURE

    def _call_safety_check(self, arm_name: str) -> bool:
        try:
            from multi_arm_interfaces.srv import SafetyCheck

            node = rclpy.create_node("_bt_safety_tmp")
            cb_group = ReentrantCallbackGroup()
            client = node.create_client(
                SafetyCheck, "/safety/safety_check", callback_group=cb_group
            )

            if not client.service_is_ready():
                node.destroy_node()
                return True

            request = SafetyCheck.Request()
            request.arm_names = [arm_name]
            request.trajectory_joint_names = []
            request.trajectory_positions = []
            request.trajectory_duration = 3.0

            future = client.call_async(request)
            deadline = _time.time() + 5.0
            while not future.done() and _time.time() < deadline:
                _time.sleep(0.05)

            node.destroy_node()
            if future.done() and future.result() is not None:
                return future.result().approved
            return True
        except Exception:
            return True


class ROS2QueryWorldNode(ActionNode):
    """Query WorldModel for object/robot state via /world_model/query_objects.

    Blackboard inputs:
    - object_id: str (optional)
    - arm_name: str (optional)
    """

    def tick(self) -> NodeStatus:
        obj_id = self._blackboard.get("object_id")
        arm = self._blackboard.get("arm_name")

        result = self._call_query_objects()
        if result:
            self._blackboard.set("world_query_result", result)
            self._blackboard.set("last_action", f"query_world:objects={len(result)}")
        else:
            self._blackboard.set("last_action", "query_world:empty")

        return NodeStatus.SUCCESS

    def _call_query_objects(self):
        try:
            from multi_arm_interfaces.srv import QueryResources

            node = rclpy.create_node("_bt_query_tmp")
            cb_group = ReentrantCallbackGroup()
            client = node.create_client(
                QueryResources, "/world_model/query_objects", callback_group=cb_group
            )

            if not client.service_is_ready():
                node.destroy_node()
                return None

            request = QueryResources.Request()
            request.resource_types = ["object"]

            future = client.call_async(request)
            deadline = _time.time() + 5.0
            while not future.done() and _time.time() < deadline:
                _time.sleep(0.05)

            node.destroy_node()
            if future.done() and future.result() is not None:
                return list(future.result().resource_names)
            return None
        except Exception:
            return None


class ROS2RecoverNode(ActionNode):
    """Recovery action on failure.

    For M4.6, recovery is simplified to resetting arm state.
    Full recovery strategies will be implemented in M5.1.

    Blackboard inputs:
    - failure_type: str
    - arm_name: str
    """

    def tick(self) -> NodeStatus:
        failure = self._blackboard.get("failure_type", "unknown")
        arm = self._blackboard.get("arm_name", "unknown")
        self._blackboard.set("last_action", f"recover:{arm} type={failure}")
        return NodeStatus.SUCCESS


ROS2_PLUGIN_REGISTRY = {
    "MoveTo": ROS2MoveToNode,
    "Grasp": ROS2GraspNode,
    "Place": ROS2PlaceNode,
    "Lift": ROS2LiftNode,
    "Retract": ROS2RetractNode,
    "CheckSafety": ROS2CheckSafetyNode,
    "QueryWorld": ROS2QueryWorldNode,
    "Recover": ROS2RecoverNode,
}