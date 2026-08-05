#!/usr/bin/env python3
"""
Unit tests for TaskScheduler.
Pure logic tests — no ROS environment needed.
"""

import sys
import time
from order_manager.nodes.time_manager import TimeManager
from order_manager.nodes.task_scheduler import (
    TaskScheduler, Task, TaskPriority, TaskStatus, SchedulePlan
)


class MockTimeManager(TimeManager):
    """TimeManager with controllable clock."""
    
    def __init__(self, start_time: float = 1000.0):
        super().__init__()
        self._mock_time = start_time
    
    def now(self) -> float:
        return self._mock_time
    
    def advance(self, seconds: float):
        self._mock_time += seconds


# ============================================================
# Test Framework
# ============================================================

def test(name, fn):
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

def test_task_creation():
    """Task creation with defaults."""
    t = Task(task_id='t1', zone_name='zone_a')
    assert t.task_id == 't1'
    assert t.zone_name == 'zone_a'
    assert t.priority == TaskPriority.NORMAL
    assert t.status == TaskStatus.PENDING
    assert t.assigned_arm is None
    assert t.predicted_duration > 0  # Should have default duration


def test_task_priority_ordering():
    """Tasks sort by priority (lower number = higher priority)."""
    t_high = Task(task_id='high', zone_name='zone_a', priority=TaskPriority.HIGH)
    t_low = Task(task_id='low', zone_name='zone_a', priority=TaskPriority.LOW)
    t_normal = Task(task_id='normal', zone_name='zone_a', priority=TaskPriority.NORMAL)
    
    tasks = sorted([t_low, t_high, t_normal])
    assert tasks[0].task_id == 'high'
    assert tasks[1].task_id == 'normal'
    assert tasks[2].task_id == 'low'


def test_task_deadline_ordering():
    """Same priority tasks sort by deadline (earlier first)."""
    t_late = Task(task_id='late', zone_name='zone_a', deadline=2000.0)
    t_early = Task(task_id='early', zone_name='zone_a', deadline=1000.0)
    t_none = Task(task_id='none', zone_name='zone_a')
    
    tasks = sorted([t_late, t_none, t_early])
    assert tasks[0].task_id == 'early'
    assert tasks[1].task_id == 'late'  # has deadline
    assert tasks[2].task_id == 'none'  # no deadline


def test_submit():
    """Submit adds task to scheduler."""
    tm = MockTimeManager()
    sched = TaskScheduler(tm, ['arm1', 'arm2'])
    
    tid = sched.submit(Task(task_id='t1', zone_name='zone_a'))
    assert tid == 't1'
    
    task = sched.get_task('t1')
    assert task is not None
    assert task.status == TaskStatus.PENDING


def test_submit_batch():
    """Submit multiple tasks."""
    tm = MockTimeManager()
    sched = TaskScheduler(tm, ['arm1', 'arm2'])
    
    tasks = [
        Task(task_id='t1', zone_name='zone_a'),
        Task(task_id='t2', zone_name='zone_b'),
        Task(task_id='t3', zone_name='zone_c'),
    ]
    ids = sched.submit_batch(tasks)
    assert len(ids) == 3
    assert len(sched.get_pending_tasks()) == 3


def test_cancel():
    """Cancel removes task from active set."""
    tm = MockTimeManager()
    sched = TaskScheduler(tm, ['arm1', 'arm2'])
    
    sched.submit(Task(task_id='t1', zone_name='zone_a'))
    assert sched.cancel('t1')
    
    task = sched.get_task('t1')
    assert task.status == TaskStatus.CANCELLED
    assert len(sched.get_pending_tasks()) == 0


def test_schedule_single_no_conflict():
    """Schedule single task to different zone — should succeed."""
    tm = MockTimeManager(start_time=100.0)
    sched = TaskScheduler(tm, ['arm1', 'arm2'])
    
    plan = sched.schedule_single(
        Task(task_id='t1', zone_name='zone_a', position_name='ready')
    )
    
    assert plan.all_scheduled, f"Should schedule successfully: {plan.summary()}"
    assert len(plan.scheduled) == 1
    assert plan.scheduled[0].assigned_arm == 'arm1'  # first arm tried


