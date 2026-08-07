"""Skill Lifecycle — K8s Pod-like lifecycle management for skills.

States: Install → Register → Validate → Ready → Execute → Monitor → Update → Remove

Each transition is guarded by conditions. Invalid transitions raise errors.
"""

from __future__ import annotations

import time as _time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class SkillLifecycleState(Enum):
    """Skill lifecycle states (K8s Pod-like)."""

    INSTALLED = "installed"
    REGISTERED = "registered"
    VALIDATED = "validated"
    READY = "ready"
    EXECUTING = "executing"
    MONITORING = "monitoring"
    UPDATING = "updating"
    REMOVING = "removing"
    REMOVED = "removed"
    INVALID = "invalid"


VALID_TRANSITIONS: dict[SkillLifecycleState, set[SkillLifecycleState]] = {
    SkillLifecycleState.INSTALLED: {
        SkillLifecycleState.REGISTERED,
        SkillLifecycleState.REMOVED,
        SkillLifecycleState.INVALID,
    },
    SkillLifecycleState.REGISTERED: {
        SkillLifecycleState.VALIDATED,
        SkillLifecycleState.INVALID,
    },
    SkillLifecycleState.VALIDATED: {
        SkillLifecycleState.READY,
        SkillLifecycleState.INVALID,
    },
    SkillLifecycleState.READY: {
        SkillLifecycleState.EXECUTING,
        SkillLifecycleState.UPDATING,
        SkillLifecycleState.REMOVING,
    },
    SkillLifecycleState.EXECUTING: {
        SkillLifecycleState.MONITORING,
        SkillLifecycleState.READY,
    },
    SkillLifecycleState.MONITORING: {
        SkillLifecycleState.READY,
        SkillLifecycleState.UPDATING,
    },
    SkillLifecycleState.UPDATING: {
        SkillLifecycleState.READY,
        SkillLifecycleState.INVALID,
    },
    SkillLifecycleState.REMOVING: {
        SkillLifecycleState.REMOVED,
    },
    SkillLifecycleState.REMOVED: set(),
    SkillLifecycleState.INVALID: {
        SkillLifecycleState.READY,
        SkillLifecycleState.REMOVING,
    },
}


@dataclass
class SkillExecutionRecord:
    """Record of a single skill execution."""

    timestamp: float = field(default_factory=_time.time)
    success: bool = False
    duration: float = 0.0
    failure_reason: str = ""


@dataclass
class SkillLifecycleEntry:
    """A skill entry in the lifecycle manager.

    Attributes:
        skill_id: Unique skill identifier.
        name: Skill name.
        version: Skill version.
        state: Current lifecycle state.
        installed_at: Installation timestamp.
        last_executed: Last execution timestamp.
        total_executions: Total execution count.
        success_count: Successful execution count.
        execution_history: Recent execution records.
        validation_errors: Errors from last validation.

    """

    skill_id: str = ""
    name: str = ""
    version: str = "1.0.0"
    state: SkillLifecycleState = SkillLifecycleState.INSTALLED
    installed_at: float = field(default_factory=_time.time)
    last_executed: float = 0.0
    total_executions: int = 0
    success_count: int = 0
    execution_history: list[SkillExecutionRecord] = field(default_factory=list)
    validation_errors: list[str] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        """Calculate success rate from history."""
        if self.total_executions == 0:
            return 0.0
        return self.success_count / self.total_executions

    def record_execution(
        self,
        success: bool,
        duration: float = 0.0,
        failure_reason: str = "",
    ) -> None:
        """Record a skill execution.

        Args:
            success: Whether execution succeeded.
            duration: Execution duration in seconds.
            failure_reason: Failure reason if unsuccessful.

        """
        self.total_executions += 1
        if success:
            self.success_count += 1
        self.last_executed = _time.time()
        self.execution_history.append(
            SkillExecutionRecord(
                success=success,
                duration=duration,
                failure_reason=failure_reason,
            )
        )
        if len(self.execution_history) > 100:
            self.execution_history = self.execution_history[-100:]


