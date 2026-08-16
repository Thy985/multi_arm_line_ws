"""Tests for M5.4 Benchmark System."""

import os
import tempfile
import time as _time

import pytest

os.environ.setdefault("ROS_HOME", "/tmp/ros_home")
os.environ.setdefault("ROS_LOG_DIR", "/tmp/ros_home/log")


class TestBenchmarkRecorder:
    """Test BenchmarkRecorder SQLite data collection."""

    def test_recorder_init(self) -> None:
        from multi_arm_benchmark.benchmark_recorder import BenchmarkRecorder
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            recorder = BenchmarkRecorder(db_path=db_path)
            assert os.path.exists(db_path)
            recorder.close()
        finally:
            os.unlink(db_path)

    def test_start_and_end_run(self) -> None:
        from multi_arm_benchmark.benchmark_recorder import BenchmarkRecorder
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            recorder = BenchmarkRecorder(db_path=db_path)
            run_id = recorder.start_run("test_scenario", git_hash="abc123")
            assert run_id > 0
            recorder.end_run(run_id)
            summary = recorder.get_run_summary(run_id)
            assert summary is not None
            assert summary["scenario_name"] == "test_scenario"
            assert summary["git_hash"] == "abc123"
            assert summary["total_duration"] is not None
            recorder.close()
        finally:
            os.unlink(db_path)

    def test_record_task(self) -> None:
        from multi_arm_benchmark.benchmark_recorder import BenchmarkRecorder
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            recorder = BenchmarkRecorder(db_path=db_path)
            run_id = recorder.start_run("test_scenario")
            record_id = recorder.record_task_start(
                run_id, "task_001", "left_arm", "move", "left_arm:zone_a:ready"
            )
            assert record_id > 0
            recorder.record_task_end(
                record_id, success=True,
                planning_time=0.5, execution_time=3.2
            )
            recorder.end_run(run_id)
            summary = recorder.get_run_summary(run_id)
            assert summary["success_count"] == 1
            assert summary["failure_count"] == 0
            assert len(summary["tasks"]) == 1
            assert summary["tasks"][0]["arm_name"] == "left_arm"
            assert summary["tasks"][0]["planning_time"] == 0.5
            assert summary["tasks"][0]["execution_time"] == 3.2
            recorder.close()
        finally:
            os.unlink(db_path)

    def test_record_failed_task(self) -> None:
        from multi_arm_benchmark.benchmark_recorder import BenchmarkRecorder
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            recorder = BenchmarkRecorder(db_path=db_path)
            run_id = recorder.start_run("test_scenario")
            record_id = recorder.record_task_start(
                run_id, "task_002", "right_arm", "move", "right_arm:zone_b:home"
            )
            recorder.record_task_end(
                record_id, success=False,
                failure_reason="collision_detected",
                recovery_count=2
            )
            recorder.end_run(run_id)
            summary = recorder.get_run_summary(run_id)
            assert summary["failure_count"] == 1
            assert summary["tasks"][0]["failure_reason"] == "collision_detected"
            assert summary["tasks"][0]["recovery_count"] == 2
            recorder.close()
        finally:
            os.unlink(db_path)

    def test_success_rate(self) -> None:
        from multi_arm_benchmark.benchmark_recorder import BenchmarkRecorder
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            recorder = BenchmarkRecorder(db_path=db_path)
            run_id = recorder.start_run("test_scenario")
            r1 = recorder.record_task_start(run_id, "t1", "left_arm", "move", "")
            recorder.record_task_end(r1, success=True)
            r2 = recorder.record_task_start(run_id, "t2", "left_arm", "move", "")
            recorder.record_task_end(r2, success=True)
            r3 = recorder.record_task_start(run_id, "t3", "left_arm", "move", "")
            recorder.record_task_end(r3, success=False)
            recorder.end_run(run_id)
            summary = recorder.get_run_summary(run_id)
            assert abs(summary["success_rate"] - 2.0/3.0) < 0.01
            recorder.close()
        finally:
            os.unlink(db_path)

    def test_avg_times(self) -> None:
        from multi_arm_benchmark.benchmark_recorder import BenchmarkRecorder
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            recorder = BenchmarkRecorder(db_path=db_path)
            run_id = recorder.start_run("test_scenario")
            r1 = recorder.record_task_start(run_id, "t1", "left_arm", "move", "")
            recorder.record_task_end(r1, success=True, planning_time=1.0, execution_time=5.0)
            r2 = recorder.record_task_start(run_id, "t2", "left_arm", "move", "")
            recorder.record_task_end(r2, success=True, planning_time=2.0, execution_time=6.0)
            recorder.end_run(run_id)
            summary = recorder.get_run_summary(run_id)
            assert abs(summary["avg_planning_time"] - 1.5) < 0.01
            assert abs(summary["avg_execution_time"] - 5.5) < 0.01
            recorder.close()
        finally:
            os.unlink(db_path)

    def test_scenario_history(self) -> None:
        from multi_arm_benchmark.benchmark_recorder import BenchmarkRecorder
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            recorder = BenchmarkRecorder(db_path=db_path)
            for i in range(3):
                run_id = recorder.start_run("single_arm")
                r = recorder.record_task_start(run_id, "t1", "left_arm", "move", "")
                recorder.record_task_end(r, success=True, planning_time=0.5, execution_time=3.0)
                recorder.end_run(run_id)
            history = recorder.get_scenario_history("single_arm", limit=3)
            assert len(history) == 3
            recorder.close()
        finally:
            os.unlink(db_path)

    def test_metadata(self) -> None:
        from multi_arm_benchmark.benchmark_recorder import BenchmarkRecorder
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            recorder = BenchmarkRecorder(db_path=db_path)
            run_id = recorder.start_run("test", metadata={"ros_version": "jazzy", "sim": True})
            recorder.end_run(run_id)
            summary = recorder.get_run_summary(run_id)
            assert summary["metadata"]["ros_version"] == "jazzy"
            assert summary["metadata"]["sim"] is True
            recorder.close()
        finally:
            os.unlink(db_path)

    def test_resource_wait_and_safety(self) -> None:
        from multi_arm_benchmark.benchmark_recorder import BenchmarkRecorder
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            recorder = BenchmarkRecorder(db_path=db_path)
            run_id = recorder.start_run("test")
            r = recorder.record_task_start(run_id, "t1", "left_arm", "move", "")
            recorder.record_task_end(
                r, success=True,
                resource_wait_time=2.5,
                collision_count=1,
                safety_rejections=0
            )
            recorder.end_run(run_id)
            summary = recorder.get_run_summary(run_id)
            assert summary["tasks"][0]["resource_wait_time"] == 2.5
            assert summary["tasks"][0]["collision_count"] == 1
            assert summary["tasks"][0]["safety_rejections"] == 0
            recorder.close()
        finally:
            os.unlink(db_path)

    def test_default_db_path(self) -> None:
        from multi_arm_benchmark.benchmark_recorder import BenchmarkRecorder
        recorder = BenchmarkRecorder()
        assert "benchmark.db" in recorder.db_path
        recorder.close()


