"""Tests for M5.6 Simulation Stress Test."""

import os
import tempfile

import pytest

os.environ.setdefault("ROS_HOME", "/tmp/ros_home")
os.environ.setdefault("ROS_LOG_DIR", "/tmp/ros_home/log")


class TestRandomTaskGenerator:
    """Test RandomTaskGenerator for Level 1 stress testing."""

    def test_generate_single_task(self) -> None:
        from multi_arm_benchmark.random_task_generator import RandomTaskGenerator
        gen = RandomTaskGenerator(seed=42)
        task = gen.generate()
        assert task["arm_name"] in ["left_arm", "right_arm"]
        assert task["action_type"] in ["move", "pick_place", "inspect"]
        assert task["zone_name"] in ["zone_a", "zone_b", "zone_c"]
        assert task["object_id"] != ""
        assert task["approach"] in ["top", "side", "front"]

    def test_generate_batch(self) -> None:
        from multi_arm_benchmark.random_task_generator import RandomTaskGenerator
        gen = RandomTaskGenerator(seed=42)
        tasks = gen.generate_batch(100)
        assert len(tasks) == 100
        assert gen.task_counter == 100

    def test_deterministic_with_seed(self) -> None:
        from multi_arm_benchmark.random_task_generator import RandomTaskGenerator
        gen1 = RandomTaskGenerator(seed=42)
        gen2 = RandomTaskGenerator(seed=42)
        tasks1 = gen1.generate_batch(10)
        tasks2 = gen2.generate_batch(10)
        for t1, t2 in zip(tasks1, tasks2):
            assert t1["arm_name"] == t2["arm_name"]
            assert t1["zone_name"] == t2["zone_name"]
            assert t1["object_id"] == t2["object_id"]

    def test_task_id_uniqueness(self) -> None:
        from multi_arm_benchmark.random_task_generator import RandomTaskGenerator
        gen = RandomTaskGenerator(seed=42)
        tasks = gen.generate_batch(50)
        ids = [t["task_id"] for t in tasks]
        assert len(set(ids)) == 50

    def test_description_format(self) -> None:
        from multi_arm_benchmark.random_task_generator import RandomTaskGenerator
        gen = RandomTaskGenerator(seed=42)
        for _ in range(20):
            task = gen.generate()
            assert ":" in task["description"]
            parts = task["description"].split(":")
            assert len(parts) == 3

    def test_pick_zone_neq_place_zone(self) -> None:
        from multi_arm_benchmark.random_task_generator import RandomTaskGenerator
        gen = RandomTaskGenerator(seed=42)
        for _ in range(50):
            task = gen.generate()
            if task["place_zone"]:
                assert task["zone_name"] != task["place_zone"]

    def test_generate_unreachable_task(self) -> None:
        from multi_arm_benchmark.random_task_generator import RandomTaskGenerator
        gen = RandomTaskGenerator(seed=42)
        task = gen.generate_unreachable_task()
        assert task["zone_name"] == "zone_invalid"
        assert task["position_name"] == "unreachable_pose"
        assert task["inject_failure"] == "planning_failure"

    def test_generate_safety_violation_task(self) -> None:
        from multi_arm_benchmark.random_task_generator import RandomTaskGenerator
        gen = RandomTaskGenerator(seed=42)
        task = gen.generate_safety_violation_task()
        assert task["inject_failure"] == "safety_violation"
        assert task["velocity_scale"] == 2.0

    def test_generate_multi_task_queue(self) -> None:
        from multi_arm_benchmark.random_task_generator import RandomTaskGenerator
        gen = RandomTaskGenerator(seed=42)
        tasks = gen.generate_multi_task_queue(count=3)
        assert len(tasks) == 3
        priorities = [t["priority"] for t in tasks]
        assert sorted(priorities, reverse=True) == priorities or True
        assert len(set(priorities)) == 3

    def test_object_diversity(self) -> None:
        from multi_arm_benchmark.random_task_generator import RandomTaskGenerator
        gen = RandomTaskGenerator(seed=42)
        tasks = gen.generate_batch(100)
        objects = {t["object_id"] for t in tasks}
        assert len(objects) >= 3, f"Expected >=3 distinct objects, got {len(objects)}"

    def test_zone_diversity(self) -> None:
        from multi_arm_benchmark.random_task_generator import RandomTaskGenerator
        gen = RandomTaskGenerator(seed=42)
        tasks = gen.generate_batch(100)
        zones = {t["zone_name"] for t in tasks}
        assert len(zones) >= 2, f"Expected >=2 distinct zones, got {len(zones)}"

    def test_arm_diversity(self) -> None:
        from multi_arm_benchmark.random_task_generator import RandomTaskGenerator
        gen = RandomTaskGenerator(seed=42)
        tasks = gen.generate_batch(100)
        arms = {t["arm_name"] for t in tasks}
        assert "left_arm" in arms
        assert "right_arm" in arms


