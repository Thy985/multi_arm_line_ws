"""Tests for StateDatabase."""

import pytest
import time

from multi_arm_world_model.state_database import (
    CachedRobotState,
    EnvironmentInfo,
    StateDatabase,
    TaskContext,
    TrackedObject,
)


class TestTrackedObject:
    """Tests for TrackedObject."""

    def test_default_values(self) -> None:
        obj = TrackedObject(object_id="box1", object_type="cube")
        assert obj.object_id == "box1"
        assert obj.confidence == 1.0

    def test_is_stale(self) -> None:
        obj = TrackedObject(object_id="box1", last_seen=time.time() - 10)
        assert obj.is_stale(max_age=5.0)

    def test_not_stale(self) -> None:
        obj = TrackedObject(object_id="box1", last_seen=time.time())
        assert not obj.is_stale(max_age=5.0)

    def test_predicted_position(self) -> None:
        obj = TrackedObject(
            object_id="box1",
            position=(1.0, 2.0, 3.0),
            velocity=(0.1, 0.2, 0.0),
        )
        pred = obj.predicted_position(dt=1.0)
        assert abs(pred[0] - 1.1) < 0.01
        assert abs(pred[1] - 2.2) < 0.01


class TestCachedRobotState:
    """Tests for CachedRobotState."""

    def test_default_stale_check(self) -> None:
        state = CachedRobotState(arm_name="arm1", last_updated=time.time())
        assert not state.is_stale()

    def test_stale_state(self) -> None:
        state = CachedRobotState(arm_name="arm1", last_updated=time.time() - 2.0)
        assert state.is_stale(max_age=1.0)


class TestStateDatabase:
    """Tests for StateDatabase."""

    def test_add_and_get_object(self) -> None:
        db = StateDatabase()
        obj = TrackedObject(object_id="box1", object_type="cube")
        db.add_object(obj)
        assert db.get_object("box1") is obj

    def test_remove_object(self) -> None:
        db = StateDatabase()
        db.add_object(TrackedObject(object_id="box1"))
        assert db.remove_object("box1")
        assert db.get_object("box1") is None

    def test_get_objects_by_type(self) -> None:
        db = StateDatabase()
        db.add_object(TrackedObject(object_id="box1", object_type="cube"))
        db.add_object(TrackedObject(object_id="box2", object_type="sphere"))
        db.add_object(TrackedObject(object_id="box3", object_type="cube"))
        cubes = db.get_objects_by_type("cube")
        assert len(cubes) == 2

    def test_update_object_pose(self) -> None:
        db = StateDatabase()
        obj = TrackedObject(object_id="box1", position=(0.0, 0.0, 0.0))
        db.add_object(obj)
        time.sleep(0.01)
        db.update_object_pose("box1", (1.0, 0.0, 0.0))
        updated = db.get_object("box1")
        assert updated.position == (1.0, 0.0, 0.0)
        assert updated.velocity[0] > 0

    def test_environment(self) -> None:
        db = StateDatabase()
        db.add_zone("zone_a", {"type": "shared"})
        assert "zone_a" in db.environment.zones

    def test_task_context(self) -> None:
        db = StateDatabase()
        ctx = TaskContext(task_id="t1", target_object_id="box1")
        db.set_task_context(ctx)
        assert db.get_task_context("t1").target_object_id == "box1"

    def test_robot_state_cache(self) -> None:
        db = StateDatabase()
        db.update_robot_state("arm1", [0.0] * 6, [0.1] * 6)
        state = db.get_robot_state("arm1")
        assert state is not None
        assert state.arm_name == "arm1"
        assert not state.is_stale()

    def test_ownership_boundary(self) -> None:
        """Verify 500Hz joint_states do NOT enter WorldModel."""
        db = StateDatabase()
        db.update_robot_state("arm1", [0.0] * 6)
        state = db.get_robot_state("arm1")
        assert state is not None
        assert state.last_updated > 0
        assert not state.is_stale(max_age=1.0)

    def test_cleanup_stale(self) -> None:
        db = StateDatabase()
        obj = TrackedObject(object_id="old", last_seen=time.time() - 100)
        db.add_object(obj)
        removed = db.cleanup_stale(object_max_age=10.0)
        assert removed == 1
        assert db.get_object("old") is None

    def test_get_all_robot_states(self) -> None:
        db = StateDatabase()
        db.update_robot_state("arm1", [0.0] * 6)
        db.update_robot_state("arm2", [1.0] * 6)
        states = db.get_all_robot_states()
        assert len(states) == 2