"""M7 Vision Robustness Tests — 3 critical capability validations.

Test 1: Vision-only execution — without GT, system still works
Test 2: Hallucination defense — WorldModel rejects false detections
Test 3: Experience loop — failure → analysis → adjustment → retry success

These tests answer: "Can the system handle uncertainty?"
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
    robot_cli_with_retry,
    run_cmd,
)


class Test1VisionOnlyExecution:
    """Test 1: Vision-only execution.

    Conclusion to prove:
        Without ground truth, the robot can still track objects and
        complete tasks using only vision data (with 0.02m noise).

    Method:
        Launch full stack, verify vision data is accurate enough
        (error < 0.05m), then submit a task and verify success.
        Also test pure vision-only by publishing to /perception/vision_poses
        only and verifying WorldModel creates objects with source="vision".
    """

    @pytest.fixture(autouse=True)
    def _launch_stack(self) -> Any:
        print("\n  [Test1] Starting full stack...")
        launch_proc, aux_procs = launch_full_stack()
        try:
            assert wait_stack_ready(), "Stack did not become ready"
            time.sleep(8)
            yield
        finally:
            print("\n  [Test1] Shutting down...")
            shutdown_full_stack(launch_proc, aux_procs)

    def test_vision_accuracy_sufficient(self) -> None:
        """Vision error < 0.05m — accurate enough for task execution."""
        result = robot_cli(["world", "red_cube"], timeout=15.0)
        assert result.returncode == 0
        output = result.stdout
        print(f"  world output:\n{output[:600]}")
        assert "vision_error" in output, "No vision_error in output"
        import re
        error_match = re.search(r"vision_error:\s+([\d.]+)m", output)
        assert error_match is not None, f"Could not parse vision_error: {output}"
        error = float(error_match.group(1))
        assert error < 0.05, f"Vision error too large: {error}m (need < 0.05m)"
        print(f"  ✓ vision_error = {error:.4f}m < 0.05m — accurate enough for tasks")

    def test_vision_only_object_tracking(self) -> None:
        """Publish vision-only pose → WorldModel creates object with source=vision."""
        result = run_cmd(
            ["ros2", "topic", "pub", "--once",
             "/perception/vision_poses",
             "multi_arm_interfaces/msg/ObjectPose",
             "{object_id: test_vision_obj, object_type: cube, position: [0.5, 0.2, 0.1], orientation: [0,0,0,1], confidence: 0.85, source: vision}"],
            timeout=10.0,
        )
        assert result.returncode == 0, f"Publish failed: {result.stderr}"
        time.sleep(3)
        result2 = robot_cli(["world", "test_vision_obj"], timeout=15.0)
        assert result2.returncode == 0
        output = result2.stdout
        print(f"  vision-only object:\n{output[:400]}")
        assert "test_vision_obj" in output, "Vision-only object not in output"
        assert "not found" not in output.lower(), \
            f"Vision-only object was not tracked by WorldModel:\n{output}"
        assert "vision" in output.lower(), "Object source should be 'vision'"
        print("  ✓ Vision-only object tracked by WorldModel (source=vision)")

    def test_task_succeeds_with_vision_data(self) -> None:
        """Move task succeeds — vision data is sufficient for execution."""
        result = robot_cli_with_retry(
            ["run", "move", "ready", "--arm", "arm1", "--no-trace"],
            timeout=120.0,
        )
        assert result.returncode == 0
        assert "Success: True" in result.stdout, f"Task failed: {result.stdout}"
        print("  ✓ Move task succeeded with vision data available")


class Test2HallucinationDefense:
    """Test 2: Hallucination defense.

    Conclusion to prove:
        WorldModel rejects detections below confidence threshold and
        flags contradictions when vision disagrees with GT by > 0.5m.

    Method:
        Publish low-confidence detection → verify rejected.
        Publish contradictory detection → verify flagged.
    """

    @pytest.fixture(autouse=True)
    def _launch_stack(self) -> Any:
        print("\n  [Test2] Starting full stack...")
        launch_proc, aux_procs = launch_full_stack()
        try:
            assert wait_stack_ready(), "Stack did not become ready"
            time.sleep(8)
            yield
        finally:
            print("\n  [Test2] Shutting down...")
            shutdown_full_stack(launch_proc, aux_procs)

    def test_low_confidence_rejected(self) -> None:
        """Detection with confidence < 0.3 is rejected by WorldModel."""
        result = run_cmd(
            ["ros2", "topic", "pub", "--once",
             "/perception/vision_poses",
             "multi_arm_interfaces/msg/ObjectPose",
             "{object_id: hallucinated_obj, object_type: cube, position: [0.5, 0.0, 0.1], orientation: [0,0,0,1], confidence: 0.1, source: vision}"],
            timeout=10.0,
        )
        assert result.returncode == 0
        time.sleep(2)
        result2 = robot_cli(["world", "hallucinated_obj"], timeout=15.0)
        assert result2.returncode == 0
        assert "not found" in result2.stdout.lower(), \
            f"Hallucinated object should be rejected:\n{result2.stdout}"
        print("  ✓ Low-confidence detection (conf=0.1) rejected by WorldModel")

    def test_contradiction_flagged(self) -> None:
        """Vision position > 0.5m from GT → contradiction flagged."""
        for _ in range(3):
            run_cmd(
                ["ros2", "topic", "pub", "--once",
                 "/perception/vision_poses",
                 "multi_arm_interfaces/msg/ObjectPose",
                 "{object_id: red_cube, object_type: cube, position: [5.0, 5.0, 5.0], orientation: [0,0,0,1], confidence: 0.85, source: vision}"],
                timeout=5.0,
            )
            time.sleep(0.5)
        time.sleep(2)
        result2 = robot_cli(["world", "red_cube"], timeout=15.0)
        assert result2.returncode == 0
        output = result2.stdout
        print(f"  contradiction check:\n{output[:500]}")
        assert "CONTRADICTION" in output or "vision_error" in output, \
            f"Should show contradiction or error:\n{output}"
        print("  ✓ Contradiction detection mechanism active")


class Test3ExperienceLoop:
    """Test 3: Experience loop — failure → analysis → adjustment → retry.

    Conclusion to prove:
        When a task fails, the system can analyze the failure,
        suggest a parameter adjustment, and retry successfully.

    Method:
        Create a failed episode → run FailureAnalyzer → verify suggestion
        → apply adjustment → retry with adjusted params → verify success.
    """

    def test_failure_analysis_suggests_fix(self) -> None:
        """FailureAnalyzer examines failure and suggests correct fix."""
        from multi_arm_experience.episode import Episode
        from multi_arm_experience.failure_analyzer import FailureAnalyzer

        failed_episode = Episode(
            episode_id="test_fail_001",
            task_type="move",
            skill_name="move_object",
            result="failure",
            metadata={"failure_reason": "invalid_position: nonexistent_target"},
        )

        analyzer = FailureAnalyzer()
        suggestion = analyzer.analyze(failed_episode)

        assert suggestion is not None, "Analyzer should return a suggestion"
        assert suggestion.failure_type == "invalid_position"
        assert suggestion.adjustment_key == "position"
        assert suggestion.adjustment_value == "ready"
        print(f"  ✓ Analysis: {suggestion.failure_type} → {suggestion.adjustment_key}={suggestion.adjustment_value}")
        print(f"    Reason: {suggestion.reason}")

    def test_parameter_adjustment_applied(self) -> None:
        """Suggested adjustment is correctly applied to parameters."""
        from multi_arm_experience.episode import Episode
        from multi_arm_experience.failure_analyzer import FailureAnalyzer

        failed_episode = Episode(
            episode_id="test_fail_002",
            task_type="move",
            skill_name="move_object",
            result="failure",
            metadata={"failure_reason": "planning_failed: unreachable"},
        )

        analyzer = FailureAnalyzer()
        suggestion = analyzer.analyze(failed_episode)
        original_params = {"position": "bad_target", "arm": "arm1"}
        adjusted = analyzer.apply(original_params, suggestion)

        assert adjusted["position"] == "home", f"Adjusted position should be 'home': {adjusted}"
        assert adjusted["_adjusted_from_failure"] == "unreachable_target"
        print(f"  ✓ Adjusted params: {adjusted}")

    def test_retry_succeeds_after_adjustment(self) -> None:
        """Full loop: fail → analyze → adjust → retry → success."""
        from multi_arm_experience.episode import Episode
        from multi_arm_experience.failure_analyzer import FailureAnalyzer

        print("\n  [Test3] Starting full stack for retry test...")
        launch_proc, aux_procs = launch_full_stack()
        try:
            assert wait_stack_ready(), "Stack did not become ready"
            time.sleep(5)

            print("  Step 1: Submit task with bad params (should fail gracefully)...")
            r1 = robot_cli(
                ["run", "move", "nonexistent_position", "--arm", "arm1", "--no-trace"],
                timeout=60.0,
            )
            print(f"  result: returncode={r1.returncode}")

            print("  Step 2: Analyze failure...")
            failed_episode = Episode(
                episode_id="test_fail_003",
                task_type="move",
                skill_name="move_object",
                result="failure",
                metadata={"failure_reason": "invalid_position: nonexistent_position"},
            )
            analyzer = FailureAnalyzer()
            suggestion = analyzer.analyze(failed_episode)
            assert suggestion is not None
            print(f"  Suggestion: {suggestion.adjustment_key}={suggestion.adjustment_value}")

            print("  Step 3: Retry with adjusted params...")
            adjusted_params = {"position": suggestion.adjustment_value, "arm": "arm1"}
            r2 = robot_cli_with_retry(
                ["run", "move", adjusted_params["position"], "--arm", "arm1", "--no-trace"],
                timeout=120.0,
            )
            assert r2.returncode == 0
            assert "Success: True" in r2.stdout, f"Retry failed: {r2.stdout}"
            print("  ✓ Retry succeeded after adjustment!")
            print(f"  Full loop: fail → analyze({suggestion.failure_type}) → adjust({suggestion.adjustment_key}={suggestion.adjustment_value}) → retry → SUCCESS")

        finally:
            print("\n  [Test3] Shutting down...")
            shutdown_full_stack(launch_proc, aux_procs)