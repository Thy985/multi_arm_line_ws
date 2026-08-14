"""Robot OS Interactive Shell — the robot> entry point.

When the user runs `robot` with no arguments, they enter this shell.
It performs a bootstrap sequence (environment, build, runtime health),
auto-repairs stale processes, and then provides an interactive prompt
where all robot commands are available.

This transforms the CLI from "ROS command wrapper" to "Robot OS Shell".
"""

from __future__ import annotations

import argparse
import os
import shlex
import sys
import time
from typing import Any

from multi_arm_tools.runtime_manager import RuntimeManager


BANNER = r"""
  ╭──────────────────────────────────────────╮
  │   M7 Embodied Robot OS                   │
  │   Dual UR5e · Gazebo · MoveIt2 · Skills  │
  ╰──────────────────────────────────────────╯
"""


def _verify_env(var: str, expected: str) -> tuple[bool, str]:
    val = os.environ.get(var, "")
    if val == expected:
        return True, f"{var}={val}"
    if val:
        return True, f"{var}={val} (expected {expected})"
    return False, f"{var} not set"


def _verify_path(path: str) -> tuple[bool, str]:
    full = os.path.join(os.getcwd(), path)
    if os.path.exists(full):
        return True, path
    return False, f"{path} not found (run colcon build)"


def _verify_dds() -> tuple[bool, str]:
    rmw = os.environ.get("RMW_IMPLEMENTATION", "")
    if "cyclonedds" in rmw:
        return True, "CycloneDDS"
    if "fastdds" in rmw:
        return True, f"{rmw} (consider CycloneDDS for stability)"
    return True, "default DDS"


def _verify_runtime() -> tuple[bool, str]:
    mgr = RuntimeManager()
    session = mgr.get_active_session()
    if session is None:
        return True, "no active session"
    if session.status == "stale":
        return False, f"stale session {session.session_id}"
    return True, f"session {session.session_id} (domain={session.domain_id})"


BOOT_STEPS = [
    ("ROS2", lambda: _verify_env("ROS_DISTRO", "jazzy")),
    ("Workspace", lambda: _verify_path("install/setup.bash")),
    ("DDS", _verify_dds),
    ("Runtime", _verify_runtime),
]


def _build_session_env():
    """Build environment with active session's DDS domain."""
    env = dict(os.environ)
    mgr = RuntimeManager()
    session = mgr.get_active_session()
    if session is not None and session.status == "running":
        env["ROS_DOMAIN_ID"] = str(session.domain_id)
    return env


def _build_cli_parser():
    """Build the same parser as CLI's main(), cached for reuse."""
    from multi_arm_tools.cli import (
        _add_lifecycle_commands, _add_sim_commands, _add_scene_commands,
        _add_doctor_commands, _add_status_commands, _add_world_commands,
        _add_vision_commands, _add_skill_commands, _add_task_commands,
        _add_run_commands, _add_episode_commands, _add_safety_commands,
        _add_trace_commands, _add_benchmark_commands, _add_watch_commands,
        _add_evaluate_commands,
    )
    parser = argparse.ArgumentParser(prog="robot")
    parser.add_argument("--json", dest="json_output", action="store_true")
    sub = parser.add_subparsers(dest="command", required=False)
    _add_lifecycle_commands(sub)
    _add_sim_commands(sub)
    _add_scene_commands(sub)
    _add_doctor_commands(sub)
    _add_status_commands(sub)
    _add_world_commands(sub)
    _add_vision_commands(sub)
    _add_skill_commands(sub)
    _add_task_commands(sub)
    _add_run_commands(sub)
    _add_episode_commands(sub)
    _add_safety_commands(sub)
    _add_trace_commands(sub)
    _add_benchmark_commands(sub)
    _add_watch_commands(sub)
    _add_evaluate_commands(sub)
    return parser


def _direct_dispatch(cmd: str, args: list[str]) -> int:
    """Dispatch a command by calling the CLI's _dispatch directly.

    This avoids subprocess overhead and inherits the current process's
    ROS_DOMAIN_ID environment.
    """
    from multi_arm_tools.cli import _dispatch
    saved_argv = sys.argv
    saved_env = dict(os.environ)
    try:
        env = _build_session_env()
        os.environ.update(env)
        sys.argv = ["robot", cmd] + args
        parser = _build_cli_parser()
        parsed = parser.parse_args(sys.argv[1:])
        parsed.json_output = False
        ret = _dispatch(parsed)
        sys.stdout.flush()
        return ret
    except SystemExit as e:
        sys.stdout.flush()
        return e.code if isinstance(e.code, int) else 1
    except Exception as e:
        print(f"  Error: {e}")
        sys.stdout.flush()
        return 1
    finally:
        sys.argv = saved_argv
        for k, v in saved_env.items():
            os.environ[k] = v
        for k in list(os.environ.keys()):
            if k not in saved_env:
                del os.environ[k]


