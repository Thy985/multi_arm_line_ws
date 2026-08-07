"""Tests for SkillManifest."""

import pytest

from multi_arm_skill_runtime.skill_manifest import SkillManifest, SkillCost


class TestSkillManifest:
    """Test SkillManifest parsing and validation."""

    def test_from_dict_basic(self) -> None:
        """Test parsing from a basic dict."""
        data = {
            "skill": {
                "name": "pick_object",
                "version": "1.0.0",
                "description": "Pick up an object",
                "required_capabilities": {
                    "manipulation": True,
                    "gripper": True,
                },
                "input": {"object_id": "string"},
                "output": {"object_state": "string"},
                "cost": {"time": 5.0, "risk": 0.1, "success_rate": 0.95},
                "preconditions": ["object exists"],
                "execute": ["perceive", "grasp"],
                "postconditions": ["object attached"],
                "recovery": {"grasp_failed": "retry(3)"},
            }
        }
        manifest = SkillManifest.from_dict(data)

        assert manifest.name == "pick_object"
        assert manifest.version == "1.0.0"
        assert manifest.description == "Pick up an object"
        assert "manipulation" in manifest.required_capabilities
        assert "gripper" in manifest.required_capabilities
        assert manifest.cost.time == 5.0
        assert manifest.cost.risk == 0.1
        assert manifest.cost.success_rate == 0.95
        assert len(manifest.preconditions) == 1
        assert len(manifest.execute_steps) == 2
        assert len(manifest.postconditions) == 1

    def test_from_dict_required_capabilities_as_list(self) -> None:
        """Test parsing when required_capabilities is a list."""
        data = {
            "skill": {
                "name": "test_skill",
                "required_capabilities": ["manipulation", "vision"],
                "execute": ["step1"],
            }
        }
        manifest = SkillManifest.from_dict(data)
        assert "manipulation" in manifest.required_capabilities
        assert "vision" in manifest.required_capabilities

    def test_from_dict_missing_name_raises(self) -> None:
        """Test that missing name raises ValueError."""
        data = {"skill": {"version": "1.0.0"}}
        with pytest.raises(ValueError, match="name"):
            SkillManifest.from_dict(data)

    def test_from_dict_defaults(self) -> None:
        """Test default values when fields are missing."""
        data = {"skill": {"name": "minimal", "execute": ["step"]}}
        manifest = SkillManifest.from_dict(data)

        assert manifest.name == "minimal"
        assert manifest.version == "1.0.0"
        assert manifest.cost.time == 5.0
        assert manifest.cost.risk == 0.1
        assert manifest.cost.success_rate == 0.95

    def test_from_yaml(self, tmp_path: pytest.fixture) -> None:
        """Test parsing from a YAML file."""
        import yaml

        yaml_content = """
skill:
  name: test_skill
  version: "2.0.0"
  description: "Test skill"
  required_capabilities:
    manipulation: true
  cost:
    time: 3.0
    risk: 0.05
    success_rate: 0.98
  execute:
    - step1
    - step2
"""
        yaml_file = tmp_path / "skill.yaml"
        yaml_file.write_text(yaml_content)

        manifest = SkillManifest.from_yaml(str(yaml_file))
        assert manifest.name == "test_skill"
        assert manifest.version == "2.0.0"
        assert manifest.cost.time == 3.0

    def test_from_yaml_not_found(self) -> None:
        """Test that missing file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            SkillManifest.from_yaml("/nonexistent/skill.yaml")

    def test_validate_valid(self) -> None:
        """Test validation of a valid manifest."""
        manifest = SkillManifest(
            name="test",
            version="1.0.0",
            execute_steps=["step1"],
        )
        errors = manifest.validate()
        assert len(errors) == 0

    def test_validate_missing_name(self) -> None:
        """Test validation catches missing name."""
        manifest = SkillManifest(name="", version="1.0.0", execute_steps=["step"])
        errors = manifest.validate()
        assert any("name" in e for e in errors)

    def test_validate_missing_execute(self) -> None:
        """Test validation catches missing execute steps."""
        manifest = SkillManifest(name="test", version="1.0.0", execute_steps=[])
        errors = manifest.validate()
        assert any("execute" in e for e in errors)

    def test_to_dict(self) -> None:
        """Test serialization to dict."""
        manifest = SkillManifest(
            name="test",
            version="1.0.0",
            description="Test",
            required_capabilities=["manipulation"],
            input_params={"object_id": "string"},
            preconditions=["pre"],
            postconditions=["post"],
            execute_steps=["step"],
            cost=SkillCost(time=3.0, risk=0.05, success_rate=0.98),
        )
        d = manifest.to_dict()

        assert d["name"] == "test"
        assert d["version"] == "1.0.0"
        assert d["cost_time"] == 3.0
        assert d["cost_risk"] == 0.05
        assert d["success_rate"] == 0.98
        assert "manipulation" in d["required_capabilities"]

    def test_skill_cost_to_dict(self) -> None:
        """Test SkillCost serialization."""
        cost = SkillCost(time=10.0, risk=0.2, success_rate=0.8)
        d = cost.to_dict()
        assert d["time"] == 10.0
        assert d["risk"] == 0.2
        assert d["success_rate"] == 0.8