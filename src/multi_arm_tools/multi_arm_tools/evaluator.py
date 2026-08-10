"""Evaluation Engine — "怎么知道它变强？" 横切评估层 (M7.E).

Computes task success rates, failure breakdown, trend comparison,
and regression detection from Episode data.
"""

from __future__ import annotations

import json
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

try:
    import sqlite3
    HAS_SQLITE = True
except ImportError:
    HAS_SQLITE = False


@dataclass
class TaskStats:
    """Statistics for a single task type."""
    task_type: str
    total: int = 0
    success: int = 0
    failure: int = 0
    durations: list[float] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        return (self.success / self.total * 100) if self.total > 0 else 0.0

    @property
    def avg_duration(self) -> float:
        return (sum(self.durations) / len(self.durations)) if self.durations else 0.0


@dataclass
class EvaluationReport:
    """Complete evaluation report."""
    timestamp: float = field(default_factory=time.time)
    task_stats: dict[str, TaskStats] = field(default_factory=dict)
    failure_breakdown: dict[str, int] = field(default_factory=dict)
    total_episodes: int = 0
    overall_success_rate: float = 0.0
    trend_vs_last: Optional[float] = None
    regressions: list[str] = field(default_factory=list)

    @property
    def is_improving(self) -> bool:
        return self.trend_vs_last is not None and self.trend_vs_last > 0

    @property
    def has_regression(self) -> bool:
        return len(self.regressions) > 0


FAILURE_CATEGORIES = ["perception", "planning", "grasp", "timeout", "execution", "unknown"]


def classify_failure(result: str, failure_reason: str = "") -> str:
    """Classify a failure into a category."""
    text = f"{result} {failure_reason}".lower()
    if any(k in text for k in ["percept", "detect", "vision", "camera", "not found"]):
        return "perception"
    if any(k in text for k in ["plan", "ik", "unreachable", "no solution", "collision"]):
        return "planning"
    if any(k in text for k in ["grasp", "gripper", "attach", "drop"]):
        return "grasp"
    if any(k in text for k in ["timeout", "time out", "expired"]):
        return "timeout"
    if any(k in text for k in ["execute", "controller", "joint", "trajectory"]):
        return "execution"
    return "unknown"


class EvaluationEngine:
    """Evaluate robot performance from Episode data.

    Works with either:
    - A list of episode dicts (for testing)
    - A SQLite database path (for production)
    - A RuntimeClient (for live ROS2 queries)
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        self._db_path = db_path
        self._last_report: Optional[EvaluationReport] = None

    def evaluate(self, episodes: Optional[list[dict]] = None) -> EvaluationReport:
        """Run evaluation on episode data.

        Args:
            episodes: List of episode dicts. If None, loads from SQLite.

        Returns:
            EvaluationReport with statistics.

        """
        if episodes is None:
            episodes = self._load_from_db()

        report = EvaluationReport()
        report.total_episodes = len(episodes)

        for ep in episodes:
            task_type = ep.get("task_type", "unknown")
            result = ep.get("result", "")
            duration = ep.get("duration", 0.0)
            failure_reason = ep.get("failure_reason", "")

            if task_type not in report.task_stats:
                report.task_stats[task_type] = TaskStats(task_type=task_type)

            stats = report.task_stats[task_type]
            stats.total += 1
            stats.durations.append(duration)

            is_success = "success" in result.lower() or result == "SUCCESS"
            if is_success:
                stats.success += 1
            else:
                stats.failure += 1
                category = classify_failure(result, failure_reason)
                report.failure_breakdown[category] = report.failure_breakdown.get(category, 0) + 1

        total_success = sum(s.success for s in report.task_stats.values())
        report.overall_success_rate = (
            total_success / report.total_episodes * 100
            if report.total_episodes > 0 else 0.0
        )

        if self._last_report is not None:
            report.trend_vs_last = report.overall_success_rate - self._last_report.overall_success_rate
            report.regressions = self._detect_regressions(report, self._last_report)

        self._last_report = report
        return report

    def _detect_regressions(
        self, current: EvaluationReport, previous: EvaluationReport
    ) -> list[str]:
        """Detect regressions between current and previous reports."""
        regressions: list[str] = []
        for task_type, curr_stats in current.task_stats.items():
            if task_type in previous.task_stats:
                prev_stats = previous.task_stats[task_type]
                if prev_stats.success_rate > 0 and curr_stats.success_rate < prev_stats.success_rate:
                    regressions.append(
                        f"{task_type}: {prev_stats.success_rate:.0f}% → {curr_stats.success_rate:.0f}%"
                    )
        return regressions

    def _load_from_db(self) -> list[dict]:
        """Load episodes from SQLite database."""
        if not self._db_path or not HAS_SQLITE:
            return []
        if not Path(self._db_path).exists():
            return []
        episodes: list[dict] = []
        conn = sqlite3.connect(self._db_path)
        try:
            cursor = conn.execute("SELECT task_type, result, duration FROM episodes")
            for row in cursor:
                episodes.append({"task_type": row[0], "result": row[1], "duration": row[2]})
        except Exception:
            pass
        finally:
            conn.close()
        return episodes

    def print_report(self, report: Optional[EvaluationReport] = None) -> None:
        """Print evaluation report to stdout."""
        if report is None:
            report = self._last_report
        if report is None:
            print("No evaluation data. Run evaluate() first.")
            return

        print("\n=== Robot Evaluation Report ===")
        print()

        print(f"Task Success Rate: {report.overall_success_rate:.0f}%")
        for task_type, stats in sorted(report.task_stats.items()):
            print(f"  {task_type:20s}  {stats.success_rate:.0f}% ({stats.success}/{stats.total})")
        print()

        if report.failure_breakdown:
            total_failures = sum(report.failure_breakdown.values())
            print("Failure Breakdown:")
            for category in FAILURE_CATEGORIES:
                count = report.failure_breakdown.get(category, 0)
                if count > 0:
                    pct = count / total_failures * 100
                    print(f"  {pct:.0f}% {category}")
            print()

        if report.trend_vs_last is not None:
            trend_str = f"{report.trend_vs_last:+.0f}%"
            status = "improving" if report.trend_vs_last > 0 else "declining" if report.trend_vs_last < 0 else "stable"
            print(f"Trend vs Last: {trend_str} ({status})")
        else:
            print("Trend vs Last: N/A (first evaluation)")

        if report.has_regression:
            print()
            print("⚠ Regressions Detected:")
            for reg in report.regressions:
                print(f"  - {reg}")

        print()
        print(f"Total Episodes: {report.total_episodes}")