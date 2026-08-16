"""Tests for episode viewer."""

import json
from unittest.mock import MagicMock

from multi_arm_tools.episode_viewer import EpisodeViewer


def test_episode_viewer_import():
    """Test EpisodeViewer can be imported."""
    assert EpisodeViewer is not None


def test_episode_summary_success(capsys):
    """Test printing a successful episode summary."""
    viewer = EpisodeViewer(MagicMock())
    record = {
        "episode_id": "ep_00001",
        "task_type": "pick_place",
        "result": "success",
        "duration": 7.24,
        "recovery": {"count": 0},
    }
    viewer._print_episode_summary(record)
    captured = capsys.readouterr()
    assert "ep_00001" in captured.out
    assert "[OK]" in captured.out
    assert "pick_place" in captured.out


def test_episode_summary_failure(capsys):
    """Test printing a failed episode summary."""
    viewer = EpisodeViewer(MagicMock())
    record = {
        "episode_id": "ep_00002",
        "task_type": "pick_place",
        "result": "failure",
        "duration": 7.18,
        "recovery": {
            "count": 2,
            "attempts": [
                {"failure_type": "grasp_failed", "strategy": "retry", "success": False},
            ],
        },
    }
    viewer._print_episode_summary(record)
    captured = capsys.readouterr()
    assert "ep_00002" in captured.out
    assert "[FAIL]" in captured.out
    assert "grasp_failed" in captured.out


def test_episode_detail_render(capsys):
    """Test rendering full episode detail."""
    viewer = EpisodeViewer(MagicMock())
    record = {
        "episode_id": "ep_00003",
        "task_type": "pick_place",
        "skill_name": "pick_object",
        "robot_id": "left_arm",
        "result": "success",
        "duration": 7.44,
        "recovery": {"count": 0, "attempts": []},
        "execution": {
            "steps": [
                {"name": "skill_select", "success": True, "duration": 0.1},
                {"name": "execute_grasp", "success": True, "duration": 2.3},
                {"name": "execute_place", "success": True, "duration": 2.1},
            ]
        },
        "initial_world": {
            "objects": {
                "red_cube": {"position": [0.42, 0.15, 0.05], "grasp_state": "FREE"}
            }
        },
        "final_world": {
            "objects": {
                "red_cube": {"position": [0.30, -0.2, 0.1], "grasp_state": "PLACED"}
            }
        },
    }
    viewer._render_episode_detail(record)
    captured = capsys.readouterr()
    assert "ep_00003" in captured.out
    assert "pick_place" in captured.out
    assert "pick_object" in captured.out
    assert "left_arm" in captured.out
    assert "skill_select" in captured.out
    assert "execute_grasp" in captured.out
    assert "red_cube" in captured.out
    assert "FREE" in captured.out
    assert "PLACED" in captured.out


def test_world_snapshot_print(capsys):
    """Test printing world snapshot."""
    viewer = EpisodeViewer(MagicMock())
    world = {
        "objects": {
            "red_cube": {"position": [0.42, 0.15, 0.05], "grasp_state": "FREE"},
            "blue_cyl": {"position": [0.30, -0.2, 0.1], "grasp_state": "ATTACHED"},
        }
    }
    viewer._print_world_snapshot(world)
    captured = capsys.readouterr()
    assert "red_cube" in captured.out
    assert "blue_cyl" in captured.out
    assert "FREE" in captured.out
    assert "ATTACHED" in captured.out


def test_world_snapshot_empty(capsys):
    """Test printing empty world snapshot."""
    viewer = EpisodeViewer(MagicMock())
    viewer._print_world_snapshot({})
    captured = capsys.readouterr()
    assert "empty" in captured.out