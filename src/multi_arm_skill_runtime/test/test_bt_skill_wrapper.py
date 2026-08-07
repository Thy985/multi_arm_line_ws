"""Tests for BTSkillWrapper."""

import pytest

from multi_arm_skill_runtime.bt_skill_wrapper import (
    bt_xml_to_skill_manifest,
    BTSkillWrapper,
)


class TestBTSkillWrapper:
    """Test BT to Skill wrapping."""

    def test_bt_xml_to_manifest(self, tmp_path: pytest.fixture) -> None:
        """Test converting BT XML to skill manifest."""
        bt_file = tmp_path / "pick_place.xml"
        bt_file.write_text("<root></root>")

        manifest = bt_xml_to_skill_manifest(str(bt_file))

        assert manifest.name == "pick_place"
        assert manifest.version == "1.0.0"
        assert "manipulation" in manifest.required_capabilities
        assert len(manifest.execute_steps) == 1

    def test_bt_xml_with_custom_name(self, tmp_path: pytest.fixture) -> None:
        """Test BT conversion with custom skill name."""
        bt_file = tmp_path / "test.xml"
        bt_file.write_text("<root></root>")

        manifest = bt_xml_to_skill_manifest(
            str(bt_file),
            skill_name="custom_skill",
        )

        assert manifest.name == "custom_skill"

    def test_bt_wrapper_execute(self, tmp_path: pytest.fixture) -> None:
        """Test BT wrapper execution."""
        bt_file = tmp_path / "test.xml"
        bt_file.write_text("<root></root>")

        wrapper = BTSkillWrapper(str(bt_file))
        result = wrapper.execute()

        assert result is True

    def test_bt_wrapper_manifest(self, tmp_path: pytest.fixture) -> None:
        """Test BT wrapper manifest property."""
        bt_file = tmp_path / "pick_place.xml"
        bt_file.write_text("<root></root>")

        wrapper = BTSkillWrapper(str(bt_file))
        manifest = wrapper.manifest

        assert manifest.name == "pick_place"
        assert "bt_xml_path" in manifest.raw

    def test_bt_wrapper_with_capabilities(self, tmp_path: pytest.fixture) -> None:
        """Test BT wrapper with custom capabilities."""
        bt_file = tmp_path / "test.xml"
        bt_file.write_text("<root></root>")

        manifest = bt_xml_to_skill_manifest(
            str(bt_file),
            required_capabilities=["manipulation", "vision", "gripper"],
        )

        assert len(manifest.required_capabilities) == 3