"""Robot Runtime Manager — session ownership, PID tree, DDS isolation.

This is the core infrastructure that transforms the CLI from "ROS command
wrapper" into "Robot OS entry point". It solves:

    1. Runtime Ownership  — who started this robot instance?
    2. Process Lifecycle  — tracked PID tree, no more orphaned gz_sim
    3. DDS Isolation      — per-session ROS_DOMAIN_ID
    4. Stale Detection    — zombie nodes, duplicate action servers
    5. Safe Cleanup       — kill only owned processes, never killall

Session directory layout::

    ~/.robot/runtime/
        current -> session-20260813-001/   # symlink to active session
        session-20260813-001/
            manifest.yaml      # session metadata + PID tree
            pid.lock           # lock file (PID of launch process)
            env.yaml           # environment snapshot
            logs/
                launch.log     # stdout/stderr of ros2 launch
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import time
import yaml
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

RUNTIME_DIR = Path(os.environ.get("HOME", "/tmp")) / ".robot" / "runtime"
SESSION_PREFIX = "session"
DEFAULT_DOMAIN_ID = 0
DOMAIN_POOL = list(range(40, 60))  # domain IDs 40-59 for runtime sessions

# Directories guaranteed on PATH so bare subprocess calls (ros2/ps/pgrep) resolve
# even when the calling environment has an empty or minimal PATH.
FALLBACK_PATH = ":".join([
    "/usr/local/bin",
    "/usr/bin",
    "/bin",
    "/usr/local/sbin",
    "/usr/sbin",
    "/opt/ros/jazzy/bin",
    str(Path.home() / ".local" / "share" / "mise" / "shims"),
])


def safe_env() -> dict[str, str]:
    """Return a copy of the environment with a reliable PATH.

    If PATH is missing/empty, fall back to FALLBACK_PATH. Otherwise keep the
    existing PATH and append any fallback dirs not already present, so bare
    commands like ``ros2``/``ps`` resolve regardless of how this process was
    launched (e.g. an agent shell with an empty PATH).
    """
    env = dict(os.environ)
    current = env.get("PATH", "")
    if not current.strip():
        env["PATH"] = FALLBACK_PATH
    else:
        parts = [p for p in current.split(":") if p]
        for d in FALLBACK_PATH.split(":"):
            if d not in parts:
                parts.append(d)
        env["PATH"] = ":".join(parts)
    return env


LAUNCH_PACKAGE = "multi_arm_simulation"
LAUNCH_FILE = "m6_pick_place_sim.launch.py"

PROCESS_PATTERNS = {
    "gazebo": ["gz sim", "gz-sim"],
    "controller_manager": ["controller_manager"],
    "move_group": ["move_group"],
    "skill_runtime": ["skill_node"],
    "runtime_api": ["runtime_api_node"],
    "coordinator": ["coordinator_node"],
    "task_planner": ["task_planner_node"],
    "world_model": ["world_model_node"],
    "safety_supervisor": ["safety_supervisor"],
    "ros_gz_bridge": ["parameter_bridge"],
    "robot_state_publisher": ["robot_state_publisher"],
    "ground_truth": ["gazebo_ground_truth_node"],
    "synthetic_camera": ["synthetic_camera_node"],
    "color_detector": ["color_detector_node"],
    "experience_node": ["experience_node"],
    "capability_registry": ["capability_registry_node"],
}


@dataclass
class ProcessInfo:
    name: str
    pid: int
    ppid: int
    cmdline: str
    alive: bool = True

    @property
    def is_orphan(self) -> bool:
        return self.ppid == 1 or self.ppid == 0


@dataclass
class SessionManifest:
    session_id: str
    created_at: str
    domain_id: int
    launch_pid: int | None = None
    processes: dict[str, int] = field(default_factory=dict)
    scene: str = "tabletop"
    gui: bool = False
    status: str = "created"

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "created_at": self.created_at,
            "domain_id": self.domain_id,
            "launch_pid": self.launch_pid,
            "processes": self.processes,
            "scene": self.scene,
            "gui": self.gui,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SessionManifest:
        return cls(
            session_id=d["session_id"],
            created_at=d["created_at"],
            domain_id=d["domain_id"],
            launch_pid=d.get("launch_pid"),
            processes=d.get("processes", {}),
            scene=d.get("scene", "tabletop"),
            gui=d.get("gui", False),
            status=d.get("status", "unknown"),
        )


class RuntimeManager:
    """Robot Runtime lifecycle owner — creates, tracks, and cleans sessions."""

    def __init__(self, runtime_dir: Path | None = None) -> None:
        self._dir = runtime_dir or RUNTIME_DIR
        self._dir.mkdir(parents=True, exist_ok=True)

    def get_active_session(self) -> SessionManifest | None:
        """Return the current active session, or None if no session."""
        current = self._dir / "current"
        if not current.exists():
            return None
        try:
            target = current.resolve()
        except OSError:
            return None
        manifest_path = target / "manifest.yaml"
        if not manifest_path.exists():
            return None
        with open(manifest_path) as f:
            data = yaml.safe_load(f)
        manifest = SessionManifest.from_dict(data)
        if not self._is_session_alive(manifest):
            manifest.status = "stale"
        return manifest

    def create_session(
        self,
        scene: str = "tabletop",
        gui: bool = False,
        domain_id: int | None = None,
    ) -> SessionManifest:
        """Create a new runtime session with isolated DDS domain."""
        self._cleanup_stale_symlinks()
        existing = self.get_active_session()
        if existing and existing.status != "stale":
            raise RuntimeError(
                f"Active session already exists: {existing.session_id} "
                f"(status={existing.status}). Use stop() first."
            )
        if existing and existing.status == "stale":
            self._repair_stale(existing)
        if domain_id is None:
            domain_id = self._allocate_domain()
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        session_id = f"{SESSION_PREFIX}-{timestamp}"
        session_dir = self._dir / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        (session_dir / "logs").mkdir(exist_ok=True)
        manifest = SessionManifest(
            session_id=session_id,
            created_at=datetime.now().isoformat(),
            domain_id=domain_id,
            scene=scene,
            gui=gui,
            status="created",
        )
        self._save_manifest(manifest)
        self._set_current(session_dir)
        return manifest

    def start_session(self, manifest: SessionManifest) -> subprocess.Popen | None:
        """Launch the simulation for this session."""
        session_dir = self._get_session_dir(manifest.session_id)
        log_path = session_dir / "logs" / "launch.log"
        env = self._build_env(manifest.domain_id)
        cmd = [
            "ros2", "launch", LAUNCH_PACKAGE, LAUNCH_FILE,
            f"gazebo_gui:={'true' if manifest.gui else 'false'}",
        ]
        log_fd = open(log_path, "w")
        proc = subprocess.Popen(
            cmd,
            stdout=log_fd,
            stderr=subprocess.STDOUT,
            env=env,
            start_new_session=True,
        )
        manifest.launch_pid = proc.pid
        manifest.status = "running"
        self._save_manifest(manifest)
        self._write_lock(session_dir, proc.pid)
        return proc

    def stop_session(self, manifest: SessionManifest | None = None) -> bool:
        """Stop a session by killing its entire process tree."""
        if manifest is None:
            manifest = self.get_active_session()
        if manifest is None:
            return False
        killed_any = False
        if manifest.launch_pid and self._pid_alive(manifest.launch_pid):
            killed_any |= self._kill_process_tree(manifest.launch_pid)
        for name, pid in list(manifest.processes.items()):
            if self._pid_alive(pid):
                killed_any |= self._kill_process_tree(pid)
        manifest.status = "stopped"
        self._save_manifest(manifest)
        current = self._dir / "current"
        if current.exists():
            try:
                current.unlink()
            except OSError:
                pass
        return killed_any

    def discover_processes(self) -> list[ProcessInfo]:
        """Discover all robot-related processes currently running."""
        result: list[ProcessInfo] = []
        try:
            output = subprocess.check_output(
                ["ps", "aux"], text=True, timeout=5, env=safe_env()
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return result
        for line in output.splitlines()[1:]:
            parts = line.split(None, 10)
            if len(parts) < 11:
                continue
            try:
                pid = int(parts[1])
                ppid_str = parts[2] if len(parts) > 2 else "0"
            except ValueError:
                continue
            cmdline = parts[10] if len(parts) > 10 else ""
            if not self._is_robot_process(cmdline):
                continue
            try:
                with open(f"/proc/{pid}/stat") as f:
                    stat = f.read().split()
                    ppid = int(stat[3])
            except (FileNotFoundError, ValueError, IndexError):
                ppid = 0
            result.append(ProcessInfo(
                name=self._classify_process(cmdline),
                pid=pid,
                ppid=ppid,
                cmdline=cmdline,
                alive=True,
            ))
        return result

    def detect_duplicates(self) -> dict[str, list[ProcessInfo]]:
        """Find duplicate process instances by name."""
        procs = self.discover_processes()
        by_name: dict[str, list[ProcessInfo]] = {}
        for p in procs:
            by_name.setdefault(p.name, []).append(p)
        return {k: v for k, v in by_name.items() if len(v) > 1}

    def detect_stale_nodes(self) -> list[str]:
        """Detect DDS ghost nodes via ros2 node list."""
        try:
            output = subprocess.check_output(
                ["ros2", "node", "list"],
                text=True,
                timeout=10,
                stderr=subprocess.DEVNULL,
                env=safe_env(),
            )
        except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.CalledProcessError):
            return []
        lines = [l.strip() for l in output.splitlines() if l.strip()]
        from collections import Counter
        counts = Counter(lines)
        return [name for name, count in counts.items() if count > 1]

    def repair(self) -> dict[str, Any]:
        """Auto-repair runtime issues: kill zombies, clean stale sessions."""
        report: dict[str, Any] = {
            "killed_zombies": [],
            "killed_duplicates": [],
            "cleaned_sessions": [],
            "dds_reset": False,
            "errors": [],
        }
        zombies = self._find_zombie_processes()
        for z in zombies:
            try:
                os.kill(z.pid, signal.SIGKILL)
                report["killed_zombies"].append({"name": z.name, "pid": z.pid})
            except ProcessLookupError:
                pass
            except PermissionError:
                report["errors"].append(f"Cannot kill PID {z.pid}: permission denied")
        duplicates = self.detect_duplicates()
        for name, procs in duplicates.items():
            if name in ("gazebo", "controller_manager", "move_group",
                        "skill_runtime", "runtime_api", "coordinator"):
                for p in procs[1:]:
                    try:
                        os.kill(p.pid, signal.SIGTERM)
                        report["killed_duplicates"].append({"name": name, "pid": p.pid})
                    except ProcessLookupError:
                        pass
                    except PermissionError:
                        report["errors"].append(
                            f"Cannot kill duplicate {name} PID {p.pid}: permission denied"
                        )
                time.sleep(0.5)
                for p in procs[1:]:
                    if self._pid_alive(p.pid):
                        try:
                            os.kill(p.pid, signal.SIGKILL)
                        except (ProcessLookupError, PermissionError):
                            pass
        if duplicates:
            time.sleep(1)
            try:
                subprocess.run(["ros2", "daemon", "stop"], timeout=5,
                              capture_output=True, env=safe_env())
                time.sleep(2)
                subprocess.run(["ros2", "daemon", "start"], timeout=5,
                              capture_output=True, env=safe_env())
                report["dds_reset"] = True
            except (subprocess.TimeoutExpired, FileNotFoundError):
                report["errors"].append("Failed to restart DDS daemon")
        for session_dir in self._dir.iterdir():
            if not session_dir.is_dir() or session_dir.name == "current":
                continue
            manifest_path = session_dir / "manifest.yaml"
            if not manifest_path.exists():
                continue
            with open(manifest_path) as f:
                data = yaml.safe_load(f)
            manifest = SessionManifest.from_dict(data)
            if not self._is_session_alive(manifest):
                report["cleaned_sessions"].append(manifest.session_id)
                manifest.status = "stale"
                self._save_manifest(manifest)
        current = self._dir / "current"
        if current.exists():
            try:
                target = current.resolve()
                manifest_path = target / "manifest.yaml"
                if manifest_path.exists():
                    with open(manifest_path) as f:
                        data = yaml.safe_load(f)
                    manifest = SessionManifest.from_dict(data)
                    if not self._is_session_alive(manifest):
                        current.unlink()
            except OSError:
                pass
        return report

    def _is_session_alive(self, manifest: SessionManifest) -> bool:
        if manifest.launch_pid is None:
            return False
        return self._pid_alive(manifest.launch_pid)

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True

    def _kill_process_tree(self, pid: int) -> bool:
        """Terminate the whole process group rooted at ``pid``.

        Sessions are launched with ``start_new_session=True``, so ``pid`` is the
        session leader and its process group contains every descendant node
        (gz sim, controller_manager, move_group, ...). Killing the group is
        sufficient and never touches processes outside this session. A
        recursive /proc-based fallback handles edge cases where the group
        lookup fails.
        """
        killed = False
        try:
            pgid = os.getpgid(pid)
        except (ProcessLookupError, PermissionError):
            pgid = pid
        try:
            os.killpg(pgid, signal.SIGTERM)
            killed = True
        except (ProcessLookupError, PermissionError):
            pass
        time.sleep(0.5)
        children = self._find_children(pid)
        for child_pid in children:
            try:
                os.kill(child_pid, signal.SIGTERM)
                killed = True
            except ProcessLookupError:
                pass
        time.sleep(0.5)
        for child_pid in children:
            if self._pid_alive(child_pid):
                try:
                    os.kill(child_pid, signal.SIGKILL)
                    killed = True
                except ProcessLookupError:
                    pass
        try:
            os.kill(pid, signal.SIGTERM)
            killed = True
        except ProcessLookupError:
            return killed
        time.sleep(0.5)
        if self._pid_alive(pid):
            try:
                os.kill(pid, signal.SIGKILL)
                killed = True
            except ProcessLookupError:
                pass
        return killed

    def _find_children(self, parent_pid: int) -> list[int]:
        """Recursively find child PIDs of ``parent_pid`` by scanning /proc.

        Uses /proc/<pid>/stat instead of ``ps`` so it works even when PATH is
        empty. Returns a flat list of all transitive descendants.
        """
        children: list[int] = []
        try:
            entries = os.listdir("/proc")
        except FileNotFoundError:
            return children
        for entry in entries:
            if not entry.isdigit():
                continue
            cpid = int(entry)
            try:
                with open(f"/proc/{cpid}/stat") as f:
                    stat = f.read().split()
                ppid = int(stat[3])
            except (FileNotFoundError, ValueError, IndexError, OSError):
                continue
            if ppid == parent_pid:
                children.append(cpid)
                children.extend(self._find_children(cpid))
        return children

    def _find_zombie_processes(self) -> list[ProcessInfo]:
        all_procs = self.discover_processes()
        return [p for p in all_procs if p.is_orphan]

    def _allocate_domain(self) -> int:
        used: set[int] = set()
        for session_dir in self._dir.iterdir():
            if not session_dir.is_dir() or session_dir.name == "current":
                continue
            manifest_path = session_dir / "manifest.yaml"
            if manifest_path.exists():
                with open(manifest_path) as f:
                    data = yaml.safe_load(f)
                if data and data.get("status") == "running":
                    used.add(data.get("domain_id", -1))
        for d in DOMAIN_POOL:
            if d not in used:
                return d
        return DEFAULT_DOMAIN_ID

    def _build_env(self, domain_id: int) -> dict[str, str]:
        env = safe_env()
        env["ROS_DOMAIN_ID"] = str(domain_id)
        env["RMW_IMPLEMENTATION"] = "rmw_cyclonedds_cpp"
        env.setdefault("ROS_HOME", "/tmp/ros_home")
        env.setdefault("GZ_SIM_SYSTEM_PLUGIN_PATH",
                       "/opt/ros/jazzy/lib:/opt/ros/jazzy/opt/gz_sim_vendor/lib/gz-sim-8/plugins")
        return env

    def _save_manifest(self, manifest: SessionManifest) -> None:
        session_dir = self._get_session_dir(manifest.session_id)
        if session_dir is None:
            return
        with open(session_dir / "manifest.yaml", "w") as f:
            yaml.safe_dump(manifest.to_dict(), f, default_flow_style=False)

    def _get_session_dir(self, session_id: str) -> Path | None:
        d = self._dir / session_id
        return d if d.exists() else None

    def _set_current(self, session_dir: Path) -> None:
        current = self._dir / "current"
        if current.exists() or current.is_symlink():
            current.unlink()
        current.symlink_to(session_dir.name)

    def _write_lock(self, session_dir: Path, pid: int) -> None:
        with open(session_dir / "pid.lock", "w") as f:
            f.write(str(pid))

    def _cleanup_stale_symlinks(self) -> None:
        current = self._dir / "current"
        if current.is_symlink() and not current.exists():
            current.unlink()

    def _repair_stale(self, manifest: SessionManifest) -> None:
        self.stop_session(manifest)

    @staticmethod
    def _is_robot_process(cmdline: str) -> bool:
        for patterns in PROCESS_PATTERNS.values():
            for pat in patterns:
                if pat in cmdline:
                    return True
        return False

    @staticmethod
    def _classify_process(cmdline: str) -> str:
        for name, patterns in PROCESS_PATTERNS.items():
            for pat in patterns:
                if pat in cmdline:
                    return name
        return "unknown"