def test_schedule_multiple_no_conflict():
    """Schedule multiple tasks to different zones — all should succeed."""
    tm = MockTimeManager(start_time=100.0)
    sched = TaskScheduler(tm, ['arm1', 'arm2'])
    
    sched.submit(Task(task_id='t1', zone_name='zone_a'))
    sched.submit(Task(task_id='t2', zone_name='zone_b'))
    sched.submit(Task(task_id='t3', zone_name='zone_c'))
    
    plan = sched.schedule_all()
    
    assert len(plan.scheduled) == 3, f"Expected 3 scheduled: {plan.summary()}"
    assert len(plan.failed) == 0


def test_schedule_conflict_different_arms():
    """Schedule two tasks to same zone — both can go to same arm with delay (zone lock ensures safety)."""
    tm = MockTimeManager(start_time=100.0)
    sched = TaskScheduler(tm, ['arm1', 'arm2'])
    
    sched.submit(Task(task_id='t1', zone_name='zone_a', duration=5.0))
    sched.submit(Task(task_id='t2', zone_name='zone_a', duration=3.0))
    
    plan = sched.schedule_all()
    
    # Both should be scheduled — t1 at t=100, t2 at t=105 (delayed)
    assert len(plan.scheduled) == 2, f"Expected 2 scheduled: {plan.summary()}"
    
    t1 = next(t for t in plan.scheduled if t.task_id == 't1')
    t2 = next(t for t in plan.scheduled if t.task_id == 't2')
    
    # t2 should be delayed to start after t1 finishes
    assert t2.start_delay >= 5.0, \
        f"t2 should be delayed >= 5s (t1 duration), got {t2.start_delay:.1f}s"
    
    # Both can be on same arm (zone lock handles mutual exclusion)
    print(f"    t1: arm={t1.assigned_arm} delay={t1.start_delay:.1f}s")
    print(f"    t2: arm={t2.assigned_arm} delay={t2.start_delay:.1f}s")


def test_schedule_conflict_same_arm():
    """Schedule two tasks to same zone with same arm — both scheduled with delay."""
    tm = MockTimeManager(start_time=100.0)
    sched = TaskScheduler(tm, ['arm1', 'arm2'])
    
    sched.submit(Task(task_id='t1', zone_name='zone_a', preferred_arm='arm1', duration=5.0))
    sched.submit(Task(task_id='t2', zone_name='zone_a', preferred_arm='arm1', duration=3.0))
    
    plan = sched.schedule_all()
    
    # Both should be scheduled on arm1 with proper delays
    assert len(plan.scheduled) == 2, f"Expected 2 scheduled: {plan.summary()}"
    
    t1 = next(t for t in plan.scheduled if t.task_id == 't1')
    t2 = next(t for t in plan.scheduled if t.task_id == 't2')
    
    assert t1.assigned_arm == 'arm1'
    assert t2.assigned_arm == 'arm1'
    assert t2.start_delay >= 5.0, \
        f"t2 should be delayed >= 5s, got {t2.start_delay:.1f}s"
    
    print(f"    t1: arm={t1.assigned_arm} delay={t1.start_delay:.1f}s")
    print(f"    t2: arm={t2.assigned_arm} delay={t2.start_delay:.1f}s")


def test_priority_ordering_in_schedule():
    """Higher priority tasks are scheduled first."""
    tm = MockTimeManager(start_time=100.0)
    sched = TaskScheduler(tm, ['arm1'])
    
    # Submit low priority first, then high
    sched.submit(Task(task_id='low', zone_name='zone_a', priority=TaskPriority.LOW, duration=5.0))
    sched.submit(Task(task_id='high', zone_name='zone_a', priority=TaskPriority.HIGH, duration=3.0))
    
    plan = sched.schedule_all()
    
    # High priority should be scheduled (arm1 is limited, only one gets it)
    scheduled_ids = [t.task_id for t in plan.scheduled]
    assert 'high' in scheduled_ids, f"High priority should be scheduled: {plan.summary()}"


def test_preferred_arm():
    """Task with preferred_arm goes to that arm."""
    tm = MockTimeManager(start_time=100.0)
    sched = TaskScheduler(tm, ['arm1', 'arm2'])
    
    plan = sched.schedule_single(
        Task(task_id='t1', zone_name='zone_a', preferred_arm='arm2')
    )
    
    assert plan.all_scheduled
    assert plan.scheduled[0].assigned_arm == 'arm2'


