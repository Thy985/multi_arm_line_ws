"""ResourceTimeoutHandler — recovery for resource wait timeouts.

Strategy:
1. Release current resource allocation
2. Re-queue the task with lower priority
3. Abort if still cannot acquire
"""

from typing import Any, Dict, Tuple

from multi_arm_recovery.failure_classifier import FailureEvent, FailureType


class ResourceTimeoutHandler:
    """Handles resource timeout events with release and re-queue strategies."""

    MAX_ATTEMPTS: int = 2

    def __init__(self, default_timeout: float = 30.0) -> None:
        self._attempt_count: int = 0
        self._default_timeout = default_timeout

    def can_handle(self, event: FailureEvent) -> bool:
        """Check if this handler can handle the given failure event.

        Args:
            event: The failure event to check.

        Returns:
            True if the event is a resource timeout.
        """
        return event.failure_type == FailureType.RESOURCE_TIMEOUT

    def get_recovery_strategy(
        self, event: FailureEvent
    ) -> Tuple[str, Dict[str, Any]]:
        """Determine the next recovery strategy for a resource timeout.

        Args:
            event: The resource timeout failure event.

        Returns:
            Tuple of (strategy_name, strategy_params).
        """
        self._attempt_count += 1

        if self._attempt_count == 1:
            return "release_and_requeue", {
                "release_zone": True,
                "wait_before_retry": 5.0,
                "priority_reduction": 1,
            }

        return "release_and_abort", {
            "release_zone": True,
            "safe_position": "home",
        }

    def reset(self) -> None:
        """Reset attempt counter."""
        self._attempt_count = 0

    @property
    def attempts(self) -> int:
        """Number of recovery attempts made so far."""
        return self._attempt_count

    @property
    def exhausted(self) -> bool:
        """Whether all recovery strategies have been exhausted."""
        return self._attempt_count >= self.MAX_ATTEMPTS