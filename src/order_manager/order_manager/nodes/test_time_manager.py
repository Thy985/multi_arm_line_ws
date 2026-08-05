#!/usr/bin/env python3
"""
Unit tests for TimeManager.
Pure logic tests — no ROS environment needed.
"""

import sys
import time
from order_manager.nodes.time_manager import (
    TimeManager, TimeWindow, WindowStatus, Conflict, ScheduleResult,
    predict_duration, SAFETY_MARGIN
)


class MockTimeManager(TimeManager):
    """TimeManager with controllable clock for testing."""
    
    def __init__(self, start_time: float = 1000.0):
        super().__init__()
        self._mock_time = start_time
    
    def now(self) -> float:
        return self._mock_time
    
    def advance(self, seconds: float):
        """Advance the mock clock."""
        self._mock_time += seconds


# ============================================================
# Test Framework
# ============================================================

def test(name, fn):
    """Run a test and print result."""
    try:
        fn()
        print(f"  [PASS] {name}")
        return True
    except AssertionError as e:
        print(f"  [FAIL] {name}: {e}")
        return False
    except Exception as e:
        print(f"  [ERROR] {name}: {e}")
        return False


# ============================================================
# Tests
# ============================================================

def test_predict_duration():
    """predict_duration returns base + safety margin."""
    d = predict_duration('ready')
    assert d == 3.0 + SAFETY_MARGIN, f"Expected {3.0 + SAFETY_MARGIN}, got {d}"
    
    d2 = predict_duration('extended')
    assert d2 == 4.0 + SAFETY_MARGIN, f"Expected {4.0 + SAFETY_MARGIN}, got {d2}"
    
    d3 = predict_duration('unknown', base_duration=5.0)
    assert d3 == 5.0 + SAFETY_MARGIN, f"Expected {5.0 + SAFETY_MARGIN}, got {d3}"


def test_time_window_overlaps():
    """TimeWindow.overlaps detects overlapping intervals."""
    w1 = TimeWindow('arm1', 'zone_a', start_time=10.0, duration=5.0)
    w2 = TimeWindow('arm2', 'zone_a', start_time=12.0, duration=5.0)  # overlaps
    w3 = TimeWindow('arm2', 'zone_a', start_time=20.0, duration=5.0)  # no overlap
    w4 = TimeWindow('arm2', 'zone_b', start_time=12.0, duration=5.0)  # different zone
    
    assert w1.overlaps(w2), "w1 and w2 should overlap"
    assert w2.overlaps(w1), "w2 and w1 should overlap (symmetric)"
    assert not w1.overlaps(w3), "w1 and w3 should NOT overlap"
    assert not w1.overlaps(w4), "w1 and w4 should NOT overlap (different zone)"
    
    # Adjacent windows (no overlap)
    w5 = TimeWindow('arm2', 'zone_a', start_time=15.0, duration=5.0)
    assert not w1.overlaps(w5), "w1 and w5 should NOT overlap (adjacent)"


def test_schedule_no_conflict():
    """Scheduling two arms to different zones should succeed."""
    tm = MockTimeManager(start_time=100.0)
    
    r1 = tm.schedule('arm1', 'zone_a', duration=3.0)
    assert r1.granted, f"arm1 should be granted: {r1.message}"
    assert r1.conflict is None
    
    r2 = tm.schedule('arm2', 'zone_b', duration=3.0)
    assert r2.granted, f"arm2 should be granted: {r2.message}"
    assert r2.conflict is None


def test_schedule_conflict_same_zone():
    """Scheduling two arms to the same zone with overlapping time should conflict."""
    tm = MockTimeManager(start_time=100.0)
    
    # arm1 enters zone_a at t=100, stays for 5s (until t=105)
    r1 = tm.schedule('arm1', 'zone_a', duration=5.0)
    assert r1.granted, f"arm1 should be granted: {r1.message}"
    
    # arm2 enters zone_a at t=102, would overlap with arm1
    tm.advance(2.0)
    r2 = tm.schedule('arm2', 'zone_a', duration=3.0)
    assert not r2.granted, f"arm2 should be conflicted: {r2.message}"
    assert r2.conflict is not None
    assert r2.conflict.arm_a == 'arm2'
    assert r2.conflict.arm_b == 'arm1'
    assert r2.suggested_delay > 0, "Should suggest a positive delay"


def test_schedule_no_conflict_sequential():
    """Scheduling two arms to same zone at different times should succeed."""
    tm = MockTimeManager(start_time=100.0)
    
    # arm1 enters zone_a at t=100, stays for 3s (until t=103)
    r1 = tm.schedule('arm1', 'zone_a', duration=3.0)
    assert r1.granted
    
    # arm2 enters zone_a at t=104 (after arm1 leaves)
    tm.advance(4.0)  # now at t=104
    r2 = tm.schedule('arm2', 'zone_a', duration=3.0)
    assert r2.granted, f"arm2 should be granted (no overlap): {r2.message}"