class TestScenarioRunner:
    """Test ScenarioRunner YAML loading and task building."""

    def test_list_scenarios(self) -> None:
        from multi_arm_benchmark.scenario_runner import ScenarioRunner
        runner = ScenarioRunner()
        scenarios = runner.list_scenarios()
        assert "single_arm" in scenarios
        assert "dual_arm" in scenarios
        assert "conflict" in scenarios
        assert "recovery" in scenarios

    def test_load_single_arm(self) -> None:
        from multi_arm_benchmark.scenario_runner import ScenarioRunner
        runner = ScenarioRunner()
        scenario = runner.load_scenario("single_arm")
        assert scenario["name"] == "single_arm"
        assert len(scenario["tasks"]) >= 2

    def test_load_dual_arm(self) -> None:
        from multi_arm_benchmark.scenario_runner import ScenarioRunner
        runner = ScenarioRunner()
        scenario = runner.load_scenario("dual_arm")
        assert scenario["name"] == "dual_arm"
        arms = {t["arm_name"] for t in scenario["tasks"]}
        assert "left_arm" in arms
        assert "right_arm" in arms

    def test_load_conflict(self) -> None:
        from multi_arm_benchmark.scenario_runner import ScenarioRunner
        runner = ScenarioRunner()
        scenario = runner.load_scenario("conflict")
        assert scenario["name"] == "conflict"
        zones = [t["zone_name"] for t in scenario["tasks"]]
        assert zones.count("zone_a") >= 2

    def test_load_recovery(self) -> None:
        from multi_arm_benchmark.scenario_runner import ScenarioRunner
        runner = ScenarioRunner()
        scenario = runner.load_scenario("recovery")
        assert scenario["name"] == "recovery"

    def test_load_nonexistent(self) -> None:
        from multi_arm_benchmark.scenario_runner import ScenarioRunner
        runner = ScenarioRunner()
        with pytest.raises(FileNotFoundError):
            runner.load_scenario("nonexistent_scenario")

    def test_validate_missing_name(self) -> None:
        from multi_arm_benchmark.scenario_runner import ScenarioRunner
        runner = ScenarioRunner()
        with pytest.raises(ValueError, match="name"):
            runner._validate_scenario({"tasks": []})

    def test_validate_missing_tasks(self) -> None:
        from multi_arm_benchmark.scenario_runner import ScenarioRunner
        runner = ScenarioRunner()
        with pytest.raises(ValueError, match="tasks"):
            runner._validate_scenario({"name": "test"})

    def test_validate_missing_arm_name(self) -> None:
        from multi_arm_benchmark.scenario_runner import ScenarioRunner
        runner = ScenarioRunner()
        with pytest.raises(ValueError, match="arm_name"):
            runner._validate_scenario({"name": "test", "tasks": [{"action_type": "move"}]})

    def test_build_execute_task_goal(self) -> None:
        from multi_arm_benchmark.scenario_runner import ScenarioRunner
        runner = ScenarioRunner()
        task = {
            "task_id": "bench_001",
            "arm_name": "left_arm",
            "action_type": "move",
            "zone_name": "zone_a",
            "position_name": "ready",
            "object_id": "red_cube",
            "approach": "top",
            "timeout": 30.0,
        }
        goal = runner.build_execute_task_goal(task)
        assert goal["task_id"] == "bench_001"
        assert goal["arm_name"] == "left_arm"
        assert goal["description"] == "left_arm:zone_a:ready"
        assert goal["object_id"] == "red_cube"
        assert goal["timeout"] == 30.0

    def test_get_tasks_without_load(self) -> None:
        from multi_arm_benchmark.scenario_runner import ScenarioRunner
        runner = ScenarioRunner()
        with pytest.raises(RuntimeError):
            runner.get_tasks()


