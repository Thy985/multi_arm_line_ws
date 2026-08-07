"""Smoke test for multi_arm_runtime_api package."""

import pytest

from multi_arm_runtime_api.runtime_api_node import RuntimeApiNode, ACTION_TYPE_TO_SKILL


def test_package_imports() -> None:
    """Test that all modules can be imported."""
    assert RuntimeApiNode is not None
    assert ACTION_TYPE_TO_SKILL is not None


def test_action_type_mapping_non_empty() -> None:
    """Test action type mapping is non-empty."""
    assert len(ACTION_TYPE_TO_SKILL) > 0