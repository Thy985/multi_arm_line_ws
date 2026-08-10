"""Tests for M7.E Evaluation Infrastructure."""

import pytest

from multi_arm_tools.evaluator import (
    EvaluationEngine,
    EvaluationReport,
    TaskStats,
    classify_failure,
)


class TestClassifyFailure:
    """Test failure classification."""

    def test_perception_failure(self):
        assert classify_failure("FAILURE", "object not found") == "perception"

    def test_planning_failure(self):
        assert classify_failure("FAILURE", "no IK solution") == "planning"

    def test_grasp_failure(self):
        assert classify_failure("FAILURE", "gripper drop") == "grasp"

    def test_timeout_failure(self):
        assert classify_failure("TIMEOUT", "expired") == "timeout"

    def test_execution_failure(self):
        assert classify_failure("FAILURE", "controller error") == "execution"

    def test_unknown_failure(self):
        assert classify_failure("FAILURE", "something weird") == "unknown"


class TestTaskStats:
    """Test TaskStats dataclass."""

    def test_success_rate(self):
        stats = TaskStats(task_type="pick", total=10, success=8, failure=2)
        assert stats.success_rate == 80.0

    def test_success_rate_zero_total(self):
        stats = TaskStats(task_type="pick")
        assert stats.success_rate == 0.0

    def test_avg_duration(self):
        stats = TaskStats(task_type="pick", durations=[1.0, 2.0, 3.0])
        assert stats.avg_duration == 2.0


class TestEvaluationEngine:
    """Test EvaluationEngine with sample episodes."""

    @pytest.fixture
    def sample_episodes(self) -> list[dict]:
        return [
            {"task_type": "pick_place", "result": "SUCCESS", "duration": 2.5},
            {"task_type": "pick_place", "result": "SUCCESS", "duration": 3.0},
            {"task_type": "pick_place", "result": "FAILURE:object not found", "duration": 1.0, "failure_reason": "object not found"},
            {"task_type": "pick_place", "result": "FAILURE:no IK solution", "duration": 0.5, "failure_reason": "no IK solution"},
            {"task_type": "move", "result": "SUCCESS", "duration": 1.5},
            {"task_type": "move", "result": "SUCCESS", "duration": 1.8},
            {"task_type": "move", "result": "FAILURE:timeout", "duration": 30.0, "failure_reason": "timeout"},
        ]

    def test_evaluate_returns_report(self, sample_episodes):
        engine = EvaluationEngine()
        report = engine.evaluate(sample_episodes)
        assert isinstance(report, EvaluationReport)

    def test_total_episodes(self, sample_episodes):
        engine = EvaluationEngine()
        report = engine.evaluate(sample_episodes)
        assert report.total_episodes == 7

    def test_overall_success_rate(self, sample_episodes):
        engine = EvaluationEngine()
        report = engine.evaluate(sample_episodes)
        assert report.overall_success_rate == pytest.approx(4 / 7 * 100, rel=1)

    def test_per_task_stats(self, sample_episodes):
        engine = EvaluationEngine()
        report = engine.evaluate(sample_episodes)
        assert "pick_place" in report.task_stats
        assert "move" in report.task_stats
        assert report.task_stats["pick_place"].total == 4
        assert report.task_stats["pick_place"].success == 2
        assert report.task_stats["move"].total == 3
        assert report.task_stats["move"].success == 2

    def test_failure_breakdown(self, sample_episodes):
        engine = EvaluationEngine()
        report = engine.evaluate(sample_episodes)
        assert report.failure_breakdown.get("perception", 0) == 1
        assert report.failure_breakdown.get("planning", 0) == 1
        assert report.failure_breakdown.get("timeout", 0) == 1

    def test_trend_comparison(self, sample_episodes):
        engine = EvaluationEngine()
        first = engine.evaluate(sample_episodes)
        second_episodes = [
            {"task_type": "pick_place", "result": "SUCCESS", "duration": 2.0},
            {"task_type": "pick_place", "result": "SUCCESS", "duration": 2.5},
        ]
        second = engine.evaluate(second_episodes)
        assert second.trend_vs_last is not None
        assert second.trend_vs_last > 0

    def test_regression_detection(self, sample_episodes):
        engine = EvaluationEngine()
        first = engine.evaluate(sample_episodes)
        worse_episodes = [
            {"task_type": "pick_place", "result": "FAILURE", "duration": 1.0},
            {"task_type": "pick_place", "result": "FAILURE", "duration": 1.0},
        ]
        worse = engine.evaluate(worse_episodes)
        assert worse.has_regression
        assert any("pick_place" in r for r in worse.regressions)

    def test_empty_episodes(self):
        engine = EvaluationEngine()
        report = engine.evaluate([])
        assert report.total_episodes == 0
        assert report.overall_success_rate == 0.0


class TestEvaluationReport:
    """Test EvaluationReport properties."""

    def test_is_improving(self):
        report = EvaluationReport(trend_vs_last=5.0)
        assert report.is_improving

    def test_not_improving(self):
        report = EvaluationReport(trend_vs_last=-5.0)
        assert not report.is_improving

    def test_has_regression(self):
        report = EvaluationReport(regressions=["pick_place: 80% → 50%"])
        assert report.has_regression

    def test_no_regression(self):
        report = EvaluationReport()
        assert not report.has_regression