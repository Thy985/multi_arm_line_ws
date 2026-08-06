"""ControllerFailureHandler — recovery for controller/JTC failures.

Strategy:
1. Wait and retry (controller may be temporarily unavailable)
2. Switch to fallback controller (if available)
3. Safe abort
"""

from typing import Any, Dict, Tuple

from multi_arm_recovery.failure_classifier import FailureEvent, FailureType


class ControllerFailureHandler:
    """Handles controller/JTC failure events with retry and fallback."""

    MAX_ATTEMPTS: int = 3

    def __init__(self) -> None:
        self._attempt_count: int = 0

    def can_handle(self, event: FailureEvent) -> bool:
        """Check if this handler can handle the given failure event.

        Args:
            event: The failure event to check.

        Returns:
            True if the event is a controller failure.
        """
        return event.failure_type == FailureType.CONTROLLER_FAILURE

    def get_recovery_strategy(
        self, event: FailureEvent
    ) -> Tuple[str, Dict[str, Any]]:
        """Determine the next recovery strategy for a controller failure.

        Args:
            event: The controller failure event.

        Returns:
            Tuple of (strategy_name, strategy_params).
        """
        self._attempt_count += 1

        if self._attempt_count == 1:
            return "wait_and_retry", {
                "wait_seconds": 2.0,
                "check_controller_active": True,
            }

        if self._attempt_count == 2:
            return "switch_controller", {
                "fallback_controller": "forward_position_controller",
                "reactivate_jtc_after": True,
            }

        return "safe_abort", {
            "release_zone": True,
            "set_arm_error": True,
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