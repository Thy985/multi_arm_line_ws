"""Dataset Pipeline — collect simulation data for training."""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class GroundTruth:
    """Ground truth annotation from Gazebo."""

    timestamp: float
    objects: list[dict[str, Any]] = field(default_factory=list)
    camera_pose: list[float] = field(default_factory=list)
    joint_states: dict[str, list[float]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary.

        Returns:
            Ground truth as dict.

        """
        return {
            "timestamp": self.timestamp,
            "objects": self.objects,
            "camera_pose": self.camera_pose,
            "joint_states": self.joint_states,
        }


@dataclass
class DataSample:
    """A single data sample from simulation."""

    sample_id: int
    timestamp: float
    rgb_path: str = ""
    depth_path: str = ""
    joint_states: dict[str, list[float]] = field(default_factory=dict)
    ground_truth: GroundTruth | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary.

        Returns:
            Sample as dict.

        """
        result: dict[str, Any] = {
            "sample_id": self.sample_id,
            "timestamp": self.timestamp,
            "rgb_path": self.rgb_path,
            "depth_path": self.depth_path,
            "joint_states": self.joint_states,
        }
        if self.ground_truth:
            result["ground_truth"] = self.ground_truth.to_dict()
        return result


class DatasetPipeline:
    """Collect simulation data and generate training datasets.

    Pipeline:
        Gazebo (random scenes)
          → sensor data (RGB + Depth + JointState)
          → dataset (auto-annotated with Ground Truth)
          → training (Vision / Skill Learning)
    """

    def __init__(self, output_dir: str | Path, db_name: str = "simulation_dataset.db") -> None:
        """Initialize dataset pipeline.

        Args:
            output_dir: Output directory for dataset.
            db_name: SQLite database filename.

        """
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = self._output_dir / db_name
        self._sample_counter = 0
        self._init_db()

    def _init_db(self) -> None:
        """Initialize SQLite database schema."""
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS samples (
                    sample_id INTEGER PRIMARY KEY,
                    timestamp REAL,
                    rgb_path TEXT,
                    depth_path TEXT,
                    joint_states TEXT,
                    ground_truth TEXT,
                    scene_name TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS episodes (
                    episode_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scene_name TEXT,
                    start_time REAL,
                    end_time REAL,
                    num_samples INTEGER,
                    metadata TEXT
                )
            """)

    def record_sample(
        self,
        rgb_path: str = "",
        depth_path: str = "",
        joint_states: dict[str, list[float]] | None = None,
        ground_truth: GroundTruth | None = None,
        scene_name: str = "",
    ) -> int:
        """Record a single data sample.

        Args:
            rgb_path: Path to RGB image.
            depth_path: Path to depth image.
            joint_states: Joint states dict.
            ground_truth: Ground truth annotation.
            scene_name: Scene name.

        Returns:
            Sample ID.

        """
        sample_id = self._sample_counter
        self._sample_counter += 1
        timestamp = time.time()

        gt_json = json.dumps(ground_truth.to_dict()) if ground_truth else ""
        js_json = json.dumps(joint_states or {})

        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """INSERT INTO samples
                   (sample_id, timestamp, rgb_path, depth_path,
                    joint_states, ground_truth, scene_name)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (sample_id, timestamp, rgb_path, depth_path, js_json, gt_json, scene_name),
            )

        return sample_id

    def start_episode(self, scene_name: str) -> int:
        """Start a new episode.

        Args:
            scene_name: Name of the scene.

        Returns:
            Episode ID.

        """
        timestamp = time.time()
        with sqlite3.connect(self._db_path) as conn:
            cursor = conn.execute(
                """INSERT INTO episodes (scene_name, start_time, num_samples)
                   VALUES (?, ?, 0)""",
                (scene_name, timestamp),
            )
            return cursor.lastrowid or 0

    def end_episode(self, episode_id: int, metadata: dict | None = None) -> None:
        """End an episode.

        Args:
            episode_id: Episode ID.
            metadata: Episode metadata.

        """
        timestamp = time.time()
        meta_json = json.dumps(metadata or {})

        with sqlite3.connect(self._db_path) as conn:
            count_result = conn.execute(
                "SELECT COUNT(*) FROM samples"
            ).fetchone()
            num_samples = count_result[0] if count_result else 0

            conn.execute(
                """UPDATE episodes
                   SET end_time = ?, num_samples = ?, metadata = ?
                   WHERE episode_id = ?""",
                (timestamp, num_samples, meta_json, episode_id),
            )

    def get_sample_count(self) -> int:
        """Get total number of recorded samples.

        Returns:
            Sample count.

        """
        with sqlite3.connect(self._db_path) as conn:
            result = conn.execute("SELECT COUNT(*) FROM samples").fetchone()
            return result[0] if result else 0

    def get_episode_count(self) -> int:
        """Get total number of episodes.

        Returns:
            Episode count.

        """
        with sqlite3.connect(self._db_path) as conn:
            result = conn.execute("SELECT COUNT(*) FROM episodes").fetchone()
            return result[0] if result else 0

    def query_samples(self, limit: int = 100) -> list[dict[str, Any]]:
        """Query recorded samples.

        Args:
            limit: Maximum number of samples.

        Returns:
            List of sample dicts.

        """
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM samples LIMIT ?", (limit,)
            ).fetchall()
            return [dict(row) for row in rows]

    def export_dataset(self, output_file: str | Path) -> int:
        """Export dataset to JSON file.

        Args:
            output_file: Output JSON file path.

        Returns:
            Number of exported samples.

        """
        samples = self.query_samples(limit=1000000)
        with open(output_file, "w") as f:
            json.dump(samples, f, indent=2)
        return len(samples)