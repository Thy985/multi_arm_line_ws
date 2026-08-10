"""Robot Runtime CLI — kubectl for robots.

Usage:
    robot sim start [--gui]         # Start full simulation stack
    robot sim stop                  # Stop simulation
    robot sim status                # Check simulation status
    robot doctor                    # Environment diagnosis
    robot status                    # System overview
    robot world [object_id]         # World state query
    robot world --relations         # Relations graph
    robot skills                    # Registered skill list
    robot capability                # Three-layer capability
    robot task list                 # List available task types
    robot task positions            # List preset positions
    robot run <task_type> [args]    # Submit task with live trace
    robot run <task_type> --debug   # Debug mode with detailed analysis
    robot episodes [--failures-only]  # Episode history
    robot episode <id>              # Episode detail + trace replay
    robot analyze <id>              # Deep episode analysis (AI Debugger)
    robot traces [--recent N]       # Trace history
    robot trace <id>                # Trace detail
    robot benchmark <task_type>     # Batch benchmark
    robot watch [--duration N]      # Real-time dashboard
"""

import argparse
import sys

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
from multi_arm_tools.watcher import Watcher
from multi_arm_tools.world_query import WorldQuery


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="robot", description="Robot Runtime CLI — kubectl for robots"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    _add_sim_commands(subparsers)
    _add_scene_commands(subparsers)
    _add_doctor_commands(subparsers)
    _add_status_commands(subparsers)
    _add_world_commands(subparsers)
    _add_skill_commands(subparsers)
    _add_task_commands(subparsers)
    _add_run_commands(subparsers)
    _add_episode_commands(subparsers)
    _add_trace_commands(subparsers)
    _add_benchmark_commands(subparsers)
    _add_watch_commands(subparsers)
    _add_evaluate_commands(subparsers)

    args = parser.parse_args()
    _dispatch(args)


def _add_sim_commands(subparsers: argparse._SubParsersAction) -> None:
    """Add sim start/stop/status commands."""
    p_sim = subparsers.add_parser("sim", help="Simulation lifecycle management")
    sim_sub = p_sim.add_subparsers(dest="sim_command", required=True)

    p_start = sim_sub.add_parser("start", help="Start full simulation stack")
    p_start.add_argument("--gui", action="store_true", help="Show Gazebo GUI")
    p_start.add_argument("--scene", default="tabletop", help="Scene name (tabletop, home, warehouse, lab)")

    sim_sub.add_parser("stop", help="Stop simulation")
    sim_sub.add_parser("status", help="Check simulation status")


def _add_scene_commands(subparsers: argparse._SubParsersAction) -> None:
    """Add scene list/show commands."""
    p_scene = subparsers.add_parser("scene", help="Scene asset management")
    scene_sub = p_scene.add_subparsers(dest="scene_command", required=True)
    scene_sub.add_parser("list", help="List all available scenes")
    p_show = scene_sub.add_parser("show", help="Show scene details")
    p_show.add_argument("scene_name", help="Scene name")


def _add_doctor_commands(subparsers: argparse._SubParsersAction) -> None:
    """Add doctor command."""
    subparsers.add_parser("doctor", help="Environment diagnosis and troubleshooting")


def _add_status_commands(subparsers: argparse._SubParsersAction) -> None:
    """Add status command."""
    subparsers.add_parser("status", help="System overview")


def _add_world_commands(subparsers: argparse._SubParsersAction) -> None:
    """Add world command."""
    p_world = subparsers.add_parser("world", help="World state query")
    p_world.add_argument("object_id", nargs="?", default=None)
    p_world.add_argument("--relations", action="store_true")


def _add_skill_commands(subparsers: argparse._SubParsersAction) -> None:
    """Add skills and capability commands."""
    subparsers.add_parser("skills", help="List registered skills")
    subparsers.add_parser("capability", help="Query three-layer capability")


def _add_task_commands(subparsers: argparse._SubParsersAction) -> None:
    """Add task management commands."""
    p_task = subparsers.add_parser("task", help="Task lifecycle management")
    task_sub = p_task.add_subparsers(dest="task_command", required=True)
    task_sub.add_parser("list", help="List available task types")
    task_sub.add_parser("positions", help="List preset positions")


