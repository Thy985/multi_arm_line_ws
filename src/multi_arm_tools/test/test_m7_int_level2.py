"""M7.INT Level 2 — Combined Skill Closed-Loop E2E.

Verifies multi-step skills (pick_place = pick + move + place) through
the full M7 Runtime API chain, and Capability Graph consultation.
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


class TestM7IntLevel2CombinedSkill:
    """Level 2: Combined skill (pick+place) closed-loop E2E."""

    @pytest.fixture(autouse=True)
    def _launch_full_stack(self) -> Any:
        """Launch full M7 stack and clean up."""
        print("\n  [Level 2] Starting full M7 stack...")
        launch_proc, aux_procs = launch_full_stack()
        try:
            assert wait_stack_ready(), "M7 stack did not become ready"
            yield
        finally:
            print("\n  [Level 2] Shutting down...")
            shutdown_full_stack(launch_proc, aux_procs)

    def test_all_three_skills_available(self) -> None:
        """All three skills (pick_object, place_object, move_object) registered."""
        print("\n  [Test] All three skills available...")
        result = robot_cli(["skills"], timeout=15.0)
        assert result.returncode == 0
        output = result.stdout
        assert "pick_object" in output, f"pick_object missing: {output}"
        assert "place_object" in output, f"place_object missing: {output}"
        assert "move_object" in output, f"move_object missing: {output}"
        print("  ✓ pick_object + place_object + move_object all registered")

    def test_capability_graph_deps(self) -> None:
        """Capability graph shows manipulation + arm_reachable."""
        print("\n  [Test] Capability graph dependencies...")
        result = robot_cli(["capability"], timeout=15.0)
        assert result.returncode == 0
        output = result.stdout
        assert "manipulation" in output
        assert "arm_reachable" in output
        print("  ✓ manipulation + arm_reachable in capability graph")

    def test_composite_pick_place_task(self) -> None:
        """`robot run pick_place red_cube zone_b` executes composite task."""
        print("\n  [Test] robot run pick_place red_cube zone_b...")
        result = robot_cli(
            ["run", "pick_place", "red_cube", "zone_b", "--no-trace"],
            timeout=120.0,
        )
        print(f"  exit: {result.returncode}")
        print(f"  stdout:\n{result.stdout[:500]}")
        assert result.returncode == 0, f"CLI failed: {result.stderr}"

    def test_sequential_move_then_pick(self) -> None:
        """Sequential tasks: move ready then pick red_cube."""
        print("\n  [Test] Sequential: move ready + pick red_cube...")
        r1 = robot_cli(
            ["run", "move", "ready", "--arm", "left_arm", "--no-trace"],
            timeout=60.0,
        )
        assert r1.returncode == 0
        r2 = robot_cli(
            ["run", "pick", "red_cube", "--arm", "left_arm", "--no-trace"],
            timeout=60.0,
        )
        assert r2.returncode == 0
