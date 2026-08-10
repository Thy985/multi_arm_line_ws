"""Tests for M7.0.3 Capability Graph — dependency, composition, conflict, propagation."""

import pytest

from multi_arm_robot_description.capability_registry import (
    Capability,
    CapabilityRegistry,
)


@pytest.fixture
def registry() -> CapabilityRegistry:
    """Create registry from actual capability.yaml."""
    from ament_index_python.packages import get_package_share_directory
    import os
    yaml_path = os.path.join(
        get_package_share_directory("multi_arm_robot_description"),
        "config", "capability.yaml",
    )
    return CapabilityRegistry(yaml_path)


class TestCapabilityGraphFields:
    """Test that graph fields exist and are populated."""

    def test_capability_has_requires_field(self, registry: CapabilityRegistry):
        cap = registry.get_capability("manipulation")
        assert cap is not None
        assert "arm_reachable" in cap.requires

    def test_capability_has_conflicts_with_field(self, registry: CapabilityRegistry):
        cap = registry.get_capability("force_control")
        assert cap is not None
        assert "manipulation" in cap.conflicts_with

    def test_skills_require_manipulation_and_gripper(self, registry: CapabilityRegistry):
        cap = registry.get_capability("skills")
        assert cap is not None
        assert "manipulation" in cap.requires
        assert "gripper" in cap.requires

    def test_context_capability_has_requires(self, registry: CapabilityRegistry):
        cap = registry.get_capability("can_grasp")
        assert cap is not None
        assert "gripper" in cap.requires

    def test_no_requires_returns_empty(self, registry: CapabilityRegistry):
        cap = registry.get_capability("gripper")
        assert cap is not None
        assert cap.requires == []


class TestDependencyQueries:
    """Test dependency query methods."""

    def test_get_dependencies(self, registry: CapabilityRegistry):
        deps = registry.get_dependencies("manipulation")
        assert "arm_reachable" in deps

    def test_get_dependencies_nonexistent(self, registry: CapabilityRegistry):
        assert registry.get_dependencies("nonexistent") == []

    def test_get_dependents(self, registry: CapabilityRegistry):
        dependents = registry.get_dependents("gripper")
        assert "skills" in dependents
        assert "can_grasp" in dependents

    def test_get_dependents_no_dependents(self, registry: CapabilityRegistry):
        dependents = registry.get_dependents("mobile")
        assert dependents == []

    def test_is_satisfied_when_deps_available(self, registry: CapabilityRegistry):
        registry.update_dynamic("arm_reachable", True, available=True)
        assert registry.is_satisfied("manipulation")

    def test_not_satisfied_when_dep_unavailable(self, registry: CapabilityRegistry):
        registry.update_dynamic("arm_reachable", False, available=False, reason="test")
        assert not registry.is_satisfied("manipulation")

    def test_is_satisfied_no_deps(self, registry: CapabilityRegistry):
        assert registry.is_satisfied("gripper")

    def test_is_satisfied_nonexistent(self, registry: CapabilityRegistry):
        assert registry.is_satisfied("nonexistent")


class TestConflictQueries:
    """Test conflict query methods."""

    def test_get_conflicts(self, registry: CapabilityRegistry):
        conflicts = registry.get_conflicts("force_control")
        assert "manipulation" in conflicts

    def test_get_conflicts_none(self, registry: CapabilityRegistry):
        assert registry.get_conflicts("gripper") == []

    def test_get_conflicts_nonexistent(self, registry: CapabilityRegistry):
        assert registry.get_conflicts("nonexistent") == []


class TestFailurePropagation:
    """Test dependency failure propagation."""

    def test_propagate_failure_marks_dependents(self, registry: CapabilityRegistry):
        registry.update_dynamic("gripper", {"available": False}, available=False, reason="test failure")
        affected = registry.propagate_failure("gripper", "test failure")
        assert "skills" in affected
        assert "can_grasp" in affected

    def test_propagate_failure_no_dependents(self, registry: CapabilityRegistry):
        affected = registry.propagate_failure("mobile", "test")
        assert affected == []

    def test_propagate_failure_cascades(self, registry: CapabilityRegistry):
        registry.update_dynamic("manipulation", {"available": False}, available=False, reason="arm broken")
        affected = registry.propagate_failure("manipulation", "arm broken")
        assert "skills" in affected
        assert "can_reach" in affected

    def test_propagate_failure_idempotent(self, registry: CapabilityRegistry):
        registry.update_dynamic("gripper", {"available": False}, available=False, reason="test")
        first = registry.propagate_failure("gripper", "test")
        second = registry.propagate_failure("gripper", "test")
        assert len(first) > 0
        assert second == []


class TestMessageFields:
    """Test that CapabilityInfo message has graph fields."""

    def test_capability_info_has_graph_fields(self):
        from multi_arm_interfaces.msg import CapabilityInfo
        msg = CapabilityInfo()
        assert hasattr(msg, "requires")
        assert hasattr(msg, "composed_of")
        assert hasattr(msg, "conflicts_with")

    def test_to_info_dict_includes_graph_fields(self, registry: CapabilityRegistry):
        cap = registry.get_capability("manipulation")
        assert cap is not None
        info = cap.to_info_dict()
        assert "requires" in info
        assert "composed_of" in info
        assert "conflicts_with" in info
        assert "arm_reachable" in info["requires"]

    def test_get_all_includes_graph_fields(self, registry: CapabilityRegistry):
        infos = registry.get_all_capabilities(include_dynamic=True)
        manipulation_info = next(i for i in infos if i["name"] == "manipulation")
        assert "arm_reachable" in manipulation_info["requires"]


class TestBackwardCompatibility:
    """Test that existing fields still work."""

    def test_capability_info_backward_compat(self):
        from multi_arm_interfaces.msg import CapabilityInfo
        msg = CapabilityInfo()
        assert hasattr(msg, "name")
        assert hasattr(msg, "category")
        assert hasattr(msg, "available")
        assert hasattr(msg, "value")
        assert hasattr(msg, "reason")

    def test_get_capability_still_works(self, registry: CapabilityRegistry):
        cap = registry.get_capability("manipulation")
        assert cap is not None
        assert cap.name == "manipulation"
        assert cap.available is True

    def test_get_all_capabilities_still_works(self, registry: CapabilityRegistry):
        infos = registry.get_all_capabilities(include_dynamic=True)
        names = [i["name"] for i in infos]
        assert "manipulation" in names
        assert "gripper" in names