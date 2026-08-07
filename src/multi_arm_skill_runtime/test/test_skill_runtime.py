"""Tests for SkillRuntime execution pipeline."""

import pytest

from multi_arm_skill_runtime.skill_manifest import SkillManifest, SkillCost
from multi_arm_skill_runtime.skill_registry import SkillRegistry
from multi_arm_skill_runtime.skill_runtime import (
    SkillRuntime,
    SkillResult,
    ExecutionStatus,
)
from multi_arm_skill_runtime.skill_lifecycle import SkillLifecycleState


class TestSkillRuntime:
    """Test SkillRuntime execution pipeline."""

    @pytest.fixture
    def setup(self) -> dict:
        """Create runtime with test skill."""
        registry = SkillRegistry()

        manifest = SkillManifest(
            name="pick_object",
            version="1.0.0",
            required_capabilities=["manipulation", "gripper"],
            preconditions=["object exists", "gripper is open"],
            postconditions=["object attached"],
            execute_steps=["perceive", "grasp"],
            cost=SkillCost(time=5.0),
            recovery={"default": "retry(3)"},
        )

        skill_id = registry.install_skill(manifest)
        registry.register_skill(skill_id)
        registry.validate_skill(skill_id)

        def exec_func(**kwargs):
            return True

        runtime = SkillRuntime(
            registry,
            execution_functions={"pick_object": exec_func},
        )

        return {
            "registry": registry,
            "runtime": runtime,
            "skill_id": skill_id,
            "manifest": manifest,
        }

    def test_execute_success(self, setup: dict) -> None:
        """Test successful skill execution."""
        result = setup["runtime"].execute(setup["skill_id"])

        assert result.status == ExecutionStatus.SUCCESS
        assert result.duration > 0

    def test_execute_with_precondition_checker(self, setup: dict) -> None:
        """Test execution with precondition checking."""
        runtime = setup["runtime"]
        runtime._precondition_checker = lambda expr, ctx: True

        result = runtime.execute(setup["skill_id"])
        assert result.status == ExecutionStatus.SUCCESS

    def test_precondition_failure(self, setup: dict) -> None:
        """Test execution fails when preconditions not met."""
        runtime = setup["runtime"]
        runtime._precondition_checker = lambda expr, ctx: False

        result = runtime.execute(setup["skill_id"])
        assert result.status == ExecutionStatus.FAILURE
        assert "precondition" in result.failure_reason

    def test_postcondition_check(self, setup: dict) -> None:
        """Test postcondition checking after execution."""
        runtime = setup["runtime"]
        runtime._postcondition_checker = lambda expr, ctx: True

        result = runtime.execute(setup["skill_id"])
        assert result.status == ExecutionStatus.SUCCESS
        assert all(result.postcondition_results)

    def test_postcondition_failure(self, setup: dict) -> None:
        """Test execution fails when postconditions not met."""
        runtime = setup["runtime"]
        runtime._postcondition_checker = lambda expr, ctx: False

        result = runtime.execute(setup["skill_id"])
        assert result.status == ExecutionStatus.FAILURE
        assert result.failure_reason == "postcondition_failed"

    def test_capability_check_failure(self, setup: dict) -> None:
        """Test execution fails when capabilities missing."""
        runtime = setup["runtime"]
        runtime._capability_checker = lambda cap: False

        result = runtime.execute(setup["skill_id"])
        assert result.status == ExecutionStatus.FAILURE
        assert "capability" in result.failure_reason or "missing" in result.failure_reason

    def test_capability_check_success(self, setup: dict) -> None:
        """Test execution succeeds when capabilities available."""
        runtime = setup["runtime"]
        runtime._capability_checker = lambda cap: True

        result = runtime.execute(setup["skill_id"])
        assert result.status == ExecutionStatus.SUCCESS

    def test_execution_function_failure(self, setup: dict) -> None:
        """Test execution fails when execution function returns False."""
        registry = setup["registry"]

        manifest2 = SkillManifest(
            name="failing_skill",
            required_capabilities=[],
            execute_steps=["step"],
        )
        sid2 = registry.install_skill(manifest2)
        registry.register_skill(sid2)
        registry.validate_skill(sid2)

        runtime = setup["runtime"]
        runtime.register_execution_function("failing_skill", lambda **kw: False)

        result = runtime.execute(sid2)
        assert result.status == ExecutionStatus.FAILURE
        assert result.failure_reason == "execution_failed"

    def test_recovery_success(self, setup: dict) -> None:
        """Test recovery after failure."""
        registry = setup["registry"]

        manifest2 = SkillManifest(
            name="recoverable_skill",
            required_capabilities=[],
            execute_steps=["step"],
            recovery={"default": "retry(3)"},
        )
        sid2 = registry.install_skill(manifest2)
        registry.register_skill(sid2)
        registry.validate_skill(sid2)

        runtime = setup["runtime"]
        runtime.register_execution_function("recoverable_skill", lambda **kw: False)
        runtime._recovery_handler = lambda name, failure: True

        result = runtime.execute(sid2)
        assert result.status == ExecutionStatus.RECOVERED
        assert result.recovery_attempts > 0

    def test_recovery_failure(self, setup: dict) -> None:
        """Test recovery failure leads to ABORTED/FAILURE."""
        registry = setup["registry"]

        manifest2 = SkillManifest(
            name="unrecoverable",
            required_capabilities=[],
            execute_steps=["step"],
            recovery={"default": "retry(3)"},
        )
        sid2 = registry.install_skill(manifest2)
        registry.register_skill(sid2)
        registry.validate_skill(sid2)

        runtime = setup["runtime"]
        runtime.register_execution_function("unrecoverable", lambda **kw: False)
        runtime._recovery_handler = lambda name, failure: False

        result = runtime.execute(sid2)
        assert result.status == ExecutionStatus.FAILURE
        assert result.recovery_attempts > 0

    def test_not_ready_skill(self, setup: dict) -> None:
        """Test executing a skill that is not READY."""
        registry = setup["registry"]
        manifest2 = SkillManifest(
            name="not_ready_skill",
            required_capabilities=[],
            execute_steps=["step"],
        )
        sid2 = registry.install_skill(manifest2)

        result = setup["runtime"].execute(sid2)
        assert result.status == ExecutionStatus.FAILURE
        assert "not_ready" in result.failure_reason or "READY" in result.message

    def test_nonexistent_skill(self, setup: dict) -> None:
        """Test executing a nonexistent skill."""
        result = setup["runtime"].execute("nonexistent")
        assert result.status == ExecutionStatus.FAILURE

    def test_execution_records_stats(self, setup: dict) -> None:
        """Test that execution updates lifecycle stats."""
        skill_id = setup["skill_id"]
        setup["runtime"].execute(skill_id)

        entry = setup["registry"].lifecycle.get_entry(skill_id)
        assert entry is not None
        assert entry.total_executions == 1
        assert entry.success_count == 1

    def test_register_execution_function(self, setup: dict) -> None:
        """Test registering an execution function."""
        runtime = setup["runtime"]
        runtime.register_execution_function("new_skill", lambda **kw: True)
        assert "new_skill" in runtime._execution_functions