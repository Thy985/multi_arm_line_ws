"""Tests for SkillLifecycle."""

import pytest

from multi_arm_skill_runtime.skill_lifecycle import (
    SkillLifecycle,
    SkillLifecycleState,
    SkillLifecycleEntry,
    SkillExecutionRecord,
)


class TestSkillLifecycle:
    """Test SkillLifecycle state transitions."""

    def test_install(self) -> None:
        """Test skill installation creates INSTALLED state."""
        lifecycle = SkillLifecycle()
        skill_id = lifecycle.install("pick_object", "1.0.0")

        assert skill_id.startswith("skill_")
        state = lifecycle.get_state(skill_id)
        assert state == SkillLifecycleState.INSTALLED

    def test_register(self) -> None:
        """Test register transition."""
        lifecycle = SkillLifecycle()
        skill_id = lifecycle.install("test")

        assert lifecycle.register(skill_id)
        assert lifecycle.get_state(skill_id) == SkillLifecycleState.REGISTERED

    def test_validate_success(self) -> None:
        """Test validate transition on success."""
        lifecycle = SkillLifecycle()
        skill_id = lifecycle.install("test")
        lifecycle.register(skill_id)

        assert lifecycle.validate(skill_id)
        assert lifecycle.get_state(skill_id) == SkillLifecycleState.VALIDATED

    def test_validate_failure(self) -> None:
        """Test validate transition on failure."""
        lifecycle = SkillLifecycle()
        skill_id = lifecycle.install("test")
        lifecycle.register(skill_id)

        assert not lifecycle.validate(skill_id, ["Missing capability"])
        assert lifecycle.get_state(skill_id) == SkillLifecycleState.INVALID

    def test_make_ready(self) -> None:
        """Test make_ready transition."""
        lifecycle = SkillLifecycle()
        skill_id = lifecycle.install("test")
        lifecycle.register(skill_id)
        lifecycle.validate(skill_id)

        assert lifecycle.make_ready(skill_id)
        assert lifecycle.get_state(skill_id) == SkillLifecycleState.READY

    def test_full_lifecycle(self) -> None:
        """Test full lifecycle: Install→Register→Validate→Ready→Execute→Monitor→Ready."""
        lifecycle = SkillLifecycle()
        skill_id = lifecycle.install("pick_object")
        assert lifecycle.get_state(skill_id) == SkillLifecycleState.INSTALLED

        assert lifecycle.register(skill_id)
        assert lifecycle.get_state(skill_id) == SkillLifecycleState.REGISTERED

        assert lifecycle.validate(skill_id)
        assert lifecycle.get_state(skill_id) == SkillLifecycleState.VALIDATED

        assert lifecycle.make_ready(skill_id)
        assert lifecycle.get_state(skill_id) == SkillLifecycleState.READY

        assert lifecycle.start_execution(skill_id)
        assert lifecycle.get_state(skill_id) == SkillLifecycleState.EXECUTING

        assert lifecycle.finish_execution(skill_id, success=True, duration=1.5)
        assert lifecycle.get_state(skill_id) == SkillLifecycleState.MONITORING

        assert lifecycle.complete_monitoring(skill_id)
        assert lifecycle.get_state(skill_id) == SkillLifecycleState.READY

    def test_invalid_transition(self) -> None:
        """Test that invalid transitions are rejected."""
        lifecycle = SkillLifecycle()
        skill_id = lifecycle.install("test")

        assert not lifecycle.start_execution(skill_id)
        assert lifecycle.get_state(skill_id) == SkillLifecycleState.INSTALLED

    def test_hot_update(self) -> None:
        """Test hot update lifecycle."""
        lifecycle = SkillLifecycle()
        skill_id = lifecycle.install("test", "1.0.0")
        lifecycle.register(skill_id)
        lifecycle.validate(skill_id)
        lifecycle.make_ready(skill_id)

        assert lifecycle.start_update(skill_id)
        assert lifecycle.get_state(skill_id) == SkillLifecycleState.UPDATING

        assert lifecycle.finish_update(skill_id, "2.0.0")
        assert lifecycle.get_state(skill_id) == SkillLifecycleState.READY

        entry = lifecycle.get_entry(skill_id)
        assert entry is not None
        assert entry.version == "2.0.0"

    def test_removal(self) -> None:
        """Test skill removal lifecycle."""
        lifecycle = SkillLifecycle()
        skill_id = lifecycle.install("test")
        lifecycle.register(skill_id)
        lifecycle.validate(skill_id)
        lifecycle.make_ready(skill_id)

        assert lifecycle.start_removal(skill_id)
        assert lifecycle.get_state(skill_id) == SkillLifecycleState.REMOVING

        assert lifecycle.finish_removal(skill_id)
        assert lifecycle.get_state(skill_id) == SkillLifecycleState.REMOVED

    def test_execution_record(self) -> None:
        """Test execution recording."""
        lifecycle = SkillLifecycle()
        skill_id = lifecycle.install("test")
        lifecycle.register(skill_id)
        lifecycle.validate(skill_id)
        lifecycle.make_ready(skill_id)
        lifecycle.start_execution(skill_id)
        lifecycle.finish_execution(skill_id, success=True, duration=2.0)

        entry = lifecycle.get_entry(skill_id)
        assert entry is not None
        assert entry.total_executions == 1
        assert entry.success_count == 1
        assert entry.success_rate == 1.0
        assert len(entry.execution_history) == 1
        assert entry.execution_history[0].success is True
        assert entry.execution_history[0].duration == 2.0

    def test_success_rate_calculation(self) -> None:
        """Test success rate calculation with mixed results."""
        lifecycle = SkillLifecycle()
        skill_id = lifecycle.install("test")
        lifecycle.register(skill_id)
        lifecycle.validate(skill_id)
        lifecycle.make_ready(skill_id)

        for success in [True, True, False, True, False]:
            lifecycle.start_execution(skill_id)
            lifecycle.finish_execution(skill_id, success=success)

        entry = lifecycle.get_entry(skill_id)
        assert entry is not None
        assert entry.total_executions == 5
        assert entry.success_count == 3
        assert entry.success_rate == pytest.approx(0.6)

    def test_execution_history_limit(self) -> None:
        """Test execution history is capped at 100 entries."""
        lifecycle = SkillLifecycle()
        skill_id = lifecycle.install("test")
        lifecycle.register(skill_id)
        lifecycle.validate(skill_id)
        lifecycle.make_ready(skill_id)

        for _ in range(150):
            lifecycle.start_execution(skill_id)
            lifecycle.finish_execution(skill_id, success=True)

        entry = lifecycle.get_entry(skill_id)
        assert entry is not None
        assert len(entry.execution_history) == 100

    def test_get_all_entries(self) -> None:
        """Test getting all lifecycle entries."""
        lifecycle = SkillLifecycle()
        id1 = lifecycle.install("skill1")
        id2 = lifecycle.install("skill2")

        entries = lifecycle.get_all_entries()
        assert len(entries) == 2
        assert id1 in entries
        assert id2 in entries

    def test_nonexistent_skill(self) -> None:
        """Test operations on nonexistent skill."""
        lifecycle = SkillLifecycle()
        assert lifecycle.register("nonexistent") is False
        assert lifecycle.get_state("nonexistent") is None
        assert lifecycle.get_entry("nonexistent") is None