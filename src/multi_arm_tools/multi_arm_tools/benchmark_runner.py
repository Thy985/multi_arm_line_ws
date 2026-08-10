"""Benchmark runner — batch execute tasks and compute statistics."""

import json
import time
from typing import Any

from multi_arm_tools.trace_viewer import TraceViewer


class BenchmarkRunner:
    """Batch task execution with statistics."""

    def __init__(self, client: Any) -> None:
        self._client = client
        self._trace_viewer = TraceViewer(client)

    def run(
        self, task_type: str, count: int = 100, output_file: str | None = None
    ) -> None:
        """Run N tasks and print statistics.

        Args:
            task_type: Action type (pick_place, move, etc.)
            count: Number of executions
            output_file: Optional JSON output file path
        """
        print(f"\nRunning {count}x {task_type}...")

        results: list[dict[str, Any]] = []
        success_count = 0
        failure_count = 0
        durations: list[float] = []
        failure_reasons: dict[str, list[float]] = {}

        for i in range(count):
            self._print_progress(i, count)

            start_time = time.time()
            result = self._client.submit_task(task_type, [], "arm1")
            elapsed = time.time() - start_time

            if result is not None and result.success:
                success_count += 1
                durations.append(elapsed)
                results.append(
                    {"index": i, "success": True, "duration": elapsed}
                )
            else:
                failure_count += 1
                reason = "unknown"
                if result and result.results:
                    reason = result.results[0] if result.results else "unknown"
                failure_reasons.setdefault(reason, []).append(elapsed)
                results.append(
                    {
                        "index": i,
                        "success": False,
                        "duration": elapsed,
                        "reason": reason,
                    }
                )

        self._print_progress(count, count)
        print()

        self._print_statistics(
            count, success_count, failure_count, durations, failure_reasons
        )

        if output_file:
            self._save_results(
                output_file, task_type, count, results
            )

    def _print_progress(self, current: int, total: int) -> None:
        """Print progress bar."""
        bar_width = 40
        filled = int(bar_width * current / total) if total > 0 else 0
        bar = "#" * filled + "-" * (bar_width - filled)
        print(f"\r[{bar}] {current}/{total}", end="", flush=True)

    def _print_statistics(
        self,
        total: int,
        success_count: int,
        failure_count: int,
        durations: list[float],
        failure_reasons: dict[str, list[float]],
    ) -> None:
        """Print benchmark statistics."""
        print("Results:")
        print(f"  Total:        {total}")
        success_rate = (success_count / total * 100) if total > 0 else 0
        failure_rate = (failure_count / total * 100) if total > 0 else 0
        print(f"  Success:       {success_count}  ({success_rate:.1f}%)")
        print(f"  Failure:        {failure_count}  ({failure_rate:.1f}%)")

        if durations:
            avg_dur = sum(durations) / len(durations)
            min_dur = min(durations)
            max_dur = max(durations)
            print(f"  Avg duration:  {avg_dur:.2f}s")
            print(f"  Min/Max:       {min_dur:.2f}s / {max_dur:.2f}s")

        if failure_reasons:
            print("\nFailure breakdown:")
            for reason, dur_list in sorted(failure_reasons.items()):
                avg = sum(dur_list) / len(dur_list) if dur_list else 0
                print(f"  {reason:<25} {len(dur_list):>3}  (avg {avg:.1f}s)")

        print()

    def _save_results(
        self,
        output_file: str,
        task_type: str,
        count: int,
        results: list[dict[str, Any]],
    ) -> None:
        """Save results to JSON file."""
        output_data = {
            "task_type": task_type,
            "count": count,
            "timestamp": time.time(),
            "results": results,
            "summary": {
                "success_count": sum(1 for r in results if r["success"]),
                "failure_count": sum(1 for r in results if not r["success"]),
                "avg_duration": (
                    sum(r["duration"] for r in results) / len(results)
                    if results
                    else 0
                ),
            },
        }
        with open(output_file, "w") as f:
            json.dump(output_data, f, indent=2)
        print(f"Saved to: {output_file}")