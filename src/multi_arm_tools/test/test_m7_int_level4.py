"""M7.INT Level 4 — Benchmark Loop E2E.

Verifies `robot benchmark` executes multiple iterations and generates
statistics, and `robot evaluate` produces a report.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from m7_int_helpers import (
    launch_full_stack,
    wait_stack_ready,
    shutdown_full_stack,
    robot_cli,
)


class TestM7IntLevel4Benchmark:
    """Level 4: Benchmark loop and statistics E2E."""

    @pytest.fixture(autouse=True)
    def _launch_full_stack(self) -> Any:
        """Launch full M7 stack and clean up."""
        print("\n  [Level 4] Starting full M7 stack...")
        launch_proc, aux_procs = launch_full_stack()
        try:
            assert wait_stack_ready(), "M7 stack did not become ready"
            yield
        finally:
            print("\n  [Level 4] Shutting down...")
            shutdown_full_stack(launch_proc, aux_procs)

    def test_task_sets_loadable(self) -> None:
        """All task_set YAMLs are loadable."""
        print("\n  [Test] Task sets loadable...")
        ts_dir = Path("/home/lenovo/multi_arm_line_ws/src/multi_arm_simulation/scenes/task_sets")
        yaml_files = list(ts_dir.glob("*.yaml"))
        assert len(yaml_files) >= 3
        names = {f.stem for f in yaml_files}
        assert {"basic", "dual_arm", "stress"}.issubset(names)
        print(f"  ✓ {len(yaml_files)} task_sets: {names}")

    def test_benchmark_move_small(self) -> None:
        """`robot benchmark move --count 3` executes batch."""
        print("\n  [Test] robot benchmark move --count 3...")
        result = robot_cli(
            ["benchmark", "move", "--count", "3"],
            timeout=180.0,
        )
        print(f"  exit: {result.returncode}")
        print(f"  stdout:\n{result.stdout[:1000]}")
        assert result.returncode == 0

    def test_evaluate_after_benchmark(self) -> None:
        """`robot evaluate` generates report after benchmark."""
        print("\n  [Test] robot evaluate after benchmark...")
        robot_cli(["benchmark", "move", "--count", "2"], timeout=120.0)
        result = robot_cli(["evaluate"], timeout=15.0)
        print(f"  exit: {result.returncode}")
        print(f"  stdout:\n{result.stdout[:500]}")
        assert result.returncode == 0