def test_schedule_suggests_delay():
    """When conflict detected, suggested_delay should be enough to avoid it."""
    tm = MockTimeManager(start_time=100.0)
    
    # arm1 enters zone_a at t=100, stays for 5s
    r1 = tm.schedule('arm1', 'zone_a', duration=5.0)
    
    # arm2 tries to enter at t=102
    tm.advance(2.0)
    r2 = tm.schedule('arm2', 'zone_a', duration=3.0)
    
    assert not r2.granted
    assert r2.suggested_delay >= 3.0, \
        f"Delay should be >= 3.0 (arm1 ends at 105, arm2 starts at 102): {r2.suggested_delay}"
    
    # Verify: if arm2 delays by suggested_delay, no conflict
    delayed_start = 102.0 + r2.suggested_delay
    delayed_window = TimeWindow('arm2', 'zone_a', start_time=delayed_start, duration=3.0)
    arm1_window = r1.window
    assert not delayed_window.overlaps(arm1_window), \
        "Delayed window should not overlap with arm1"


def test_cancel():
    """Cancelling an arm removes its scheduled windows."""
    tm = MockTimeManager(start_time=100.0)
    
    tm.schedule('arm1', 'zone_a', duration=5.0)
    tm.schedule('arm2', 'zone_b', duration=3.0)
    
    # Cancel arm1
    cancelled = tm.cancel('arm1')
    assert cancelled, "Should cancel arm1's windows"
    
    active = tm.get_active_windows()
    arm1_windows = [w for w in active if w.arm_name == 'arm1']
    assert len(arm1_windows) == 0, "arm1 should have no active windows"
    
    # arm2 should still be active
    arm2_windows = [w for w in active if w.arm_name == 'arm2']
    assert len(arm2_windows) == 1, "arm2 should still have 1 active window"


def test_lifecycle():
    """Test scheduled -> executing -> completed lifecycle."""
    tm = MockTimeManager(start_time=100.0)
    
    tm.schedule('arm1', 'zone_a', duration=3.0, start_delay=0.0)
    
    # Initially scheduled
    windows = tm.get_active_windows('zone_a')
    assert len(windows) == 1
    assert windows[0].status == WindowStatus.SCHEDULED
    
    # Start executing
    tm.start_executing('arm1')
    windows = tm.get_active_windows('zone_a')
    assert windows[0].status == WindowStatus.EXECUTING
    
    # Complete
    tm.complete('arm1')
    windows = tm.get_active_windows('zone_a')
    assert len(windows) == 0, "Completed window should not be active"


def test_zone_end_time():
    """get_zone_end_time returns the latest end time of active windows."""
    tm = MockTimeManager(start_time=100.0)
    
    # No windows -> returns current time
    end = tm.get_zone_end_time('zone_a')
    assert end == 100.0
    
    # arm1: zone_a, duration 5 (ends at 105)
    tm.schedule('arm1', 'zone_a', duration=5.0)
    end = tm.get_zone_end_time('zone_a')
    assert end == 105.0
    
    # arm2: zone_a, duration 3 starting at t=102 (ends at 105)
    tm.advance(2.0)
    tm.schedule('arm2', 'zone_a', duration=3.0)
    end = tm.get_zone_end_time('zone_a')
    assert end == 105.0, f"Should be 105 (max of both end times), got {end}"


def test_cleanup():
    """cleanup removes old completed windows."""
    tm = MockTimeManager(start_time=100.0)
    
    tm.schedule('arm1', 'zone_a', duration=3.0)
    tm.start_executing('arm1')
    tm.complete('arm1')
    
    # Window is completed but still in list
    assert len(tm._windows) == 1
    
    # Advance time past cleanup threshold
    tm.advance(70.0)
    tm.cleanup()
    
    # Should be cleaned up
    assert len(tm._windows) == 0, "Old completed window should be cleaned up"


def test_arm_end_time():
    """get_arm_end_time returns latest end time for an arm's windows."""
    tm = MockTimeManager(start_time=100.0)
    
    # No windows
    end = tm.get_arm_end_time('arm1')
    assert end == 100.0
    
    # arm1 in zone_a (ends at 105)
    tm.schedule('arm1', 'zone_a', duration=5.0)
    end = tm.get_arm_end_time('arm1')
    assert end == 105.0


def test_multiple_zones():
    """Arms in different zones don't conflict."""
    tm = MockTimeManager(start_time=100.0)
    
    r1 = tm.schedule('arm1', 'zone_a', duration=5.0)
    r2 = tm.schedule('arm2', 'zone_b', duration=5.0)
    
    assert r1.granted and r2.granted, "Different zones should not conflict"


# ============================================================
# Main
# ============================================================

def main():
    print("=" * 50)
    print("  TimeManager Unit Tests")
    print("=" * 50)
    
    tests = [
        ("predict_duration", test_predict_duration),
        ("time_window_overlaps", test_time_window_overlaps),
        ("schedule_no_conflict", test_schedule_no_conflict),
        ("schedule_conflict_same_zone", test_schedule_conflict_same_zone),
        ("schedule_no_conflict_sequential", test_schedule_no_conflict_sequential),
        ("schedule_suggests_delay", test_schedule_suggests_delay),
        ("cancel", test_cancel),
        ("lifecycle", test_lifecycle),
        ("zone_end_time", test_zone_end_time),
        ("cleanup", test_cleanup),
        ("arm_end_time", test_arm_end_time),
        ("multiple_zones", test_multiple_zones),
    ]
    
    passed = 0
    for name, fn in tests:
        if test(name, fn):
            passed += 1
    
    print(f"\n  Result: {passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == '__main__':
    sys.exit(main())
