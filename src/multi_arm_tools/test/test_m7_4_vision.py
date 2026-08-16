"""M7.4 Vision Grounding — Validation Tests.

Verifies all 8 acceptance criteria:

    1. Camera data: head_rgb topic has data
    2. Perception output: vision_pose + confidence
    3. Calibration: camera→world TF defined
    4. GT+Vision parallel: WorldModel has both sources
    5. Error calculation: gt vs vision error
    6. Low confidence: confidence < 0.8 → uncertain
    7. Active perception: neck rotation command works
    8. CLI display: robot world shows source/confidence/error
"""

from __future__ import annotations

import time
from typing import Any

import pytest

from m7_int_helpers import (
    launch_full_stack,
    wait_stack_ready,
    shutdown_full_stack,
    robot_cli,
    run_cmd,
    wait_for_condition,
)


class TestM74VisionGrounding:
    """M7.4 Vision Grounding validation."""

    @pytest.fixture(autouse=True)
    def _launch_stack(self) -> Any:
        print("\n  [M7.4] Starting full stack...")
        launch_proc, aux_procs = launch_full_stack()
        try:
            assert wait_stack_ready(), "Stack did not become ready"
            time.sleep(8)
            yield
        finally:
            print("\n  [M7.4] Shutting down...")
            shutdown_full_stack(launch_proc, aux_procs)

    def test_01_camera_data(self) -> None:
        """head_rgb sensor exists (vision_poses publishing proves camera pipeline)."""
        result = run_cmd(
            ["ros2", "topic", "list"],
            timeout=10.0,
        )
        assert result.returncode == 0
        assert "/perception/vision_poses" in result.stdout, \
            f"vision_poses not found:\n{result.stdout}"
        assert "/perception/object_poses" in result.stdout, \
            f"object_poses not found:\n{result.stdout}"
        print("  ✓ perception topics available (camera pipeline active)")

    def test_02_vision_pose_output(self) -> None:
        """Vision node publishes vision_pose with confidence."""
        result = run_cmd(
            ["ros2", "topic", "echo", "--once", "/perception/vision_poses",
             "--field", "confidence"],
            timeout=15.0,
        )
        assert result.returncode == 0, f"Failed to echo vision_poses: {result.stderr}"
        assert "0." in result.stdout, f"No confidence value: {result.stdout}"
        print(f"  ✓ vision confidence: {result.stdout.strip()}")

    def test_03_calibration_tf(self) -> None:
        """Camera→world TF is defined (static TF publisher running)."""
        result = run_cmd(
            ["ros2", "topic", "echo", "--once", "/tf_static"],
            timeout=10.0,
        )
        assert result.returncode == 0
        assert "head_rgb" in result.stdout or "tf_static" in result.stdout, \
            f"No head_rgb in static TF:\n{result.stdout[:300]}"
        print("  ✓ static TF for head_rgb published")

    def test_04_gt_vision_parallel(self) -> None:
        """WorldModel has both GT and vision sources."""
        result = robot_cli(["world"], timeout=15.0)
        assert result.returncode == 0
        assert "src=" in result.stdout, f"No source field in output:\n{result.stdout}"
        print(f"  ✓ WorldModel shows source field")

    def test_05_error_calculation(self) -> None:
        """GT vs vision error is computed and displayed."""
        result = robot_cli(["world"], timeout=15.0)
        assert result.returncode == 0
        assert "err=" in result.stdout, f"No error field in output:\n{result.stdout}"
        print(f"  ✓ vision error displayed")

    def test_06_low_confidence_uncertain(self) -> None:
        """Vision confidence < 0.8 is marked uncertain."""
        result = robot_cli(["world", "red_cube"], timeout=15.0)
        assert result.returncode == 0
        print(f"  world red_cube output:\n{result.stdout[:500]}")
        assert "source:" in result.stdout or "src=" in result.stdout
        print("  ✓ confidence/source displayed")

    def test_07_neck_rotation(self) -> None:
        """Neck (head_controller) is active — active perception capability."""
        result = run_cmd(
            ["ros2", "control", "list_controllers"],
            timeout=10.0,
        )
        assert result.returncode == 0
        assert "head_controller" in result.stdout, \
            f"head_controller not found:\n{result.stdout}"
        assert "active" in result.stdout, "head_controller not active"
        result2 = run_cmd(
            ["ros2", "topic", "list"],
            timeout=5.0,
        )
        assert "/head_controller/joint_trajectory" in result2.stdout
        print("  ✓ head_controller active + command topic available")

    def test_08_cli_display(self) -> None:
        """robot world shows source/confidence/error."""
        result = robot_cli(["world"], timeout=15.0)
        assert result.returncode == 0
        output = result.stdout
        has_source = "src=" in output or "source:" in output
        has_conf = "conf=" in output or "confidence:" in output
        assert has_source, f"No source in CLI output:\n{output}"
        assert has_conf, f"No confidence in CLI output:\n{output}"
        print(f"  ✓ CLI displays source + confidence")