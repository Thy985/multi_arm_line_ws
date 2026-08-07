"""DatasetExporter — export Robot Experience to SQLite + JSON.

Exports episodes, failure memory, and skill traces to:
1. SQLite database (structured query, M7 training data source)
2. JSON files (human-readable, version control friendly)

SQLite Schema:
    episodes: episode_id, task_type, skill_name, robot_id, result, duration, recovery_count, timestamp, json_data
    failures: episode_id, task_type, skill_name, failure_reason, recovery_count, recovery_succeeded, timestamp
    skill_traces: episode_id, step_name, success, duration, timestamp
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from multi_arm_experience.episode import Episode
from multi_arm_experience.experience_recorder import ExperienceRecorder


class DatasetExporter:
    """Export Robot Experience to SQLite + JSON dataset.

    Args:
        db_path: Path to SQLite database file.
        json_dir: Directory for JSON export files.

    """

    def __init__(
        self,
        db_path: str | Path = "experience.db",
        json_dir: str | Path | None = None,
    ) -> None:
        """Initialize dataset exporter.

        Args:
            db_path: Path to SQLite database.
            json_dir: Directory for JSON files (None = no JSON export).

        """
        self._db_path = Path(db_path)
        self._json_dir = Path(json_dir) if json_dir else None
        self._init_db()

    def _init_db(self) -> None:
        """Initialize SQLite schema."""
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS episodes (
                    episode_id TEXT PRIMARY KEY,
                    task_type TEXT,
                    skill_name TEXT,
                    robot_id TEXT,
                    result TEXT,
                    duration REAL,
                    recovery_count INTEGER,
                    timestamp REAL,
                    json_data TEXT
                );

                CREATE TABLE IF NOT EXISTS failures (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    episode_id TEXT,
                    task_type TEXT,
                    skill_name TEXT,
                    failure_reason TEXT,
                    recovery_count INTEGER,
                    recovery_succeeded INTEGER,
                    timestamp REAL
                );

                CREATE TABLE IF NOT EXISTS skill_traces (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    episode_id TEXT,
                    step_name TEXT,
                    success INTEGER,
                    duration REAL,
                    timestamp REAL
                );
            """)

    def export_recorder(self, recorder: ExperienceRecorder) -> int:
        """Export all data from an ExperienceRecorder.

        Args:
            recorder: ExperienceRecorder with recorded data.

        Returns:
            Number of episodes exported.

        """
        episodes = recorder.get_all_episodes()
        for episode in episodes:
            self.export_episode(episode)

        for failure in recorder.get_failure_memory():
            self._export_failure(failure)

        if self._json_dir:
            self.export_json(recorder)

        return len(episodes)

    def export_episode(self, episode: Episode) -> None:
        """Export a single episode to SQLite.

        Args:
            episode: Episode to export.

        """
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO episodes
                   (episode_id, task_type, skill_name, robot_id, result,
                    duration, recovery_count, timestamp, json_data)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    episode.episode_id,
                    episode.task_type,
                    episode.skill_name,
                    episode.robot_id,
                    episode.result,
                    episode.duration,
                    episode.recovery_count,
                    episode.timestamp,
                    episode.to_json(),
                ),
            )

            for step in episode.execution_steps:
                conn.execute(
                    """INSERT INTO skill_traces
                       (episode_id, step_name, success, duration, timestamp)
                       VALUES (?, ?, ?, ?, ?)""",
                    (
                        episode.episode_id,
                        step.step_name,
                        int(step.success),
                        step.duration,
                        episode.timestamp,
                    ),
                )

    def _export_failure(self, failure: dict[str, Any]) -> None:
        """Export a failure record to SQLite.

        Args:
            failure: Failure record dict.

        """
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.execute(
                """INSERT INTO failures
                   (episode_id, task_type, skill_name, failure_reason,
                    recovery_count, recovery_succeeded, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    failure.get("episode_id", ""),
                    failure.get("task_type", ""),
                    failure.get("skill_name", ""),
                    failure.get("failure_reason", ""),
                    failure.get("recovery_count", 0),
                    int(failure.get("recovery_succeeded", False)),
                    failure.get("timestamp", 0.0),
                ),
            )

    def export_json(self, recorder: ExperienceRecorder) -> Path:
        """Export all episodes to a JSON file.

        Args:
            recorder: ExperienceRecorder with data.

        Returns:
            Path to the JSON file.

        """
        if self._json_dir is None:
            self._json_dir = Path(".")

        self._json_dir.mkdir(parents=True, exist_ok=True)
        json_path = self._json_dir / "experience_dataset.json"

        data = {
            "episodes": [ep.to_dict() for ep in recorder.get_all_episodes()],
            "failure_memory": recorder.get_failure_memory(),
            "summary": {
                "total_episodes": recorder.episode_count,
                "total_failures": recorder.failure_count,
                "success_rate": recorder.success_rate,
            },
        }

        with open(json_path, "w") as f:
            json.dump(data, f, indent=2)

        return json_path

    def query(
        self,
        table: str = "episodes",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Query the SQLite database.

        Args:
            table: Table name ("episodes"|"failures"|"skill_traces").
            limit: Max results.

        Returns:
            List of result dicts.

        """
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"SELECT * FROM {table} LIMIT ?",  # noqa: S608
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

    def get_episode_count(self) -> int:
        """Get total episode count from database."""
        with sqlite3.connect(str(self._db_path)) as conn:
            result = conn.execute("SELECT COUNT(*) FROM episodes").fetchone()
            return result[0] if result else 0

    def get_failure_count(self) -> int:
        """Get total failure count from database."""
        with sqlite3.connect(str(self._db_path)) as conn:
            result = conn.execute("SELECT COUNT(*) FROM failures").fetchone()
            return result[0] if result else 0