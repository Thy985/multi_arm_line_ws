"""Tests for Scheduler and AllocationStrategy."""

import pytest

from multi_arm_core.coordination.resource_manager import (
    Resource,
    ResourceManager,
    ResourceState,
    ResourceType,
)
from multi_arm_core.coordination.capability_matcher import CapabilityMatcher
from multi_arm_core.coordination.time_manager import TimeManager
from multi_arm_core.scheduler.scheduler import (
    AllocationStrategy,
    Scheduler,
    Task,
    TaskPriority,
    TaskStatus,
    SchedulePlan,
)


def _make_resource_manager() -> ResourceManager:
    mgr = ResourceManager()
    mgr.register(
        Resource(
            name="left_arm",
            resource_type=ResourceType.ROBOT,
            capabilities={
                "payload_kg": 5.0,
                "reachable_zones": ["zone_a", "zone_b", "home"],
            },
        )
    )
    mgr.register(
        Resource(
            name="right_arm",
            resource_type=ResourceType.ROBOT,
            capabilities={
                "payload_kg": 5.0,
                "reachable_zones": ["zone_a", "zone_c", "home"],
            },
        )
    )
    mgr.register(Resource(name="zone_a", resource_type=ResourceType.ZONE))
    mgr.register(Resource(name="zone_b", resource_type=ResourceType.ZONE))
    mgr.register(Resource(name="zone_c", resource_type=ResourceType.ZONE))
    return mgr


class TestAllocationStrategy:
    """Tests for AllocationStrategy."""

    def test_find_candidate_arms_auto(self) -> None:
        mgr = _make_resource_manager()
        strategy = AllocationStrategy(CapabilityMatcher())
        task = Task(task_id="t1", zone_name="zone_b")
        candidates = strategy.find_candidate_arms(task, mgr)
        assert "left_arm" in candidates

    def test_find_candidate_arms_preferred(self) -> None:
        mgr = _make_resource_manager()
        strategy = AllocationStrategy(CapabilityMatcher())
        task = Task(task_id="t1", zone_name="zone_a", preferred_arm="right_arm")
        candidates = strategy.find_candidate_arms(task, mgr)
        assert candidates == ["right_arm"]

    def test_find_candidate_arms_zone_c(self) -> None:
        mgr = _make_resource_manager()
        strategy = AllocationStrategy(CapabilityMatcher())
        task = Task(task_id="t1", zone_name="zone_c")
        candidates = strategy.find_candidate_arms(task, mgr)
        assert "right_arm" in candidates


class TestScheduler:
    """Tests for the Scheduler class."""

    def test_submit_task(self) -> None:
        mgr = _make_resource_manager()
        scheduler = Scheduler(TimeManager(), mgr)
        task = Task(task_id="t1", zone_name="zone_a")
        task_id = scheduler.submit(task)
        assert task_id == "t1"
        assert task.status == TaskStatus.PENDING

    def test_cancel_task(self) -> None:
        mgr = _make_resource_manager()
        scheduler = Scheduler(TimeManager(), mgr)
        task = Task(task_id="t1", zone_name="zone_a")
        scheduler.submit(task)
        assert scheduler.cancel("t1")
        assert task.status == TaskStatus.CANCELLED

    def test_schedule_all(self) -> None:
        mgr = _make_resource_manager()
        scheduler = Scheduler(TimeManager(), mgr)
        task1 = Task(task_id="t1", zone_name="zone_a")
        task2 = Task(task_id="t2", zone_name="zone_b")
        scheduler.submit(task1)
        scheduler.submit(task2)
        plan = scheduler.schedule_all()
        assert len(plan.scheduled) == 2

    def test_schedule_with_capability_matching(self) -> None:
        mgr = _make_resource_manager()
        scheduler = Scheduler(TimeManager(), mgr)
        task = Task(
            task_id="t1",
            zone_name="zone_c",
            required_capabilities={"reachable_zones": ["zone_c"]},
        )
        scheduler.submit(task)
        plan = scheduler.schedule_all()
        assert len(plan.scheduled) == 1
        assert plan.scheduled[0].assigned_arm == "right_arm"

    def test_get_pending_tasks(self) -> None:
        mgr = _make_resource_manager()
        scheduler = Scheduler(TimeManager(), mgr)
        scheduler.submit(Task(task_id="t1", zone_name="zone_a"))
        pending = scheduler.get_pending_tasks()
        assert len(pending) == 1

    def test_get_active_tasks(self) -> None:
        mgr = _make_resource_manager()
        scheduler = Scheduler(TimeManager(), mgr)
        scheduler.submit(Task(task_id="t1", zone_name="zone_a"))
        active = scheduler.get_active_tasks()
        assert len(active) == 1


class TestTask:
    """Tests for Task dataclass."""

    def test_priority_ordering(self) -> None:
        t1 = Task(task_id="t1", zone_name="zone_a", priority=TaskPriority.HIGH)
        t2 = Task(task_id="t2", zone_name="zone_a", priority=TaskPriority.LOW)
        assert t1 < t2

    def test_is_active(self) -> None:
        t = Task(task_id="t1", zone_name="zone_a")
        assert t.is_active
        t.status = TaskStatus.COMPLETED
        assert not t.is_active

    def test_predicted_duration(self) -> None:
        t = Task(task_id="t1", zone_name="zone_a", position_name="ready")
        assert t.predicted_duration > 0

    def test_custom_duration(self) -> None:
        t = Task(task_id="t1", zone_name="zone_a", duration=5.0)
        assert t.predicted_duration == 5.0