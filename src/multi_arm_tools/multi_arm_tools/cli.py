"""Robot Runtime CLI v2 — Operator Interface for M7/M8.

Three cognitive layers:
    1. OBSERVE:  status, doctor
    2. DIAGNOSE: world, vision, episode, skills, capability
    3. ACT:      task, safety, benchmark, evaluate

Contracts:
    - Command Contract: frozen subcommand hierarchy
    - Output Contract: human-readable by default, --json for machine
    - Exit Code Contract: 0=success, 1=error, 2=safety, 3=timeout

Usage:
    robot status                     # System overview
    robot doctor                     # System diagnosis
    robot world                      # World state
    robot world show <object>        # Object detail (belief, observations, health)
    robot vision status              # Perception pipeline
    robot vision objects             # Detected objects
    robot task run <task> [args]     # Submit task
    robot task history               # Task history
    robot run <task> [args]          # Shorthand for task run
    robot episode list               # Episode history
    robot episode show <id>          # Episode detail
    robot safety status              # Safety state
    robot safety stop                # EMERGENCY STOP (bypasses pipeline)
    robot safety check               # Safety check
    robot skills                     # Skill list
    robot capability                 # Capability graph
    robot benchmark <task>           # Batch benchmark
    robot evaluate                   # Independent evaluation
    robot sim start/stop/status      # Simulation lifecycle
    robot watch                      # Real-time dashboard

Global flags:
    --json                           # Machine-readable JSON output
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any

from multi_arm_tools.analyzer import EpisodeAnalyzer
from multi_arm_tools.benchmark_runner import BenchmarkRunner
from multi_arm_tools.doctor import Doctor
from multi_arm_tools.episode_viewer import EpisodeViewer
from multi_arm_tools.evaluator import EvaluationEngine
from multi_arm_tools.runtime_client import RuntimeClient
from multi_arm_tools.scene_manager import SceneManager
from multi_arm_tools.sim_manager import SimManager
from multi_arm_tools.task_manager import TaskManager
from multi_arm_tools.trace_viewer import TraceViewer
from multi_arm_tools.vision_query import VisionQuery
from multi_arm_tools.watcher import Watcher
from multi_arm_tools.world_query import WorldQuery

EXIT_SUCCESS = 0
EXIT_ERROR = 1
EXIT_SAFETY = 2
EXIT_TIMEOUT = 3


def _add_json_arg(parser: argparse.ArgumentParser) -> None:
    """Add --json flag to a subparser."""
    parser.add_argument("--json", dest="json_subjson", action="store_true",
                        help="Machine-readable JSON output")


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="robot", description="Robot Runtime CLI v2 — Operator Interface"
    )
    parser.add_argument("--json", dest="json_output", action="store_true",
                        help="Machine-readable JSON output")
    subparsers = parser.add_subparsers(dest="command", required=False)

    _add_lifecycle_commands(subparsers)
    _add_sim_commands(subparsers)
    _add_scene_commands(subparsers)
    _add_doctor_commands(subparsers)
    _add_status_commands(subparsers)
    _add_world_commands(subparsers)
    _add_vision_commands(subparsers)
    _add_skill_commands(subparsers)
    _add_task_commands(subparsers)
    _add_run_commands(subparsers)
    _add_episode_commands(subparsers)
    _add_safety_commands(subparsers)
    _add_trace_commands(subparsers)
    _add_benchmark_commands(subparsers)
    _add_watch_commands(subparsers)
    _add_evaluate_commands(subparsers)

    args = parser.parse_args()

    if args.command is None:
        from multi_arm_tools.interactive_shell import InteractiveShell
        sys.exit(InteractiveShell().run())

    json_sub = getattr(args, "json_subjson", False)
    args.json_output = getattr(args, "json_output", False) or json_sub
    exit_code = _dispatch(args)
    sys.exit(exit_code)


def _add_lifecycle_commands(subparsers: argparse._SubParsersAction) -> None:
    p_start = subparsers.add_parser("start", help="Start robot runtime session")
    p_start.add_argument("--gui", action="store_true", help="Show Gazebo GUI")
    p_start.add_argument("--scene", default="tabletop", help="Scene name")
    p_start.add_argument("--domain", type=int, default=None, help="DDS domain ID")
    subparsers.add_parser("stop", help="Stop robot runtime session")
    subparsers.add_parser("repair", help="Auto-repair runtime issues")
    p_restart = subparsers.add_parser("restart", help="Restart robot runtime")
    p_restart.add_argument("--gui", action="store_true")
    p_restart.add_argument("--scene", default="tabletop")


def _add_sim_commands(subparsers: argparse._SubParsersAction) -> None:
    p_sim = subparsers.add_parser("sim", help="Simulation lifecycle")
    sim_sub = p_sim.add_subparsers(dest="sim_command", required=True)
    p_start = sim_sub.add_parser("start", help="Start simulation")
    p_start.add_argument("--gui", action="store_true")
    p_start.add_argument("--scene", default="tabletop")
    sim_sub.add_parser("stop", help="Stop simulation")
    sim_sub.add_parser("status", help="Simulation status")


def _add_scene_commands(subparsers: argparse._SubParsersAction) -> None:
    p_scene = subparsers.add_parser("scene", help="Scene management")
    scene_sub = p_scene.add_subparsers(dest="scene_command", required=True)
    scene_sub.add_parser("list", help="List scenes")
    p_show = scene_sub.add_parser("show", help="Show scene details")
    p_show.add_argument("scene_name")


def _add_doctor_commands(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("doctor", help="System diagnosis")
    _add_json_arg(p)


def _add_status_commands(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("status", help="System overview")
    _add_json_arg(p)


def _add_world_commands(subparsers: argparse._SubParsersAction) -> None:
    p_world = subparsers.add_parser("world", help="World model state")
    p_world.add_argument("object_id", nargs="?", default=None)
    p_world.add_argument("--relations", action="store_true")
    _add_json_arg(p_world)


def _add_vision_commands(subparsers: argparse._SubParsersAction) -> None:
    p_vision = subparsers.add_parser("vision", help="Perception layer")
    vision_sub = p_vision.add_subparsers(dest="vision_command", required=True)
    p_vs = vision_sub.add_parser("status", help="Vision pipeline status")
    _add_json_arg(p_vs)
    p_vo = vision_sub.add_parser("objects", help="Detected objects")
    _add_json_arg(p_vo)


def _add_skill_commands(subparsers: argparse._SubParsersAction) -> None:
    p1 = subparsers.add_parser("skills", help="List registered skills")
    _add_json_arg(p1)
    p2 = subparsers.add_parser("capability", help="Three-layer capability")
    _add_json_arg(p2)


def _add_task_commands(subparsers: argparse._SubParsersAction) -> None:
    p_task = subparsers.add_parser("task", help="Task management")
    task_sub = p_task.add_subparsers(dest="task_command", required=True)
    task_sub.add_parser("list", help="List task types")
    task_sub.add_parser("positions", help="List preset positions")
    p_run = task_sub.add_parser("run", help="Submit task")
    p_run.add_argument("task_type", help="Task type")
    p_run.add_argument("args", nargs="*", help="Task arguments")
    p_run.add_argument("--arm", default=None)
    p_run.add_argument("--no-trace", action="store_true")
    p_run.add_argument("--debug", action="store_true")
    task_sub.add_parser("history", help="Task history")


def _add_run_commands(subparsers: argparse._SubParsersAction) -> None:
    p_run = subparsers.add_parser("run", help="Submit task (shorthand for task run)")
    p_run.add_argument("task_type")
    p_run.add_argument("args", nargs="*")
    p_run.add_argument("--arm", default=None)
    p_run.add_argument("--no-trace", action="store_true")
    p_run.add_argument("--debug", action="store_true")
    _add_json_arg(p_run)


def _add_episode_commands(subparsers: argparse._SubParsersAction) -> None:
    p_ep = subparsers.add_parser("episode", help="Episode detail or subcommand")
    p_ep.add_argument("subcommand_or_id", nargs="?", default=None,
                      help="episode_id, 'list', or 'show <id>'")
    p_ep.add_argument("episode_id", nargs="?", default=None,
                      help="Episode ID (when subcommand is 'show')")
    p_ep.add_argument("--failures-only", action="store_true")
    p_ep.add_argument("--recent", type=int, default=20)
    _add_json_arg(p_ep)

    p_eps = subparsers.add_parser("episodes", help="Episode history (shorthand)")
    p_eps.add_argument("--failures-only", action="store_true")
    p_eps.add_argument("--recent", type=int, default=20)
    _add_json_arg(p_eps)

    p_an = subparsers.add_parser("analyze", help="Deep episode analysis")
    p_an.add_argument("episode_id")


def _add_safety_commands(subparsers: argparse._SubParsersAction) -> None:
    p_safety = subparsers.add_parser("safety", help="Safety supervisor")
    safety_sub = p_safety.add_subparsers(dest="safety_command", required=True)
    p_ss = safety_sub.add_parser("status", help="Safety state")
    _add_json_arg(p_ss)
    p_sc = safety_sub.add_parser("check", help="Safety check")
    _add_json_arg(p_sc)
    safety_sub.add_parser("stop", help="EMERGENCY STOP (bypasses pipeline)")


def _add_trace_commands(subparsers: argparse._SubParsersAction) -> None:
    p_tr = subparsers.add_parser("traces", help="Trace history")
    p_tr.add_argument("--recent", type=int, default=20)
    p_t = subparsers.add_parser("trace", help="Trace detail")
    p_t.add_argument("trace_id")


def _add_benchmark_commands(subparsers: argparse._SubParsersAction) -> None:
    p_bm = subparsers.add_parser("benchmark", help="Batch benchmark")
    p_bm.add_argument("task_type")
    p_bm.add_argument("--count", type=int, default=100)
    p_bm.add_argument("--output", default=None)


def _add_watch_commands(subparsers: argparse._SubParsersAction) -> None:
    p_w = subparsers.add_parser("watch", help="Real-time dashboard")
    p_w.add_argument("--duration", type=float, default=0.0)


def _add_evaluate_commands(subparsers: argparse._SubParsersAction) -> None:
    p_ev = subparsers.add_parser("evaluate", help="Independent evaluation")
    p_ev.add_argument("--db", default=None)


def _dispatch(args: argparse.Namespace) -> int:
    """Dispatch command. Returns exit code."""
    json_output = getattr(args, "json_output", False)

    if args.command in ("start", "stop", "repair", "restart"):
        return _dispatch_lifecycle(args)
    if args.command == "sim":
        return _dispatch_sim(args)
    if args.command == "scene":
        return _dispatch_scene(args)
    if args.command == "evaluate":
        engine = EvaluationEngine(db_path=getattr(args, "db", None))
        report = engine.evaluate()
        engine.print_report(report)
        return EXIT_SUCCESS
    if args.command == "doctor":
        Doctor().run()
        return EXIT_SUCCESS
    if args.command == "watch":
        Watcher(duration=args.duration).watch()
        return EXIT_SUCCESS

    if args.command == "safety":
        return _dispatch_safety(args, json_output)

    if args.command == "task":
        return _dispatch_task(args, json_output)

    client = RuntimeClient()
    try:

        if args.command == "status":
            return _cmd_status(client, json_output)
        elif args.command == "world":
            WorldQuery(client).print_world(args.object_id, args.relations)
            return EXIT_SUCCESS
        elif args.command == "vision":
            return _cmd_vision(client, args, json_output)
        elif args.command == "skills":
            return _cmd_skills(client, json_output)
        elif args.command == "capability":
            return _cmd_capability(client, json_output)
        elif args.command == "run":
            return _cmd_run(client, args, json_output)
        elif args.command == "episode":
            return _cmd_episode(client, args, json_output)
        elif args.command == "episodes":
            EpisodeViewer(client).print_episodes(args.failures_only, args.recent)
            return EXIT_SUCCESS
        elif args.command == "analyze":
            EpisodeAnalyzer(client).analyze(args.episode_id)
            return EXIT_SUCCESS
        elif args.command == "traces":
            TraceViewer(client).print_traces(args.recent)
            return EXIT_SUCCESS
        elif args.command == "trace":
            TraceViewer(client).print_trace_detail(args.trace_id)
            return EXIT_SUCCESS
        elif args.command == "benchmark":
            BenchmarkRunner(client).run(args.task_type, args.count, args.output)
            return EXIT_SUCCESS
    except KeyboardInterrupt:
        print("\nInterrupted.")
        return EXIT_ERROR
    finally:
        client.shutdown()

    return EXIT_ERROR


def _dispatch_lifecycle(args: argparse.Namespace) -> int:
    """Handle start/stop/repair/restart lifecycle commands."""
    from multi_arm_tools.runtime_manager import RuntimeManager
    mgr = RuntimeManager()

    if args.command == "start":
        existing = mgr.get_active_session()
        if existing and existing.status == "running":
            print(f"\n  Session already active: {existing.session_id}")
            print(f"  Domain: {existing.domain_id}, Scene: {existing.scene}")
            print(f"  Use 'robot stop' first.\n")
            return EXIT_ERROR
        if existing and existing.status == "stale":
            print("\n  Stale session detected, auto-repairing...")
            mgr.repair()
            print()
        try:
            manifest = mgr.create_session(
                scene=getattr(args, "scene", "tabletop"),
                gui=getattr(args, "gui", False),
                domain_id=getattr(args, "domain", None),
            )
        except RuntimeError as e:
            print(f"\n  Error: {e}\n")
            return EXIT_ERROR
        print(f"\n  Session: {manifest.session_id}")
        print(f"  Domain:  {manifest.domain_id}")
        print(f"  Scene:   {manifest.scene}")
        print(f"  Launching simulation...")
        proc = mgr.start_session(manifest)
        if proc is None:
            print("  [FAIL] Could not start launch process.\n")
            return EXIT_ERROR
        print(f"  PID:     {proc.pid}")
        print("  Waiting for nodes to initialize (30s)...")
        time.sleep(30)
        print("  [OK] Session started.\n")
        return EXIT_SUCCESS

    if args.command == "stop":
        session = mgr.get_active_session()
        if session is None:
            print("\n  No active session.\n")
            return EXIT_ERROR
        print(f"\n  Stopping session {session.session_id}...")
        mgr.stop_session(session)
        print("  [OK] Session stopped.\n")
        return EXIT_SUCCESS

    if args.command == "repair":
        print("\n  Detecting runtime issues...")
        report = mgr.repair()
        killed = report.get("killed_zombies", [])
        dupes = report.get("killed_duplicates", [])
        cleaned = report.get("cleaned_sessions", [])
        dds_reset = report.get("dds_reset", False)
        errors = report.get("errors", [])
        if killed:
            print(f"\n  ✓ Killed {len(killed)} zombie process(es):")
            for z in killed:
                print(f"    {z['name']} (PID {z['pid']})")
        if dupes:
            print(f"  ✓ Killed {len(dupes)} duplicate process(es):")
            for z in dupes:
                print(f"    {z['name']} (PID {z['pid']})")
        if dds_reset:
            print("  ✓ DDS daemon restarted (ghost nodes cleared)")
        if cleaned:
            print(f"  ✓ Cleaned {len(cleaned)} stale session(s)")
        if errors:
            print(f"  ⚠ {len(errors)} error(s):")
            for e in errors:
                print(f"    {e}")
        if not killed and not dupes and not cleaned and not errors and not dds_reset:
            print("  No issues found. Runtime is clean.")
        print()
        return EXIT_SUCCESS

    if args.command == "restart":
        session = mgr.get_active_session()
        if session:
            print("\n  Stopping current session...")
            mgr.stop_session(session)
            time.sleep(2)
        return _dispatch_lifecycle(
            argparse.Namespace(
                command="start",
                gui=getattr(args, "gui", False),
                scene=getattr(args, "scene", "tabletop"),
                domain=None,
            )
        )

    return EXIT_ERROR


def _dispatch_sim(args: argparse.Namespace) -> int:
    mgr = SimManager()
    if args.sim_command == "start":
        mgr.start(gui=args.gui, scene=getattr(args, "scene", "tabletop"))
    elif args.sim_command == "stop":
        mgr.stop()
    elif args.sim_command == "status":
        mgr.status()
    return EXIT_SUCCESS


def _dispatch_scene(args: argparse.Namespace) -> int:
    mgr = SceneManager()
    if args.scene_command == "list":
        mgr.print_list()
    elif args.scene_command == "show":
        mgr.print_scene(args.scene_name)
    return EXIT_SUCCESS


def _dispatch_safety(args: argparse.Namespace, json_output: bool) -> int:
    """Dispatch safety subcommands — direct to SafetySupervisor."""
    client = RuntimeClient()
    try:
        if args.safety_command == "stop":
            success, message = client.emergency_stop()
            if json_output:
                print(json.dumps({"success": success, "message": message}))
            else:
                if success:
                    print("● EMERGENCY STOP ACTIVATED")
                    print(f"  {message}")
                else:
                    print(f"✗ Emergency stop failed: {message}")
            return EXIT_SAFETY if success else EXIT_ERROR

        elif args.safety_command == "check":
            approved, scale, message = client.safety_check()
            if json_output:
                print(json.dumps({
                    "approved": approved, "speed_scale": scale, "message": message
                }))
            else:
                print("\nSAFETY CHECK")
                print(f"  approved:     {'✓ YES' if approved else '✗ NO'}")
                print(f"  speed_scale:  {scale:.2f}")
                print(f"  message:      {message}")
            return EXIT_SUCCESS if approved else EXIT_SAFETY

        elif args.safety_command == "status":
            approved, scale, message = client.safety_check()
            if json_output:
                print(json.dumps({
                    "supervisor": "active" if approved else "triggered",
                    "speed_scale": scale,
                    "message": message,
                    "authority": "Safety > Coordinator > Skill > Task",
                }))
            else:
                print("\nSAFETY")
                print("-" * 40)
                print(f"  Supervisor       {'● ACTIVE' if approved else '● TRIGGERED'}")
                print(f"  Speed scale      {scale:.2f}")
                print(f"  Message          {message}")
                print()
                print("Authority:")
                print("  Safety > Coordinator > Skill > Task")
            return EXIT_SUCCESS
    finally:
        client.shutdown()
    return EXIT_ERROR


def _dispatch_task(args: argparse.Namespace, json_output: bool) -> int:
    """Dispatch task subcommands."""
    client = RuntimeClient()
    try:
        tm = TaskManager(client)
        if args.task_command == "list":
            tm.list_tasks()
            return EXIT_SUCCESS
        elif args.task_command == "positions":
            tm.list_positions()
            return EXIT_SUCCESS
        elif args.task_command == "run":
            return _cmd_run(client, args, json_output)
        elif args.task_command == "history":
            EpisodeViewer(client).print_episodes(False, 20)
            return EXIT_SUCCESS
    finally:
        client.shutdown()
    return EXIT_ERROR


def _cmd_run(client: RuntimeClient, args: argparse.Namespace, json_output: bool) -> int:
    """Handle run command."""
    if getattr(args, "debug", False):
        TaskManager(client).run_debug(
            args.task_type, args.args, args.arm or ""
        )
        return EXIT_SUCCESS

    result = client.submit_task(args.task_type, args.args, args.arm or "")
    if result is None:
        if json_output:
            print(json.dumps({"success": False, "error": "task submission failed"}))
        return EXIT_ERROR

    if json_output:
        print(json.dumps({
            "success": result.success,
            "success_count": result.success_count,
            "total_count": result.total_count,
            "results": [str(r) for r in result.results],
        }))
    else:
        if not getattr(args, "no_trace", False):
            TraceViewer(client).print_live_trace(
                args.task_type, args.args, args.arm or ""
            )
        else:
            print(f"Success: {result.success}")
            print(f"  {result.success_count}/{result.total_count}")
            for r in result.results:
                print(f"  {r}")

    return EXIT_SUCCESS if result.success else EXIT_ERROR


def _cmd_status(client: RuntimeClient, json_output: bool) -> int:
    """Print enhanced system overview — answers 6 operator questions."""
    world_resp = client.query_world()
    skills_resp = client.list_skills()
    cap_resp = client.get_capability()
    ep_resp = client.query_experience(
        data_type="episodes", filter_json='{"recent": 100}'
    )

    status_data: dict[str, Any] = {}

    obj_count = len(world_resp.object_states) if world_resp else 0
    rel_count = len(world_resp.relations) if world_resp else 0
    objects = world_resp.object_states if world_resp else []
    uncertain_count = sum(1 for o in objects if o.uncertain)
    contradiction_count = sum(1 for o in objects if o.contradiction)
    stale_count = sum(1 for o in objects if o.ttl > 0 and o.updated_at > 0 and (time.time() - o.updated_at > o.ttl)) if world_resp else 0

    skill_count = len(skills_resp.skills) if skills_resp else 0
    skill_ready = skill_count

    cap_total = len(cap_resp.capabilities) if cap_resp else 0
    cap_available = sum(1 for c in cap_resp.capabilities if c.available) if cap_resp else 0

    ep_count = ep_resp.count if ep_resp else 0
    ep_success = 0
    ep_failure = 0
    last_task = None
    if ep_resp and ep_resp.count > 0:
        for rj in ep_resp.records_json:
            r = json.loads(rj)
            if r.get("result") in ("success", "recovered"):
                ep_success += 1
            else:
                ep_failure += 1
        last_record = json.loads(ep_resp.records_json[-1])
        last_task = {
            "task": last_record.get("task", "?"),
            "result": last_record.get("result", "?"),
            "duration": last_record.get("duration", 0.0),
            "episode_id": last_record.get("episode_id", "?"),
        }

    status_data = {
        "system": "READY",
        "world": {
            "objects": obj_count,
            "observed": obj_count,
            "uncertain": uncertain_count,
            "conflicts": contradiction_count,
            "stale": stale_count,
            "relations": rel_count,
        },
        "skills": {"ready": skill_ready, "total": skill_count},
        "capability": {"available": cap_available, "total": cap_total},
        "episodes": {"total": ep_count, "success": ep_success, "failure": ep_failure},
        "last_task": last_task,
    }

    if json_output:
        print(json.dumps(status_data, indent=2))
        return EXIT_SUCCESS

    print()
    print("╭" + "─" * 46 + "╮")
    print("│ ROBOT STATUS" + " " * 33 + "│")
    print("├" + "─" * 46 + "┤")
    print(f"│ System       ● {status_data['system']:<29}│")
    print(f"│ Skills       {skill_ready}/{skill_count} READY{' ' * (29 - len(f'{skill_ready}/{skill_count} READY'))}│")
    print(f"│ Capability   {cap_available}/{cap_total} AVAILABLE{' ' * (29 - len(f'{cap_available}/{cap_total} AVAILABLE'))}│")
    print("╰" + "─" * 46 + "╯")
    print()

    print("WORLD")
    print(f"  Objects    {obj_count}")
    print(f"  Observed   {obj_count}")
    print(f"  Uncertain  {uncertain_count}")
    print(f"  Conflicts  {contradiction_count}")
    print(f"  Stale      {stale_count}")
    print()

    if objects:
        print("OBJECTS")
        for o in objects:
            pos = o.pose.position
            src = o.source if o.source else "unknown"
            flags = []
            if o.uncertain:
                flags.append("UNCERTAIN")
            if o.contradiction:
                flags.append("CONFLICT")
            flag_str = f" [{' '.join(flags)}]" if flags else ""
            print(f"  {o.object_id:<15} [{pos[0]:6.2f}, {pos[1]:6.2f}, {pos[2]:6.2f}]  "
                  f"conf={o.confidence:.2f}  src={src}{flag_str}")
        print()

    if skills_resp and skills_resp.skills:
        print(f"SKILLS ({skill_count})")
        for skill in skills_resp.skills:
            print(f"  {skill.name:<20} v{skill.version}  success={skill.success_rate:.2f}")
        print()

    if last_task:
        print("LAST TASK")
        print(f"  {last_task['task']} → {last_task['result'].upper()}")
        print(f"  duration: {last_task['duration']:.1f}s")
        print(f"  episode: {last_task['episode_id']}")
        print()

    print(f"EPISODES: {ep_count} ({ep_success} success, {ep_failure} failure)")
    print()

    return EXIT_SUCCESS



def _cmd_vision(client: RuntimeClient, args: argparse.Namespace, json_output: bool) -> int:
    """Handle vision commands."""
    vq = VisionQuery(client)
    if args.vision_command == "status":
        vq.print_status(json_output=json_output)
    elif args.vision_command == "objects":
        vq.print_objects(json_output=json_output)
    return EXIT_SUCCESS


def _cmd_episode(client: RuntimeClient, args: argparse.Namespace, json_output: bool) -> int:
    """Handle episode commands.

    Supports:
        robot episode              → list
        robot episode list         → list
        robot episode show <id>    → detail
        robot episode <id>         → detail (backward compat)
    """
    viewer = EpisodeViewer(client)
    sub = getattr(args, "subcommand_or_id", None)

    if sub is None:
        viewer.print_episodes(False, 20)
    elif sub == "list":
        viewer.print_episodes(getattr(args, "failures_only", False), args.recent)
    elif sub == "show":
        eid = getattr(args, "episode_id", None)
        if eid:
            viewer.print_episode_detail(eid)
        else:
            viewer.print_episodes(False, 20)
    else:
        viewer.print_episode_detail(sub)

    return EXIT_SUCCESS


def _cmd_skills(client: RuntimeClient, json_output: bool) -> int:
    """Print registered skills."""
    response = client.list_skills()
    if response is None:
        return EXIT_ERROR

    if json_output:
        skills = [
            {"name": s.name, "version": s.version, "success_rate": s.success_rate}
            for s in response.skills
        ]
        print(json.dumps({"skills": skills}, indent=2))
        return EXIT_SUCCESS

    if not response.skills:
        print("No skills registered.")
        return EXIT_SUCCESS

    print(f"\nRegistered Skills ({len(response.skills)}):")
    print()
    for skill in response.skills:
        print(f"  {skill.name:<20} v{skill.version}")
        if skill.description:
            print(f"    {skill.description}")
        print(f"    cost: {skill.cost_time:.1f}s  success_rate: {skill.success_rate:.2f}")
        if skill.required_capabilities:
            print(f"    requires: {', '.join(skill.required_capabilities)}")
        print()

    return EXIT_SUCCESS


def _cmd_capability(client: RuntimeClient, json_output: bool) -> int:
    """Print three-layer capability."""
    response = client.get_capability()
    if response is None:
        return EXIT_ERROR

    if json_output:
        caps = [
            {"name": c.name, "category": c.category, "available": c.available}
            for c in response.capabilities
        ]
        print(json.dumps({"capabilities": caps}, indent=2))
        return EXIT_SUCCESS

    if not response.capabilities:
        print("No capabilities found.")
        return EXIT_SUCCESS

    categories: dict[str, list] = {}
    for cap in response.capabilities:
        categories.setdefault(cap.category, []).append(cap)

    print(f"\nThree-Layer Capability ({len(response.capabilities)}):")
    print()
    for category, caps in sorted(categories.items()):
        print(f"  [{category}]")
        for cap in caps:
            icon = "[x]" if cap.available else "[ ]"
            value_str = f" = {cap.value}" if cap.value else ""
            reason_str = f"  ({cap.reason})" if cap.reason and not cap.available else ""
            print(f"    {icon} {cap.name:<25}{value_str}{reason_str}")
        print()

    return EXIT_SUCCESS


if __name__ == "__main__":
    import time
    main()
