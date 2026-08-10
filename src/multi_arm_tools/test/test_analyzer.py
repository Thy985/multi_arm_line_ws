"""Tests for episode analyzer module."""

from unittest.mock import MagicMock

from multi_arm_tools.analyzer import EpisodeAnalyzer


def test_analyzer_import():
    """Test EpisodeAnalyzer can be imported."""
    assert EpisodeAnalyzer is not None


def test_analyze_success(capsys):
    """Test analyzing a successful episode."""
    analyzer = EpisodeAnalyzer(MagicMock())
    record = {
        "episode_id": "ep_001",
        "task_type": "pick_place",
        "skill_name": "pick_object",
        "result": "success",
        "duration": 7.44,
        "execution": {
            "steps": [
                {"name": "skill_select", "success": True, "duration": 0.1},
                {"name": "execute_grasp", "success": True, "duration": 2.3},
                {"name": "execute_place", "success": True, "duration": 2.1},
            ]
        },
        "initial_world": {"objects": {}},
        "final_world": {"objects": {}},
        "recovery": {"count": 0, "attempts": []},
    }
    analyzer._render_analysis(record)
    captured = capsys.readouterr()
    assert "ep_001" in captured.out
    assert "pick_place" in captured.out
    assert "No failure" in captured.out or "succeeded" in captured.out


def test_analyze_failure(capsys):
    """Test analyzing a failed episode."""
    analyzer = EpisodeAnalyzer(MagicMock())
    record = {
        "episode_id": "ep_002",
        "task_type": "pick_place",
        "skill_name": "pick_object",
        "result": "failure",
        "duration": 5.32,
        "execution": {
            "steps": [
                {"name": "skill_select", "success": True, "duration": 0.1},
                {"name": "execute_grasp", "success": False, "duration": 2.3,
                 "details": {"reason": "force_insufficient", "force": 2.1}},
            ]
        },
        "initial_world": {"objects": {"red_cube": {"position": [0.4, 0.1, 0.05], "grasp_state": "FREE"}}},
        "final_world": {"objects": {"red_cube": {"position": [0.4, 0.1, 0.05], "grasp_state": "FREE"}}},
        "recovery": {"count": 1, "attempts": [
            {"failure_type": "grasp_failed", "strategy": "retry", "success": False}
        ]},
    }
    analyzer._render_analysis(record)
    captured = capsys.readouterr()
    assert "ep_002" in captured.out
    assert "Failure Point" in captured.out
    assert "execute_grasp" in captured.out
    assert "force_insufficient" in captured.out


def test_analyze_world_change(capsys):
    """Test world state change analysis."""
    analyzer = EpisodeAnalyzer(MagicMock())
    record = {
        "episode_id": "ep_003",
        "task_type": "pick_place",
        "result": "success",
        "duration": 7.0,
        "execution": {"steps": []},
        "initial_world": {"objects": {
            "red_cube": {"position": [0.5, 0.1, 0.05], "grasp_state": "FREE"}
        }},
        "final_world": {"objects": {
            "red_cube": {"position": [0.3, -0.2, 0.1], "grasp_state": "PLACED"}
        }},
        "recovery": {"count": 0, "attempts": []},
    }
    analyzer._render_analysis(record)
    captured = capsys.readouterr()
    assert "World State Changes" in captured.out
    assert "FREE" in captured.out
    assert "PLACED" in captured.out


def test_analyze_suggestions(capsys):
    """Test improvement suggestions."""
    analyzer = EpisodeAnalyzer(MagicMock())
    record = {
        "episode_id": "ep_004",
        "task_type": "pick_place",
        "result": "failure",
        "duration": 20.0,
        "execution": {"steps": [
            {"name": "execute_grasp", "success": False, "duration": 2.0}
        ]},
        "initial_world": {"objects": {}},
        "final_world": {"objects": {}},
        "recovery": {"count": 3, "attempts": [
            {"failure_type": "grasp_failed", "strategy": "retry", "success": False},
            {"failure_type": "grasp_failed", "strategy": "retry", "success": False},
            {"failure_type": "grasp_failed", "strategy": "retry", "success": False},
        ]},
    }
    analyzer._render_analysis(record)
    captured = capsys.readouterr()
    assert "Suggested" in captured.out or "improvement" in captured.out.lower()
    assert "recovery" in captured.out.lower() or "grasp" in captured.out.lower()


def test_find_failure_step():
    """Test finding the failure step."""
    analyzer = EpisodeAnalyzer(MagicMock())
    steps = [
        {"name": "step1", "success": True},
        {"name": "step2", "success": False},
        {"name": "step3", "success": True},
    ]
    failure = analyzer._find_failure_step(steps)
    assert failure is not None
    assert failure["name"] == "step2"


def test_find_failure_step_none():
    """Test no failure step found."""
    analyzer = EpisodeAnalyzer(MagicMock())
    steps = [
        {"name": "step1", "success": True},
        {"name": "step2", "success": True},
    ]
    failure = analyzer._find_failure_step(steps)
    assert failure is None