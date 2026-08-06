"""GraspRetryHandler — recovery for grasp/gripper failures.

Strategy:
1. Retry with adjusted approach (max 3 attempts)
2. Release resource and abort
"""

from typing import Any, Dict, Tuple

from multi_arm_recovery.failure_classifier import FailureEvent, FailureType


class GraspRetryHandler:
    """Handles grasp failures with retry and approach adjustment."""

    MAX_RETRIES: int = 3

    def __init__(self) -> None:
        self._retry_count: int = 0

    def can_handle(self, event: FailureEvent) -> bool:
        """Check if this handler can handle the given failure event.

        Args:
            event: The failure event to check.

        Returns:
            True if the event is a grasp failure.
        """
        return event.failure_type == FailureType.GRASP_FAILURE

    def get_recovery_strategy(
        self, event: FailureEvent
    ) -> Tuple[str, Dict[str, Any]]:
        """Determine the next recovery strategy for a grasp failure.

        Args:
            event: The grasp failure event.

        Returns:
            Tuple of (strategy_name, strategy_params).
        """
        self._retry_count += 1

        if self._retry_count <= self.MAX_RETRIES:
            offset = 0.01 * self._retry_count
            return "retry_grasp", {
                "attempt": self._retry_count,
                "approach_offset_z": offset,
                "grip_force_increase": 0.1 * self._retry_count,
            }

        return "release_and_abort", {
            "release_zone": True,
            "safe_position": "home",
        }

    def reset(self) -> None:
        """Reset retry counter."""
        self._retry_count = 0

    @property
    def attempts(self) -> int:
        """Number of recovery attempts made so far."""
        return self._retry_count

    @property
    def exhausted(self) -> bool:
        """Whether all recovery strategies have been exhausted."""
        return self._retry_count > self.MAX_RETRIES