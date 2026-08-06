"""RegressionDetector — detects performance regressions across benchmark runs.

Compares latest run metrics against historical baseline and flags
significant degradations.
"""

from typing import Any, Dict, List, Optional, Tuple


class RegressionDetector:
    """Detects performance regressions by comparing benchmark runs.

    Default thresholds:
        - success_rate: 10% relative drop
        - avg_planning_time: 30% relative increase
        - avg_execution_time: 30% relative increase
        - avg_total_time: 30% relative increase

    Usage:
        detector = RegressionDetector()
        result = detector.compare_runs(current_summary, baseline_summary)
        if result["regressed"]:
            print(f"Regressions: {result['regressions']}")
    """

    DEFAULT_THRESHOLDS: Dict[str, float] = {
        "success_rate": 0.10,
        "avg_planning_time": 0.30,
        "avg_execution_time": 0.30,
        "avg_total_time": 0.30,
    }

    HIGHER_IS_BETTER: Dict[str, bool] = {
        "success_rate": True,
        "avg_planning_time": False,
        "avg_execution_time": False,
        "avg_total_time": False,
    }

    def __init__(self, thresholds: Optional[Dict[str, float]] = None) -> None:
        self._thresholds = thresholds or dict(self.DEFAULT_THRESHOLDS)

    @property
    def thresholds(self) -> Dict[str, float]:
        return self._thresholds

    def compare_runs(
        self, current: Dict[str, Any], baseline: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Compare current run against baseline for regressions.

        Args:
            current: Current run summary (from BenchmarkRecorder.get_run_summary).
            baseline: Baseline run summary to compare against.

        Returns:
            Dict with 'regressed' (bool), 'regressions' (list), 'improvements' (list),
            'details' (dict of metric comparisons).
        """
        regressions: List[str] = []
        improvements: List[str] = []
        details: Dict[str, Dict[str, Any]] = {}

        for metric, threshold in self._thresholds.items():
            current_val = current.get(metric, 0.0)
            baseline_val = baseline.get(metric, 0.0)

            if baseline_val == 0.0 and current_val == 0.0:
                details[metric] = {
                    "current": current_val,
                    "baseline": baseline_val,
                    "change_pct": 0.0,
                    "status": "unchanged",
                }
                continue

            if baseline_val == 0.0:
                details[metric] = {
                    "current": current_val,
                    "baseline": baseline_val,
                    "change_pct": float("inf"),
                    "status": "new_metric",
                }
                continue

            change_pct = (current_val - baseline_val) / abs(baseline_val)
            higher_is_better = self.HIGHER_IS_BETTER.get(metric, False)

            if higher_is_better:
                is_regression = change_pct < -threshold
                is_improvement = change_pct > threshold
            else:
                is_regression = change_pct > threshold
                is_improvement = change_pct < -threshold

            if is_regression:
                regressions.append(metric)
                status = "regression"
            elif is_improvement:
                improvements.append(metric)
                status = "improvement"
            else:
                status = "unchanged"

            details[metric] = {
                "current": current_val,
                "baseline": baseline_val,
                "change_pct": change_pct,
                "status": status,
            }

        return {
            "regressed": len(regressions) > 0,
            "regressions": regressions,
            "improvements": improvements,
            "details": details,
        }

    def check_regression_history(
        self, history: List[Dict[str, Any]], window: int = 5
    ) -> Dict[str, Any]:
        """Check for regression trends across multiple runs.

        Args:
            history: List of run summaries (newest first).
            window: Number of recent runs to consider.

        Returns:
            Dict with trend analysis.
        """
        if len(history) < 2:
            return {"trend": "insufficient_data", "runs_analyzed": len(history)}

        recent = history[:window]
        oldest = recent[-1]
        newest = recent[0]

        comparison = self.compare_runs(newest, oldest)
        comparison["trend"] = "regressing" if comparison["regressed"] else "stable"
        comparison["runs_analyzed"] = len(recent)

        return comparison