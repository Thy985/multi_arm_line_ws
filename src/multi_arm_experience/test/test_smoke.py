"""Smoke test for multi_arm_experience package."""

import pytest

from multi_arm_experience.episode import (
    Episode,
    RecoveryRecord,
    SkillTraceStep,
    WorldStateSnapshot,
)
from multi_arm_experience.experience_recorder import ExperienceRecorder
from multi_arm_experience.dataset_exporter import DatasetExporter


def test_package_imports() -> None:
    """Test that all modules can be imported."""
    assert Episode is not None
    assert WorldStateSnapshot is not None
    assert SkillTraceStep is not None
    assert RecoveryRecord is not None
    assert ExperienceRecorder is not None
    assert DatasetExporter is not None


def test_basic_episode_recording(tmp_path) -> None:
    """Test basic episode recording and export."""
    recorder = ExperienceRecorder()

    ep = recorder.start_episode("pick_place", "pick_object", "left_arm")
    recorder.record_step(ep, "grasp", success=True, duration=1.0)
    recorder.finish_episode(ep, result="success", duration=2.0)

    assert recorder.episode_count == 1
    assert recorder.success_rate == 1.0

    exporter = DatasetExporter(db_path=str(tmp_path / "smoke.db"))
    count = exporter.export_recorder(recorder)
    assert count == 1
    assert exporter.get_episode_count() == 1