"""ExperienceRecorder — captures robot experience during skill execution.

Integrates with Skill Runtime: before execution captures initial world,
after execution captures final world, during execution records steps.

Usage:
    recorder = ExperienceRecorder()
    episode = recorder.start_episode("pick_place", "pick_object", "arm1")

    recorder.record_step(episode, "perceive", success=True)
    recorder.record_step(episode, "grasp", success=True)

    recorder.finish_episode(episode, result="success", duration=2.5)
    recorder.export_dataset("output.json")
"""

from __future__ import annotations

import time as _time
from typing import Any

from multi_arm_experience.episode import (
    Episode,
    WorldStateSnapshot,
    SkillTraceStep,
    RecoveryRecord,
)


class ExperienceRecorder:
    """Records robot experience as structured Episodes.

    Captures:
    - Episode: complete task execution record
    - WorldStateSnapshot: WorldModel state before/after
    - SkillTrace: step-by-step execution trace
    - FailureMemory: failure cases with recovery
    """

    def __init__(self) -> None:
        """Initialize experience recorder."""
        self._episodes: list[Episode] = []
        self._failure_memory: list[dict[str, Any]] = []
        self._next_id: int = 1

    def start_episode(
        self,
        task_type: str,
        skill_name: str,
        robot_id: str = "dual_ur5e",
        initial_world: WorldStateSnapshot | None = None,
    ) -> Episode:
        """Start recording a new episode.

        Args:
            task_type: Type of task.
            skill_name: Name of skill.
            robot_id: Robot identifier.
            initial_world: Initial world state snapshot.

        Returns:
            New Episode instance.

        """
        episode_id = f"episode_{self._next_id:05d}"
        self._next_id += 1

        episode = Episode(
            episode_id=episode_id,
            task_type=task_type,
            skill_name=skill_name,
            robot_id=robot_id,
            initial_world=initial_world or WorldStateSnapshot(),
            timestamp=_time.time(),
        )
        self._episodes.append(episode)
        return episode

    def record_step(
        self,
        episode: Episode,
        step_name: str,
        success: bool = True,
        duration: float = 0.0,
        **details: Any,
    ) -> None:
        """Record an execution step within an episode.

        Args:
            episode: Episode to record into.
            step_name: Name of the step.
            success: Whether step succeeded.
            duration: Step duration.
            **details: Additional step data.

        """
        episode.add_step(step_name, success, duration, **details)

    def record_recovery(
        self,
        episode: Episode,
        failure_type: str,
        strategy: str,
        success: bool,
    ) -> None:
        """Record a recovery attempt within an episode.

        Args:
            episode: Episode to record into.
            failure_type: Type of failure.
            strategy: Recovery strategy.
            success: Whether recovery succeeded.

        """
        episode.add_recovery(failure_type, strategy, success)

    def finish_episode(
        self,
        episode: Episode,
        result: str = "success",
        duration: float = 0.0,
        final_world: WorldStateSnapshot | None = None,
    ) -> Episode:
        """Finish recording an episode.

        Args:
            episode: Episode to finish.
            result: "success" | "failure" | "recovered".
            duration: Total execution duration.
            final_world: Final world state snapshot.

        Returns:
            The finished Episode.

        """
        episode.result = result
        episode.duration = duration
        episode.final_world = final_world or WorldStateSnapshot()

        if result in ("failure", "recovered"):
            self._failure_memory.append({
                "episode_id": episode.episode_id,
                "task_type": episode.task_type,
                "skill_name": episode.skill_name,
                "failure_reason": result,
                "recovery_count": episode.recovery_count,
                "recovery_succeeded": result == "recovered",
                "timestamp": episode.timestamp,
            })

        return episode

    def capture_world_snapshot(
        self,
        objects: dict[str, dict[str, Any]] | None = None,
        relations: list[dict[str, str]] | None = None,
    ) -> WorldStateSnapshot:
        """Capture a snapshot of WorldModel state.

        Args:
            objects: Dict of object states.
            relations: List of relations.

        Returns:
            WorldStateSnapshot.

        """
        return WorldStateSnapshot(
            objects=objects or {},
            relations=relations or [],
            timestamp=_time.time(),
        )

    def get_episode(self, episode_id: str) -> Episode | None:
        """Get episode by ID.

        Args:
            episode_id: Episode ID.

        Returns:
            Episode or None.

        """
        for ep in self._episodes:
            if ep.episode_id == episode_id:
                return ep
        return None

    def get_all_episodes(self) -> list[Episode]:
        """Get all recorded episodes."""
        return list(self._episodes)

    def get_failure_memory(self) -> list[dict[str, Any]]:
        """Get all failure records."""
        return list(self._failure_memory)

    def query(
        self,
        data_type: str = "episode",
        filter_fn: Any = None,
    ) -> list[Any]:
        """Query experience data.

        Args:
            data_type: "episode" | "failure" | "skill_trace".
            filter_fn: Optional filter function.

        Returns:
            List of matching records.

        """
        if data_type == "episode":
            results: list[Any] = list(self._episodes)
        elif data_type == "failure":
            results = list(self._failure_memory)
        elif data_type == "skill_trace":
            results = []
            for ep in self._episodes:
                results.extend(ep.execution_steps)
        else:
            results = list(self._episodes)

        if filter_fn is not None:
            results = [r for r in results if filter_fn(r)]

        return results

    @property
    def episode_count(self) -> int:
        """Total number of episodes."""
        return len(self._episodes)

    @property
    def failure_count(self) -> int:
        """Total number of failures."""
        return len(self._failure_memory)

    @property
    def success_rate(self) -> float:
        """Overall success rate across all episodes."""
        if not self._episodes:
            return 0.0
        successes = sum(1 for ep in self._episodes if ep.success)
        return successes / len(self._episodes)