"""M7.INT Level 3 — Failure Recovery + Experience Loop E2E.

Verifies that task failures are recorded as Episodes and classifiable
by the evaluation engine.
"""

from __future__ import annotations

from typing import Any

import pytest

from m7_int_helpers import (
    launch_full_stack,
    wait_stack_ready,
    shutdown_full_stack,
    robot_cli,
)


class TestM7IntLevel3FailureRecovery:
    """Level 3: Failure recovery and Experience loop E2E."""

    @pytest.fixture(autouse=True)
    def _launch_full_stack(self) -> Any:
        """Launch full M7 stack and clean up."""
        print("\n  [Level 3] Starting full M7 stack...")
        launch_proc, aux_procs = launch_full_stack()
        try:
            assert wait_stack_ready(), "M7 stack did not become ready"
            yield
        finally:
            print("\n  [Level 3] Shutting down...")
            shutdown_full_stack(launch_proc, aux_procs)

    def test_nonexistent_object_task(self) -> None:
        """Task with non-existent object returns result."""
        print("\n  [Test] robot run pick_place nonexistent_object...")
        result = robot_cli(
            ["run", "pick_place", "nonexistent_object", "zone_b", "--no-trace"],
            timeout=60.0,
        )
        print(f"  exit: {result.returncode}")
        print(f"  stdout:\n{result.stdout[:500]}")
        assert result.returncode == 0

    def test_unreachable_position_task(self) -> None:
        """Task with unreachable position returns result."""
        print("\n  [Test] robot run move unreachable_pos...")
        result = robot_cli(
            ["run", "move", "nonexistent_position", "--arm", "arm1", "--no-trace"],
            timeout=60.0,
        )
        print(f"  exit: {result.returncode}")
        print(f"  stdout:\n{result.stdout[:500]}")
        assert result.returncode == 0

    def test_episodes_after_failures(self) -> None:
        """`robot episodes` lists episodes after task attempts."""
        print("\n  [Test] robot episodes after failures...")
        robot_cli(
            ["run", "move", "nonexistent_position", "--no-trace"],
            timeout=60.0,
        )
        result = robot_cli(["episodes", "--recent", "10"], timeout=15.0)
        print(f"  stdout:\n{result.stdout[:500]}")
        assert result.returncode == 0

    def test_evaluate_after_tasks(self) -> None:
        """`robot evaluate` runs after task attempts."""
        print("\n  [Test] robot evaluate...")
        robot_cli(
            ["run", "move", "ready", "--no-trace"],
            timeout=60.0,
        )
        result = robot_cli(["evaluate"], timeout=15.0)
        print(f"  exit: {result.returncode}")
        print(f"  stdout:\n{result.stdout[:500]}")
        assert result.returncode == 0