def _add_run_commands(subparsers: argparse._SubParsersAction) -> None:
    """Add run command."""
    p_run = subparsers.add_parser("run", help="Submit task with live trace")
    p_run.add_argument("task_type", help="Task type (pick_place, move, grasp, ...)")
    p_run.add_argument("args", nargs="*", help="Task arguments")
    p_run.add_argument("--arm", default=None, help="Arm name (arm1, arm2)")
    p_run.add_argument("--no-trace", action="store_true", help="Disable trace output")
    p_run.add_argument("--debug", action="store_true", help="Debug mode with detailed analysis")


def _add_episode_commands(subparsers: argparse._SubParsersAction) -> None:
    """Add episode commands."""
    p_eps = subparsers.add_parser("episodes", help="Episode history")
    p_eps.add_argument("--failures-only", action="store_true")
    p_eps.add_argument("--recent", type=int, default=20)

    p_ep = subparsers.add_parser("episode", help="Episode detail + trace replay")
    p_ep.add_argument("episode_id")

    p_an = subparsers.add_parser("analyze", help="Deep episode analysis (AI Debugger)")
    p_an.add_argument("episode_id")


def _add_trace_commands(subparsers: argparse._SubParsersAction) -> None:
    """Add trace commands."""
    p_tr = subparsers.add_parser("traces", help="Trace history")
    p_tr.add_argument("--recent", type=int, default=20)

    p_t = subparsers.add_parser("trace", help="Trace detail")
    p_t.add_argument("trace_id")


def _add_benchmark_commands(subparsers: argparse._SubParsersAction) -> None:
    """Add benchmark command."""
    p_bm = subparsers.add_parser("benchmark", help="Batch benchmark")
    p_bm.add_argument("task_type")
    p_bm.add_argument("--count", type=int, default=100)
    p_bm.add_argument("--output", default=None)


def _add_watch_commands(subparsers: argparse._SubParsersAction) -> None:
    """Add watch command."""
    p_w = subparsers.add_parser("watch", help="Real-time dashboard (like htop)")
    p_w.add_argument("--duration", type=float, default=0.0, help="Watch duration in seconds (0=infinite)")


def _add_evaluate_commands(subparsers: argparse._SubParsersAction) -> None:
    """Add evaluate command."""
    p_ev = subparsers.add_parser("evaluate", help="Run evaluation and generate report")
    p_ev.add_argument("--db", default=None, help="SQLite database path")


def _dispatch(args: argparse.Namespace) -> None:
    """Dispatch command to appropriate handler."""
    if args.command == "sim":
        _dispatch_sim(args)
        return

    if args.command == "scene":
        _dispatch_scene(args)
        return

    if args.command == "evaluate":
        engine = EvaluationEngine(db_path=getattr(args, "db", None))
        report = engine.evaluate()
        engine.print_report(report)
        return

    if args.command == "doctor":
        Doctor().run()
        return

    if args.command == "watch":
        Watcher(duration=args.duration).watch()
        return

    if args.command == "task":
        client = RuntimeClient()
        try:
            tm = TaskManager(client)
            if args.task_command == "list":
                tm.list_tasks()
            elif args.task_command == "positions":
                tm.list_positions()
        finally:
            client.shutdown()
        return

    client = RuntimeClient()
    try:
        if args.command == "status":
            _cmd_status(client)
        elif args.command == "world":
            WorldQuery(client).print_world(args.object_id, args.relations)
        elif args.command == "skills":
            _cmd_skills(client)
        elif args.command == "capability":
            _cmd_capability(client)
        elif args.command == "run":
            _cmd_run(client, args)
        elif args.command == "episodes":
            EpisodeViewer(client).print_episodes(args.failures_only, args.recent)
        elif args.command == "episode":
            EpisodeViewer(client).print_episode_detail(args.episode_id)
        elif args.command == "analyze":
            EpisodeAnalyzer(client).analyze(args.episode_id)
        elif args.command == "traces":
            TraceViewer(client).print_traces(args.recent)
        elif args.command == "trace":
            TraceViewer(client).print_trace_detail(args.trace_id)
        elif args.command == "benchmark":
            BenchmarkRunner(client).run(args.task_type, args.count, args.output)
    except KeyboardInterrupt:
        print("\nInterrupted.")
    finally:
        client.shutdown()


