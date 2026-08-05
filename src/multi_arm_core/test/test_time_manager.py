"""Tests for TimeManager."""

import pytest
import time

from multi_arm_core.coordination.time_manager import (
    TimeManager,
    TimeWindow,
    WindowStatus,
    ScheduleResult,
    Conflict,
    predict_duration,
    SAFETY_MARGIN,
)


class TestPredictDuration:
    """Tests for duration prediction."""

    def test_known_position(self) -> None:
        assert predict_duration("home") == 3.0 + SAFETY_MARGIN

    def test_unknown_position(self) -> None:
        assert predict_duration("unknown") == 3.0 + SAFETY_MARGIN

    def test_custom_base(self) -> None:
        assert predict_duration("unknown", 5.0) == 5.0 + SAFETY_MARGIN


class TestTimeWindow:
    """Tests for TimeWindow dataclass."""

    def test_end_time(self) -> None:
        w = TimeWindow(
            arm_name="arm1",
            zone_name="zone_a",
            start_time=100.0,
            duration=3.5,
        )
        assert w.end_time == 103.5

    def test_overlaps_same_zone(self) -> None:
        w1 = TimeWindow(
            arm_name="arm1",
            zone_name="zone_a",
            start_time=100.0,
            duration=3.0,
        )
        w2 = TimeWindow(
            arm_name="arm2",
            zone_name="zone_a",
            start_time=101.0,
            duration=3.0,
        )
        assert w1.overlaps(w2)

    def test_no_overlap_different_zone(self) -> None:
        w1 = TimeWindow(
            arm_name="arm1",
            zone_name="zone_a",
            start_time=100.0,
            duration=3.0,
        )
        w2 = TimeWindow(
            arm_name="arm2",
            zone_name="zone_b",
            start_time=101.0,
            duration=3.0,
        )
        assert not w1.overlaps(w2)

    def test_no_overlap_sequential(self) -> None:
        w1 = TimeWindow(
            arm_name="arm1",
            zone_name="zone_a",
            start_time=100.0,
            duration=3.0,
        )
        w2 = TimeWindow(
            arm_name="arm2",
            zone_name="zone_a",
            start_time=103.5,
            duration=3.0,
        )
        assert not w1.overlaps(w2)

    def test_is_active(self) -> None:
        w = TimeWindow(
            arm_name="arm1",
            zone_name="zone_a",
            start_time=100.0,
            duration=3.0,
        )
        assert w.is_active()
        w.status = WindowStatus.COMPLETED
        assert not w.is_active()


class TestTimeManager:
    """Tests for the TimeManager class."""

    def test_schedule_no_conflict(self) -> None:
        tm = TimeManager()
        result = tm.schedule("arm1", "zone_a", duration=3.0)
        assert result.granted
        assert result.window is not None
        assert result.conflict is None

    def test_schedule_conflict_same_zone(self) -> None:
        tm = TimeManager()
        tm.schedule("arm1", "zone_a", duration=3.0)
        result = tm.schedule("arm2", "zone_a", duration=3.0)
        assert not result.granted
        assert result.conflict is not None
        assert result.suggested_delay > 0

    def test_no_conflict_different_zone(self) -> None:
        tm = TimeManager()
        tm.schedule("arm1", "zone_a", duration=3.0)
        result = tm.schedule("arm2", "zone_b", duration=3.0)
        assert result.granted

    def test_no_conflict_same_arm(self) -> None:
        tm = TimeManager()
        tm.schedule("arm1", "zone_a", duration=3.0)
        result = tm.schedule("arm1", "zone_a", duration=3.0, start_delay=5.0)
        assert result.granted

    def test_cancel(self) -> None:
        tm = TimeManager()
        tm.schedule("arm1", "zone_a", duration=3.0, start_delay=10.0)
        assert tm.cancel("arm1")

    def test_start_executing(self) -> None:
        tm = TimeManager()
        result = tm.schedule("arm1", "zone_a", duration=3.0)
        tm.start_executing("arm1")
        active = tm.get_active_windows("zone_a")
        assert any(w.status == WindowStatus.EXECUTING for w in active)

    def test_complete(self) -> None:
        tm = TimeManager()
        tm.schedule("arm1", "zone_a", duration=3.0)
        tm.start_executing("arm1")
        tm.complete("arm1")
        active = tm.get_active_windows("zone_a")
        assert len(active) == 0

    def test_get_zone_end_time(self) -> None:
        tm = TimeManager()
        now = tm.now()
        result = tm.schedule("arm1", "zone_a", duration=3.0)
        end_time = tm.get_zone_end_time("zone_a")
        assert end_time > now

    def test_get_arm_end_time(self) -> None:
        tm = TimeManager()
        now = tm.now()
        tm.schedule("arm1", "zone_a", duration=3.0)
        end_time = tm.get_arm_end_time("arm1")
        assert end_time > now

    def test_cleanup(self) -> None:
        tm = TimeManager()
        tm.schedule("arm1", "zone_a", duration=3.0)
        tm.start_executing("arm1")
        tm.complete("arm1")
        tm.cleanup()

    def test_schedule_with_delay_avoids_conflict(self) -> None:
        tm = TimeManager()
        result1 = tm.schedule("arm1", "zone_a", duration=3.0)
        assert result1.granted

        result2 = tm.schedule("arm2", "zone_a", duration=3.0)
        assert not result2.granted

        result3 = tm.schedule(
            "arm2", "zone_a", duration=3.0, start_delay=result2.suggested_delay + 0.1
        )
        assert result3.granted