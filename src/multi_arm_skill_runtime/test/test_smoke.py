"""Smoke test for multi_arm_skill_runtime package."""

import pytest

from multi_arm_skill_runtime.skill_manifest import SkillManifest
from multi_arm_skill_runtime.skill_lifecycle import SkillLifecycle, SkillLifecycleState
from multi_arm_skill_runtime.skill_registry import SkillRegistry
from multi_arm_skill_runtime.skill_runtime import SkillRuntime, ExecutionStatus
from multi_arm_skill_runtime.skill_composer import SkillComposer
from multi_arm_skill_runtime.bt_skill_wrapper import bt_xml_to_skill_manifest


def test_package_imports() -> None:
    """Test that all modules can be imported."""
    assert SkillManifest is not None
    assert SkillLifecycle is not None
    assert SkillRegistry is not None
    assert SkillRuntime is not None
    assert SkillComposer is not None


def test_basic_skill_lifecycle() -> None:
    """Test basic skill lifecycle flow."""
    registry = SkillRegistry()
    manifest = SkillManifest(
        name="test_skill",
        version="1.0.0",
        required_capabilities=["manipulation"],
        execute_steps=["step1"],
    )

    skill_id = registry.install_skill(manifest)
    assert registry.register_skill(skill_id)
    assert registry.validate_skill(skill_id)

    runtime = SkillRuntime(
        registry,
        execution_functions={"test_skill": lambda **kw: True},
    )

    result = runtime.execute(skill_id)
    assert result.status == ExecutionStatus.SUCCESS