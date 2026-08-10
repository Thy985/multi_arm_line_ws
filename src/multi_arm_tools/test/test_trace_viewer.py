"""Tests for trace viewer rendering."""

import json
from unittest.mock import MagicMock

from multi_arm_tools.trace_viewer import TraceViewer


def test_trace_viewer_import():
    """Test TraceViewer can be imported."""
    assert TraceViewer is not None


def test_trace_viewer_event_icons():
    """Test event icon mapping."""
    assert "task_received" in TraceViewer.EVENT_ICONS
    assert "success" in TraceViewer.EVENT_ICONS
    assert "failure" in TraceViewer.EVENT_ICONS
    assert TraceViewer.EVENT_ICONS["success"] == "[OK]"
    assert TraceViewer.EVENT_ICONS["failure"] == "[FAIL]"


def test_trace_viewer_render_from_record_success(capsys):
    """Test rendering a successful trace record."""
    viewer = TraceViewer(MagicMock())
    record = {
        "episode_id": "ep_001",
        "task_type": "pick_place",
        "skill_name": "pick_object",
        "result": "success",
        "duration": 7.44,
        "recovery": {"count": 0},
        "execution": {
            "steps": [
                {"name": "skill_select", "success": True, "duration": 0.1},
                {"name": "execute_grasp", "success": True, "duration": 2.3},
                {"name": "execute_place", "success": True, "duration": 2.1},
            ]
        },
    }
    viewer._render_trace_from_record(record)
    captured = capsys.readouterr()
    assert "ep_001" in captured.out
    assert "[OK]" in captured.out
    assert "pick_place" in captured.out
    assert "skill_select" in captured.out


def test_trace_viewer_render_from_record_failure(capsys):
    """Test rendering a failed trace record."""
    viewer = TraceViewer(MagicMock())
    record = {
        "episode_id": "ep_002",
        "task_type": "pick_place",
        "skill_name": "pick_object",
        "result": "failure",
        "duration": 5.32,
        "recovery": {
            "count": 2,
            "attempts": [
                {"failure_type": "grasp_failed", "strategy": "retry", "success": False},
                {"failure_type": "grasp_failed", "strategy": "change_approach", "success": False},
            ],
        },
        "execution": {
            "steps": [
                {"name": "skill_select", "success": True, "duration": 0.1},
                {"name": "execute_grasp", "success": False, "duration": 2.3},
            ]
        },
    }
    viewer._render_trace_from_record(record)
    captured = capsys.readouterr()
    assert "ep_002" in captured.out
    assert "[FAIL]" in captured.out
    assert "grasp_failed" in captured.out
    assert "retry" in captured.out


def test_trace_viewer_render_with_details(capsys):
    """Test rendering trace with step details."""
    viewer = TraceViewer(MagicMock())
    record = {
        "episode_id": "ep_003",
        "task_type": "move",
        "skill_name": "move_object",
        "result": "success",
        "duration": 3.5,
        "recovery": {"count": 0},
        "execution": {
            "steps": [
                {
                    "name": "plan_trajectory",
                    "success": True,
                    "duration": 0.08,
                    "details": {"planner": "OMPL", "waypoints": 15},
                },
            ]
        },
    }
    viewer._render_trace_from_record(record)
    captured = capsys.readouterr()
    assert "plan_trajectory" in captured.out
    assert "planner" in captured.out
    assert "OMPL" in captured.out