"""Unit tests for DatasetExporter."""

import json
import sqlite3
from pathlib import Path

import pytest

from multi_arm_experience.episode import Episode, WorldStateSnapshot
from multi_arm_experience.experience_recorder import ExperienceRecorder
from multi_arm_experience.dataset_exporter import DatasetExporter


@pytest.fixture
def tmp_db(tmp_path: Path) -> str:
    """Fixture for temporary database path."""
    return str(tmp_path / "test_experience.db")


@pytest.fixture
def tmp_json_dir(tmp_path: Path) -> str:
    """Fixture for temporary JSON directory."""
    return str(tmp_path / "json_output")


@pytest.fixture
def recorder_with_data() -> ExperienceRecorder:
    """Fixture for recorder with sample data."""
    recorder = ExperienceRecorder()

    ep1 = recorder.start_episode("pick_place", "pick_object", "arm1")
    recorder.record_step(ep1, "grasp", success=True, duration=1.0)
    recorder.finish_episode(ep1, result="success", duration=2.0)

    ep2 = recorder.start_episode("pick_place", "pick_object", "arm2")
    recorder.record_step(ep2, "grasp", success=False, duration=1.0)
    recorder.record_recovery(ep2, "grasp_failed", "retry", True)
    recorder.finish_episode(ep2, result="recovered", duration=3.0)

    ep3 = recorder.start_episode("move", "move_object", "arm1")
    recorder.record_step(ep3, "plan", success=True, duration=0.5)
    recorder.finish_episode(ep3, result="failure", duration=1.0)

    return recorder


class TestDatasetExporter:
    """Tests for DatasetExporter."""

    def test_init_creates_db(self, tmp_db: str) -> None:
        """Test that init creates the database."""
        exporter = DatasetExporter(db_path=tmp_db)
        assert Path(tmp_db).exists()

    def test_init_creates_tables(self, tmp_db: str) -> None:
        """Test that init creates all tables."""
        exporter = DatasetExporter(db_path=tmp_db)

        with sqlite3.connect(tmp_db) as conn:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            table_names = {t[0] for t in tables}
            assert "episodes" in table_names
            assert "failures" in table_names
            assert "skill_traces" in table_names

    def test_export_episode(self, tmp_db: str) -> None:
        """Test exporting a single episode."""
        exporter = DatasetExporter(db_path=tmp_db)

        ep = Episode(
            episode_id="test_ep_001",
            task_type="pick_place",
            skill_name="pick_object",
            robot_id="arm1",
            result="success",
            duration=2.5,
        )
        ep.add_step("grasp", success=True, duration=1.0)
        ep.add_step("lift", success=True, duration=0.5)

        exporter.export_episode(ep)

        assert exporter.get_episode_count() == 1

        rows = exporter.query(table="episodes")
        assert len(rows) == 1
        assert rows[0]["episode_id"] == "test_ep_001"
        assert rows[0]["task_type"] == "pick_place"
        assert rows[0]["result"] == "success"

    def test_export_episode_with_traces(self, tmp_db: str) -> None:
        """Test that episode export includes skill traces."""
        exporter = DatasetExporter(db_path=tmp_db)

        ep = Episode(episode_id="ep_001", task_type="pick", skill_name="pick_object")
        ep.add_step("step1", success=True, duration=0.5)
        ep.add_step("step2", success=False, duration=1.0)

        exporter.export_episode(ep)

        traces = exporter.query(table="skill_traces")
        assert len(traces) == 2
        assert traces[0]["step_name"] == "step1"
        assert traces[1]["step_name"] == "step2"

    def test_export_recorder(self, tmp_db: str, recorder_with_data: ExperienceRecorder) -> None:
        """Test exporting all data from recorder."""
        exporter = DatasetExporter(db_path=tmp_db)

        count = exporter.export_recorder(recorder_with_data)

        assert count == 3
        assert exporter.get_episode_count() == 3
        assert exporter.get_failure_count() == 2

    def test_export_recorder_with_json(
        self,
        tmp_db: str,
        tmp_json_dir: str,
        recorder_with_data: ExperienceRecorder,
    ) -> None:
        """Test exporting with JSON output."""
        exporter = DatasetExporter(db_path=tmp_db, json_dir=tmp_json_dir)

        exporter.export_recorder(recorder_with_data)

        json_path = Path(tmp_json_dir) / "experience_dataset.json"
        assert json_path.exists()

        with open(json_path) as f:
            data = json.load(f)
        assert len(data["episodes"]) == 3
        assert data["summary"]["total_episodes"] == 3
        assert data["summary"]["total_failures"] == 2

    def test_query_episodes(self, tmp_db: str, recorder_with_data: ExperienceRecorder) -> None:
        """Test querying episodes table."""
        exporter = DatasetExporter(db_path=tmp_db)
        exporter.export_recorder(recorder_with_data)

        rows = exporter.query(table="episodes", limit=10)
        assert len(rows) == 3

    def test_query_failures(self, tmp_db: str, recorder_with_data: ExperienceRecorder) -> None:
        """Test querying failures table."""
        exporter = DatasetExporter(db_path=tmp_db)
        exporter.export_recorder(recorder_with_data)

        rows = exporter.query(table="failures", limit=10)
        assert len(rows) == 2

    def test_query_skill_traces(
        self,
        tmp_db: str,
        recorder_with_data: ExperienceRecorder,
    ) -> None:
        """Test querying skill_traces table."""
        exporter = DatasetExporter(db_path=tmp_db)
        exporter.export_recorder(recorder_with_data)

        rows = exporter.query(table="skill_traces", limit=100)
        assert len(rows) == 3

    def test_get_episode_count(self, tmp_db: str) -> None:
        """Test get_episode_count."""
        exporter = DatasetExporter(db_path=tmp_db)
        assert exporter.get_episode_count() == 0

        ep = Episode(episode_id="ep_1", task_type="task", skill_name="skill")
        exporter.export_episode(ep)
        assert exporter.get_episode_count() == 1

    def test_get_failure_count(self, tmp_db: str, recorder_with_data: ExperienceRecorder) -> None:
        """Test get_failure_count."""
        exporter = DatasetExporter(db_path=tmp_db)
        assert exporter.get_failure_count() == 0

        exporter.export_recorder(recorder_with_data)
        assert exporter.get_failure_count() == 2

    def test_episode_json_data_is_valid(self, tmp_db: str) -> None:
        """Test that stored json_data is valid JSON."""
        exporter = DatasetExporter(db_path=tmp_db)

        ep = Episode(
            episode_id="ep_001",
            task_type="pick_place",
            skill_name="pick_object",
            robot_id="arm1",
        )
        ep.add_step("grasp", success=True, duration=1.0)
        ep.initial_world = WorldStateSnapshot(objects={"cube": {"pos": [0, 0, 0]}})

        exporter.export_episode(ep)

        with sqlite3.connect(tmp_db) as conn:
            row = conn.execute("SELECT json_data FROM episodes").fetchone()
            data = json.loads(row[0])
            assert data["episode_id"] == "ep_001"
            assert data["initial_world"]["objects"]["cube"]["pos"] == [0, 0, 0]