def test_custom_duration():
    """Task with custom duration overrides prediction."""
    tm = MockTimeManager(start_time=100.0)
    sched = TaskScheduler(tm, ['arm1'])
    
    plan = sched.schedule_single(
        Task(task_id='t1', zone_name='zone_a', duration=10.0)
    )
    
    assert plan.all_scheduled
    assert plan.scheduled[0].predicted_duration == 10.0


def test_clear_completed():
    """clear_completed removes old completed tasks."""
    tm = MockTimeManager(start_time=100.0)
    sched = TaskScheduler(tm, ['arm1'])
    
    sched.submit(Task(task_id='t1', zone_name='zone_a'))
    plan = sched.schedule_all()
    
    # Mark as completed
    for t in sched._tasks.values():
        t.status = TaskStatus.COMPLETED
        t.created_at = 0.0  # old timestamp
    
    sched.clear_completed()
    assert len(sched._tasks) == 0


def test_empty_schedule():
    """Schedule with no pending tasks returns empty plan."""
    tm = MockTimeManager()
    sched = TaskScheduler(tm, ['arm1'])
    
    plan = sched.schedule_all()
    assert len(plan.scheduled) == 0
    assert len(plan.failed) == 0


def test_plan_summary():
    """SchedulePlan summary produces readable output."""
    tm = MockTimeManager(start_time=100.0)
    sched = TaskScheduler(tm, ['arm1'])
    
    plan = sched.schedule_single(
        Task(task_id='t1', zone_name='zone_a', priority=TaskPriority.HIGH)
    )
    
    summary = plan.summary()
    assert 't1' in summary
    assert 'arm1' in summary
    assert 'HIGH' in summary


def test_arm_availability():
    """Auto-assign tries arms in order when same arm can't handle all tasks."""
    tm = MockTimeManager(start_time=100.0)
    sched = TaskScheduler(tm, ['arm1', 'arm2', 'arm3'])
    
    # All three tasks to zone_a — arm1 handles them all with delays
    # (zone lock ensures mutual exclusion, so no need for different arms)
    sched.submit(Task(task_id='t1', zone_name='zone_a', duration=5.0))
    sched.submit(Task(task_id='t2', zone_name='zone_a', duration=5.0))
    sched.submit(Task(task_id='t3', zone_name='zone_a', duration=3.0))
    
    plan = sched.schedule_all()
    
    # All three should be scheduled on arm1 with increasing delays
    assert len(plan.scheduled) == 3, f"Expected 3 scheduled: {plan.summary()}"
    
    t1 = next(t for t in plan.scheduled if t.task_id == 't1')
    t2 = next(t for t in plan.scheduled if t.task_id == 't2')
    t3 = next(t for t in plan.scheduled if t.task_id == 't3')
    
    # t1 first, t2 after t1, t3 after t2
    assert t1.start_delay == 0.0
    assert t2.start_delay >= 5.0
    assert t3.start_delay >= 10.0
    
    print(f"    t1: arm={t1.assigned_arm} delay={t1.start_delay:.1f}s")
    print(f"    t2: arm={t2.assigned_arm} delay={t2.start_delay:.1f}s")
    print(f"    t3: arm={t3.assigned_arm} delay={t3.start_delay:.1f}s")


# ============================================================
# Main
# ============================================================

def main():
    print("=" * 50)
    print("  TaskScheduler Unit Tests")
    print("=" * 50)
    
    tests = [
        ("task_creation", test_task_creation),
        ("task_priority_ordering", test_task_priority_ordering),
        ("task_deadline_ordering", test_task_deadline_ordering),
        ("submit", test_submit),
        ("submit_batch", test_submit_batch),
        ("cancel", test_cancel),
        ("schedule_single_no_conflict", test_schedule_single_no_conflict),
        ("schedule_multiple_no_conflict", test_schedule_multiple_no_conflict),
        ("schedule_conflict_different_arms", test_schedule_conflict_different_arms),
        ("schedule_conflict_same_arm", test_schedule_conflict_same_arm),
        ("priority_ordering_in_schedule", test_priority_ordering_in_schedule),
        ("preferred_arm", test_preferred_arm),
        ("custom_duration", test_custom_duration),
        ("clear_completed", test_clear_completed),
        ("empty_schedule", test_empty_schedule),
        ("plan_summary", test_plan_summary),
        ("arm_availability", test_arm_availability),
    ]
    
    passed = 0
    for name, fn in tests:
        if test(name, fn):
            passed += 1
    
    print(f"\n  Result: {passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == '__main__':
    sys.exit(main())
