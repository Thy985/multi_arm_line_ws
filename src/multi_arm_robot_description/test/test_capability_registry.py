"""Tests for CapabilityRegistry three-layer model."""

import json
from pathlib import Path

import pytest
import yaml

from multi_arm_robot_description.capability_registry import (
    Capability,
    CapabilityCategory,
    CapabilityRegistry,
)


@pytest.fixture
def capability_yaml(tmp_path: Path) -> Path:
    """Create a test capability.yaml file."""
    data = {
        "capabilities": {
            "manipulation": {
                "type": "joint_position",
                "dof": 6,
                "payload_kg": 5.0,
                "available": True,
            },
            "force_control": {
                "available": False,
                "reason": "UR5e simulation has no force control",
            },
            "gripper": {
                "type": "parallel_jaw",
                "max_opening_mm": 85,
                "available": True,
            },
        },
        "dynamic_capabilities": {
            "payload_remaining": {"compute": "max - load", "default": 5.0},
            "gripper_temperature": {
                "compute": "sensor",
                "default": 25.0,
                "threshold_overheat": 80.0,
            },
        },
        "context_capabilities": {
            "can_reach": {"compute": "workspace_check", "depends_on": "world_model"},
        },
    }
    path = tmp_path / "capability.yaml"
    with open(path, "w") as f:
        yaml.dump(data, f)
    return path


class TestCapability:
    """Tests for Capability dataclass."""

    def test_merge_static_only(self) -> None:
        cap = Capability(name="test", static_value={"available": True, "dof": 6})
        cap.merge()
        assert cap.available is True
        assert cap.reason == ""

    def test_merge_static_unavailable(self) -> None:
        cap = Capability(
            name="test",
            static_value={"available": False, "reason": "not implemented"},
        )
        cap.merge()
        assert cap.available is False
        assert "not implemented" in cap.reason

    def test_merge_dynamic_overrides(self) -> None:
        cap = Capability(
            name="gripper",
            static_value={"available": True, "max_opening_mm": 85},
            dynamic_value={"available": False, "reason": "overheated"},
        )
        cap.merge()
        assert cap.available is False
        assert "overheated" in cap.reason

    def test_merge_context_restricts(self) -> None:
        cap = Capability(
            name="can_reach",
            static_value={"available": True},
            context_value={"available": False, "reason": "out of workspace"},
        )
        cap.merge()
        assert cap.available is False
        assert "out of workspace" in cap.reason

    def test_to_info_dict(self) -> None:
        cap = Capability(name="manipulation", available=True, value={"dof": 6})
        info = cap.to_info_dict("static")
        assert info["name"] == "manipulation"
        assert info["category"] == "static"
        assert info["available"] is True
        assert "dof" in info["value"]


class TestCapabilityRegistry:
    """Tests for CapabilityRegistry."""

    def test_load_static_capabilities(self, capability_yaml: Path) -> None:
        registry = CapabilityRegistry(capability_yaml)
        cap = registry.get_capability("manipulation")
        assert cap is not None
        assert cap.available is True

    def test_get_nonexistent_capability(self, capability_yaml: Path) -> None:
        registry = CapabilityRegistry(capability_yaml)
        cap = registry.get_capability("nonexistent")
        assert cap is None

    def test_static_unavailable(self, capability_yaml: Path) -> None:
        registry = CapabilityRegistry(capability_yaml)
        cap = registry.get_capability("force_control")
        assert cap is not None
        assert cap.available is False

    def test_update_dynamic(self, capability_yaml: Path) -> None:
        registry = CapabilityRegistry(capability_yaml)
        registry.update_dynamic("payload_remaining", 3.5)
        cap = registry.get_capability("payload_remaining")
        assert cap is not None
        assert cap.value == 3.5

    def test_update_context(self, capability_yaml: Path) -> None:
        registry = CapabilityRegistry(capability_yaml)
        registry.update_context("can_reach", True, available=True)
        cap = registry.get_capability("can_reach")
        assert cap is not None
        assert cap.available is True

    def test_check_overheated(self, capability_yaml: Path) -> None:
        registry = CapabilityRegistry(capability_yaml)
        overheated = registry.check_overheated(90.0, threshold=80.0)
        assert overheated is True
        cap = registry.get_capability("gripper")
        assert cap is not None
        assert cap.available is False

    def test_check_not_overheated(self, capability_yaml: Path) -> None:
        registry = CapabilityRegistry(capability_yaml)
        overheated = registry.check_overheated(50.0, threshold=80.0)
        assert overheated is False

    def test_check_payload(self, capability_yaml: Path) -> None:
        registry = CapabilityRegistry(capability_yaml)
        remaining = registry.check_payload(2.0, max_payload=5.0)
        assert remaining == 3.0

    def test_check_payload_overload(self, capability_yaml: Path) -> None:
        registry = CapabilityRegistry(capability_yaml)
        remaining = registry.check_payload(7.0, max_payload=5.0)
        assert remaining == 0.0

    def test_get_all_capabilities(self, capability_yaml: Path) -> None:
        registry = CapabilityRegistry(capability_yaml)
        infos = registry.get_all_capabilities()
        names = [info["name"] for info in infos]
        assert "manipulation" in names
        assert "gripper" in names
        assert "force_control" in names

    def test_get_all_without_dynamic(self, capability_yaml: Path) -> None:
        registry = CapabilityRegistry(capability_yaml)
        infos = registry.get_all_capabilities(include_dynamic=False)
        names = [info["name"] for info in infos]
        assert "manipulation" in names
        assert "can_reach" not in names

    def test_file_not_found(self) -> None:
        with pytest.raises(FileNotFoundError):
            CapabilityRegistry("/nonexistent/path/capability.yaml")

    def test_empty_registry(self) -> None:
        registry = CapabilityRegistry()
        cap = registry.get_capability("anything")
        assert cap is None
        infos = registry.get_all_capabilities()
        assert infos == []