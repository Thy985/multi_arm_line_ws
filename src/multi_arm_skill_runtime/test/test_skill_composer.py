"""Tests for SkillComposer."""

import pytest

from multi_arm_skill_runtime.skill_manifest import SkillManifest, SkillCost
from multi_arm_skill_runtime.skill_registry import SkillRegistry
from multi_arm_skill_runtime.skill_runtime import SkillRuntime
from multi_arm_skill_runtime.skill_composer import SkillComposer, CompositeResult


class TestSkillComposer:
    """Test skill composition and chaining."""

    @pytest.fixture
    def setup(self) -> dict:
        """Create composer with chained skills."""
        registry = SkillRegistry()

        for name in ["pick_object", "move_object", "place_object"]:
            manifest = SkillManifest(
                name=name,
                required_capabilities=["manipulation"],
                execute_steps=["step"],
                cost=SkillCost(time=3.0),
            )
            sid = registry.install_skill(manifest)
            registry.register_skill(sid)
            registry.validate_skill(sid)

        runtime = SkillRuntime(
            registry,
            execution_functions={
                "pick_object": lambda **kw: True,
                "move_object": lambda **kw: True,
                "place_object": lambda **kw: True,
            },
        )
        composer = SkillComposer(runtime)

        return {
            "registry": registry,
            "runtime": runtime,
            "composer": composer,
        }

    def test_compose_and_execute(self, setup: dict) -> None:
        """Test composing and executing a skill chain."""
        registry = setup["registry"]
        composer = setup["composer"]

        pick_id = registry.find_by_name("pick_object")
        move_id = registry.find_by_name("move_object")
        place_id = registry.find_by_name("place_object")

        result = (
            composer.compose("transport_object")
            .add_step(pick_id)
            .add_step(move_id)
            .add_step(place_id)
            .execute()
        )

        assert result.success
        assert result.completed_steps == 3
        assert len(result.step_results) == 3

    def test_compose_with_failure(self, setup: dict) -> None:
        """Test chain stops on failure."""
        registry = setup["registry"]
        runtime = setup["runtime"]

        runtime.register_execution_function("move_object", lambda **kw: False)

        composer = setup["composer"]
        pick_id = registry.find_by_name("pick_object")
        move_id = registry.find_by_name("move_object")
        place_id = registry.find_by_name("place_object")

        result = (
            composer.compose("transport")
            .add_step(pick_id)
            .add_step(move_id)
            .add_step(place_id)
            .execute()
        )

        assert not result.success
        assert result.completed_steps == 1

    def test_compose_with_optional_step(self, setup: dict) -> None:
        """Test optional step failure doesn't stop chain."""
        registry = setup["registry"]
        runtime = setup["runtime"]

        runtime.register_execution_function("move_object", lambda **kw: False)

        composer = setup["composer"]
        pick_id = registry.find_by_name("pick_object")
        move_id = registry.find_by_name("move_object")
        place_id = registry.find_by_name("place_object")

        result = (
            composer.compose("transport")
            .add_step(pick_id)
            .add_step(move_id, optional=True)
            .add_step(place_id)
            .execute()
        )

        assert result.completed_steps == 2

    def test_build_composite_manifest(self, setup: dict) -> None:
        """Test building a composite manifest."""
        registry = setup["registry"]
        composer = setup["composer"]

        pick_id = registry.find_by_name("pick_object")
        move_id = registry.find_by_name("move_object")

        builder = (
            composer.compose("transport")
            .add_step(pick_id)
            .add_step(move_id)
            .require_capability("manipulation")
        )

        manifest = builder.build_manifest()
        assert manifest.name == "transport"
        assert "manipulation" in manifest.required_capabilities
        assert len(manifest.execute_steps) == 2

    def test_execute_chain_directly(self, setup: dict) -> None:
        """Test execute_chain method directly."""
        registry = setup["registry"]
        composer = setup["composer"]

        pick_id = registry.find_by_name("pick_object")
        place_id = registry.find_by_name("place_object")

        result = composer.execute_chain([
            {"skill_id": pick_id, "parameters": {}},
            {"skill_id": place_id, "parameters": {}},
        ])

        assert result.success
        assert result.completed_steps == 2

    def test_empty_chain(self, setup: dict) -> None:
        """Test executing an empty chain."""
        result = setup["composer"].execute_chain([])
        assert result.success
        assert result.completed_steps == 0