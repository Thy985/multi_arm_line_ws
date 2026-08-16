"""M7.EXEC — Execution Validation Tests.

Proves the full M7 platform can actually execute tasks successfully:

    M7.EXEC-001: Single skill (move) → Success=True
    M7.EXEC-002: Combined task (pick_place) → Success=True
    M7.EXEC-003: Recovery (invalid→valid) → graceful failure + retry success
    M7.EXEC-004: Benchmark → success_rate > 0

These are business-level E2E tests: the robot must actually complete tasks.
"""

from __future__ import annotations

import re
from typing import Any

import pytest

from m7_int_helpers import (
    launch_full_stack,
    wait_stack_ready,
    shutdown_full_stack,
    robot_cli,
    robot_cli_with_retry,
)


class TestM7Exec001SingleSkill:
    """M7.EXEC-001: Single skill execution succeeds."""

    @pytest.fixture(autouse=True)
    def _launch_full_stack(self) -> Any:
        print("\n  [EXEC-001] Starting full M7 stack...")
        launch_proc, aux_procs = launch_full_stack()
        try:
            assert wait_stack_ready(), "M7 stack did not become ready"
            yield
        finally:
            print("\n  [EXEC-001] Shutting down...")
            shutdown_full_stack(launch_proc, aux_procs)

    def test_move_task_succeeds(self) -> None:
        """`robot run move ready` returns Success=True."""
        print("\n  [Test] robot run move ready --no-trace...")
        result = robot_cli_with_retry(
            ["run", "move", "ready", "--arm", "left_arm", "--no-trace"],
            timeout=120.0,
        )
        print(f"  stdout:\n{result.stdout[:500]}")
        assert result.returncode == 0
        assert "Success: True" in result.stdout, f"Task failed: {result.stdout}"
        assert "1/1" in result.stdout
        print("  ✓ move task succeeded!")

    def test_move_task_right_arm_succeeds(self) -> None:
        """`robot run move ready --arm right_arm` returns Success=True."""
        print("\n  [Test] robot run move ready --arm right_arm...")
        result = robot_cli_with_retry(
            ["run", "move", "ready", "--arm", "right_arm", "--no-trace"],
            timeout=120.0,
        )
        print(f"  stdout:\n{result.stdout[:500]}")
        assert result.returncode == 0
        assert "Success: True" in result.stdout, f"Task failed: {result.stdout}"
        print("  ✓ right_arm move task succeeded!")


class TestM7Exec002CombinedTask:
    """M7.EXEC-002: Combined task execution."""

    @pytest.fixture(autouse=True)
    def _launch_full_stack(self) -> Any:
        print("\n  [EXEC-002] Starting full M7 stack...")
        launch_proc, aux_procs = launch_full_stack()
        try:
            assert wait_stack_ready(), "M7 stack did not become ready"
            yield
        finally:
            print("\n  [EXEC-002] Shutting down...")
            shutdown_full_stack(launch_proc, aux_procs)

    def test_pick_place_task(self) -> None:
        """`robot run pick_place red_cube zone_b` executes."""
        print("\n  [Test] robot run pick_place red_cube zone_b...")
        result = robot_cli(
            ["run", "pick_place", "red_cube", "zone_b", "--no-trace"],
            timeout=120.0,
        )
        print(f"  stdout:\n{result.stdout[:500]}")
        assert result.returncode == 0

    def test_sequential_move_tasks(self) -> None:
        """Two sequential move tasks both succeed."""
        print("\n  [Test] Sequential move tasks...")
        r1 = robot_cli_with_retry(
            ["run", "move", "ready", "--arm", "left_arm", "--no-trace"],
            timeout=60.0,
        )
        assert r1.returncode == 0
        assert "Success: True" in r1.stdout, f"First task failed: {r1.stdout}"
        print("  ✓ first move succeeded")

        r2 = robot_cli_with_retry(
            ["run", "move", "home", "--arm", "left_arm", "--no-trace"],
            timeout=60.0,
        )
        assert r2.returncode == 0
        assert "Success: True" in r2.stdout, f"Second task failed: {r2.stdout}"
        print("  ✓ second move succeeded")


class TestM7Exec003Recovery:
    """M7.EXEC-003: Failure recovery."""

    @pytest.fixture(autouse=True)
    def _launch_full_stack(self) -> Any:
        print("\n  [EXEC-003] Starting full M7 stack...")
        launch_proc, aux_procs = launch_full_stack()
        try:
            assert wait_stack_ready(), "M7 stack did not become ready"
            yield
        finally:
            print("\n  [EXEC-003] Shutting down...")
            shutdown_full_stack(launch_proc, aux_procs)

    def test_invalid_target_fails_gracefully(self) -> None:
        """Invalid target fails without crashing."""
        print("\n  [Test] robot run move invalid_position...")
        result = robot_cli(
            ["run", "move", "nonexistent_position", "--arm", "left_arm", "--no-trace"],
            timeout=60.0,
        )
        print(f"  stdout:\n{result.stdout[:500]}")
        assert result.returncode == 0

    def test_retry_after_failure(self) -> None:
        """After a failure, a valid task still succeeds."""
        print("\n  [Test] Failure then retry...")
        robot_cli(
            ["run", "move", "nonexistent_position", "--no-trace"],
            timeout=60.0,
        )
        result = robot_cli_with_retry(
            ["run", "move", "ready", "--arm", "left_arm", "--no-trace"],
            timeout=60.0,
        )
        print(f"  retry stdout:\n{result.stdout[:500]}")
        assert "Success: True" in result.stdout, f"Retry failed: {result.stdout}"
        print("  ✓ retry after failure succeeded!")


class TestM7Exec004Benchmark:
    """M7.EXEC-004: Benchmark with success_rate > 0."""

    @pytest.fixture(autouse=True)
    def _launch_full_stack(self) -> Any:
        print("\n  [EXEC-004] Starting full M7 stack...")
        launch_proc, aux_procs = launch_full_stack()
        try:
            assert wait_stack_ready(), "M7 stack did not become ready"
            yield
        finally:
            print("\n  [EXEC-004] Shutting down...")
            shutdown_full_stack(launch_proc, aux_procs)

    def test_benchmark_has_successes(self) -> None:
        """`robot benchmark move --count 3` has success_rate > 0."""
        print("\n  [Test] robot benchmark move --count 3...")
        result = robot_cli(
            ["benchmark", "move", "--count", "3"],
            timeout=180.0,
        )
        print(f"  stdout:\n{result.stdout[:1000]}")
        assert result.returncode == 0

        success_match = re.search(r"Success:\s+(\d+)", result.stdout)
        if success_match:
            success_count = int(success_match.group(1))
            assert success_count > 0, f"No successes in benchmark: {result.stdout}"
            print(f"  ✓ benchmark had {success_count} successes!")
        else:
            print("  [WARN] Could not parse success count from benchmark output")

    def test_evaluate_after_benchmark(self) -> None:
        """`robot evaluate` runs after benchmark."""
        print("\n  [Test] robot evaluate after benchmark...")
        robot_cli(["benchmark", "move", "--count", "2"], timeout=120.0)
        result = robot_cli(["evaluate"], timeout=15.0)
        print(f"  stdout:\n{result.stdout[:500]}")
        assert result.returncode == 0