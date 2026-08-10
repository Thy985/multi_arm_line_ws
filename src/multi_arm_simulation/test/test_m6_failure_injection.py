"""M6 Failure Injection Simulation E2E Test — Phase 3 recovery validation.

Verifies the M6 stack's failure recovery in Gazebo simulation:

    Scenario 1: Planning failure injection (unreachable target)
    Scenario 2: Safety check service verification
    Scenario 3: E-Stop activation and task rejection
    Scenario 4: Normal task after failure recovery
    Scenario 5: WorldModel consistency after failures

This proves the system degrades gracefully — when failures occur,
the system handles them, recovers, and maintains state consistency.

Test approach: subprocess launch + run E2E runner script + verify results.
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
    "m6_pick_place_sim.launch.py",
]

RUNNER_CMD = [
    "python3",
    "src/multi_arm_simulation/scripts/m6_failure_injection_e2e.py",
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


def _ros2_node_exists(node_name: str) -> bool:
    """Check if a ROS2 node exists."""
    result = _run_cmd(["ros2", "node", "list"], timeout=3.0)
    if result.returncode != 0:
        return False
    return any(node_name in line for line in result.stdout.splitlines())


def _action_server_available(action: str) -> bool:
    """Check if a ROS2 action server is available."""
    result = _run_cmd(["ros2", "action", "list"], timeout=3.0)
    if result.returncode != 0:
        return False
    return action in result.stdout


def _service_available(service: str) -> bool:
    """Check if a ROS2 service is available."""
    result = _run_cmd(["ros2", "service", "list"], timeout=3.0)
    if result.returncode != 0:
        return False
    return service in result.stdout


class TestM6FailureInjectionE2E:
    """Phase 3: Failure injection and recovery in simulation."""

    @pytest.fixture(autouse=True)
    def _launch_simulation(self) -> Any:
        """Launch full M6 simulation stack and clean up after test."""
        env = _source_env()

        print("\n  Starting M6 simulation stack for failure injection...")
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

            _run_cmd(["pkill", "-f", "gz sim"], timeout=3.0)
            _run_cmd(["pkill", "-f", "ros2 launch"], timeout=3.0)
            _run_cmd(["pkill", "-f", "move_group"], timeout=3.0)
            _run_cmd(["pkill", "-f", "component_container"], timeout=3.0)
            time.sleep(3)

    def test_safety_services_available(self) -> None:
        """Safety services are available for failure injection."""
        print("\n  [Test] Safety services available...")

        assert _wait_for_condition(
            lambda: _service_available("/safety/safety_check"),
            timeout=20.0, description="/safety/safety_check",
        ), "/safety/safety_check not available"
        print("  ✓ /safety/safety_check available")

        assert _wait_for_condition(
            lambda: _service_available("/safety/emergency_stop"),
            timeout=10.0, description="/safety/emergency_stop",
        ), "/safety/emergency_stop not available"
        print("  ✓ /safety/emergency_stop available")

    def test_coordinator_ready(self) -> None:
        """Coordinator is ready for failure injection."""
        print("\n  [Test] Coordinator ready...")

        assert _wait_for_condition(
            lambda: _action_server_available("/coordinator/execute_task"),
            timeout=30.0, description="coordinator execute_task",
        ), "/coordinator/execute_task not available"
        print("  ✓ /coordinator/execute_task available")

    def test_worldmodel_ready(self) -> None:
        """WorldModel is ready with objects before failure injection."""
        print("\n  [Test] WorldModel ready...")

        assert _wait_for_condition(
            lambda: _service_available("/world_model/query_world"),
            timeout=20.0, description="/world_model/query_world",
        ), "/world_model/query_world not available"
        print("  ✓ /world_model/query_world available")

    def test_full_failure_injection_e2e(self) -> None:
        """Full failure injection E2E: 5 scenarios."""
        print("\n  [Test] Full Failure Injection E2E (5 scenarios)...")

        assert _wait_for_condition(
            lambda: _action_server_available("/coordinator/execute_task"),
            timeout=30.0, description="coordinator ready",
        ), "Coordinator not ready for E2E"

        time.sleep(5)

        print("  Running failure injection runner script...")
        result = _run_cmd(RUNNER_CMD, timeout=180.0)

        print(f"  Runner exit code: {result.returncode}")
        if result.stdout:
            print(f"  Runner stdout (last 3000 chars):\n{result.stdout[-3000:]}")
        if result.stderr:
            print(f"  Runner stderr (last 1500 chars):\n{result.stderr[-1500:]}")

        json_match = re.search(r"JSON:\s*(\{.*\})", result.stdout, re.DOTALL)
        if json_match:
            try:
                e2e_results = json.loads(json_match.group(1))
                print(f"\n  E2E Results:")
                for key, val in e2e_results.items():
                    if isinstance(val, dict):
                        print(f"    {key}: success={val.get('success', '?')}")
                    else:
                        print(f"    {key}: {val}")

                assert e2e_results.get("overall_success", False), (
                    f"E2E failed: {e2e_results}"
                )
                print("  ✓ Full Failure Injection E2E PASSED")
            except json.JSONDecodeError:
                print("  WARNING: Could not parse JSON results")
                assert result.returncode == 0, "E2E runner failed"
        else:
            assert result.returncode == 0, "E2E runner failed with no JSON output"