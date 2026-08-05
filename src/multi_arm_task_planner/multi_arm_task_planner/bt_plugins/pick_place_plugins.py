"""BT Python plugins for multi-arm task planning."""

from typing import Optional
from multi_arm_task_planner.behavior_tree import (
    ActionNode,
    Blackboard,
    ConditionNode,
    NodeStatus,
)


class MoveToNode(ActionNode):
    """Move arm to a target position/zone.

    Blackboard inputs:
    - target_position: str (position name or zone)
    - arm_name: str
    - duration: float (optional)
    """

    def tick(self) -> NodeStatus:
        target = self._blackboard.get("target_position")
        arm = self._blackboard.get("arm_name")
        if not target or not arm:
            return NodeStatus.FAILURE
        self._blackboard.set("last_action", f"move_to:{arm}->{target}")
        return NodeStatus.SUCCESS


class GraspNode(ActionNode):
    """Close gripper to grasp object.

    Blackboard inputs:
    - object_id: str
    - arm_name: str
    - approach: str (top/side)
    """

    def tick(self) -> NodeStatus:
        obj_id = self._blackboard.get("object_id")
        arm = self._blackboard.get("arm_name")
        approach = self._blackboard.get("approach", "top")
        if not obj_id or not arm:
            return NodeStatus.FAILURE
        self._blackboard.set("last_action", f"grasp:{arm}->{obj_id}({approach})")
        self._blackboard.set("grasp_success", True)
        return NodeStatus.SUCCESS


class PlaceNode(ActionNode):
    """Open gripper to place object at target.

    Blackboard inputs:
    - target_zone: str
    - arm_name: str
    """

    def tick(self) -> NodeStatus:
        target = self._blackboard.get("target_zone")
        arm = self._blackboard.get("arm_name")
        if not target or not arm:
            return NodeStatus.FAILURE
        self._blackboard.set("last_action", f"place:{arm}->{target}")
        return NodeStatus.SUCCESS


class LiftNode(ActionNode):
    """Lift object to a safe height.

    Blackboard inputs:
    - arm_name: str
    - lift_height: float (optional, default 0.1)
    """

    def tick(self) -> NodeStatus:
        arm = self._blackboard.get("arm_name")
        height = self._blackboard.get("lift_height", 0.1)
        if not arm:
            return NodeStatus.FAILURE
        self._blackboard.set("last_action", f"lift:{arm} h={height}")
        return NodeStatus.SUCCESS


class RetractNode(ActionNode):
    """Retract arm to safe position after placing.

    Blackboard inputs:
    - arm_name: str
    """

    def tick(self) -> NodeStatus:
        arm = self._blackboard.get("arm_name")
        if not arm:
            return NodeStatus.FAILURE
        self._blackboard.set("last_action", f"retract:{arm}")
        return NodeStatus.SUCCESS


class CheckSafetyNode(ConditionNode):
    """Check if operation is safe via Safety Plane.

    Blackboard inputs:
    - arm_name: str
    - target_position: str
    """

    def tick(self) -> NodeStatus:
        arm = self._blackboard.get("arm_name")
        if not arm:
            return NodeStatus.FAILURE
        is_safe = self._blackboard.get("safety_approved", True)
        return NodeStatus.SUCCESS if is_safe else NodeStatus.FAILURE


class QueryWorldNode(ActionNode):
    """Query WorldModel for object/robot state.

    Blackboard inputs:
    - object_id: str (optional)
    - arm_name: str (optional)
    """

    def tick(self) -> NodeStatus:
        obj_id = self._blackboard.get("object_id")
        arm = self._blackboard.get("arm_name")
        if obj_id:
            self._blackboard.set("last_action", f"query_object:{obj_id}")
        if arm:
            self._blackboard.set("last_action", f"query_robot:{arm}")
        return NodeStatus.SUCCESS


class RecoverNode(ActionNode):
    """Recovery action on failure.

    Blackboard inputs:
    - failure_type: str
    - arm_name: str
    """

    def tick(self) -> NodeStatus:
        failure = self._blackboard.get("failure_type", "unknown")
        arm = self._blackboard.get("arm_name", "unknown")
        self._blackboard.set("last_action", f"recover:{arm} type={failure}")
        return NodeStatus.SUCCESS


PLUGIN_REGISTRY = {
    "MoveTo": MoveToNode,
    "Grasp": GraspNode,
    "Place": PlaceNode,
    "Lift": LiftNode,
    "Retract": RetractNode,
    "CheckSafety": CheckSafetyNode,
    "QueryWorld": QueryWorldNode,
    "Recover": RecoverNode,
}