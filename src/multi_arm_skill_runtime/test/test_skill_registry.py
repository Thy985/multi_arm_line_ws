"""Tests for SkillRegistry."""

import pytest

from multi_arm_skill_runtime.skill_manifest import SkillManifest, SkillCost
from multi_arm_skill_runtime.skill_registry import SkillRegistry
from multi_arm_skill_runtime.skill_lifecycle import SkillLifecycleState


class TestSkillRegistry:
    """Test SkillRegistry operations."""

    @pytest.fixture
    def registry(self) -> SkillRegistry:
        """Create a registry with test skills."""
        reg = SkillRegistry()

        manifest1 = SkillManifest(
            name="pick_object",
            version="1.0.0",
            required_capabilities=["manipulation", "gripper", "vision"],
            execute_steps=["perceive", "grasp"],
            cost=SkillCost(time=5.0, risk=0.1, success_rate=0.95),
        )
        manifest2 = SkillManifest(
            name="place_object",
            version="1.0.0",
            required_capabilities=["manipulation", "gripper"],
            execute_steps=["move", "release"],
            cost=SkillCost(time=4.0, risk=0.08, success_rate=0.96),
        )
        manifest3 = SkillManifest(
            name="move_object",
            version="1.0.0",
            required_capabilities=["manipulation"],
            execute_steps=["plan", "execute"],
            cost=SkillCost(time=3.0, risk=0.05, success_rate=0.98),
        )

        for m in [manifest1, manifest2, manifest3]:
            sid = reg.install_skill(m)
            reg.register_skill(sid)
            reg.validate_skill(sid)

        return reg

    def test_install_and_get(self, registry: SkillRegistry) -> None:
        """Test install and get manifest."""
        skills = registry.get_all_skills()
        assert len(skills) == 3

    def test_find_by_name(self, registry: SkillRegistry) -> None:
        """Test finding skill by name."""
        skill_id = registry.find_by_name("pick_object")
        assert skill_id is not None

        manifest = registry.get_manifest(skill_id)
        assert manifest is not None
        assert manifest.name == "pick_object"

    def test_find_by_name_not_found(self, registry: SkillRegistry) -> None:
        """Test finding nonexistent skill."""
        assert registry.find_by_name("nonexistent") is None

    def test_list_ready_skills(self, registry: SkillRegistry) -> None:
        """Test listing READY skills."""
        ready = registry.list_ready_skills()
        assert len(ready) == 3

    def test_list_ready_skills_sorted_by_cost(self, registry: SkillRegistry) -> None:
        """Test READY skills are sorted by cost (time ascending)."""
        ready = registry.list_ready_skills()
        costs = [m.cost.time for _, m in ready]
        assert costs == sorted(costs)
        assert costs[0] == 3.0

    def test_list_by_capability(self, registry: SkillRegistry) -> None:
        """Test filtering by required capabilities."""
        skills = registry.list_ready_skills(required_capabilities=["vision"])
        assert len(skills) == 1
        assert skills[0][1].name == "pick_object"

    def test_list_by_capability_multiple(self, registry: SkillRegistry) -> None:
        """Test filtering by multiple required capabilities."""
        skills = registry.list_ready_skills(
            required_capabilities=["manipulation", "gripper"],
        )
        assert len(skills) == 2
        names = {m.name for _, m in skills}
        assert "pick_object" in names
        assert "place_object" in names

    def test_list_by_state(self, registry: SkillRegistry) -> None:
        """Test filtering by lifecycle state."""
        skills = registry.list_skills(lifecycle_state="ready")
        assert len(skills) == 3

    def test_validate_with_capability_checker(self) -> None:
        """Test validation with capability checker."""
        reg = SkillRegistry()
        manifest = SkillManifest(
            name="test",
            required_capabilities=["manipulation", "nonexistent_cap"],
            execute_steps=["step"],
        )

        sid = reg.install_skill(manifest)
        reg.register_skill(sid)

        def checker(cap: str) -> bool:
            return cap == "manipulation"

        result = reg.validate_skill(sid, capability_checker=checker)
        assert result is False

        state = reg.lifecycle.get_state(sid)
        assert state == SkillLifecycleState.INVALID

    def test_validate_passes_with_checker(self) -> None:
        """Test validation passes when capabilities are available."""
        reg = SkillRegistry()
        manifest = SkillManifest(
            name="test",
            required_capabilities=["manipulation"],
            execute_steps=["step"],
        )

        sid = reg.install_skill(manifest)
        reg.register_skill(sid)

        def checker(cap: str) -> bool:
            return True

        result = reg.validate_skill(sid, capability_checker=checker)
        assert result is True
        assert reg.lifecycle.get_state(sid) == SkillLifecycleState.READY

    def test_get_status(self, registry: SkillRegistry) -> None:
        """Test getting skill status."""
        skill_id = registry.find_by_name("pick_object")
        status = registry.get_status(skill_id)

        assert status is not None
        assert status["name"] == "pick_object"
        assert status["lifecycle_state"] == "ready"
        assert status["total_executions"] == 0

    def test_remove_skill(self, registry: SkillRegistry) -> None:
        """Test removing a skill."""
        skill_id = registry.find_by_name("move_object")
        assert registry.remove_skill(skill_id)

        assert registry.get_manifest(skill_id) is None
        assert registry.find_by_name("move_object") is None

    def test_remove_nonexistent(self, registry: SkillRegistry) -> None:
        """Test removing nonexistent skill fails."""
        assert not registry.remove_skill("nonexistent")