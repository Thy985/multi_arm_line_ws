"""Unit tests for ExperienceRecorder."""

import pytest

from multi_arm_experience.episode import Episode, WorldStateSnapshot
from multi_arm_experience.experience_recorder import ExperienceRecorder


class TestExperienceRecorder:
    """Tests for ExperienceRecorder."""

    def test_init(self) -> None:
        """Test initialization."""
        recorder = ExperienceRecorder()
        assert recorder.episode_count == 0
        assert recorder.failure_count == 0
        assert recorder.success_rate == 0.0

    def test_start_episode(self) -> None:
        """Test starting an episode."""
        recorder = ExperienceRecorder()
        ep = recorder.start_episode("pick_place", "pick_object", "arm1")

        assert ep.episode_id == "episode_00001"
        assert ep.task_type == "pick_place"
        assert ep.skill_name == "pick_object"
        assert ep.robot_id == "arm1"
        assert recorder.episode_count == 1

    def test_start_episode_auto_increment(self) -> None:
        """Test episode ID auto-increment."""
        recorder = ExperienceRecorder()
        ep1 = recorder.start_episode("task", "skill")
        ep2 = recorder.start_episode("task", "skill")
        ep3 = recorder.start_episode("task", "skill")

        assert ep1.episode_id == "episode_00001"
        assert ep2.episode_id == "episode_00002"
        assert ep3.episode_id == "episode_00003"

    def test_start_episode_with_initial_world(self) -> None:
        """Test starting episode with initial world snapshot."""
        recorder = ExperienceRecorder()
        world = WorldStateSnapshot(objects={"cube": {"pos": [0, 0, 0]}})
        ep = recorder.start_episode("pick", "pick_object", initial_world=world)

        assert ep.initial_world.objects == {"cube": {"pos": [0, 0, 0]}}

    def test_record_step(self) -> None:
        """Test recording a step."""
        recorder = ExperienceRecorder()
        ep = recorder.start_episode("pick_place", "pick_object")

        recorder.record_step(ep, "perceive", success=True, duration=0.5)
        recorder.record_step(ep, "grasp", success=True, duration=1.0, object_id="cube")

        assert len(ep.execution_steps) == 2
        assert ep.execution_steps[0].step_name == "perceive"
        assert ep.execution_steps[1].details == {"object_id": "cube"}

    def test_record_recovery(self) -> None:
        """Test recording a recovery."""
        recorder = ExperienceRecorder()
        ep = recorder.start_episode("pick_place", "pick_object")

        recorder.record_recovery(ep, "planning_failed", "relax", True)

        assert ep.recovery_count == 1
        assert ep.recovery[0].strategy == "relax"

    def test_finish_episode_success(self) -> None:
        """Test finishing episode with success."""
        recorder = ExperienceRecorder()
        ep = recorder.start_episode("pick_place", "pick_object")

        result = recorder.finish_episode(ep, result="success", duration=2.5)

        assert result.result == "success"
        assert result.duration == 2.5
        assert recorder.failure_count == 0

    def test_finish_episode_failure(self) -> None:
        """Test finishing episode with failure."""
        recorder = ExperienceRecorder()
        ep = recorder.start_episode("pick_place", "pick_object")

        recorder.finish_episode(ep, result="failure", duration=3.0)

        assert recorder.failure_count == 1
        failures = recorder.get_failure_memory()
        assert failures[0]["episode_id"] == ep.episode_id
        assert failures[0]["recovery_succeeded"] is False

    def test_finish_episode_recovered(self) -> None:
        """Test finishing episode with recovered."""
        recorder = ExperienceRecorder()
        ep = recorder.start_episode("pick_place", "pick_object")
        recorder.record_recovery(ep, "fail", "retry", True)
        recorder.finish_episode(ep, result="recovered", duration=4.0)

        assert recorder.failure_count == 1
        failures = recorder.get_failure_memory()
        assert failures[0]["recovery_succeeded"] is True

    def test_capture_world_snapshot(self) -> None:
        """Test capturing world snapshot."""
        recorder = ExperienceRecorder()
        snap = recorder.capture_world_snapshot(
            objects={"cube": {"pos": [0.5, 0, 0.05]}},
            relations=[{"subject": "cube", "predicate": "on", "object": "table"}],
        )

        assert snap.objects == {"cube": {"pos": [0.5, 0, 0.05]}}
        assert len(snap.relations) == 1

    def test_get_episode(self) -> None:
        """Test getting episode by ID."""
        recorder = ExperienceRecorder()
        ep = recorder.start_episode("task", "skill")

        found = recorder.get_episode(ep.episode_id)
        assert found is not None
        assert found.episode_id == ep.episode_id

        not_found = recorder.get_episode("nonexistent")
        assert not_found is None

    def test_get_all_episodes(self) -> None:
        """Test getting all episodes."""
        recorder = ExperienceRecorder()
        recorder.start_episode("task1", "skill1")
        recorder.start_episode("task2", "skill2")

        all_eps = recorder.get_all_episodes()
        assert len(all_eps) == 2

    def test_query_episodes(self) -> None:
        """Test querying episodes."""
        recorder = ExperienceRecorder()
        ep1 = recorder.start_episode("pick", "pick_object")
        ep2 = recorder.start_episode("move", "move_object")

        results = recorder.query(data_type="episode")
        assert len(results) == 2

    def test_query_failures(self) -> None:
        """Test querying failures."""
        recorder = ExperienceRecorder()
        ep = recorder.start_episode("pick", "pick_object")
        recorder.finish_episode(ep, result="failure")

        results = recorder.query(data_type="failure")
        assert len(results) == 1

    def test_query_skill_traces(self) -> None:
        """Test querying skill traces."""
        recorder = ExperienceRecorder()
        ep = recorder.start_episode("pick", "pick_object")
        recorder.record_step(ep, "step1", success=True)
        recorder.record_step(ep, "step2", success=True)

        results = recorder.query(data_type="skill_trace")
        assert len(results) == 2

    def test_query_with_filter(self) -> None:
        """Test querying with filter function."""
        recorder = ExperienceRecorder()
        ep1 = recorder.start_episode("pick", "pick_object")
        ep2 = recorder.start_episode("move", "move_object")

        results = recorder.query(
            data_type="episode",
            filter_fn=lambda e: e.task_type == "pick",
        )
        assert len(results) == 1
        assert results[0].task_type == "pick"

    def test_success_rate(self) -> None:
        """Test success rate calculation."""
        recorder = ExperienceRecorder()

        ep1 = recorder.start_episode("task", "skill")
        recorder.finish_episode(ep1, result="success")

        ep2 = recorder.start_episode("task", "skill")
        recorder.finish_episode(ep2, result="failure")

        ep3 = recorder.start_episode("task", "skill")
        recorder.finish_episode(ep3, result="success")

        assert recorder.episode_count == 3
        assert recorder.success_rate == pytest.approx(2.0 / 3.0)

    def test_full_episode_lifecycle(self) -> None:
        """Test full episode lifecycle."""
        recorder = ExperienceRecorder()

        initial_world = recorder.capture_world_snapshot(
            objects={"cube_1": {"position": [0.5, 0.0, 0.05], "state": "free"}},
        )

        ep = recorder.start_episode(
            "pick_place",
            "pick_object",
            "arm1",
            initial_world=initial_world,
        )

        recorder.record_step(ep, "perceive", success=True, duration=0.3)
        recorder.record_step(ep, "plan_grasp", success=True, duration=0.1)
        recorder.record_step(ep, "execute_grasp", success=True, duration=1.5)
        recorder.record_step(ep, "lift", success=True, duration=0.5)

        final_world = recorder.capture_world_snapshot(
            objects={"cube_1": {"position": [0.5, 0.0, 0.3], "state": "attached"}},
            relations=[{"subject": "cube_1", "predicate": "attached_to", "object": "gripper"}],
        )

        recorder.finish_episode(ep, result="success", duration=2.4, final_world=final_world)

        assert ep.success is True
        assert len(ep.execution_steps) == 4
        assert ep.initial_world.objects["cube_1"]["state"] == "free"
        assert ep.final_world.objects["cube_1"]["state"] == "attached"
        assert recorder.episode_count == 1
        assert recorder.success_rate == 1.0