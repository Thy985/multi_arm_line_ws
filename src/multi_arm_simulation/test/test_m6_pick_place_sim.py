"""M6 Pick-Place Simulation E2E Test — Phase 2 full stack closed loop.

Verifies the full M6 stack in Gazebo simulation:
    GazeboGroundTruth → WorldModel → Coordinator → MoveIt2 → JTC → Gazebo
    → JointStates → WorldModel update

This proves M6 is a "robot operating system runtime" — not just components
that work in isolation, but a full closed-loop system that:
    1. Perceives objects from Gazebo (ground truth)
    2. Updates WorldModel with object poses
    3. Accepts tasks via Coordinator
    4. Plans motion via MoveIt2
    5. Executes motion via JTC in Gazebo
    6. Robot actually moves (joint positions change)
    7. WorldModel tracks robot state

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
    "src/multi_arm_simulation/scripts/m6_pick_place_sim_e2e.py",
    "--timeout", "180",
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


def _ros2_topic_exists(topic: str) -> bool:
    """Check if a ROS2 topic exists."""
    result = _run_cmd(["ros2", "topic", "list"], timeout=3.0)
    if result.returncode != 0:
        return False
    return topic in result.stdout


def _ros2_controller_active(controller: str) -> bool:
    """Check if a ROS2 controller is active."""
    result = _run_cmd(["ros2", "control", "list_controllers"], timeout=3.0)
    if result.returncode != 0:
        return False
    return controller in result.stdout and "active" in result.stdout


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


class TestM6PickPlaceSimE2E:
    """Phase 2: Full M6 stack Pick-Place simulation E2E."""

    @pytest.fixture(autouse=True)
    def _launch_simulation(self) -> Any:
        """Launch full M6 simulation stack and clean up after test."""
        env = _source_env()

        print("\n  Starting M6 Pick-Place simulation stack...")
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

    def test_all_nodes_running(self) -> None:
        """All M6 stack nodes are running."""
        print("\n  [Test] All M6 stack nodes are running...")

        assert _wait_for_condition(
            lambda: _ros2_node_exists("gazebo_ground_truth"),
            timeout=20.0, description="ground truth node",
        ), "GazeboGroundTruthNode not running"
        print("  ✓ gazebo_ground_truth_node")

        assert _wait_for_condition(
            lambda: _ros2_node_exists("world_model"),
            timeout=10.0, description="world model node",
        ), "WorldModelNode not running"
        print("  ✓ world_model_node")

        assert _wait_for_condition(
            lambda: _ros2_node_exists("safety_supervisor"),
            timeout=10.0, description="safety node",
        ), "SafetySupervisor not running"
        print("  ✓ safety_supervisor")

        assert _wait_for_condition(
            lambda: _ros2_node_exists("coordinator"),
            timeout=15.0, description="coordinator node",
        ), "CoordinatorNode not running"
        print("  ✓ coordinator_node")

        assert _wait_for_condition(
            lambda: _ros2_node_exists("task_planner"),
            timeout=15.0, description="task planner node",
        ), "TaskPlannerNode not running"
        print("  ✓ task_planner_node")

    def test_moveit_available(self) -> None:
        """MoveIt2 move_group is running and action available."""
        print("\n  [Test] MoveIt2 is available...")

        assert _wait_for_condition(
            lambda: _ros2_node_exists("move_group"),
            timeout=30.0, description="move_group node",
        ), "move_group not running"
        print("  ✓ move_group running")

        assert _wait_for_condition(
            lambda: _action_server_available("/move_action"),
            timeout=15.0, description="move_action server",
        ), "move_action not available"
        print("  ✓ move_action available")

    def test_controllers_active(self) -> None:
        """Joint trajectory controllers are active."""
        print("\n  [Test] Controllers are active...")

        assert _wait_for_condition(
            lambda: _ros2_controller_active("arm1_joint_trajectory_controller"),
            timeout=30.0, description="arm1_JTC active",
        ), "arm1_JTC not active"
        print("  ✓ arm1_joint_trajectory_controller active")

        assert _wait_for_condition(
            lambda: _ros2_controller_active("arm2_joint_trajectory_controller"),
            timeout=10.0, description="arm2_JTC active",
        ), "arm2_JTC not active"
        print("  ✓ arm2_joint_trajectory_controller active")

    def test_perception_worldmodel_link(self) -> None:
        """Perception → WorldModel link: object poses flow."""
        print("\n  [Test] Perception → WorldModel link...")

        assert _wait_for_condition(
            lambda: _ros2_topic_exists("/perception/object_poses"),
            timeout=15.0, description="/perception/object_poses",
        ), "/perception/object_poses not available"
        print("  ✓ /perception/object_poses exists")

        assert _wait_for_condition(
            lambda: _ros2_topic_exists("/world_model/state"),
            timeout=10.0, description="/world_model/state",
        ), "/world_model/state not available"
        print("  ✓ /world_model/state exists")

        assert _wait_for_condition(
            lambda: _service_available("/world_model/query_world"),
            timeout=10.0, description="/world_model/query_world",
        ), "/world_model/query_world not available"
        print("  ✓ /world_model/query_world service available")

    def test_coordinator_action_available(self) -> None:
        """Coordinator ExecuteTask action is available."""
        print("\n  [Test] Coordinator action available...")

        assert _wait_for_condition(
            lambda: _action_server_available("/coordinator/execute_task"),
            timeout=20.0, description="coordinator execute_task",
        ), "/coordinator/execute_task not available"
        print("  ✓ /coordinator/execute_task available")

    def test_full_pick_place_e2e(self) -> None:
        """Full Pick-Place E2E: task execution + robot motion + state sync."""
        print("\n  [Test] Full Pick-Place E2E (runner script)...")

        assert _wait_for_condition(
            lambda: _action_server_available("/coordinator/execute_task"),
            timeout=30.0, description="coordinator ready",
        ), "Coordinator not ready for E2E"

        time.sleep(3)

        print("  Running E2E runner script...")
        result = _run_cmd(RUNNER_CMD, timeout=180.0)

        print(f"  Runner exit code: {result.returncode}")
        if result.stdout:
            print(f"  Runner stdout (last 2000 chars):\n{result.stdout[-2000:]}")
        if result.stderr:
            print(f"  Runner stderr (last 1000 chars):\n{result.stderr[-1000:]}")

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
                print("  ✓ Full Pick-Place E2E PASSED")
            except json.JSONDecodeError:
                print("  WARNING: Could not parse JSON results")
                assert result.returncode == 0, "E2E runner failed"
        else:
            assert result.returncode == 0, "E2E runner failed with no JSON output"

    def test_scene_summary(self) -> None:
        """Print full scene summary for debugging."""
        print("\n  [Test] M6 Simulation Scene Summary")
        print("  " + "=" * 60)

        time.sleep(5)

        result = _run_cmd(["ros2", "node", "list"], timeout=3.0)
        if result.returncode == 0:
            nodes = result.stdout.splitlines()
            print(f"  ROS2 nodes: {len(nodes)}")
            for n in sorted(nodes):
                if any(k in n for k in ["world", "safety", "coord", "planner",
                                        "ground", "move_group"]):
                    print(f"    {n}")

        result = _run_cmd(["ros2", "topic", "list"], timeout=3.0)
        if result.returncode == 0:
            topics = result.stdout.splitlines()
            print(f"  ROS2 topics: {len(topics)}")
            for t in sorted(topics):
                if any(k in t for k in ["perception", "world_model",
                                        "joint_states", "coordinator"]):
                    print(f"    {t}")

        result = _run_cmd(["ros2", "action", "list"], timeout=3.0)
        if result.returncode == 0:
            actions = result.stdout.splitlines()
            print(f"  ROS2 actions: {len(actions)}")
            for a in actions:
                print(f"    {a}")

        result = _run_cmd(["ros2", "service", "list"], timeout=3.0)
        if result.returncode == 0:
            services = result.stdout.splitlines()
            wm_services = [s for s in services if "world_model" in s]
            print(f"  WorldModel services: {len(wm_services)}")
            for s in wm_services:
                print(f"    {s}")

        print("  " + "=" * 60)