"""Tests for benchmark runner."""

import json
import os
import tempfile
from unittest.mock import MagicMock, patch

from multi_arm_tools.benchmark_runner import BenchmarkRunner


def test_benchmark_runner_import():
    """Test BenchmarkRunner can be imported."""
    assert BenchmarkRunner is not None


def test_benchmark_print_statistics(capsys):
    """Test printing benchmark statistics."""
    runner = BenchmarkRunner(MagicMock())
    runner._print_statistics(
        total=100,
        success_count=96,
        failure_count=4,
        durations=[7.2, 5.1, 12.3, 6.8, 7.5],
        failure_reasons={"grasp_failed": [7.5, 7.2, 7.8], "planning_failed": [5.3]},
    )
    captured = capsys.readouterr()
    assert "Total:" in captured.out
    assert "100" in captured.out
    assert "96" in captured.out
    assert "4" in captured.out
    assert "grasp_failed" in captured.out
    assert "planning_failed" in captured.out


def test_benchmark_save_results():
    """Test saving benchmark results to JSON."""
    runner = BenchmarkRunner(MagicMock())
    results = [
        {"index": 0, "success": True, "duration": 7.2},
        {"index": 1, "success": False, "duration": 5.3, "reason": "planning_failed"},
    ]
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        tmp_path = f.name

    try:
        runner._save_results(tmp_path, "pick_place", 2, results)
        with open(tmp_path) as f:
            data = json.load(f)
        assert data["task_type"] == "pick_place"
        assert data["count"] == 2
        assert len(data["results"]) == 2
        assert data["summary"]["success_count"] == 1
        assert data["summary"]["failure_count"] == 1
    finally:
        os.unlink(tmp_path)


def test_benchmark_progress_bar(capsys):
    """Test progress bar rendering."""
    runner = BenchmarkRunner(MagicMock())
    runner._print_progress(50, 100)
    captured = capsys.readouterr()
    assert "50/100" in captured.out


def test_benchmark_run_with_mock(capsys):
    """Test benchmark run with mocked client."""
    mock_client = MagicMock()
    mock_result = MagicMock()
    mock_result.success = True
    mock_result.results = []
    mock_client.submit_task.return_value = mock_result

    runner = BenchmarkRunner(mock_client)
    runner.run("pick_place", count=3)

    captured = capsys.readouterr()
    assert "Running 3x pick_place" in captured.out
    assert "Total:" in captured.out
    assert "Success:" in captured.out