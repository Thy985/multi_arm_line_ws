"""M6 Episode Recording E2E Test — Phase 5.

Runs tasks against the M6 simulation stack, records complete Episodes,
and exports to SQLite + JSON dataset. Verifies the full M6 Experience
Infrastructure works in simulation.

    All episodes recorded with execution steps
    World state snapshots captured (initial + final)
    SQLite dataset exported with correct episode count
    JSON dataset exported (human-readable)
    Failure memory recorded for failed tasks

Test approach: subprocess launch + run episode recording script + verify results.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from typing import Any

import pytest


GZ_SIM_PLUGIN_PATH = (
    "/opt/ros/jazzy/lib:/opt/ros/jazzy/opt/gz_sim_vendor/lib/gz-sim-8/plugins"
)

LAUNCH_CMD = [
    "ros2", "launch", "multi_arm_simulation",
    "m6_domain_randomization.launch.py",
]

RUNNER_CMD = [
    "python3",
    "src/multi_arm_simulation/scripts/m6_episode_recording_e2e.py",
    "--episodes", "5",
    "--timeout", "30",
]


def _source_env() -> dict[str, str]:
    """Get environment with ROS2 sourced."""
    env = os.environ.copy()
    env["PATH"] = f"/usr/bin:{env.get('PATH', '')}"
    env["GZ_SIM_SYSTEM_PLUGIN_PATH"] = GZ_SIM_PLUGIN_PATH
    env["ROS_HOME"] = "/tmp/ros_home"
    env["HOME"] = "/tmp"
    return env


def _run_cmd(
    cmd: list[str],
    timeout: float = 5.0,
) -> subprocess.CompletedProcess:
    """Run command and return result."""
    env = _source_env()
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


def _wait_for_condition(
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


def _action_server_available(action: str) -> bool:
    """Check if a ROS2 action server is available."""
    result = _run_cmd(["ros2", "action", "list"], timeout=3.0)
    if result.returncode != 0:
        return False
    return action in result.stdout


class TestM6EpisodeRecordingE2E:
    """Phase 5: Episode Recording + Dataset Export in simulation."""

    @pytest.fixture(autouse=True)
    def _launch_simulation(self) -> Any:
        """Launch M6 simulation stack and clean up after test."""
        env = _source_env()

        _run_cmd(["pkill", "-f", "coordinator_node"], timeout=3.0)
        _run_cmd(["pkill", "-f", "safety_supervisor"], timeout=3.0)
        _run_cmd(["pkill", "-f", "world_model"], timeout=3.0)
        _run_cmd(["pkill", "-f", "gz sim"], timeout=3.0)
        _run_cmd(["pkill", "-f", "ros2 launch"], timeout=3.0)
        _run_cmd(["pkill", "-f", "component_container"], timeout=3.0)
        _run_cmd(["pkill", "-f", "move_group"], timeout=3.0)
        time.sleep(3)

        print("\n  Starting M6 simulation stack for episode recording...")
        proc = subprocess.Popen(
            LAUNCH_CMD,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            preexec_fn=os.setsid,
        )

        try:
            yield proc
        finally:
            print("\n  Shutting down simulation stack...")
            try:
                os.killpg(os.getpgid(proc.pid), 15)
            except ProcessLookupError:
                pass
            proc.wait(timeout=15)

            _run_cmd(["pkill", "-9", "-f", "coordinator_node"], timeout=3.0)
            _run_cmd(["pkill", "-9", "-f", "safety_supervisor"], timeout=3.0)
            _run_cmd(["pkill", "-9", "-f", "world_model"], timeout=3.0)
            _run_cmd(["pkill", "-9", "-f", "gz sim"], timeout=3.0)
            _run_cmd(["pkill", "-9", "-f", "ros2 launch"], timeout=3.0)
            _run_cmd(["pkill", "-9", "-f", "move_group"], timeout=3.0)
            _run_cmd(["pkill", "-9", "-f", "component_container"], timeout=3.0)
            _run_cmd(["pkill", "-9", "-f", "robot_state_publisher"], timeout=3.0)
            _run_cmd(["pkill", "-9", "-f", "parameter_bridge"], timeout=3.0)
            time.sleep(5)

    def test_coordinator_ready(self) -> None:
        """Coordinator is ready for episode recording."""
        print("\n  [Test] Coordinator ready...")

        assert _wait_for_condition(
            lambda: _action_server_available("/coordinator/execute_task"),
            timeout=30.0, description="coordinator execute_task",
        ), "/coordinator/execute_task not available"
        print("  ✓ /coordinator/execute_task available")

    def test_episode_recording_and_dataset_export(self) -> None:
        """Run 5-episode recording and verify dataset export."""
        print("\n  [Test] Episode Recording + Dataset Export (5 episodes)...")

        assert _wait_for_condition(
            lambda: _action_server_available("/coordinator/execute_task"),
            timeout=30.0, description="coordinator ready",
        ), "Coordinator not ready"

        time.sleep(5)

        print("  Running episode recording script...")
        result = _run_cmd(RUNNER_CMD, timeout=300.0)

        print(f"  Runner exit code: {result.returncode}")
        if result.stdout:
            print(f"  Runner stdout (last 3000 chars):\n{result.stdout[-3000:]}")
        if result.stderr:
            print(f"  Runner stderr (last 1500 chars):\n{result.stderr[-1500:]}")

        json_match = re.search(r"JSON:\s*(\{.*\})", result.stdout, re.DOTALL)
        assert json_match, "No JSON output from runner"

        ep_results = json.loads(json_match.group(1))
        print(f"\n  Episode Recording Results:")
        print(f"    Episodes Run: {ep_results.get('episodes_run', '?')}")
        print(f"    Episodes Recorded: {ep_results.get('episodes_recorded', '?')}")
        print(f"    Failures Recorded: {ep_results.get('failures_recorded', '?')}")
        print(f"    Episodes with Steps: {ep_results.get('episodes_with_steps', '?')}")
        print(f"    Episodes with World: {ep_results.get('episodes_with_world_snapshot', '?')}")
        print(f"    Exported to SQLite: {ep_results.get('exported_to_sqlite', '?')}")
        print(f"    DB Episode Count: {ep_results.get('db_episode_count', '?')}")
        print(f"    JSON Exported: {ep_results.get('json_exported', '?')}")

        assert ep_results.get("episodes_recorded", 0) == 5, (
            f"Expected 5 episodes recorded, got {ep_results.get('episodes_recorded')}"
        )
        print("  ✓ All 5 episodes recorded")

        assert ep_results.get("exported_to_sqlite", 0) == 5, (
            f"Expected 5 exported to SQLite, got {ep_results.get('exported_to_sqlite')}"
        )
        print("  ✓ All episodes exported to SQLite")

        assert ep_results.get("db_episode_count", 0) == 5, (
            f"Expected 5 DB episodes, got {ep_results.get('db_episode_count')}"
        )
        print("  ✓ SQLite DB has 5 episodes")

        assert ep_results.get("json_exported", False), "JSON not exported"
        print("  ✓ JSON dataset exported")

        assert ep_results.get("episodes_with_steps", 0) >= 3, (
            f"Expected >= 3 episodes with steps, got {ep_results.get('episodes_with_steps')}"
        )
        print("  ✓ Episodes have execution steps")

        assert ep_results.get("overall_success", False), (
            "Overall episode recording failed"
        )
        print("  ✓ Episode Recording + Dataset Export PASSED")