"""RecoveryManager — orchestrates recovery strategies for failure events.

Receives FailureEvents from the Coordinator, routes them to appropriate
handlers, and executes recovery strategies progressively. If all
strategies fail, performs a safe abort.

Recovery chain:
    FailureEvent → FailureClassifier → Handler selection
    → Strategy 1 → execute → success? → done
                              ↓ failed
    → Strategy 2 → execute → success? → done
                              ↓ failed
    → Strategy N → safe abort
"""

import time as _time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional

from multi_arm_recovery.failure_classifier import (
    FailureClassifier,
    FailureEvent,
    FailureType,
)
from multi_arm_recovery.handlers.planning_failure import PlanningFailureHandler
from multi_arm_recovery.handlers.collision_handler import CollisionHandler
from multi_arm_recovery.handlers.resource_timeout import ResourceTimeoutHandler
from multi_arm_recovery.handlers.controller_failure import ControllerFailureHandler
from multi_arm_recovery.handlers.grasp_retry import GraspRetryHandler


class RecoveryStatus(Enum):
    """Status of a recovery attempt."""

    PENDING = auto()
    IN_PROGRESS = auto()
    RECOVERED = auto()
    FAILED = auto()
    ABORTED = auto()


@dataclass
class RecoveryRecord:
    """Record of a recovery attempt for auditing and benchmarking.

    Attributes:
        task_id: ID of the task being recovered.
        failure_event: The original failure event.
        status: Current recovery status.
        strategies_tried: List of strategies attempted.
        current_strategy: Name of the current strategy being executed.
        start_time: Timestamp when recovery started.
        end_time: Timestamp when recovery ended (None if still in progress).
        recovery_count: Number of recovery attempts for this task.
    """

    task_id: str
    failure_event: FailureEvent
    status: RecoveryStatus = RecoveryStatus.PENDING
    strategies_tried: List[str] = field(default_factory=list)
    current_strategy: str = ""
    start_time: float = 0.0
    end_time: Optional[float] = None
    recovery_count: int = 0


class RecoveryManager:
    """Orchestrates failure recovery for the multi-arm system.

    Usage:
        recovery_mgr = RecoveryManager()
        result = recovery_mgr.handle_failure(event, executor=coordinator_execute)

    The executor callback is provided by the Coordinator and performs
    the actual motion commands (MoveIt, JTC, etc.).
    """

    def __init__(self) -> None:
        self._classifier = FailureClassifier()
        self._handlers: Dict[FailureType, Any] = {
            FailureType.PLANNING_FAILURE: PlanningFailureHandler(),
            FailureType.COLLISION_DETECTED: CollisionHandler(),
            FailureType.RESOURCE_TIMEOUT: ResourceTimeoutHandler(),
            FailureType.CONTROLLER_FAILURE: ControllerFailureHandler(),
            FailureType.GRASP_FAILURE: GraspRetryHandler(),
        }
        self._history: List[RecoveryRecord] = []
        self._active_records: Dict[str, RecoveryRecord] = {}

    def classify_failure(
        self,
        message: str,
        arm_name: str = "",
        context: Optional[Dict[str, Any]] = None,
        task_id: str = "",
    ) -> FailureEvent:
        """Classify a failure message into a typed FailureEvent.

        Args:
            message: Error message from the failing component.
            arm_name: Name of the arm that failed.
            context: Additional context for classification.
            task_id: ID of the task that failed.

        Returns:
            Classified FailureEvent.
        """
        return self._classifier.classify(message, arm_name, context, task_id)

    def handle_failure(
        self,
        event: FailureEvent,
        executor: Optional[Callable[..., Any]] = None,
    ) -> RecoveryRecord:
        """Handle a failure event with progressive recovery strategies.

        Args:
            event: The classified failure event.
            executor: Optional callback that executes recovery actions.
                Signature: executor(strategy_name, strategy_params, event) -> bool

        Returns:
            RecoveryRecord with the outcome of recovery attempts.
        """
        record = RecoveryRecord(
            task_id=event.task_id,
            failure_event=event,
            status=RecoveryStatus.IN_PROGRESS,
            start_time=_time.time(),
        )
        self._active_records[event.task_id] = record

        if not event.recoverable:
            record.status = RecoveryStatus.ABORTED
            record.end_time = _time.time()
            self._finalize_record(record)
            return record

        handler = self._handlers.get(event.failure_type)
        if handler is None:
            record.status = RecoveryStatus.ABORTED
            record.end_time = _time.time()
            self._finalize_record(record)
            return record

        handler.reset()

        while not handler.exhausted:
            strategy_name, strategy_params = handler.get_recovery_strategy(event)
            record.current_strategy = strategy_name
            record.strategies_tried.append(strategy_name)
            record.recovery_count += 1

            if executor is not None:
                success = executor(strategy_name, strategy_params, event)
            else:
                success = self._execute_strategy(strategy_name, strategy_params, event)

            if success:
                record.status = RecoveryStatus.RECOVERED
                record.end_time = _time.time()
                self._finalize_record(record)
                return record

        record.status = RecoveryStatus.FAILED
        record.end_time = _time.time()
        self._finalize_record(record)
        return record

    def _execute_strategy(
        self,
        strategy_name: str,
        strategy_params: Dict[str, Any],
        event: FailureEvent,
    ) -> bool:
        """Execute a recovery strategy without an external executor.

        Used for testing and when no executor is provided. Returns
        False by default — real execution requires an executor callback.

        Args:
            strategy_name: Name of the strategy to execute.
            strategy_params: Parameters for the strategy.
            event: The failure event being recovered.

        Returns:
            True if the strategy succeeded, False otherwise.
        """
        return False

    def _finalize_record(self, record: RecoveryRecord) -> None:
        """Move record from active to history.

        Args:
            record: The completed recovery record.
        """
        if record.task_id in self._active_records:
            del self._active_records[record.task_id]
        self._history.append(record)

    def get_history(self, task_id: str = "") -> List[RecoveryRecord]:
        """Get recovery history, optionally filtered by task_id.

        Args:
            task_id: Optional task ID to filter by.

        Returns:
            List of RecoveryRecord objects.
        """
        if not task_id:
            return list(self._history)
        return [r for r in self._history if r.task_id == task_id]

    def get_active(self, task_id: str = "") -> Optional[RecoveryRecord]:
        """Get active recovery record for a task.

        Args:
            task_id: Task ID to look up.

        Returns:
            Active RecoveryRecord if found, None otherwise.
        """
        return self._active_records.get(task_id)

    @property
    def total_recoveries(self) -> int:
        """Total number of recovery attempts across all tasks."""
        return len(self._history)

    @property
    def successful_recoveries(self) -> int:
        """Number of successful recoveries."""
        return sum(
            1 for r in self._history if r.status == RecoveryStatus.RECOVERED
        )

    @property
    def recovery_success_rate(self) -> float:
        """Ratio of successful recoveries to total attempts."""
        if not self._history:
            return 0.0
        return self.successful_recoveries / self.total_recoveries

    def get_handler(self, failure_type: FailureType) -> Optional[Any]:
        """Get the handler for a specific failure type.

        Args:
            failure_type: The failure type to get a handler for.

        Returns:
            The handler instance, or None if no handler is registered.
        """
        return self._handlers.get(failure_type)

    def register_handler(self, failure_type: FailureType, handler: Any) -> None:
        """Register or replace a handler for a failure type.

        Args:
            failure_type: The failure type to handle.
            handler: The handler instance.
        """
        self._handlers[failure_type] = handler