class TestRegressionDetector:
    """Test RegressionDetector performance regression detection."""

    def test_no_regression(self) -> None:
        from multi_arm_benchmark.regression_detector import RegressionDetector
        detector = RegressionDetector()
        current = {"success_rate": 0.95, "avg_planning_time": 1.0, "avg_execution_time": 5.0, "avg_total_time": 6.0}
        baseline = {"success_rate": 0.90, "avg_planning_time": 1.1, "avg_execution_time": 5.2, "avg_total_time": 6.3}
        result = detector.compare_runs(current, baseline)
        assert not result["regressed"]
        assert len(result["regressions"]) == 0

    def test_success_rate_regression(self) -> None:
        from multi_arm_benchmark.regression_detector import RegressionDetector
        detector = RegressionDetector()
        current = {"success_rate": 0.70, "avg_planning_time": 1.0, "avg_execution_time": 5.0, "avg_total_time": 6.0}
        baseline = {"success_rate": 0.95, "avg_planning_time": 1.0, "avg_execution_time": 5.0, "avg_total_time": 6.0}
        result = detector.compare_runs(current, baseline)
        assert result["regressed"]
        assert "success_rate" in result["regressions"]

    def test_planning_time_regression(self) -> None:
        from multi_arm_benchmark.regression_detector import RegressionDetector
        detector = RegressionDetector()
        current = {"success_rate": 1.0, "avg_planning_time": 2.0, "avg_execution_time": 5.0, "avg_total_time": 7.0}
        baseline = {"success_rate": 1.0, "avg_planning_time": 1.0, "avg_execution_time": 5.0, "avg_total_time": 6.0}
        result = detector.compare_runs(current, baseline)
        assert result["regressed"]
        assert "avg_planning_time" in result["regressions"]

    def test_improvement_detection(self) -> None:
        from multi_arm_benchmark.regression_detector import RegressionDetector
        detector = RegressionDetector()
        current = {"success_rate": 1.0, "avg_planning_time": 0.5, "avg_execution_time": 3.0, "avg_total_time": 3.5}
        baseline = {"success_rate": 0.9, "avg_planning_time": 1.0, "avg_execution_time": 5.0, "avg_total_time": 6.0}
        result = detector.compare_runs(current, baseline)
        assert not result["regressed"]
        assert len(result["improvements"]) > 0

    def test_custom_thresholds(self) -> None:
        from multi_arm_benchmark.regression_detector import RegressionDetector
        detector = RegressionDetector(thresholds={"success_rate": 0.05, "avg_planning_time": 0.10})
        current = {"success_rate": 0.88, "avg_planning_time": 1.15}
        baseline = {"success_rate": 0.95, "avg_planning_time": 1.0}
        result = detector.compare_runs(current, baseline)
        assert result["regressed"]
        assert "success_rate" in result["regressions"]
        assert "avg_planning_time" in result["regressions"]

    def test_zero_baseline(self) -> None:
        from multi_arm_benchmark.regression_detector import RegressionDetector
        detector = RegressionDetector()
        current = {"success_rate": 0.5, "avg_planning_time": 1.0}
        baseline = {"success_rate": 0.0, "avg_planning_time": 0.0}
        result = detector.compare_runs(current, baseline)
        assert result["details"]["success_rate"]["status"] == "new_metric"
        assert result["details"]["avg_planning_time"]["status"] == "new_metric"

    def test_unchanged_metrics(self) -> None:
        from multi_arm_benchmark.regression_detector import RegressionDetector
        detector = RegressionDetector()
        current = {"success_rate": 1.0, "avg_planning_time": 1.0}
        baseline = {"success_rate": 1.0, "avg_planning_time": 1.0}
        result = detector.compare_runs(current, baseline)
        assert not result["regressed"]
        assert result["details"]["success_rate"]["status"] == "unchanged"

    def test_regression_history_insufficient(self) -> None:
        from multi_arm_benchmark.regression_detector import RegressionDetector
        detector = RegressionDetector()
        result = detector.check_regression_history([{"success_rate": 1.0}])
        assert result["trend"] == "insufficient_data"

    def test_regression_history_stable(self) -> None:
        from multi_arm_benchmark.regression_detector import RegressionDetector
        detector = RegressionDetector()
        history = [
            {"success_rate": 1.0, "avg_planning_time": 1.0, "avg_execution_time": 5.0, "avg_total_time": 6.0},
            {"success_rate": 0.95, "avg_planning_time": 1.05, "avg_execution_time": 5.1, "avg_total_time": 6.15},
            {"success_rate": 0.98, "avg_planning_time": 0.98, "avg_execution_time": 4.9, "avg_total_time": 5.88},
        ]
        result = detector.check_regression_history(history)
        assert result["trend"] == "stable"


class TestSmokeBenchmark:
    """Smoke tests for benchmark package imports."""

    def test_import_benchmark_recorder(self) -> None:
        from multi_arm_benchmark.benchmark_recorder import BenchmarkRecorder
        assert BenchmarkRecorder is not None

    def test_import_scenario_runner(self) -> None:
        from multi_arm_benchmark.scenario_runner import ScenarioRunner
        assert ScenarioRunner is not None

    def test_import_regression_detector(self) -> None:
        from multi_arm_benchmark.regression_detector import RegressionDetector
        assert RegressionDetector is not None

    def test_import_benchmark_node(self) -> None:
        from multi_arm_benchmark.benchmark_node import BenchmarkNode
        assert BenchmarkNode is not None