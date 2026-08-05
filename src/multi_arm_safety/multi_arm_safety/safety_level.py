"""SafetyLevel definitions for the Safety Plane."""

from enum import IntEnum


class SafetyLevel(IntEnum):
    """Safety levels in order of increasing severity.

    NORMAL: All operations permitted, no restrictions.
    SPEED_LIMITED: Speed scaling active, reduced velocity.
    PAUSED: All motion paused, can resume.
    EMERGENCY_STOP: All motion stopped immediately, manual reset required.
    """
    NORMAL = 0
    SPEED_LIMITED = 1
    PAUSED = 2
    EMERGENCY_STOP = 3

    def allows_motion(self) -> bool:
        """Whether motion is permitted at this safety level."""
        return self < SafetyLevel.PAUSED

    def allows_new_commands(self) -> bool:
        """Whether new commands are accepted at this safety level."""
        return self < SafetyLevel.EMERGENCY_STOP