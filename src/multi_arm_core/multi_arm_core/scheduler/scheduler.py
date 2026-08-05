"""Scheduler and AllocationStrategy for multi-arm task scheduling."""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Optional
import time as _time

from multi_arm_core.coordination.resource_manager import (
    Resource,
    ResourceManager,
    ResourceState,
    ResourceType,
)
from multi_arm_core.coordination.capability_matcher import CapabilityMatcher
from multi_arm_core.coordination.time_manager import (
    TimeManager,
    TimeWindow,
    ScheduleResult,
    predict_duration,
    SAFETY_MARGIN,
)


class TaskPriority(Enum):
    """Task priority levels (lower number = higher priority)."""
    CRITICAL = 0
    HIGH = 10
    NORMAL = 50
    LOW = 100
    BATCH = 200


class TaskStatus(Enum):
    """Lifecycle status of a task."""
    PENDING = auto()
    SCHEDULED = auto()
    QUEUED = auto()
    EXECUTING = auto()
    COMPLETED = auto()
    FAILED = auto()
    CANCELLED = auto()


@dataclass
class Task:
    """A high-level task request for a robot arm."""
    task_id: str
    zone_name: str
    position_name: str = "ready"
    priority: TaskPriority = TaskPriority.NORMAL
    deadline: Optional[float] = None
    preferred_arm: Optional[str] = None
    duration: Optional[float] = None
    required_capabilities: Dict = field(default_factory=dict)
    retries: int = 0
    metadata: Dict = field(default_factory=dict)

    status: TaskStatus = TaskStatus.PENDING
    assigned_arm: Optional[str] = None
    scheduled_window: Optional[TimeWindow] = None
    start_delay: float = 0.0
    created_at: float = field(default_factory=_time.time)
    error_message: str = ""

    @property
    def predicted_duration(self) -> float:
        """Get predicted duration (override or auto-estimate)."""
        if self.duration is not None:
            return self.duration
        return predict_duration(self.position_name, 3.0)

    @property
    def is_active(self) -> bool:
        """Whether this task is in an active state."""
        return self.status in (
            TaskStatus.PENDING,
            TaskStatus.SCHEDULED,
            TaskStatus.QUEUED,
            TaskStatus.EXECUTING,
        )

    def __lt__(self, other: "Task") -> bool:
        """For priority queue ordering."""
        if self.priority.value != other.priority.value:
            return self.priority.value < other.priority.value
        if self.deadline and other.deadline:
            return self.deadline < other.deadline
        if self.deadline:
            return True
        return self.created_at < other.created_at


@dataclass
class SchedulePlan:
    """Result of scheduling a batch of tasks."""
    tasks: List[Task]
    scheduled: List[Task]
    failed: List[Task]
    conflicts: List[Dict]

    @property
    def all_scheduled(self) -> bool:
        return len(self.failed) == 0


class AllocationStrategy:
    """Strategy for assigning tasks to arms.

    Uses CapabilityMatcher to find the best arm for each task.
    """

    def __init__(self, capability_matcher: CapabilityMatcher) -> None:
        self._matcher = capability_matcher

    def find_candidate_arms(
        self,
        task: Task,
        resource_manager: ResourceManager,
    ) -> List[str]:
        """Find candidate arms for a task, ordered by capability match.

        Args:
            task: The task to find arms for.
            resource_manager: The resource manager to query.

        Returns:
            List of arm names ordered by match score (best first).
        """
        if task.preferred_arm:
            arm = resource_manager.get(task.preferred_arm)
            if arm and arm.resource_type == ResourceType.ROBOT:
                return [task.preferred_arm]
            return []

        requirements = dict(task.required_capabilities)
        requirements["reachable_zones"] = [task.zone_name]

        robots = resource_manager.get_robots()
        free_robots = [r for r in robots if r.state in (ResourceState.FREE, ResourceState.RESERVED)]

        if not free_robots:
            free_robots = robots

        matched = self._matcher.match(requirements, free_robots, ResourceType.ROBOT)
        return [r.name for r in matched]


