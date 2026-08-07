"""Unit tests for Episode data structures."""

import json
import time

import pytest

from multi_arm_experience.episode import (
    Episode,
    RecoveryRecord,
    SkillTraceStep,
    WorldStateSnapshot,
)


class TestWorldStateSnapshot:
    """Tests for WorldStateSnapshot."""

    def test_default_construction(self) -> None:
        """Test default construction."""
        snap = WorldStateSnapshot()
        assert snap.objects == {}
        assert snap.relations == []
        assert snap.timestamp > 0

    def test_construction_with_data(self) -> None:
        """Test construction with data."""
        objects = {"cube_1": {"position": [0.5, 0.0, 0.05], "state": "free"}}
        relations = [{"subject": "cube_1", "predicate": "on", "object": "table"}]
        snap = WorldStateSnapshot(objects=objects, relations=relations)
        assert snap.objects == objects
        assert snap.relations == relations

    def test_to_dict(self) -> None:
        """Test serialization to dict."""
        snap = WorldStateSnapshot(
            objects={"a": {"x": 1}},
            relations=[{"subject": "a", "predicate": "on", "object": "b"}],
            timestamp=100.0,
        )
        d = snap.to_dict()
        assert d["objects"] == {"a": {"x": 1}}
        assert d["relations"] == [{"subject": "a", "predicate": "on", "object": "b"}]
        assert d["timestamp"] == 100.0

    def test_to_json(self) -> None:
        """Test serialization to JSON."""
        snap = WorldStateSnapshot(objects={"a": {"x": 1}})
        s = snap.to_json()
        d = json.loads(s)
        assert d["objects"] == {"a": {"x": 1}}


class TestSkillTraceStep:
    """Tests for SkillTraceStep."""

    def test_default_construction(self) -> None:
        """Test default construction."""
        step = SkillTraceStep()
        assert step.step_name == ""
        assert step.success is True
        assert step.duration == 0.0
        assert step.details == {}

    def test_construction_with_data(self) -> None:
        """Test construction with data."""
        step = SkillTraceStep(
            step_name="grasp",
            success=False,
            duration=1.5,
            details={"gripper": "robotiq_2f_85"},
        )
        assert step.step_name == "grasp"
        assert step.success is False
        assert step.duration == 1.5
        assert step.details == {"gripper": "robotiq_2f_85"}


class TestRecoveryRecord:
    """Tests for RecoveryRecord."""

    def test_default_construction(self) -> None:
        """Test default construction."""
        rec = RecoveryRecord()
        assert rec.failure_type == ""
        assert rec.strategy == ""
        assert rec.success is False
        assert rec.timestamp > 0

    def test_construction_with_data(self) -> None:
        """Test construction with data."""
        rec = RecoveryRecord(
            failure_type="planning_failed",
            strategy="relax_constraints",
            success=True,
        )
        assert rec.failure_type == "planning_failed"
        assert rec.strategy == "relax_constraints"
        assert rec.success is True


class TestEpisode:
    """Tests for Episode."""

    def test_default_construction(self) -> None:
        """Test default construction."""
        ep = Episode()
        assert ep.episode_id == ""
        assert ep.task_type == ""
        assert ep.skill_name == ""
        assert ep.robot_id == ""
        assert ep.result == "success"
        assert ep.duration == 0.0
        assert ep.execution_steps == []
        assert ep.recovery == []
        assert ep.metadata == {}

    def test_add_step(self) -> None:
        """Test adding execution steps."""
        ep = Episode(episode_id="ep_1", task_type="pick_place")
        ep.add_step("perceive", success=True, duration=0.5, object_id="cube_1")
        ep.add_step("grasp", success=True, duration=1.0)

        assert len(ep.execution_steps) == 2
        assert ep.execution_steps[0].step_name == "perceive"
        assert ep.execution_steps[0].details == {"object_id": "cube_1"}
        assert ep.execution_steps[1].step_name == "grasp"

    def test_add_recovery(self) -> None:
        """Test adding recovery records."""
        ep = Episode(episode_id="ep_1")
        ep.add_recovery("planning_failed", "relax_constraints", True)
        ep.add_recovery("grasp_failed", "retry", False)

        assert len(ep.recovery) == 2
        assert ep.recovery[0].strategy == "relax_constraints"
        assert ep.recovery[1].success is False

    def test_recovery_count_property(self) -> None:
        """Test recovery_count property."""
        ep = Episode()
        assert ep.recovery_count == 0
        ep.add_recovery("fail", "strategy", True)
        assert ep.recovery_count == 1
        ep.add_recovery("fail", "strategy", False)
        assert ep.recovery_count == 2

    def test_success_property(self) -> None:
        """Test success property."""
        ep = Episode()
        ep.result = "success"
        assert ep.success is True

        ep.result = "recovered"
        assert ep.success is True

        ep.result = "failure"
        assert ep.success is False

    def test_to_dict(self) -> None:
        """Test serialization to dict."""
        ep = Episode(
            episode_id="ep_001",
            task_type="pick_place",
            skill_name="pick_object",
            robot_id="arm1",
            result="success",
            duration=2.5,
        )
        ep.add_step("grasp", success=True, duration=1.0)
        ep.add_recovery("planning_failed", "relax", True)

        d = ep.to_dict()
        assert d["episode_id"] == "ep_001"
        assert d["task"] == "pick_place"
        assert d["skill"] == "pick_object"
        assert d["robot"] == "arm1"
        assert d["result"] == "success"
        assert d["duration"] == 2.5
        assert len(d["execution"]["steps"]) == 1
        assert d["recovery"]["count"] == 1

    def test_to_json(self) -> None:
        """Test serialization to JSON."""
        ep = Episode(episode_id="ep_001", task_type="pick_place")
        s = ep.to_json()
        d = json.loads(s)
        assert d["episode_id"] == "ep_001"
        assert d["task"] == "pick_place"

    def test_to_json_is_valid_json(self) -> None:
        """Test that to_json produces valid JSON."""
        ep = Episode(
            episode_id="ep_1",
            task_type="pick_place",
            skill_name="pick",
            robot_id="arm1",
        )
        ep.add_step("step1", success=True, duration=0.5)
        ep.add_recovery("fail", "retry", True)
        ep.initial_world = WorldStateSnapshot(
            objects={"cube": {"pos": [0, 0, 0]}},
        )
        ep.final_world = WorldStateSnapshot(
            objects={"cube": {"pos": [1, 0, 0]}},
        )

        s = ep.to_json()
        d = json.loads(s)
        assert d["initial_world"]["objects"]["cube"]["pos"] == [0, 0, 0]
        assert d["final_world"]["objects"]["cube"]["pos"] == [1, 0, 0]