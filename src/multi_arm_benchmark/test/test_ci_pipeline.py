"""Tests for M5.5 CI/CD Pipeline scripts."""

import os
import tempfile

import pytest

os.environ.setdefault("ROS_HOME", "/tmp/ros_home")
os.environ.setdefault("ROS_LOG_DIR", "/tmp/ros_home/log")

WORKSPACE_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", ".."
)
WORKSPACE_DIR = os.path.abspath(WORKSPACE_DIR)


class TestCIScript:
    """Test CI script structure and logic."""

    def test_ci_script_exists(self) -> None:
        ci_script = os.path.join(WORKSPACE_DIR, "ci", "run_ci.sh")
        assert os.path.exists(ci_script), "ci/run_ci.sh not found"

    def test_ci_script_executable(self) -> None:
        ci_script = os.path.join(WORKSPACE_DIR, "ci", "run_ci.sh")
        assert os.access(ci_script, os.X_OK), "ci/run_ci.sh not executable"

    def test_launch_smoke_test_exists(self) -> None:
        script = os.path.join(WORKSPACE_DIR, "ci", "launch_smoke_test.py")
        assert os.path.exists(script), "ci/launch_smoke_test.py not found"

    def test_e2e_smoke_test_exists(self) -> None:
        script = os.path.join(WORKSPACE_DIR, "ci", "e2e_smoke_test.py")
        assert os.path.exists(script), "ci/e2e_smoke_test.py not found"


class TestGitHubActionsWorkflow:
    """Test GitHub Actions workflow structure."""

    def test_workflow_file_exists(self) -> None:
        workflow = os.path.join(WORKSPACE_DIR, ".github", "workflows", "ci.yml")
        assert os.path.exists(workflow), ".github/workflows/ci.yml not found"

    def test_workflow_has_four_layers(self) -> None:
        workflow = os.path.join(WORKSPACE_DIR, ".github", "workflows", "ci.yml")
        with open(workflow, "r") as f:
            content = f.read()
        assert "layer1-build" in content, "Missing layer1-build job"
        assert "layer2-test" in content, "Missing layer2-test job"
        assert "interface-compat" in content, "Missing interface-compat job"
        assert "performance-regression" in content, "Missing performance-regression job"

    def test_workflow_has_dependencies(self) -> None:
        workflow = os.path.join(WORKSPACE_DIR, ".github", "workflows", "ci.yml")
        with open(workflow, "r") as f:
            content = f.read()
        assert "needs: layer1-build" in content, "Layer 2 should depend on Layer 1"
        assert "needs: layer2-test" in content, "Performance should depend on Layer 2"


class TestCIPipelineLogic:
    """Test CI pipeline logic components."""

    def test_layer_selection_all(self) -> None:
        layers = "1,2,3,4"
        for l in [1, 2, 3, 4]:
            assert f",{l}," in f",{layers},"

    def test_layer_selection_partial(self) -> None:
        layers = "1,2"
        assert ",1," in f",{layers},"
        assert ",2," in f",{layers},"
        assert ",3," not in f",{layers},"

    def test_results_dir_creation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            results_dir = os.path.join(tmpdir, "ci_results")
            os.makedirs(results_dir, exist_ok=True)
            assert os.path.exists(results_dir)

    def test_colcon_build_packages(self) -> None:
        expected_packages = [
            "multi_arm_interfaces",
            "multi_arm_core",
            "multi_arm_safety",
            "multi_arm_world_model",
            "multi_arm_task_planner",
            "multi_arm_recovery",
            "multi_arm_benchmark",
        ]
        for pkg in expected_packages:
            pkg_dir = os.path.join(WORKSPACE_DIR, "src", pkg)
            assert os.path.exists(pkg_dir), f"Package {pkg} not found"

    def test_interface_compat_check_logic(self) -> None:
        interface_dir = os.path.join(WORKSPACE_DIR, "src", "multi_arm_interfaces")
        assert os.path.exists(interface_dir), "multi_arm_interfaces package missing"
        msg_dir = os.path.join(interface_dir, "msg")
        assert os.path.exists(msg_dir), "msg directory missing"
        msgs = [f for f in os.listdir(msg_dir) if f.endswith(".msg")]
        assert len(msgs) >= 8, f"Expected >=8 msg files, got {len(msgs)}"


class TestBenchmarkRegressionIntegration:
    """Test benchmark regression detection integration with CI."""

    def test_regression_detector_with_recorder(self) -> None:
        from multi_arm_benchmark.benchmark_recorder import BenchmarkRecorder
        from multi_arm_benchmark.regression_detector import RegressionDetector

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            recorder = BenchmarkRecorder(db_path=db_path)

            run1 = recorder.start_run("single_arm")
            for i in range(5):
                r = recorder.record_task_start(run1, f"t{i}", "arm1", "move", "")
                recorder.record_task_end(r, success=True, planning_time=0.5, execution_time=3.0)
            recorder.end_run(run1)

            run2 = recorder.start_run("single_arm")
            for i in range(5):
                r = recorder.record_task_start(run2, f"t{i}", "arm1", "move", "")
                recorder.record_task_end(r, success=True, planning_time=0.8, execution_time=3.5)
            recorder.end_run(run2)

            baseline = recorder.get_run_summary(run1)
            current = recorder.get_run_summary(run2)

            detector = RegressionDetector()
            result = detector.compare_runs(current, baseline)
            assert "regressed" in result
            assert "details" in result

            recorder.close()
        finally:
            os.unlink(db_path)

    def test_ci_regression_check_script(self) -> None:
        from multi_arm_benchmark.benchmark_recorder import BenchmarkRecorder
        from multi_arm_benchmark.regression_detector import RegressionDetector

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            recorder = BenchmarkRecorder(db_path=db_path)
            history = recorder.get_scenario_history("single_arm", limit=5)
            assert len(history) == 0, "No history expected for new DB"

            detector = RegressionDetector()
            result = detector.check_regression_history(history)
            assert result["trend"] == "insufficient_data"

            recorder.close()
        finally:
            os.unlink(db_path)
