"""Episode viewer — inspect historical episodes and failures."""

import json
from typing import Any


class EpisodeViewer:
    """Terminal viewer for episode history and replay."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def print_episodes(
        self, failures_only: bool = False, recent: int = 20
    ) -> None:
        """Print episode list."""
        filter_dict: dict[str, Any] = {"recent": recent}
        if failures_only:
            filter_dict["result"] = "failure"

        response = self._client.query_experience(
            data_type="episodes", filter_json=json.dumps(filter_dict)
        )
        if response is None or response.count == 0:
            label = "Failed episodes" if failures_only else "Episodes"
            print(f"No {label.lower()} found.")
            return

        label = "Failed Episodes" if failures_only else "Recent Episodes"
        print(f"\n{label} ({response.count}):")

        for record_json in response.records_json:
            record = json.loads(record_json)
            self._print_episode_summary(record)

        print()

    def _print_episode_summary(self, record: dict) -> None:
        """Print single episode summary line."""
        eid = record.get("episode_id", "?")
        task = record.get("task", record.get("task_type", "?"))
        result = record.get("result", "?")
        duration = record.get("duration", 0.0)
        recovery = record.get("recovery", {})
        recovery_count = recovery.get("count", 0)

        if result in ("success", "recovered"):
            icon = "[OK]"
            recovery_str = f"{recovery_count} recovery"
        else:
            icon = "[FAIL]"
            attempts = recovery.get("attempts", [])
            failure_types = [a.get("failure_type", "?") for a in attempts]
            recovery_str = (
                f"{recovery_count} recovery ({', '.join(failure_types)})"
                if failure_types
                else f"{recovery_count} recovery"
            )

        print(f"  {eid:<20} {task:<15} {icon:<6} {duration:.2f}s  {recovery_str}")

    def print_episode_detail(self, episode_id: str) -> None:
        """Print episode detail with step-by-step replay."""
        response = self._client.query_experience(
            data_type="episodes",
            filter_json=json.dumps({"episode_id": episode_id}),
        )
        if response is None or response.count == 0:
            print(f"Episode '{episode_id}' not found.")
            return

        record = json.loads(response.records_json[0])
        self._render_episode_detail(record)

    def _render_episode_detail(self, record: dict) -> None:
        """Render full episode detail."""
        eid = record.get("episode_id", "?")
        task = record.get("task", record.get("task_type", "?"))
        skill = record.get("skill", record.get("skill_name", "?"))
        robot = record.get("robot", record.get("robot_id", "?"))
        result = record.get("result", "?")
        duration = record.get("duration", 0.0)
        recovery = record.get("recovery", {})

        icon = "[OK]" if result in ("success", "recovered") else "[FAIL]"

        print(f"\nEpisode: {eid}")
        print(f"  Task:       {task}")
        print(f"  Skill:      {skill}")
        print(f"  Robot:      {robot}")
        print(f"  Result:     {icon} {result.upper()}")
        print(f"  Duration:   {duration:.2f}s")
        print(f"  Recovery:   {recovery.get('count', 0)} attempts")

        steps = record.get("execution", {}).get("steps", [])
        if steps:
            print(f"\nSteps ({len(steps)}):")
            for i, step in enumerate(steps):
                name = step.get("name", step.get("step_name", f"step_{i}"))
                success = step.get("success", True)
                step_dur = step.get("duration", 0.0)
                details = step.get("details", {})
                step_icon = "[OK]" if success else "[FAIL]"
                detail_str = f"  {details}" if details else ""
                print(
                    f"  [{i+1}] {step_dur:.1f}s  {name:<25} {step_icon}{detail_str}"
                )

        initial_world = record.get("initial_world", {})
        final_world = record.get("final_world", {})
        if initial_world or final_world:
            print("\nWorld State (initial):")
            self._print_world_snapshot(initial_world)
            print("\nWorld State (final):")
            self._print_world_snapshot(final_world)

        attempts = recovery.get("attempts", [])
        if attempts:
            print(f"\nRecovery attempts ({len(attempts)}):")
            for j, attempt in enumerate(attempts):
                ft = attempt.get("failure_type", "?")
                strategy = attempt.get("strategy", "?")
                success = attempt.get("success", False)
                icon = "[OK]" if success else "[FAIL]"
                print(f"  [{j+1}] {ft:<20} strategy={strategy:<25} {icon}")

        print()

    def _print_world_snapshot(self, world: dict) -> None:
        """Print world state snapshot."""
        objects = world.get("objects", {})
        if not objects:
            print("  (empty)")
            return
        for obj_id, obj_data in objects.items():
            pos = obj_data.get("position", [0, 0, 0])
            state = obj_data.get("grasp_state", obj_data.get("state", "?"))
            if isinstance(pos, list):
                pos_str = f"[{pos[0]:.2f}, {pos[1]:.2f}, {pos[2]:.2f}]"
            else:
                pos_str = str(pos)
            print(f"  {obj_id:<15} {pos_str}  {state}")