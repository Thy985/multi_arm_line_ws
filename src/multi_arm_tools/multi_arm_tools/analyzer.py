"""Episode analyzer — deep analysis of execution failures (AI Debugger)."""

import json
from typing import Any

from multi_arm_tools.runtime_client import RuntimeClient


class EpisodeAnalyzer:
    """Deep analysis of episode execution — root cause and improvement suggestions."""

    def __init__(self, client: RuntimeClient) -> None:
        self._client = client

    def analyze(self, episode_id: str) -> None:
        """Analyze an episode in depth.

        Args:
            episode_id: The episode to analyze
        """
        response = self._client.query_experience(
            data_type="episodes",
            filter_json=json.dumps({"episode_id": episode_id}),
        )
        if response is None or response.count == 0:
            print(f"Episode '{episode_id}' not found.")
            return

        record = json.loads(response.records_json[0])
        self._render_analysis(record)

    def _render_analysis(self, record: dict) -> None:
        """Render full episode analysis."""
        eid = record.get("episode_id", "?")
        task = record.get("task", record.get("task_type", "?"))
        skill = record.get("skill", record.get("skill_name", "?"))
        result = record.get("result", "?")
        duration = record.get("duration", 0.0)

        print(f"\n=== Episode Analysis ===")
        print(f"  ID: {eid}")
        print(f"  Task: {task}")
        print(f"  Skill: {skill}")
        print(f"  Result: {result.upper()}")
        print(f"  Duration: {duration:.2f}s")
        print()

        steps = record.get("execution", {}).get("steps", [])
        failure_step = self._find_failure_step(steps)
        if failure_step:
            self._analyze_failure(failure_step, steps)
        else:
            print("  No failure detected — episode succeeded.")
            print()
            self._analyze_success(record)

        self._analyze_world_change(record)
        self._analyze_recovery(record)
        self._suggest_improvements(record, failure_step)

    def _find_failure_step(self, steps: list[dict]) -> dict | None:
        """Find the first failing step."""
        for step in steps:
            if not step.get("success", True):
                return step
        return None

    def _analyze_failure(self, failure_step: dict, all_steps: list[dict]) -> None:
        """Analyze the failure point."""
        name = failure_step.get("name", failure_step.get("step_name", "?"))
        idx = all_steps.index(failure_step)

        print("  Failure Point:")
        print(f"    Step {idx + 1}: {name}")
        print()

        details = failure_step.get("details", {})
        if details:
            print("    Details:")
            for k, v in details.items():
                print(f"      {k}: {v}")
            print()

        if idx > 0:
            print("    Context (previous steps):")
            for i in range(max(0, idx - 2), idx):
                prev = all_steps[i]
                prev_name = prev.get("name", prev.get("step_name", f"step_{i}"))
                prev_success = "[OK]" if prev.get("success", True) else "[FAIL]"
                print(f"      [{i+1}] {prev_name} {prev_success}")
            print()

    def _analyze_success(self, record: dict) -> None:
        """Analyze a successful episode for performance insights."""
        steps = record.get("execution", {}).get("steps", [])
        if not steps:
            return

        durations = [s.get("duration", 0.0) for s in steps]
        total = sum(durations)
        if total > 0:
            print("  Performance Breakdown:")
            for i, step in enumerate(steps):
                name = step.get("name", step.get("step_name", f"step_{i}"))
                dur = step.get("duration", 0.0)
                pct = dur / total * 100 if total > 0 else 0
                bar = "#" * int(pct / 5)
                print(f"    [{i+1}] {name:<25} {dur:.2f}s ({pct:.0f}%) {bar}")
            print()

    def _analyze_world_change(self, record: dict) -> None:
        """Analyze world state changes."""
        initial = record.get("initial_world", {})
        final = record.get("final_world", {})
        initial_objects = initial.get("objects", {})
        final_objects = final.get("objects", {})

        if not initial_objects and not final_objects:
            return

        print("  World State Changes:")
        all_ids = set(initial_objects.keys()) | set(final_objects.keys())
        for obj_id in sorted(all_ids):
            init = initial_objects.get(obj_id, {})
            fin = final_objects.get(obj_id, {})
            init_state = init.get("grasp_state", init.get("state", "?"))
            fin_state = fin.get("grasp_state", fin.get("state", "?"))
            if init_state != fin_state:
                print(f"    {obj_id}: {init_state} -> {fin_state}")
            init_pos = init.get("position", [])
            fin_pos = fin.get("position", [])
            if init_pos and fin_pos and init_pos != fin_pos:
                dx = fin_pos[0] - init_pos[0] if len(fin_pos) > 0 and len(init_pos) > 0 else 0
                dy = fin_pos[1] - init_pos[1] if len(fin_pos) > 1 and len(init_pos) > 1 else 0
                dz = fin_pos[2] - init_pos[2] if len(fin_pos) > 2 and len(init_pos) > 2 else 0
                print(f"    {obj_id} moved: dx={dx:.3f} dy={dy:.3f} dz={dz:.3f}")
        print()

    def _analyze_recovery(self, record: dict) -> None:
        """Analyze recovery attempts."""
        recovery = record.get("recovery", {})
        attempts = recovery.get("attempts", [])
        if not attempts:
            return

        print(f"  Recovery Analysis ({len(attempts)} attempts):")
        for i, attempt in enumerate(attempts):
            ft = attempt.get("failure_type", "?")
            strategy = attempt.get("strategy", "?")
            success = attempt.get("success", False)
            icon = "[OK]" if success else "[FAIL]"
            print(f"    [{i+1}] {ft} -> strategy: {strategy} {icon}")
        print()

    def _suggest_improvements(
        self, record: dict, failure_step: dict | None
    ) -> None:
        """Suggest improvements based on analysis."""
        suggestions: list[str] = []
        result = record.get("result", "")

        if failure_step:
            name = failure_step.get("name", "")
            details = failure_step.get("details", {})

            if "grasp" in name.lower():
                suggestions.append(
                    "Grasp failure: Increase perception frequency or adjust grasp tolerance"
                )
                if details.get("force"):
                    suggestions.append(
                        f"Force threshold not met: {details['force']}"
                    )

            if "planning" in name.lower():
                suggestions.append(
                    "Planning failure: Try relaxing position tolerances or alternative approach"
                )

            if "safety" in name.lower():
                suggestions.append(
                    "Safety rejection: Check workspace limits and collision scene"
                )

        recovery = record.get("recovery", {})
        if recovery.get("count", 0) > 2:
            suggestions.append(
                f"High recovery count ({recovery['count']}): "
                "Consider improving initial perception quality"
            )

        duration = record.get("duration", 0.0)
        if duration > 15.0:
            suggestions.append(
                f"Long duration ({duration:.1f}s): "
                "Consider optimizing trajectory planning"
            )

        if suggestions:
            print("  Suggested Improvements:")
            for s in suggestions:
                print(f"    -> {s}")
        else:
            print("  No improvements suggested — execution looks healthy.")
        print()