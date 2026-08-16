"""Tests for DatasetPipeline."""

from pathlib import Path

import pytest

from multi_arm_simulation.dataset_pipeline import (
    DataSample,
    DatasetPipeline,
    GroundTruth,
)


@pytest.fixture
def pipeline(tmp_path: Path) -> DatasetPipeline:
    """Create a test dataset pipeline."""
    return DatasetPipeline(tmp_path / "test_dataset")


class TestDatasetPipeline:
    """Tests for DatasetPipeline."""

    def test_init_creates_db(self, pipeline: DatasetPipeline) -> None:
        assert pipeline._db_path.exists()

    def test_record_sample(self, pipeline: DatasetPipeline) -> None:
        sample_id = pipeline.record_sample(
            joint_states={"left_arm": [0.0, -1.57, 1.57, 0.0, 0.0, 0.0]},
            scene_name="test",
        )
        assert sample_id == 0
        assert pipeline.get_sample_count() == 1

    def test_record_multiple_samples(self, pipeline: DatasetPipeline) -> None:
        for i in range(5):
            pipeline.record_sample(scene_name="test")
        assert pipeline.get_sample_count() == 5

    def test_record_with_ground_truth(self, pipeline: DatasetPipeline) -> None:
        gt = GroundTruth(
            timestamp=1.0,
            objects=[{"name": "red_cube", "position": [0.5, 0.5, 0.1]}],
        )
        sample_id = pipeline.record_sample(ground_truth=gt)
        samples = pipeline.query_samples()
        assert len(samples) == 1
        assert samples[0]["sample_id"] == sample_id

    def test_episode(self, pipeline: DatasetPipeline) -> None:
        ep_id = pipeline.start_episode("test_scene")
        assert ep_id > 0
        pipeline.record_sample(scene_name="test_scene")
        pipeline.end_episode(ep_id, metadata={"success": True})
        assert pipeline.get_episode_count() == 1

    def test_query_samples(self, pipeline: DatasetPipeline) -> None:
        for i in range(10):
            pipeline.record_sample()
        samples = pipeline.query_samples(limit=5)
        assert len(samples) == 5

    def test_export_dataset(self, pipeline: DatasetPipeline, tmp_path: Path) -> None:
        for i in range(3):
            pipeline.record_sample()
        output = tmp_path / "export.json"
        count = pipeline.export_dataset(output)
        assert count == 3
        assert output.exists()


class TestGroundTruth:
    """Tests for GroundTruth."""

    def test_to_dict(self) -> None:
        gt = GroundTruth(
            timestamp=1.0,
            objects=[{"name": "cube", "position": [0, 0, 0]}],
        )
        d = gt.to_dict()
        assert d["timestamp"] == 1.0
        assert len(d["objects"]) == 1


class TestDataSample:
    """Tests for DataSample."""

    def test_to_dict(self) -> None:
        sample = DataSample(
            sample_id=0,
            timestamp=1.0,
            joint_states={"left_arm": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]},
        )
        d = sample.to_dict()
        assert d["sample_id"] == 0
        assert "joint_states" in d