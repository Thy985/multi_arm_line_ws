#!/usr/bin/env python3
"""
Task Scheduler for multi-arm coordination.

Accepts high-level task requests, sorts by priority/deadline,
assigns to arms, and produces a time-window schedule via TimeManager.
Integrates with Coordinator for execution.
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Optional, Dict, Callable
import time
import heapq

from order_manager.nodes.time_manager import (
    TimeManager, TimeWindow, WindowStatus, ScheduleResult,
    predict_duration, SAFETY_MARGIN
)


class TaskPriority(Enum):
    """Task priority levels (lower number = higher priority)."""
    CRITICAL = 0     # Safety-critical, must execute first
    HIGH = 10        # Time-sensitive
    NORMAL = 50      # Default
    LOW = 100        # Background tasks
    BATCH = 200      # Batch processing, can wait


class TaskStatus(Enum):
    """Lifecycle status of a task."""
    PENDING = auto()     # Submitted, not yet scheduled
    SCHEDULED = auto()   # Scheduled with time window
    QUEUED = auto()      # Waiting for arm/zone availability
    EXECUTING = auto()   # Currently being executed
    COMPLETED = auto()   # Finished successfully
    FAILED = auto()      # Execution failed
    CANCELLED = auto()   # Cancelled by user


@dataclass
class Task:
    """
    A high-level task request for a robot arm.
    
    Example:
        Task(
            task_id='weld_001',
            zone_name='zone_a',
            position_name='ready',
            priority=TaskPriority.HIGH,
        )
    """
    task_id: str
    zone_name: str
    position_name: str = 'ready'
    priority: TaskPriority = TaskPriority.NORMAL
    deadline: Optional[float] = None           # Absolute timestamp (None = no deadline)
    preferred_arm: Optional[str] = None        # None = auto-assign
    duration: Optional[float] = None           # Override predicted duration
    retries: int = 0                           # Number of retries allowed
    callback: Optional[Callable] = None        # Completion callback(task)
    metadata: Dict = field(default_factory=dict)  # Arbitrary data
    
    # Runtime state (managed by scheduler)
    status: TaskStatus = TaskStatus.PENDING
    assigned_arm: Optional[str] = None
    scheduled_window: Optional[TimeWindow] = None
    start_delay: float = 0.0                   # Seconds from now when task starts
    created_at: float = field(default_factory=time.time)
    error_message: str = ''
    
    @property
    def predicted_duration(self) -> float:
        """Get predicted duration (override or auto-estimate)."""
        if self.duration is not None:
            return self.duration
        return predict_duration(self.position_name, 3.0)
    
    @property
    def is_active(self) -> bool:
        """Whether this task is in an active state."""
        return self.status in (TaskStatus.PENDING, TaskStatus.SCHEDULED, 
                               TaskStatus.QUEUED, TaskStatus.EXECUTING)
    
    def __lt__(self, other):
        """For priority queue ordering (lower priority number = higher priority)."""
        if self.priority.value != other.priority.value:
            return self.priority.value < other.priority.value
        # Same priority: earlier deadline first
        if self.deadline and other.deadline:
            return self.deadline < other.deadline
        if self.deadline:
            return True
        # Same priority, no deadline: earlier creation first
        return self.created_at < other.created_at


@dataclass
class SchedulePlan:
    """
    Result of scheduling a batch of tasks.
    
    Contains the ordered execution plan and any conflicts encountered.
    """
    tasks: List[Task]                    # All tasks (with status updated)
    scheduled: List[Task]                # Tasks successfully scheduled
    failed: List[Task]                   # Tasks that couldn't be scheduled
    conflicts: List[Dict]               # Conflict details
    
    @property
    def all_scheduled(self) -> bool:
        return len(self.failed) == 0
    
    def summary(self) -> str:
        lines = [
            f"SchedulePlan: {len(self.scheduled)} scheduled, {len(self.failed)} failed"
        ]
        for t in self.scheduled:
            arm = t.assigned_arm or '?'
            lines.append(
                f"  [{t.task_id}] arm={arm} zone={t.zone_name} "
                f"pos={t.position_name} priority={t.priority.name} "
                f"delay={t.start_delay:.1f}s"
            )
        for t in self.failed:
            lines.append(
                f"  [{t.task_id}] FAILED: {t.error_message}"
            )
        return '\n'.join(lines)


# =====================================================================
# Task Scheduler
# =====================================================================

class TaskScheduler:
    """
    High-level task scheduler for multi-arm coordination.
    
    Responsibilities:
    1. Accept task submissions
    2. Sort by priority/deadline
    3. Assign tasks to arms (auto or manual)
    4. Schedule time windows via TimeManager
    5. Execute tasks through Coordinator callback
    
    Usage:
        scheduler = TaskScheduler(time_manager, ['left_arm', 'right_arm'])
        
        # Submit tasks
        scheduler.submit(Task(task_id='t1', zone_name='zone_a', priority=TaskPriority.HIGH))
        scheduler.submit(Task(task_id='t2', zone_name='zone_b'))
        
        # Generate schedule
        plan = scheduler.schedule_all()
        print(plan.summary())
        
        # Execute
        scheduler.execute_plan(plan, coordinator)
    """
    
    def __init__(self, time_manager: TimeManager, arm_names: List[str]):
        self.time_manager = time_manager
        self.arm_names = arm_names
        self._tasks: Dict[str, Task] = {}  # task_id -> Task
        self._task_counter = 0
    
    def submit(self, task: Task) -> str:
        """
        Submit a new task.
        
        Returns:
            task_id for tracking
        """
        if not task.task_id:
            self._task_counter += 1
            task.task_id = f"task_{self._task_counter}"
        
        task.status = TaskStatus.PENDING
        self._tasks[task.task_id] = task
        return task.task_id
    
    def submit_batch(self, tasks: List[Task]) -> List[str]:
        """Submit multiple tasks. Returns list of task IDs."""
        return [self.submit(t) for t in tasks]
    
    def cancel(self, task_id: str) -> bool:
        """Cancel a pending or scheduled task."""
        task = self._tasks.get(task_id)
        if not task or not task.is_active:
            return False
        
        task.status = TaskStatus.CANCELLED
        # Cancel time window if scheduled
        if task.assigned_arm:
            self.time_manager.cancel(task.assigned_arm)
        return True
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """Get task by ID."""
        return self._tasks.get(task_id)
    
    def get_pending_tasks(self) -> List[Task]:
        """Get all pending tasks, sorted by priority."""
        pending = [t for t in self._tasks.values() 
                   if t.status == TaskStatus.PENDING]
        return sorted(pending)
    
    def get_active_tasks(self) -> List[Task]:
        """Get all active (non-completed/failed/cancelled) tasks."""
        return [t for t in self._tasks.values() if t.is_active]
    
    def clear_completed(self):
        """Remove completed/failed/cancelled tasks older than 5 minutes."""
        cutoff = time.time() - 300.0
        to_remove = [
            tid for tid, t in self._tasks.items()
            if t.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED)
            and t.created_at < cutoff
        ]
        for tid in to_remove:
            del self._tasks[tid]
    
    # =====================================================================
    # Scheduling
    # =====================================================================
    
    def schedule_all(self) -> SchedulePlan:
        """
        Schedule all pending tasks.
        
        Algorithm:
        1. Sort pending tasks by priority, then deadline
        2. For each task:
           a. Assign arm (manual or auto)
           b. Calculate start_delay based on zone/arm availability
           c. Try to schedule via TimeManager
           d. If conflict, try next available arm
           e. If no arm available, mark as failed
        
        Returns:
            SchedulePlan with scheduled and failed tasks
        """
        pending = self.get_pending_tasks()
        scheduled = []
        failed = []
        conflicts = []
        
        for task in pending:
            # Determine which arm(s) to try
            arms_to_try = self._get_candidate_arms(task)
            
            # Calculate start delay based on zone and arm availability
            zone_free_at = self.time_manager.get_zone_end_time(task.zone_name)
            now = self.time_manager.now()
            base_delay = max(0.0, zone_free_at - now)
            
            scheduled_ok = False
            for arm_name in arms_to_try:
                # Also consider arm-specific availability
                arm_free_at = self.time_manager.get_arm_end_time(arm_name)
                arm_delay = max(0.0, arm_free_at - now)
                
                # Use the later of zone and arm availability
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
                    conflicts.append({
                        'task_id': task.task_id,
                        'arm': arm_name,
                        'conflict': result.conflict,
                        'suggested_delay': result.suggested_delay,
                    })
                    
                    # Try next arm with increased delay
                    base_delay = max(base_delay, result.suggested_delay)
                    continue
            
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
    
    def schedule_single(self, task: Task) -> SchedulePlan:
        """
        Schedule a single task (convenience method).
        
        Returns:
            SchedulePlan with just this task
        """
        self.submit(task)
        return self.schedule_all()
    
    # =====================================================================
    # Execution
    # =====================================================================
    
    def execute_plan(self, plan: SchedulePlan, coordinator) -> int:
        """
        Execute a schedule plan by sending commands to the coordinator.
        
        Args:
            plan: SchedulePlan from schedule_all()
            coordinator: EnhancedMultiArmCoordinator instance
        
        Returns:
            Number of tasks submitted for execution
        """
        executed = 0
        for task in plan.scheduled:
            if task.status != TaskStatus.SCHEDULED:
                continue
            
            success = coordinator.send_to_zone(
                arm_name=task.assigned_arm,
                zone_name=task.zone_name,
                position_name=task.position_name,
                duration=task.predicted_duration - SAFETY_MARGIN,  # subtract safety margin
            )
            
            if success:
                task.status = TaskStatus.EXECUTING
                executed += 1
            else:
                task.status = TaskStatus.QUEUED
        
        return executed
    
    # =====================================================================
    # Internal
    # =====================================================================
    
    def _get_candidate_arms(self, task: Task) -> List[str]:
        """
        Get list of candidate arms for a task, in priority order.
        
        If task has preferred_arm, only try that arm.
        Otherwise, try all arms (they'll be filtered by TimeManager conflicts).
        """
        if task.preferred_arm:
            if task.preferred_arm in self.arm_names:
                return [task.preferred_arm]
            return []
        
        # Auto-assign: try all arms
        return list(self.arm_names)
    
    def print_status(self) -> str:
        """Print scheduler status."""
        lines = ["=== Task Scheduler Status ==="]
        
        pending = self.get_pending_tasks()
        active = self.get_active_tasks()
        
        lines.append(f"  Total tasks: {len(self._tasks)}")
        lines.append(f"  Pending: {len(pending)}")
        lines.append(f"  Active: {len(active)}")
        
        if pending:
            lines.append("  --- Pending Queue ---")
            for t in pending[:5]:  # show top 5
                lines.append(
                    f"    [{t.task_id}] {t.priority.name} "
                    f"zone={t.zone_name} pos={t.position_name}"
                )
        
        # Status distribution
        status_counts = {}
        for t in self._tasks.values():
            s = t.status.name
            status_counts[s] = status_counts.get(s, 0) + 1
        lines.append(f"  Status: {status_counts}")
        
        lines.append("==========================")
        return '\n'.join(lines)
