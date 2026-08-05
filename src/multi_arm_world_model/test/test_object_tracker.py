"""Tests for ObjectTracker."""

import pytest

from multi_arm_world_model.state_database import StateDatabase, TrackedObject
from multi_arm_world_model.object_tracker import ObjectTracker


class TestObjectTracker:
    """Tests for the ObjectTracker class."""

    def test_new_detection_creates_object(self) -> None:
        db = StateDatabase()
        tracker = ObjectTracker()
        ids = tracker.update(db, [
            {"object_type": "cube", "position": (0.3, 0.1, 0.05)}
        ])
        assert len(ids) == 1
        assert db.get_object(ids[0]) is not None

    def test_existing_object_updated(self) -> None:
        db = StateDatabase()
        tracker = ObjectTracker()
        ids1 = tracker.update(db, [
            {"object_type": "cube", "position": (0.3, 0.1, 0.05)}
        ])
        import time
        time.sleep(0.01)
        ids2 = tracker.update(db, [
            {"object_type": "cube", "position": (0.35, 0.1, 0.05)}
        ])
        assert ids1[0] == ids2[0]
        obj = db.get_object(ids1[0])
        assert abs(obj.position[0] - 0.35) < 0.01

    def test_id_association(self) -> None:
        db = StateDatabase()
        tracker = ObjectTracker()
        ids = tracker.update(db, [
            {"id": "box001", "object_type": "cube", "position": (0.3, 0.1, 0.05)}
        ])
        assert ids[0] == "box001"

    def test_multiple_detections(self) -> None:
        db = StateDatabase()
        tracker = ObjectTracker()
        ids = tracker.update(db, [
            {"object_type": "cube", "position": (0.3, 0.1, 0.05)},
            {"object_type": "sphere", "position": (-0.3, 0.1, 0.05)},
        ])
        assert len(ids) == 2
        assert len(db.get_all_objects()) == 2

    def test_lost_object_removal(self) -> None:
        db = StateDatabase()
        tracker = ObjectTracker(max_lost_frames=2)
        tracker.update(db, [
            {"object_type": "cube", "position": (0.3, 0.1, 0.05)}
        ])
        assert len(db.get_all_objects()) == 1
        tracker.update(db, [])
        tracker.update(db, [])
        assert len(db.get_all_objects()) == 0

    def test_predict_positions(self) -> None:
        db = StateDatabase()
        tracker = ObjectTracker()
        tracker.update(db, [
            {"id": "box1", "object_type": "cube", "position": (0.0, 0.0, 0.0)}
        ])
        import time
        time.sleep(0.01)
        tracker.update(db, [
            {"id": "box1", "object_type": "cube", "position": (0.1, 0.0, 0.0)}
        ])
        predictions = tracker.predict_positions(db, dt=1.0)
        assert "box1" in predictions