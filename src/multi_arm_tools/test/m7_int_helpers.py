"""Shared helpers for M7.INT integration tests."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from typing import Any


GZ_SIM_PLUGIN_PATH = (
    "/opt/ros/jazzy/lib:/opt/ros/jazzy/opt/gz_sim_vendor/lib/gz-sim-8/plugins"
)

LAUNCH_CMD = [
    "ros2", "launch", "multi_arm_simulation",
    "m6_pick_place_sim.launch.py",
]

RUNTIME_API_CMD = [
    "ros2", "run", "multi_arm_runtime_api", "runtime_api_node",
]

SKILL_NODE_CMD = [
    "ros2", "run", "multi_arm_skill_runtime", "skill_node",
]

CAPABILITY_NODE_CMD = [
    "ros2", "run", "multi_arm_robot_description", "capability_registry_node",
]

EXPERIENCE_NODE_CMD = [
    "ros2", "run", "multi_arm_experience", "experience_node",
]

AUX_NODE_CMDS = [
    CAPABILITY_NODE_CMD,
    SKILL_NODE_CMD,
    EXPERIENCE_NODE_CMD,
    RUNTIME_API_CMD,
]

CLEANUP_PATTERNS = [
    "gz sim",
    "ros2 launch",
    "move_group",
    "component_container",
    "runtime_api",
    "skill_node",
    "capability_registry",
    "experience_node",
]


def clean_shm_locks() -> None:
    """Remove stale FastDDS SHM lock files from /dev/shm."""
    import glob as globmod
    for f in globmod.glob("/dev/shm/fastrtps_*"):
        try:
            os.remove(f)
        except OSError:
            pass


def source_env() -> dict[str, str]:
    """Get environment with ROS2 sourced.

    Uses CycloneDDS to avoid FastDDS SHM transport conflicts that occur
    when CLI processes rapidly create/destroy DDS participants.
    """
    env = os.environ.copy()
    env["PATH"] = f"/usr/bin:{env.get('PATH', '')}"
    env["GZ_SIM_SYSTEM_PLUGIN_PATH"] = GZ_SIM_PLUGIN_PATH
    env["ROS_HOME"] = "/tmp/ros_home"
    env["HOME"] = "/tmp"
    env["RMW_IMPLEMENTATION"] = "rmw_cyclonedds_cpp"
    return env


def run_cmd(
    cmd: list[str],
    timeout: float = 10.0,
) -> subprocess.CompletedProcess:
    """Run command and return result."""
    env = source_env()
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
    except subprocess.TimeoutExpired as e:
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=-1,
            stdout=e.stdout or "",
            stderr=e.stderr or "",
        )


def robot_cli(args: list[str], timeout: float = 30.0) -> subprocess.CompletedProcess:
    """Run robot CLI command via subprocess."""
    time.sleep(0.5)
    cmd = [sys.executable, "-m", "multi_arm_tools.cli"] + args
    return run_cmd(cmd, timeout=timeout)


def robot_cli_with_retry(
    args: list[str],
    timeout: float = 30.0,
    retries: int = 3,
) -> subprocess.CompletedProcess:
    """Run robot CLI with retry on failure."""
    result = robot_cli(args, timeout=timeout)
    for attempt in range(retries):
        if result.returncode == 0 and "Success: True" in result.stdout:
            return result
        time.sleep(2.0)
        result = robot_cli(args, timeout=timeout)
    return result


def wait_for_condition(
    check_fn: Any,
    timeout: float = 30.0,
    interval: float = 1.0,
    description: str = "",
) -> bool:
    """Wait for condition to be true."""
    start = time.time()
    while time.time() - start < timeout:
        if check_fn():
            return True
        time.sleep(interval)
    print(f"  TIMEOUT waiting for: {description}")
    return False


def ros2_node_exists(node_name: str) -> bool:
    """Check if a ROS2 node exists."""
    result = run_cmd(["ros2", "node", "list"], timeout=5.0)
    if result.returncode != 0:
        return False
    return any(node_name in line for line in result.stdout.splitlines())


def service_available(service: str) -> bool:
    """Check if a ROS2 service is available."""
    result = run_cmd(["ros2", "service", "list"], timeout=5.0)
    if result.returncode != 0:
        return False
    return service in result.stdout


def action_available(action: str) -> bool:
    """Check if a ROS2 action is available."""
    result = run_cmd(["ros2", "action", "list"], timeout=5.0)
    if result.returncode != 0:
        return False
    return action in result.stdout


def launch_full_stack() -> tuple[subprocess.Popen, list[subprocess.Popen]]:
    """Launch full M7 stack. Returns (launch_proc, aux_procs).

    Caller is responsible for cleanup via shutdown_full_stack().
    """
    clean_shm_locks()
    env = source_env()
    launch_proc = subprocess.Popen(
        LAUNCH_CMD,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
        preexec_fn=os.setsid,
    )

    aux_procs: list[subprocess.Popen] = []
    for cmd in AUX_NODE_CMDS:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
            preexec_fn=os.setsid,
        )
        aux_procs.append(proc)
        time.sleep(2)

    return launch_proc, aux_procs


def wait_stack_ready() -> bool:
    """Wait for M7 stack to be fully ready."""
    if not wait_for_condition(
        lambda: ros2_node_exists("coordinator"),
        timeout=30.0, description="coordinator",
    ):
        return False

    if not wait_for_condition(
        lambda: action_available("/coordinator/execute_task"),
        timeout=30.0, description="coordinator action",
    ):
        return False

    if not wait_for_condition(
        lambda: action_available("/move_action"),
        timeout=45.0, description="move_action (MoveIt2)",
    ):
        print("  [WARN] MoveIt2 /move_action not available")

    if not wait_for_condition(
        lambda: service_available("/runtime/list_skills"),
        timeout=15.0, description="runtime list_skills",
    ):
        return False

    time.sleep(5)
    return True


def shutdown_full_stack(
    launch_proc: subprocess.Popen,
    aux_procs: list[subprocess.Popen],
) -> None:
    """Shutdown full M7 stack."""
    for proc in reversed(aux_procs):
        if proc.poll() is None:
            try:
                os.killpg(os.getpgid(proc.pid), 15)
            except ProcessLookupError:
                pass
            proc.wait(timeout=5)

    try:
        os.killpg(os.getpgid(launch_proc.pid), 15)
    except ProcessLookupError:
        pass
    launch_proc.wait(timeout=15)

    for pattern in CLEANUP_PATTERNS:
        run_cmd(["pkill", "-f", pattern], timeout=3.0)
    time.sleep(3)
    clean_shm_locks()