def _dispatch_sim(args: argparse.Namespace) -> None:
    """Dispatch sim subcommands."""
    mgr = SimManager()
    if args.sim_command == "start":
        mgr.start(gui=args.gui, scene=getattr(args, "scene", "tabletop"))
    elif args.sim_command == "stop":
        mgr.stop()
    elif args.sim_command == "status":
        mgr.status()


def _dispatch_scene(args: argparse.Namespace) -> None:
    """Dispatch scene subcommands."""
    mgr = SceneManager()
    if args.scene_command == "list":
        mgr.print_list()
    elif args.scene_command == "show":
        mgr.print_scene(args.scene_name)


def _cmd_run(client: RuntimeClient, args: argparse.Namespace) -> None:
    """Handle run command with trace/debug/no-trace modes."""
    if args.debug:
        TaskManager(client).run_debug(
            args.task_type, args.args, args.arm or ""
        )
    elif args.no_trace:
        result = client.submit_task(args.task_type, args.args, args.arm or "")
        if result:
            print(f"Success: {result.success}")
            print(f"  {result.success_count}/{result.total_count}")
            for r in result.results:
                print(f"  {r}")
    else:
        TraceViewer(client).print_live_trace(
            args.task_type, args.args, args.arm or ""
        )


def _cmd_status(client: RuntimeClient) -> None:
    """Print system overview."""
    print("\n=== Robot Runtime Status ===")
    print()

    world_resp = client.query_world()
    if world_resp:
        obj_count = len(world_resp.object_states)
        rel_count = len(world_resp.relations)
        print(f"World:")
        print(f"  Objects: {obj_count}  Relations: {rel_count}")
        if world_resp.object_states:
            names = [o.object_id for o in world_resp.object_states]
            print(f"  ({', '.join(names)})")
    else:
        print("World: (unavailable)")
    print()

    skills_resp = client.list_skills()
    if skills_resp:
        print(f"Skills ({len(skills_resp.skills)}):")
        for skill in skills_resp.skills:
            print(f"  {skill.name:<20} v{skill.version}  (success={skill.success_rate:.2f})")
    else:
        print("Skills: (unavailable)")
    print()

    cap_resp = client.get_capability()
    if cap_resp:
        available = [c for c in cap_resp.capabilities if c.available]
        print(f"Capability ({len(available)}/{len(cap_resp.capabilities)} available):")
        for cap in cap_resp.capabilities:
            icon = "[x]" if cap.available else "[ ]"
            print(f"  {icon} {cap.name:<20} ({cap.category})")
    else:
        print("Capability: (unavailable)")
    print()

    ep_resp = client.query_experience(
        data_type="episodes", filter_json='{"recent": 100}'
    )
    if ep_resp and ep_resp.count > 0:
        import json
        success = 0
        failure = 0
        for rj in ep_resp.records_json:
            r = json.loads(rj)
            if r.get("result") in ("success", "recovered"):
                success += 1
            else:
                failure += 1
        print(f"Episodes: {ep_resp.count} ({success} success, {failure} failure)")
    else:
        print("Episodes: 0")
    print()


def _cmd_skills(client: RuntimeClient) -> None:
    """Print registered skill list."""
    response = client.list_skills()
    if response is None:
        return

    if not response.skills:
        print("No skills registered.")
        return

    print(f"\nRegistered Skills ({len(response.skills)}):")
    print()
    for skill in response.skills:
        print(f"  {skill.name:<20} v{skill.version}")
        if skill.description:
            print(f"    {skill.description}")
        print(
            f"    cost: {skill.cost_time:.1f}s  "
            f"success_rate: {skill.success_rate:.2f}  "
            f"risk: {skill.cost_risk:.2f}"
        )
        if skill.required_capabilities:
            print(f"    requires: {', '.join(skill.required_capabilities)}")
        print()


def _cmd_capability(client: RuntimeClient) -> None:
    """Print three-layer capability."""
    response = client.get_capability()
    if response is None:
        return

    if not response.capabilities:
        print("No capabilities found.")
        return

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


if __name__ == "__main__":
    main()