class InteractiveShell:
    """Robot OS interactive shell — robot> prompt with bootstrap."""

    def __init__(self) -> None:
        self._mgr = RuntimeManager()
        self._history: list[str] = []

    def run(self) -> int:
        """Run the shell: bootstrap → prompt loop."""
        print(BANNER)
        if not self._bootstrap():
            return 1
        self._check_and_repair()
        self._show_status_brief()
        return self._prompt_loop()

    def _bootstrap(self) -> bool:
        print("Checking environment...\n")
        all_ok = True
        for name, check_fn in BOOT_STEPS:
            ok, detail = check_fn()
            mark = "✓" if ok else "✗"
            print(f"  {mark} {name}: {detail}")
            if not ok:
                all_ok = False
        print()
        if not all_ok:
            print("  Bootstrap failed. Run 'robot doctor' for details.")
            return False
        print("  Ready.\n")
        return True

    def _check_and_repair(self) -> None:
        duplicates = self._mgr.detect_duplicates()
        stale_nodes = self._mgr.detect_stale_nodes()
        if not duplicates and not stale_nodes:
            return
        print("  ⚠ Runtime issues detected:\n")
        if duplicates:
            for name, procs in duplicates.items():
                pids = ", ".join(str(p.pid) for p in procs)
                print(f"    Duplicate {name}: PID {pids}")
        if stale_nodes:
            for node in stale_nodes[:5]:
                print(f"    Stale DDS node: {node}")
        print()
        try:
            answer = input("  Auto-repair? [Y/n] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            answer = "n"
        if answer in ("", "y", "yes"):
            report = self._mgr.repair()
            killed = report.get("killed_zombies", []) + report.get("killed_duplicates", [])
            if killed:
                print(f"\n  ✓ Killed {len(killed)} stale process(es)")
            print("  ✓ Runtime repaired\n")
            time.sleep(1)
        else:
            print("  Skipped repair. Run 'robot repair' later if needed.\n")

    def _show_status_brief(self) -> None:
        session = self._mgr.get_active_session()
        if session and session.status == "running":
            print(f"  Active session: {session.session_id}")
            print(f"  Domain: {session.domain_id}")
            print(f"  Scene: {session.scene}\n")
        else:
            print("  No active session. Type 'start' to launch simulation.\n")

    def _prompt_loop(self) -> int:
        while True:
            try:
                line = input("robot> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n  Bye.")
                return 0
            if not line:
                continue
            if line in ("exit", "quit", "q"):
                print("  Bye.")
                return 0
            self._history.append(line)
            try:
                tokens = shlex.split(line)
            except ValueError as e:
                print(f"  Error: {e}")
                continue
            if not tokens:
                continue
            cmd = tokens[0]
            args = tokens[1:]
            if cmd == "help":
                self._print_help()
                continue
            exit_code = self._dispatch(cmd, args)
            if exit_code == -1:
                print(f"  Unknown command: {cmd}. Type 'help' for commands.")

    def _dispatch(self, cmd: str, args: list[str]) -> int:
        """Dispatch a command within the shell."""
        if cmd in ("start", "stop", "status", "repair", "restart"):
            return _direct_dispatch(cmd, args)
        return _direct_dispatch(cmd, args)

    def _print_help(self) -> None:
        print("\n  Robot OS Commands:\n")
        print("  Lifecycle:")
        print("    start [--gui] [--scene NAME]  Start simulation session")
        print("    stop                          Stop current session")
        print("    status                        Show session status")
        print("    repair                        Auto-repair runtime issues")
        print("    doctor                        Full system diagnosis")
        print()
        print("  Observe:")
        print("    status                        System overview")
        print("    world [object]                World model state")
        print("    skills                        Registered skills")
        print("    vision status                 Perception pipeline")
        print()
        print("  Act:")
        print("    run <task> [args]             Execute a task")
        print("    safety status                 Safety state")
        print("    safety stop                   EMERGENCY STOP")
        print()
        print("  Other:")
        print("    help                          Show this help")
        print("    exit / quit                   Leave shell")
        print()
