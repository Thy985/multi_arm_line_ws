"""PlanningFailureHandler — recovery strategies for motion planning failures.

Strategy chain:
1. Relax constraints (increase tolerance, reduce velocity scaling)
2. Change grasp pose (try alternative approach angle)
3. Release resource and abort
"""

from typing import Any, Dict, Optional, Tuple

from multi_arm_recovery.failure_classifier import FailureEvent, FailureType


class PlanningFailureHandler:
    """Handles planning failures with progressive constraint relaxation.

    Each strategy attempt increases constraint relaxation. After all
    strategies are exhausted, the handler recommends safe abort.
    """

    MAX_ATTEMPTS: int = 3

    def __init__(self) -> None:
        self._attempt_count: int = 0

    def can_handle(self, event: FailureEvent) -> bool:
        """Check if this handler can handle the given failure event.

        Args:
            event: The failure event to check.

        Returns:
            True if the event is a planning failure.
        """
        return event.failure_type == FailureType.PLANNING_FAILURE

    def get_recovery_strategy(
        self, event: FailureEvent
    ) -> Tuple[str, Dict[str, Any]]:
        """Determine the next recovery strategy for a planning failure.

        Args:
            event: The planning failure event.

        Returns:
            Tuple of (strategy_name, strategy_params).
        """
        self._attempt_count += 1

        if self._attempt_count == 1:
            return "relax_constraints", {
                "tolerance_multiplier": 2.0,
                "velocity_scaling": 0.1,
                "accel_scaling": 0.1,
                "planning_time": 20.0,
                "planning_attempts": 20,
            }

        if self._attempt_count == 2:
            return "change_grasp_pose", {
                "approach_offset": [0.0, 0.05, 0.0],
                "velocity_scaling": 0.1,
                "planning_time": 30.0,
            }

        if self._attempt_count == 3:
            return "release_and_abort", {
                "release_zone": True,
                "safe_position": "home",
            }

        return "safe_abort", {"release_zone": True}

    def reset(self) -> None:
        """Reset attempt counter for a new failure sequence."""
        self._attempt_count = 0

    @property
    def attempts(self) -> int:
        """Number of recovery attempts made so far."""
        return self._attempt_count

    @property
    def exhausted(self) -> bool:
        """Whether all recovery strategies have been exhausted."""
        return self._attempt_count >= self.MAX_ATTEMPTS