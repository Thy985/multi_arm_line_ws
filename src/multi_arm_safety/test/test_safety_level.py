"""Tests for SafetyLevel."""

import pytest

from multi_arm_safety.safety_level import SafetyLevel


class TestSafetyLevel:
    """Tests for SafetyLevel enum."""

    def test_ordering(self) -> None:
        assert SafetyLevel.NORMAL < SafetyLevel.SPEED_LIMITED
        assert SafetyLevel.SPEED_LIMITED < SafetyLevel.PAUSED
        assert SafetyLevel.PAUSED < SafetyLevel.EMERGENCY_STOP

    def test_allows_motion(self) -> None:
        assert SafetyLevel.NORMAL.allows_motion()
        assert SafetyLevel.SPEED_LIMITED.allows_motion()
        assert not SafetyLevel.PAUSED.allows_motion()
        assert not SafetyLevel.EMERGENCY_STOP.allows_motion()

    def test_allows_new_commands(self) -> None:
        assert SafetyLevel.NORMAL.allows_new_commands()
        assert SafetyLevel.SPEED_LIMITED.allows_new_commands()
        assert SafetyLevel.PAUSED.allows_new_commands()
        assert not SafetyLevel.EMERGENCY_STOP.allows_new_commands()

    def test_int_values(self) -> None:
        assert SafetyLevel.NORMAL == 0
        assert SafetyLevel.EMERGENCY_STOP == 3