"""CollisionHandler — recovery strategies for collision events.

Strategy chain:
1. Retreat to safe position
2. Replan with collision avoidance
3. Release resource and abort
"""

from typing import Any, Dict, Tuple

from multi_arm_recovery.failure_classifier import FailureEvent, FailureType


class CollisionHandler:
    """Handles collision detection events with retreat and replan strategies."""

    MAX_ATTEMPTS: int = 3

    def __init__(self) -> None:
        self._attempt_count: int = 0

    def can_handle(self, event: FailureEvent) -> bool:
        """Check if this handler can handle the given failure event.

        Args:
            event: The failure event to check.

        Returns:
            True if the event is a collision detection.
        """
        return event.failure_type == FailureType.COLLISION_DETECTED

    def get_recovery_strategy(
        self, event: FailureEvent
    ) -> Tuple[str, Dict[str, Any]]:
        """Determine the next recovery strategy for a collision.

        Args:
            event: The collision failure event.

        Returns:
            Tuple of (strategy_name, strategy_params).
        """
        self._attempt_count += 1

        if self._attempt_count == 1:
            return "retreat_to_safe", {
                "safe_position": "home",
                "velocity_scaling": 0.05,
            }

        if self._attempt_count == 2:
            return "replan_with_avoidance", {
                "collision_padding": 0.05,
                "velocity_scaling": 0.1,
                "planning_time": 30.0,
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