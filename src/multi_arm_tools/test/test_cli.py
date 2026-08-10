"""Tests for CLI command parsing."""

import sys
from unittest.mock import MagicMock, patch

import pytest


def test_cli_import():
    """Test that CLI module can be imported."""
    from multi_arm_tools import cli
    assert hasattr(cli, "main")
    assert hasattr(cli, "_dispatch")


def test_cli_argparse_status():
    """Test 'robot status' command parsing."""
    from multi_arm_tools.cli import main
    with patch.object(sys, "argv", ["robot", "status"]):
        with patch("multi_arm_tools.cli._dispatch") as mock_dispatch:
            main()
            mock_dispatch.assert_called_once()
            args = mock_dispatch.call_args[0][0]
            assert args.command == "status"


def test_cli_argparse_world():
    """Test 'robot world' command parsing."""
    from multi_arm_tools.cli import main
    with patch.object(sys, "argv", ["robot", "world", "red_cube", "--relations"]):
        with patch("multi_arm_tools.cli._dispatch") as mock_dispatch:
            main()
            args = mock_dispatch.call_args[0][0]
            assert args.command == "world"
            assert args.object_id == "red_cube"
            assert args.relations is True


def test_cli_argparse_world_no_args():
    """Test 'robot world' with no arguments."""
    from multi_arm_tools.cli import main
    with patch.object(sys, "argv", ["robot", "world"]):
        with patch("multi_arm_tools.cli._dispatch") as mock_dispatch:
            main()
            args = mock_dispatch.call_args[0][0]
            assert args.command == "world"
            assert args.object_id is None
            assert args.relations is False


def test_cli_argparse_skills():
    """Test 'robot skills' command parsing."""
    from multi_arm_tools.cli import main
    with patch.object(sys, "argv", ["robot", "skills"]):
        with patch("multi_arm_tools.cli._dispatch") as mock_dispatch:
            main()
            args = mock_dispatch.call_args[0][0]
            assert args.command == "skills"


def test_cli_argparse_capability():
    """Test 'robot capability' command parsing."""
    from multi_arm_tools.cli import main
    with patch.object(sys, "argv", ["robot", "capability"]):
        with patch("multi_arm_tools.cli._dispatch") as mock_dispatch:
            main()
            args = mock_dispatch.call_args[0][0]
            assert args.command == "capability"


def test_cli_argparse_run():
    """Test 'robot run' command parsing."""
    from multi_arm_tools.cli import main
    with patch.object(sys, "argv", ["robot", "run", "pick_place", "red_cube", "zone_b", "--arm", "arm1"]):
        with patch("multi_arm_tools.cli._dispatch") as mock_dispatch:
            main()
            args = mock_dispatch.call_args[0][0]
            assert args.command == "run"
            assert args.task_type == "pick_place"
            assert args.args == ["red_cube", "zone_b"]
            assert args.arm == "arm1"
            assert args.no_trace is False


def test_cli_argparse_run_no_trace():
    """Test 'robot run --no-trace'."""
    from multi_arm_tools.cli import main
    with patch.object(sys, "argv", ["robot", "run", "move", "ready", "--no-trace"]):
        with patch("multi_arm_tools.cli._dispatch") as mock_dispatch:
            main()
            args = mock_dispatch.call_args[0][0]
            assert args.no_trace is True


def test_cli_argparse_episodes():
    """Test 'robot episodes' command parsing."""
    from multi_arm_tools.cli import main
    with patch.object(sys, "argv", ["robot", "episodes", "--failures-only", "--recent", "10"]):
        with patch("multi_arm_tools.cli._dispatch") as mock_dispatch:
            main()
            args = mock_dispatch.call_args[0][0]
            assert args.command == "episodes"
            assert args.failures_only is True
            assert args.recent == 10


def test_cli_argparse_episode():
    """Test 'robot episode <id>' command parsing."""
    from multi_arm_tools.cli import main
    with patch.object(sys, "argv", ["robot", "episode", "ep_00001"]):
        with patch("multi_arm_tools.cli._dispatch") as mock_dispatch:
            main()
            args = mock_dispatch.call_args[0][0]
            assert args.command == "episode"
            assert args.episode_id == "ep_00001"


def test_cli_argparse_traces():
    """Test 'robot traces' command parsing."""
    from multi_arm_tools.cli import main
    with patch.object(sys, "argv", ["robot", "traces", "--recent", "5"]):
        with patch("multi_arm_tools.cli._dispatch") as mock_dispatch:
            main()
            args = mock_dispatch.call_args[0][0]
            assert args.command == "traces"
            assert args.recent == 5


def test_cli_argparse_trace():
    """Test 'robot trace <id>' command parsing."""
    from multi_arm_tools.cli import main
    with patch.object(sys, "argv", ["robot", "trace", "trace_001"]):
        with patch("multi_arm_tools.cli._dispatch") as mock_dispatch:
            main()
            args = mock_dispatch.call_args[0][0]
            assert args.command == "trace"
            assert args.trace_id == "trace_001"


def test_cli_argparse_benchmark():
    """Test 'robot benchmark' command parsing."""
    from multi_arm_tools.cli import main
    with patch.object(sys, "argv", ["robot", "benchmark", "pick_place", "--count", "50", "--output", "results.json"]):
        with patch("multi_arm_tools.cli._dispatch") as mock_dispatch:
            main()
            args = mock_dispatch.call_args[0][0]
            assert args.command == "benchmark"
            assert args.task_type == "pick_place"
            assert args.count == 50
            assert args.output == "results.json"


def test_cli_no_command_fails():
    """Test that no command fails."""
    from multi_arm_tools.cli import main
    with patch.object(sys, "argv", ["robot"]):
        with pytest.raises(SystemExit):
            main()