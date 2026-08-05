"""TaskManager for managing task lifecycle and state transitions."""

from typing import Callable, Dict, List, Optional
import time as _time

from multi_arm_core.scheduler.scheduler import Task, TaskPriority, TaskStatus


class TaskManager:
    """Manages task lifecycle, state transitions, and completion callbacks.

    Separates task lifecycle management from scheduling logic.
    """

    def __init__(self) -> None:
        self._tasks: Dict[str, Task] = {}
        self._task_counter = 0
        self._callbacks: Dict[str, Callable] = {}

    def create_task(
        self,
        zone_name: str,
        position_name: str = "ready",
        priority: TaskPriority = TaskPriority.NORMAL,
        preferred_arm: Optional[str] = None,
        deadline: Optional[float] = None,
        required_capabilities: Optional[Dict] = None,
        callback: Optional[Callable] = None,
    ) -> Task:
        """Create a new task with auto-generated ID.

        Args:
            zone_name: Target zone for the task.
            position_name: Target position name.
            priority: Task priority level.
            preferred_arm: Optional preferred arm assignment.
            deadline: Optional absolute deadline timestamp.
            required_capabilities: Optional capability requirements.
            callback: Optional completion callback.

        Returns:
            The created Task object.
        """
        self._task_counter += 1
        task_id = f"task_{self._task_counter}"
        task = Task(
            task_id=task_id,
            zone_name=zone_name,
            position_name=position_name,
            priority=priority,
            preferred_arm=preferred_arm,
            deadline=deadline,
            required_capabilities=required_capabilities or {},
        )
        if callback:
            self._callbacks[task_id] = callback
        self._tasks[task_id] = task
        return task

    def get_task(self, task_id: str) -> Optional[Task]:
        """Get task by ID."""
        return self._tasks.get(task_id)

    def update_status(self, task_id: str, status: TaskStatus, error_message: str = "") -> bool:
        """Update task status.

        Args:
            task_id: Task ID to update.
            status: New status.
            error_message: Optional error message.

        Returns:
            True if task was found and updated.
        """
        task = self._tasks.get(task_id)
        if task is None:
            return False

        old_status = task.status
        task.status = status
        if error_message:
            task.error_message = error_message

        if status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
            callback = self._callbacks.pop(task_id, None)
            if callback:
                try:
                    callback(task)
                except Exception:
                    pass

        return True

    def assign_arm(self, task_id: str, arm_name: str) -> bool:
        """Assign an arm to a task."""
        task = self._tasks.get(task_id)
        if task is None:
            return False
        task.assigned_arm = arm_name
        return True

    def get_active_tasks(self) -> List[Task]:
        """Get all active tasks."""
        return [t for t in self._tasks.values() if t.is_active]

    def get_pending_tasks(self) -> List[Task]:
        """Get all pending tasks sorted by priority."""
        pending = [t for t in self._tasks.values() if t.status == TaskStatus.PENDING]
        return sorted(pending)

    def get_tasks_by_status(self, status: TaskStatus) -> List[Task]:
        """Get all tasks with the given status."""
        return [t for t in self._tasks.values() if t.status == status]

    def clear_completed(self, max_age_s: float = 300.0) -> int:
        """Remove completed/failed/cancelled tasks older than max_age_s.

        Args:
            max_age_s: Maximum age in seconds (default 5 minutes).

        Returns:
            Number of tasks removed.
        """
        cutoff = _time.time() - max_age_s
        to_remove = [
            tid
            for tid, t in self._tasks.items()
            if t.status
            in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED)
            and t.created_at < cutoff
        ]
        for tid in to_remove:
            self._callbacks.pop(tid, None)
            del self._tasks[tid]
        return len(to_remove)