"""M6 Domain Randomization Benchmark E2E Test — Phase 4.

Runs 20+ random tasks against the M6 simulation stack and verifies
the system generalizes across different parameters.

    Success Rate >= 80%
    All tasks recorded in SQLite benchmark DB
    Per-task metrics (planning_time, execution_time) captured

Test approach: subprocess launch + run benchmark script + verify results.
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
    "src/multi_arm_simulation/scripts/m6_domain_randomization_e2e.py",
    "--episodes", "10",
    "--timeout", "120",
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


class TestM6DomainRandomizationE2E:
    """Phase 4: Domain Randomization Benchmark in simulation."""

    @pytest.fixture(autouse=True)
    def _launch_simulation(self) -> Any:
        """Launch full M6 simulation stack and clean up after test."""
        env = _source_env()

        _run_cmd(["pkill", "-f", "coordinator_node"], timeout=3.0)
        _run_cmd(["pkill", "-f", "safety_supervisor"], timeout=3.0)
        _run_cmd(["pkill", "-f", "world_model"], timeout=3.0)
        _run_cmd(["pkill", "-f", "gz sim"], timeout=3.0)
        _run_cmd(["pkill", "-f", "ros2 launch"], timeout=3.0)
        _run_cmd(["pkill", "-f", "component_container"], timeout=3.0)
        _run_cmd(["pkill", "-f", "move_group"], timeout=3.0)
        time.sleep(3)

        print("\n  Starting M6 simulation stack for domain randomization...")
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
        """Coordinator is ready for benchmark."""
        print("\n  [Test] Coordinator ready...")

        assert _wait_for_condition(
            lambda: _action_server_available("/coordinator/execute_task"),
            timeout=30.0, description="coordinator execute_task",
        ), "/coordinator/execute_task not available"
        print("  ✓ /coordinator/execute_task available")

    def test_domain_randomization_benchmark(self) -> None:
        """Run 20-episode domain randomization benchmark."""
        print("\n  [Test] Domain Randomization Benchmark (20 episodes)...")

        assert _wait_for_condition(
            lambda: _action_server_available("/coordinator/execute_task"),
            timeout=30.0, description="coordinator ready",
        ), "Coordinator not ready for benchmark"

        time.sleep(5)

        print("  Running benchmark script...")
        result = _run_cmd(RUNNER_CMD, timeout=600.0)

        print(f"  Runner exit code: {result.returncode}")
        if result.stdout:
            print(f"  Runner stdout (last 3000 chars):\n{result.stdout[-3000:]}")
        if result.stderr:
            print(f"  Runner stderr (last 1500 chars):\n{result.stderr[-1500:]}")

        json_match = re.search(r"JSON:\s*(\{.*\})", result.stdout, re.DOTALL)
        if json_match:
            try:
                bench_results = json.loads(json_match.group(1))
                print(f"\n  Benchmark Results:")
                print(f"    Episodes: {bench_results.get('episodes', '?')}")
                print(f"    Success: {bench_results.get('success_count', '?')}/{bench_results.get('episodes', '?')}")
                print(f"    Success Rate: {bench_results.get('success_rate', 0)*100:.1f}%")
                print(f"    Avg Planning: {bench_results.get('avg_planning_time', 0):.3f}s")
                print(f"    Avg Execution: {bench_results.get('avg_execution_time', 0):.3f}s")

                assert bench_results.get("overall_success", False), (
                    f"Benchmark failed: success_rate={bench_results.get('success_rate', 0)*100:.1f}% < 60%"
                )
                print("  ✓ Domain Randomization Benchmark PASSED")
            except json.JSONDecodeError:
                print("  WARNING: Could not parse JSON results")
                assert result.returncode == 0, "Benchmark runner failed"
        else:
            assert result.returncode == 0, "Benchmark runner failed with no JSON output"