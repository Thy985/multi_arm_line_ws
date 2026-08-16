"""Tests for task manager module."""

from unittest.mock import MagicMock

from multi_arm_tools.task_manager import (
    AVAILABLE_POSITIONS,
    TASK_TEMPLATES,
    TaskManager,
)


def test_task_manager_import():
    """Test TaskManager can be imported."""
    assert TaskManager is not None


def test_task_templates_defined():
    """Test task templates are defined."""
    assert "pick_place" in TASK_TEMPLATES
    assert "move" in TASK_TEMPLATES
    assert "grasp" in TASK_TEMPLATES
    assert len(TASK_TEMPLATES) >= 7


def test_available_positions_defined():
    """Test available positions are defined."""
    assert "home" in AVAILABLE_POSITIONS
    assert "ready" in AVAILABLE_POSITIONS
    assert len(AVAILABLE_POSITIONS) >= 7


def test_list_tasks(capsys):
    """Test listing tasks."""
    tm = TaskManager(MagicMock())
    tm.list_tasks()
    captured = capsys.readouterr()
    assert "pick_place" in captured.out
    assert "move" in captured.out
    assert "inputs" in captured.out
    assert "skills" in captured.out
    assert "example" in captured.out


def test_list_positions(capsys):
    """Test listing positions."""
    tm = TaskManager(MagicMock())
    tm.list_positions()
    captured = capsys.readouterr()
    assert "home" in captured.out
    assert "ready" in captured.out


def test_describe_goal_pick_place():
    """Test goal description for pick_place."""
    tm = TaskManager(MagicMock())
    info = tm._describe_goal("pick_place", ["red_cube", "zone_b"], "left_arm")
    assert info["action_type"] == "pick_place"
    assert info["object_id"] == "red_cube"
    assert info["zone_name"] == "zone_b"
    assert info["arm_name"] == "left_arm"


def test_describe_goal_move():
    """Test goal description for move."""
    tm = TaskManager(MagicMock())
    info = tm._describe_goal("move", ["ready"], "")
    assert info["action_type"] == "move"
    assert info["position_name"] == "ready"
    assert info["arm_name"] == "left_arm"


def test_describe_goal_default_arm():
    """Test default arm assignment."""
    tm = TaskManager(MagicMock())
    info = tm._describe_goal("move", ["home"], "")
    assert info["arm_name"] == "left_arm"