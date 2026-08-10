"""Trace viewer — renders Skill execution trace in terminal."""

import json
from datetime import datetime
from typing import Any


class TraceViewer:
    """Terminal renderer for Skill execution traces."""

    EVENT_ICONS = {
        "task_received": "[>]",
        "skill_selected": "[*]",
        "precondition_check": "[?]",
        "safety_check": "[S]",
        "execute_start": "[>]",
        "execute_end": "[.]",
        "postcondition_check": "[?]",
        "recovery": "[R]",
        "success": "[OK]",
        "failure": "[FAIL]",
    }

    def __init__(self, client: Any) -> None:
        self._client = client

    def print_traces(self, recent: int = 20) -> None:
        """Print trace history list from episodes."""
        response = self._client.query_experience(
            data_type="episodes",
            filter_json=json.dumps({"recent": recent}),
        )
        if response is None or response.count == 0:
            print("No traces found.")
            return

        print(f"\nRecent Traces ({response.count}):")
        for record_json in response.records_json:
            record = json.loads(record_json)
            trace_id = record.get("episode_id", "?")
            task = record.get("task", record.get("task_type", "?"))
            result = record.get("result", "?")
            duration = record.get("duration", 0.0)
            steps = record.get("execution", {}).get("steps", [])
            icon = "[OK]" if result in ("success", "recovered") else "[FAIL]"
            print(
                f"  {trace_id:<20} {task:<15} {icon:<6} "
                f"{duration:.2f}s  {len(steps)} events"
            )
        print()

    def print_trace_detail(self, trace_id: str) -> None:
        """Print full trace with all events."""
        response = self._client.query_experience(
            data_type="episodes",
            filter_json=json.dumps({"episode_id": trace_id}),
        )
        if response is None or response.count == 0:
            print(f"Trace '{trace_id}' not found.")
            return

        record = json.loads(response.records_json[0])
        self._render_trace_from_record(record)

    def print_live_trace(
        self, task_type: str, args: list[str], arm_name: str = ""
    ) -> None:
        """Submit task and stream live trace output."""
        print(f"\nTask submitted: {task_type}({' '.join(args)})")
        print()

        def on_feedback(feedback: Any) -> None:
            ts = datetime.now().strftime("%H:%M:%S")
            print(f"[{ts}] {feedback.current_goal} ({feedback.progress*100:.0f}%)")

        result = self._client.submit_task(
            task_type, args, arm_name, on_feedback=on_feedback
        )

        if result is None:
            print("\nTask failed: no result returned.")
            return

        if result.success:
            print(f"\n[OK] SUCCESS")
            print(f"  Success: {result.success_count}/{result.total_count}")
            if result.results:
                for r in result.results:
                    print(f"  {r}")
        else:
            print(f"\n[FAIL] FAILURE")
            print(f"  Success: {result.success_count}/{result.total_count}")
            if result.results:
                for r in result.results:
                    print(f"  {r}")
        print()

    def _render_trace_from_record(self, record: dict) -> None:
        """Render trace from an episode record dict."""
        trace_id = record.get("episode_id", "?")
        task = record.get("task", record.get("task_type", "?"))
        skill = record.get("skill", record.get("skill_name", "?"))
        result = record.get("result", "?")
        duration = record.get("duration", 0.0)
        recovery_count = record.get("recovery", {}).get("count", 0)

        icon = "[OK]" if result in ("success", "recovered") else "[FAIL]"

        print(f"\nTrace: {trace_id}    Status: {icon}    Duration: {duration:.2f}s")
        print(f"Task: {task}  Skill: {skill}  Recovery: {recovery_count}")
        print()

        steps = record.get("execution", {}).get("steps", [])
        if steps:
            print("Events:")
            for i, step in enumerate(steps):
                name = step.get("name", step.get("step_name", f"step_{i}"))
                success = step.get("success", True)
                step_dur = step.get("duration", 0.0)
                details = step.get("details", {})
                step_icon = "[OK]" if success else "[FAIL]"

                print(f"  [{i+1}] {step_dur:.1f}s  {name:<25} {step_icon}")
                if details:
                    for k, v in details.items():
                        print(f"       {k}: {v}")

        recovery = record.get("recovery", {})
        attempts = recovery.get("attempts", [])
        if attempts:
            print(f"\nRecovery ({recovery.get('count', 0)} attempts):")
            for j, attempt in enumerate(attempts):
                ft = attempt.get("failure_type", "?")
                strategy = attempt.get("strategy", "?")
                success = attempt.get("success", False)
                icon = "[OK]" if success else "[FAIL]"
                print(f"  [{j+1}] {ft:<20} {strategy:<25} {icon}")

        print()