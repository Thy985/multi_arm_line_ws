"""FailureClassifier — classifies failure events into recovery categories.

Maps error messages and context into typed FailureEvent objects that
RecoveryManager can route to appropriate handlers.
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional


class FailureType(Enum):
    """Classification of failure categories."""

    PLANNING_FAILURE = auto()
    COLLISION_DETECTED = auto()
    RESOURCE_TIMEOUT = auto()
    CONTROLLER_FAILURE = auto()
    GRASP_FAILURE = auto()
    SAFETY_REJECTION = auto()
    EXECUTION_TIMEOUT = auto()
    GOAL_REJECTED = auto()
    UNKNOWN = auto()


@dataclass
class FailureEvent:
    """Represents a classified failure event.

    Attributes:
        failure_type: The classified category of the failure.
        arm_name: Name of the arm that failed.
        message: Original error message string.
        context: Additional context (zone, position, error_code, etc.).
        recoverable: Whether the failure is potentially recoverable.
        task_id: ID of the task that failed.
    """

    failure_type: FailureType
    arm_name: str = ""
    message: str = ""
    context: Dict[str, Any] = field(default_factory=dict)
    recoverable: bool = True
    task_id: str = ""


class FailureClassifier:
    """Classifies raw failure signals into typed FailureEvent objects.

    Uses pattern matching on error messages and context to determine
    the failure type and whether it is recoverable.
    """

    PLANNING_PATTERNS: List[str] = [
        "moveit_error_",
        "goal_send_timeout",
        "move_group_not_ready",
        "moveit_unavailable",
        "goal_rejected",
    ]

    COLLISION_PATTERNS: List[str] = [
        "collision",
        "collided",
    ]

    RESOURCE_PATTERNS: List[str] = [
        "occupied",
        "resource",
    ]

    CONTROLLER_PATTERNS: List[str] = [
        "jtc_failed",
        "jtc_goal_rejected",
        "jtc_execution_timeout",
        "jtc_goal_send_failed",
        "jtc action server not available",
        "error_code",
    ]

    SAFETY_PATTERNS: List[str] = [
        "safety",
        "e_stop",
        "e-stop",
        "estop",
    ]

    EXECUTION_TIMEOUT_PATTERNS: List[str] = [
        "execution_timeout",

        "goal timeout",
    ]

    GRASP_PATTERNS: List[str] = [
        "grasp",
        "grip",
        "gripper",
    ]

    NON_RECOVERABLE_TYPES: set = {
        FailureType.SAFETY_REJECTION,
    }

    def classify(
        self,
        message: str,
        arm_name: str = "",
        context: Optional[Dict[str, Any]] = None,
        task_id: str = "",
    ) -> FailureEvent:
        """Classify a failure from its error message and context.

        Args:
            message: Error message string from the failing component.
            arm_name: Name of the arm that experienced the failure.
            context: Additional context for classification.
            task_id: ID of the task that failed.

        Returns:
            Classified FailureEvent with type and recoverability.
        """
        msg_lower = message.lower()
        ctx = context or {}

        if ctx.get("collision_detected"):
            return self._make_event(
                FailureType.COLLISION_DETECTED, message, arm_name, ctx, task_id
            )

        if ctx.get("grasp_failed"):
            return self._make_event(
                FailureType.GRASP_FAILURE, message, arm_name, ctx, task_id
            )

        if ctx.get("resource_timeout"):
            return self._make_event(
                FailureType.RESOURCE_TIMEOUT, message, arm_name, ctx, task_id
            )

        for pattern in self.SAFETY_PATTERNS:
            if pattern in msg_lower:
                return self._make_event(
                    FailureType.SAFETY_REJECTION, message, arm_name, ctx, task_id
                )

        for pattern in self.COLLISION_PATTERNS:
            if pattern in msg_lower:
                return self._make_event(
                    FailureType.COLLISION_DETECTED, message, arm_name, ctx, task_id
                )

        for pattern in self.RESOURCE_PATTERNS:
            if pattern in msg_lower:
                return self._make_event(
                    FailureType.RESOURCE_TIMEOUT, message, arm_name, ctx, task_id
                )

        for pattern in self.EXECUTION_TIMEOUT_PATTERNS:
            if pattern in msg_lower:
                return self._make_event(
                    FailureType.EXECUTION_TIMEOUT, message, arm_name, ctx, task_id
                )

        for pattern in self.CONTROLLER_PATTERNS:
            if pattern in msg_lower:
                return self._make_event(
                    FailureType.CONTROLLER_FAILURE, message, arm_name, ctx, task_id
                )

        for pattern in self.PLANNING_PATTERNS:
            if pattern in msg_lower:
                return self._make_event(
                    FailureType.PLANNING_FAILURE, message, arm_name, ctx, task_id
                )

        for pattern in self.GRASP_PATTERNS:
            if pattern in msg_lower:
                return self._make_event(
                    FailureType.GRASP_FAILURE, message, arm_name, ctx, task_id
                )

        if "goal_rejected" in msg_lower:
            return self._make_event(
                FailureType.GOAL_REJECTED, message, arm_name, ctx, task_id
            )

        return self._make_event(
            FailureType.UNKNOWN, message, arm_name, ctx, task_id
        )

    def _make_event(
        self,
        failure_type: FailureType,
        message: str,
        arm_name: str,
        context: Dict[str, Any],
        task_id: str,
    ) -> FailureEvent:
        """Create a FailureEvent with recoverability determined by type.

        Args:
            failure_type: Classified failure type.
            message: Original error message.
            arm_name: Arm that failed.
            context: Additional context.
            task_id: Task ID.

        Returns:
            FailureEvent with recoverability set.
        """
        recoverable = failure_type not in self.NON_RECOVERABLE_TYPES
        return FailureEvent(
            failure_type=failure_type,
            arm_name=arm_name,
            message=message,
            context=context,
            recoverable=recoverable,
            task_id=task_id,
        )