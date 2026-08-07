"""Episode — complete record of a single task execution.

An Episode captures the full lifecycle of one task execution:
    initial world state → execution steps → result → recovery → final state

This is NOT a log entry. It is a structured, replayable record of
what the robot experienced during one task.
"""

from __future__ import annotations

import json
import time as _time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class WorldStateSnapshot:
    """Snapshot of WorldModel state at a point in time.

    Attributes:
        objects: Dict of object_id -> {position, state, type}.
        relations: List of relation dicts {subject, predicate, object}.
        timestamp: When snapshot was taken.

    """

    objects: dict[str, dict[str, Any]] = field(default_factory=dict)
    relations: list[dict[str, str]] = field(default_factory=list)
    timestamp: float = field(default_factory=_time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {
            "objects": self.objects,
            "relations": self.relations,
            "timestamp": self.timestamp,
        }

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict())


@dataclass
class SkillTraceStep:
    """One step in a skill execution trace.

    Attributes:
        step_name: Name of the step.
        success: Whether step succeeded.
        duration: Step duration in seconds.
        details: Additional step data.

    """

    step_name: str = ""
    success: bool = True
    duration: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class RecoveryRecord:
    """Record of a recovery attempt within an episode.

    Attributes:
        failure_type: Type of failure that triggered recovery.
        strategy: Recovery strategy attempted.
        success: Whether recovery succeeded.
        timestamp: When recovery was attempted.

    """

    failure_type: str = ""
    strategy: str = ""
    success: bool = False
    timestamp: float = field(default_factory=_time.time)


@dataclass
class Episode:
    """Complete record of one task execution — the robot's experience.

    Attributes:
        episode_id: Unique identifier (episode_00001 format).
        task_type: Type of task ("pick_place", "move", etc).
        skill_name: Name of skill executed.
        robot_id: Robot identifier ("dual_ur5e", "arm1", etc).
        initial_world: World state before execution.
        final_world: World state after execution.
        execution_steps: Ordered list of skill trace steps.
        result: "success" | "failure" | "recovered".
        duration: Total execution duration in seconds.
        recovery: List of recovery attempts.
        timestamp: Episode start time.
        metadata: Additional episode metadata.

    """

    episode_id: str = ""
    task_type: str = ""
    skill_name: str = ""
    robot_id: str = ""
    initial_world: WorldStateSnapshot = field(default_factory=WorldStateSnapshot)
    final_world: WorldStateSnapshot = field(default_factory=WorldStateSnapshot)
    execution_steps: list[SkillTraceStep] = field(default_factory=list)
    result: str = "success"
    duration: float = 0.0
    recovery: list[RecoveryRecord] = field(default_factory=list)
    timestamp: float = field(default_factory=_time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def recovery_count(self) -> int:
        """Number of recovery attempts."""
        return len(self.recovery)

    @property
    def success(self) -> bool:
        """Whether episode was successful."""
        return self.result in ("success", "recovered")

    def add_step(
        self,
        step_name: str,
        success: bool = True,
        duration: float = 0.0,
        **details: Any,
    ) -> None:
        """Add an execution step.

        Args:
            step_name: Name of the step.
            success: Whether step succeeded.
            duration: Step duration.
            **details: Additional step data.

        """
        self.execution_steps.append(
            SkillTraceStep(
                step_name=step_name,
                success=success,
                duration=duration,
                details=details,
            )
        )

    def add_recovery(
        self,
        failure_type: str,
        strategy: str,
        success: bool,
    ) -> None:
        """Add a recovery attempt.

        Args:
            failure_type: Type of failure.
            strategy: Recovery strategy.
            success: Whether recovery succeeded.

        """
        self.recovery.append(
            RecoveryRecord(
                failure_type=failure_type,
                strategy=strategy,
                success=success,
            )
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for JSON/SQLite export."""
        return {
            "episode_id": self.episode_id,
            "task": self.task_type,
            "skill": self.skill_name,
            "robot": self.robot_id,
            "initial_world": self.initial_world.to_dict(),
            "final_world": self.final_world.to_dict(),
            "execution": {
                "steps": [
                    {
                        "name": s.step_name,
                        "success": s.success,
                        "duration": s.duration,
                        **s.details,
                    }
                    for s in self.execution_steps
                ],
            },
            "result": self.result,
            "duration": self.duration,
            "recovery": {
                "count": self.recovery_count,
                "attempts": [
                    {
                        "failure_type": r.failure_type,
                        "strategy": r.strategy,
                        "success": r.success,
                    }
                    for r in self.recovery
                ],
            },
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=2)