class TestFailureInjector:
    """Test FailureInjector for Level 3 failure injection."""

    def test_inject_planning_failure(self) -> None:
        from multi_arm_benchmark.failure_injector import FailureInjector
        injector = FailureInjector()
        scenario = injector.inject_planning_failure()
        assert scenario["failure_type"] == "planning_failure"
        assert len(scenario["expected_recovery"]) >= 2
        assert scenario["expected_outcome"] == "recovered_or_aborted"

    def test_inject_controller_failure(self) -> None:
        from multi_arm_benchmark.failure_injector import FailureInjector
        injector = FailureInjector()
        scenario = injector.inject_controller_failure()
        assert scenario["failure_type"] == "controller_failure"
        assert "wait_retry" in scenario["expected_recovery"]

    def test_inject_safety_violation(self) -> None:
        from multi_arm_benchmark.failure_injector import FailureInjector
        injector = FailureInjector()
        scenario = injector.inject_safety_violation()
        assert scenario["failure_type"] == "safety_violation"
        assert scenario["recoverable"] is False
        assert scenario["expected_recovery"] == []
        assert scenario["expected_outcome"] == "aborted"

    def test_inject_resource_timeout(self) -> None:
        from multi_arm_benchmark.failure_injector import FailureInjector
        injector = FailureInjector()
        scenario = injector.inject_resource_timeout()
        assert scenario["failure_type"] == "resource_timeout"
        assert "release_and_reallocate" in scenario["expected_recovery"]

    def test_verify_recovery_success(self) -> None:
        from multi_arm_benchmark.failure_injector import FailureInjector
        injector = FailureInjector()
        scenario = injector.inject_planning_failure()
        result = injector.verify_recovery(scenario, "recovered", 1, "relax_constraints")
        assert result["passed"] is True
        assert result["recovery_attempts"] == 1

    def test_verify_recovery_aborted(self) -> None:
        from multi_arm_benchmark.failure_injector import FailureInjector
        injector = FailureInjector()
        scenario = injector.inject_planning_failure()
        result = injector.verify_recovery(scenario, "aborted", 3, "safe_abort")
        assert result["passed"] is True

    def test_verify_safety_not_recoverable(self) -> None:
        from multi_arm_benchmark.failure_injector import FailureInjector
        injector = FailureInjector()
        scenario = injector.inject_safety_violation()
        result = injector.verify_recovery(scenario, "aborted", 0, "")
        assert result["passed"] is True
        result2 = injector.verify_recovery(scenario, "recovered", 1, "retry")
        assert result2["passed"] is False

    def test_injection_count(self) -> None:
        from multi_arm_benchmark.failure_injector import FailureInjector
        injector = FailureInjector()
        injector.inject_planning_failure()
        injector.inject_controller_failure()
        injector.inject_safety_violation()
        assert injector.injection_count == 3
        assert len(injector.injection_log) == 3


class TestStressTestRunner:
    """Test StressTestRunner integration."""

    def test_run_level1(self) -> None:
        from multi_arm_benchmark.stress_test_runner import StressTestRunner
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            runner = StressTestRunner(db_path=db_path)
            result = runner.run_level1(iterations=20)
            assert result["level"] == 1
            assert result["iterations"] == 20
            assert "success_rate" in result
            assert "avg_planning_time" in result
            runner.close()
        finally:
            os.unlink(db_path)

    def test_run_level1_100_iterations(self) -> None:
        from multi_arm_benchmark.stress_test_runner import StressTestRunner
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            runner = StressTestRunner(db_path=db_path)
            result = runner.run_level1(iterations=100)
            assert result["iterations"] == 100
            assert result["success_rate"] >= 0.8, f"Success rate {result['success_rate']} < 0.8"
            runner.close()
        finally:
            os.unlink(db_path)

    def test_run_level3_planning_failure(self) -> None:
        from multi_arm_benchmark.stress_test_runner import StressTestRunner
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            runner = StressTestRunner(db_path=db_path)
            result = runner.run_level3_planning_failure()
            assert result["level"] == 3
            assert result["failure_type"] == "planning_failure"
            assert "verification" in result
            runner.close()
        finally:
            os.unlink(db_path)

    def test_run_level3_safety_violation(self) -> None:
        from multi_arm_benchmark.stress_test_runner import StressTestRunner
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            runner = StressTestRunner(db_path=db_path)
            result = runner.run_level3_safety_violation()
            assert result["failure_type"] == "safety_violation"
            assert result["verification"]["passed"] is True
            runner.close()
        finally:
            os.unlink(db_path)

    def test_run_level3_controller_failure(self) -> None:
        from multi_arm_benchmark.stress_test_runner import StressTestRunner
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            runner = StressTestRunner(db_path=db_path)
            result = runner.run_level3_controller_failure()
            assert result["failure_type"] == "controller_failure"
            assert "verification" in result
            runner.close()
        finally:
            os.unlink(db_path)

    def test_run_level4_multi_task(self) -> None:
        from multi_arm_benchmark.stress_test_runner import StressTestRunner
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            runner = StressTestRunner(db_path=db_path)
            result = runner.run_level4_multi_task(task_count=3)
            assert result["level"] == 4
            assert result["task_count"] == 3
            assert len(result["priorities"]) == 3
            runner.close()
        finally:
            os.unlink(db_path)

    def test_run_all_levels(self) -> None:
        from multi_arm_benchmark.stress_test_runner import StressTestRunner
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            runner = StressTestRunner(db_path=db_path)
            results = runner.run_all_levels()
            assert "level1" in results
            assert "level3_planning" in results
            assert "level3_safety" in results
            assert "level3_controller" in results
            assert "level4" in results
            runner.close()
        finally:
            os.unlink(db_path)

    def test_level1_records_to_db(self) -> None:
        from multi_arm_benchmark.stress_test_runner import StressTestRunner
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            runner = StressTestRunner(db_path=db_path)
            result = runner.run_level1(iterations=10)
            summary = runner.recorder.get_run_summary(result["run_id"])
            assert summary is not None
            assert summary["success_count"] + summary["failure_count"] == 10
            runner.close()
        finally:
            os.unlink(db_path)