class SkillLifecycle:
    """Skill lifecycle manager — enforces valid state transitions.

    Similar to K8s Pod lifecycle: Install→Register→Validate→Ready→Execute→Monitor→Update→Remove
    """

    def __init__(self) -> None:
        """Initialize lifecycle manager."""
        self._entries: dict[str, SkillLifecycleEntry] = {}
        self._next_id: int = 1

    def install(self, name: str, version: str = "1.0.0") -> str:
        """Install a skill (create lifecycle entry).

        Args:
            name: Skill name.
            version: Skill version.

        Returns:
            Skill ID.

        """
        skill_id = f"skill_{self._next_id:04d}"
        self._next_id += 1
        self._entries[skill_id] = SkillLifecycleEntry(
            skill_id=skill_id,
            name=name,
            version=version,
            state=SkillLifecycleState.INSTALLED,
        )
        return skill_id

    def register(self, skill_id: str) -> bool:
        """Register an installed skill.

        Args:
            skill_id: Skill ID to register.

        Returns:
            True if transition succeeded.

        """
        return self._transition(
            skill_id,
            SkillLifecycleState.REGISTERED,
        )

    def validate(
        self,
        skill_id: str,
        validation_errors: list[str] | None = None,
    ) -> bool:
        """Validate a registered skill.

        Args:
            skill_id: Skill ID to validate.
            validation_errors: Errors from validation (None = passed).

        Returns:
            True if validation passed and transition to VALIDATED succeeded.

        """
        entry = self._entries.get(skill_id)
        if entry is None:
            return False

        if validation_errors:
            entry.validation_errors = validation_errors
            self._transition(skill_id, SkillLifecycleState.INVALID)
            return False

        entry.validation_errors = []
        return self._transition(skill_id, SkillLifecycleState.VALIDATED)

    def make_ready(self, skill_id: str) -> bool:
        """Transition a validated skill to READY.

        Args:
            skill_id: Skill ID.

        Returns:
            True if transition succeeded.

        """
        return self._transition(skill_id, SkillLifecycleState.READY)

    def start_execution(self, skill_id: str) -> bool:
        """Start executing a READY skill.

        Args:
            skill_id: Skill ID.

        Returns:
            True if transition succeeded.

        """
        return self._transition(skill_id, SkillLifecycleState.EXECUTING)

    def finish_execution(
        self,
        skill_id: str,
        success: bool,
        duration: float = 0.0,
        failure_reason: str = "",
    ) -> bool:
        """Finish execution and transition to MONITORING.

        Args:
            skill_id: Skill ID.
            success: Whether execution succeeded.
            duration: Execution duration.
            failure_reason: Failure reason if unsuccessful.

        Returns:
            True if transition succeeded.

        """
        entry = self._entries.get(skill_id)
        if entry is None:
            return False

        entry.record_execution(success, duration, failure_reason)
        return self._transition(skill_id, SkillLifecycleState.MONITORING)

    def complete_monitoring(self, skill_id: str) -> bool:
        """Complete monitoring, return to READY.

        Args:
            skill_id: Skill ID.

        Returns:
            True if transition succeeded.

        """
        return self._transition(skill_id, SkillLifecycleState.READY)

    def start_update(self, skill_id: str) -> bool:
        """Start a hot update.

        Args:
            skill_id: Skill ID.

        Returns:
            True if transition succeeded.

        """
        return self._transition(skill_id, SkillLifecycleState.UPDATING)

    def finish_update(self, skill_id: str, new_version: str) -> bool:
        """Finish a hot update.

        Args:
            skill_id: Skill ID.
            new_version: New version string.

        Returns:
            True if transition succeeded.

        """
        entry = self._entries.get(skill_id)
        if entry is None:
            return False
        entry.version = new_version
        return self._transition(skill_id, SkillLifecycleState.READY)

    def start_removal(self, skill_id: str) -> bool:
        """Start removal (waits for execution to complete).

        Args:
            skill_id: Skill ID.

        Returns:
            True if transition succeeded.

        """
        return self._transition(skill_id, SkillLifecycleState.REMOVING)

    def finish_removal(self, skill_id: str) -> bool:
        """Complete removal.

        Args:
            skill_id: Skill ID.

        Returns:
            True if transition succeeded.

        """
        return self._transition(skill_id, SkillLifecycleState.REMOVED)

    def get_entry(self, skill_id: str) -> SkillLifecycleEntry | None:
        """Get lifecycle entry for a skill.

        Args:
            skill_id: Skill ID.

        Returns:
            Lifecycle entry or None.

        """
        return self._entries.get(skill_id)

    def get_state(self, skill_id: str) -> SkillLifecycleState | None:
        """Get current lifecycle state.

        Args:
            skill_id: Skill ID.

        Returns:
            Current state or None.

        """
        entry = self._entries.get(skill_id)
        return entry.state if entry else None

    def get_all_entries(self) -> dict[str, SkillLifecycleEntry]:
        """Get all lifecycle entries."""
        return dict(self._entries)

    def _transition(
        self,
        skill_id: str,
        target: SkillLifecycleState,
    ) -> bool:
        """Execute a state transition if valid.

        Args:
            skill_id: Skill ID.
            target: Target state.

        Returns:
            True if transition succeeded.

        """
        entry = self._entries.get(skill_id)
        if entry is None:
            return False

        current = entry.state
        if target not in VALID_TRANSITIONS.get(current, set()):
            return False

        entry.state = target
        return True