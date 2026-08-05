"""Tests for TaskManager."""

import pytest

from multi_arm_core.task.task_manager import TaskManager
from multi_arm_core.scheduler.scheduler import TaskPriority, TaskStatus


class TestTaskManager:
    """Tests for the TaskManager class."""

    def test_create_task(self) -> None:
        tm = TaskManager()
        task = tm.create_task(zone_name="zone_a", position_name="ready")
        assert task.task_id.startswith("task_")
        assert task.status == TaskStatus.PENDING
        assert task.zone_name == "zone_a"

    def test_create_task_with_priority(self) -> None:
        tm = TaskManager()
        task = tm.create_task(
            zone_name="zone_a", priority=TaskPriority.HIGH
        )
        assert task.priority == TaskPriority.HIGH

    def test_update_status(self) -> None:
        tm = TaskManager()
        task = tm.create_task(zone_name="zone_a")
        assert tm.update_status(task.task_id, TaskStatus.SCHEDULED)
        assert task.status == TaskStatus.SCHEDULED

    def test_update_status_nonexistent(self) -> None:
        tm = TaskManager()
        assert not tm.update_status("nonexistent", TaskStatus.SCHEDULED)

    def test_completion_callback(self) -> None:
        tm = TaskManager()
        results = []

        def on_complete(task):
            results.append(task.task_id)

        task = tm.create_task(zone_name="zone_a", callback=on_complete)
        tm.update_status(task.task_id, TaskStatus.COMPLETED)
        assert results == [task.task_id]

    def test_assign_arm(self) -> None:
        tm = TaskManager()
        task = tm.create_task(zone_name="zone_a")
        assert tm.assign_arm(task.task_id, "arm1")
        assert task.assigned_arm == "arm1"

    def test_get_active_tasks(self) -> None:
        tm = TaskManager()
        tm.create_task(zone_name="zone_a")
        tm.create_task(zone_name="zone_b")
        assert len(tm.get_active_tasks()) == 2

    def test_get_pending_tasks(self) -> None:
        tm = TaskManager()
        tm.create_task(zone_name="zone_a")
        assert len(tm.get_pending_tasks()) == 1

    def test_get_tasks_by_status(self) -> None:
        tm = TaskManager()
        task = tm.create_task(zone_name="zone_a")
        tm.update_status(task.task_id, TaskStatus.SCHEDULED)
        scheduled = tm.get_tasks_by_status(TaskStatus.SCHEDULED)
        assert len(scheduled) == 1

    def test_clear_completed(self) -> None:
        tm = TaskManager()
        task = tm.create_task(zone_name="zone_a")
        tm.update_status(task.task_id, TaskStatus.COMPLETED)
        cleared = tm.clear_completed(max_age_s=0.0)
        assert cleared == 1

    def test_auto_increment_task_id(self) -> None:
        tm = TaskManager()
        t1 = tm.create_task(zone_name="zone_a")
        t2 = tm.create_task(zone_name="zone_b")
        assert t1.task_id != t2.task_id