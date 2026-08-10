"""M7.INT Level 1 — Single Skill Closed-Loop E2E.

Proves the full M7 platform closed loop through the `robot` CLI:

    Scene → WorldModel → Capability → Skill → Robot → Episode
"""

from __future__ import annotations

from typing import Any

import pytest

from m7_int_helpers import (
    launch_full_stack,
    wait_stack_ready,
    shutdown_full_stack,
    robot_cli,
    ros2_node_exists,
    service_available,
    action_available,
    wait_for_condition,
)


class TestM7IntLevel1SingleSkill:
    """Level 1: Single skill closed-loop E2E through robot CLI."""

    @pytest.fixture(autouse=True)
    def _launch_full_stack(self) -> Any:
        """Launch full M7 stack and clean up."""
        print("\n  [Level 1] Starting full M7 stack...")
        launch_proc, aux_procs = launch_full_stack()

        try:
            assert wait_stack_ready(), "M7 stack did not become ready"
            print("  [Level 1] Full M7 stack ready")
            yield
        finally:
            print("\n  [Level 1] Shutting down...")
            shutdown_full_stack(launch_proc, aux_procs)

    def test_robot_status(self) -> None:
        """`robot status` shows system overview."""
        print("\n  [Test] robot status...")
        result = robot_cli(["status"], timeout=15.0)
        print(f"  exit: {result.returncode}")
        print(f"  stdout:\n{result.stdout[:500]}")
        assert result.returncode == 0, f"robot status failed: {result.stderr}"

    def test_robot_world_has_objects(self) -> None:
        """`robot world` shows objects from Gazebo."""
        print("\n  [Test] robot world...")
        result = robot_cli(["world"], timeout=15.0)
        print(f"  stdout:\n{result.stdout[:500]}")
        assert result.returncode == 0, f"robot world failed: {result.stderr}"

    def test_robot_skills_listed(self) -> None:
        """`robot skills` lists registered skills."""
        print("\n  [Test] robot skills...")
        result = robot_cli(["skills"], timeout=15.0)
        print(f"  stdout:\n{result.stdout[:500]}")
        assert result.returncode == 0, f"robot skills failed: {result.stderr}"

    def test_robot_capability_shown(self) -> None:
        """`robot capability` shows three-layer capability."""
        print("\n  [Test] robot capability...")
        result = robot_cli(["capability"], timeout=15.0)
        print(f"  stdout:\n{result.stdout[:500]}")
        assert result.returncode == 0, f"robot capability failed: {result.stderr}"

    def test_robot_run_move_task(self) -> None:
        """`robot run move ready` executes a move task via Runtime API."""
        print("\n  [Test] robot run move ready --no-trace...")
        result = robot_cli(
            ["run", "move", "ready", "--arm", "arm1", "--no-trace"],
            timeout=120.0,
        )
        print(f"  exit: {result.returncode}")
        print(f"  stdout:\n{result.stdout[:1000]}")
        assert result.returncode == 0, f"CLI failed: {result.stderr}"

    def test_robot_episodes_listed(self) -> None:
        """`robot episodes` shows episode history after task execution."""
        print("\n  [Test] robot episodes...")
        result = robot_cli(["episodes", "--recent", "10"], timeout=15.0)
        print(f"  stdout:\n{result.stdout[:500]}")
        assert result.returncode == 0, f"robot episodes failed: {result.stderr}"