class Scheduler:
    """High-level task scheduler for multi-arm coordination.

    Responsibilities:
    1. Accept task submissions
    2. Sort by priority/deadline
    3. Assign tasks to arms via AllocationStrategy
    4. Schedule time windows via TimeManager
    """

    def __init__(
        self,
        time_manager: TimeManager,
        resource_manager: ResourceManager,
        allocation_strategy: Optional[AllocationStrategy] = None,
    ) -> None:
        self.time_manager = time_manager
        self.resource_manager = resource_manager
        self._matcher = CapabilityMatcher()
        self._strategy = allocation_strategy or AllocationStrategy(self._matcher)
        self._tasks: Dict[str, Task] = {}
        self._task_counter = 0

    def submit(self, task: Task) -> str:
        """Submit a new task.

        Args:
            task: Task object with zone, position, priority, etc.

        Returns:
            task_id for tracking.
        """
        if not task.task_id:
            self._task_counter += 1
            task.task_id = f"task_{self._task_counter}"

        task.status = TaskStatus.PENDING
        self._tasks[task.task_id] = task
        return task.task_id

    def cancel(self, task_id: str) -> bool:
        """Cancel a pending or scheduled task."""
        task = self._tasks.get(task_id)
        if not task or not task.is_active:
            return False

        task.status = TaskStatus.CANCELLED
        if task.assigned_arm:
            self.time_manager.cancel(task.assigned_arm)
        return True

    def get_task(self, task_id: str) -> Optional[Task]:
        """Get task by ID."""
        return self._tasks.get(task_id)

    def get_pending_tasks(self) -> List[Task]:
        """Get all pending tasks, sorted by priority."""
        pending = [t for t in self._tasks.values() if t.status == TaskStatus.PENDING]
        return sorted(pending)

    def get_active_tasks(self) -> List[Task]:
        """Get all active tasks."""
        return [t for t in self._tasks.values() if t.is_active]

    def schedule_all(self) -> SchedulePlan:
        """Schedule all pending tasks.

        Algorithm:
        1. Sort pending tasks by priority, then deadline
        2. For each task:
           a. Find candidate arms via AllocationStrategy
           b. Calculate start_delay based on zone/arm availability
           c. Try to schedule via TimeManager
           d. If conflict, try next available arm
           e. If no arm available, mark as failed

        Returns:
            SchedulePlan with scheduled and failed tasks.
        """
        pending = self.get_pending_tasks()
        scheduled: List[Task] = []
        failed: List[Task] = []
        conflicts: List[Dict] = []

        for task in pending:
            arms_to_try = self._strategy.find_candidate_arms(task, self.resource_manager)

            zone_free_at = self.time_manager.get_zone_end_time(task.zone_name)
            now = self.time_manager.now()
            base_delay = max(0.0, zone_free_at - now)

            scheduled_ok = False
            for arm_name in arms_to_try:
                arm_free_at = self.time_manager.get_arm_end_time(arm_name)
                arm_delay = max(0.0, arm_free_at - now)
                start_delay = max(base_delay, arm_delay)

                result = self.time_manager.schedule(
                    arm_name=arm_name,
                    zone_name=task.zone_name,
                    duration=task.predicted_duration,
                    position_name=task.position_name,
                    start_delay=start_delay,
                )

                if result.granted:
                    task.status = TaskStatus.SCHEDULED
                    task.assigned_arm = arm_name
                    task.scheduled_window = result.window
                    task.start_delay = start_delay
                    scheduled.append(task)
                    scheduled_ok = True
                    break
                else:
                    conflicts.append(
                        {
                            "task_id": task.task_id,
                            "arm": arm_name,
                            "conflict": result.conflict,
                            "suggested_delay": result.suggested_delay,
                        }
                    )
                    base_delay = max(base_delay, result.suggested_delay)

            if not scheduled_ok:
                task.status = TaskStatus.FAILED
                task.error_message = f"No available arm for zone {task.zone_name}"
                failed.append(task)

        return SchedulePlan(
            tasks=list(self._tasks.values()),
            scheduled=scheduled,
            failed=failed,
            conflicts=conflicts,
        )

    def clear_completed(self) -> None:
        """Remove completed/failed/cancelled tasks older than 5 minutes."""
        cutoff = _time.time() - 300.0
        to_remove = [
            tid
            for tid, t in self._tasks.items()
            if t.status
            in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED)
            and t.created_at < cutoff
        ]
        for tid in to_remove:
            del self._tasks[tid]