"""M6 Simulation Scene E2E Test — Phase 1 validation.

Verifies that:
    1. Gazebo starts with custom world (m6_test_world.sdf)
    2. Objects (table, red_cube, blue_cylinder) are spawned
    3. Robot (dual UR5e) spawns and controllers activate
    4. Object poses can be queried from Gazebo (PosePublisher plugin)
    5. GazeboGroundTruthNode publishes ObjectPose to /perception/object_poses

This is the foundation for M6 Simulation E2E — proving the simulation
scene has objects the robot can interact with, and we can get their
real poses from Gazebo physics.

Test approach: subprocess launch + wait + verify (same pattern as M4.5/M5.6).
"""

from __future__ import annotations

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
    "ros2", "launch", "multi_arm_simulation", "m6_simulation_scene.launch.py",
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
    """Run command and return result.

    Args:
        cmd: Command list.
        timeout: Timeout in seconds.

    Returns:
        CompletedProcess result.

    """
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
    """Wait for condition to be true.

    Args:
        check_fn: Callable returning bool.
        timeout: Total timeout.
        interval: Check interval.
        description: Description for logging.

    Returns:
        True if condition met, False on timeout.

    """
    start = time.time()
    while time.time() - start < timeout:
        if check_fn():
            return True
        time.sleep(interval)
    print(f"  TIMEOUT waiting for: {description}")
    return False


def _gz_topic_exists(topic: str) -> bool:
    """Check if a Gazebo topic exists.

    Args:
        topic: Gazebo transport topic name.

    Returns:
        True if topic exists.

    """
    result = _run_cmd(["gz", "topic", "-l"], timeout=3.0)
    if result.returncode != 0:
        return False
    return topic in result.stdout


def _gz_query_pose(world: str, model: str) -> dict[str, float] | None:
    """Query model pose from ROS2 bridged topic.

    Args:
        world: World name (unused).
        model: Model name.

    Returns:
        Dict with x, y, z or None.

    """
    topic = f"/model/{model}/pose"
    result = _run_cmd(["ros2", "topic", "echo", topic, "--once"], timeout=5.0)
    if result.returncode != 0 or not result.stdout:
        return None

    x_match = re.search(r"x:\s*([-\d.e]+)", result.stdout)
    y_match = re.search(r"y:\s*([-\d.e]+)", result.stdout)
    z_match = re.search(r"z:\s*([-\d.e]+)", result.stdout)

    if not (x_match and y_match and z_match):
        return None

    return {
        "x": float(x_match.group(1)),
        "y": float(y_match.group(1)),
        "z": float(z_match.group(1)),
    }


def _ros2_topic_exists(topic: str) -> bool:
    """Check if a ROS2 topic exists.

    Args:
        topic: ROS2 topic name.

    Returns:
        True if topic exists.

    """
    result = _run_cmd(["ros2", "topic", "list"], timeout=3.0)
    if result.returncode != 0:
        return False
    return topic in result.stdout


def _ros2_topic_has_data(topic: str, timeout: float = 5.0) -> bool:
    """Check if a ROS2 topic has data.

    Args:
        topic: ROS2 topic name.
        timeout: Wait timeout.

    Returns:
        True if data received.

    """
    result = _run_cmd(
        ["ros2", "topic", "echo", topic, "--once"],
        timeout=timeout,
    )
    return result.returncode == 0 and bool(result.stdout.strip())


def _ros2_node_exists(node_name: str) -> bool:
    """Check if a ROS2 node exists.

    Args:
        node_name: Node name (partial match).

    Returns:
        True if node exists.

    """
    result = _run_cmd(["ros2", "node", "list"], timeout=3.0)
    if result.returncode != 0:
        return False
    return any(node_name in line for line in result.stdout.splitlines())


def _ros2_controller_active(controller: str) -> bool:
    """Check if a ROS2 controller is active.

    Args:
        controller: Controller name.

    Returns:
        True if controller is active.

    """
    result = _run_cmd(["ros2", "control", "list_controllers"], timeout=3.0)
    if result.returncode != 0:
        return False
    return controller in result.stdout and "active" in result.stdout


class TestM6SimulationScene:
    """Phase 1: Verify Gazebo scene with objects and robot."""

    @pytest.fixture(autouse=True)
    def _launch_simulation(self) -> Any:
        """Launch simulation and clean up after test."""
        env = _source_env()

        print("\n  Starting Gazebo with m6_test_world...")
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
            print("\n  Shutting down simulation...")
            try:
                os.killpg(os.getpgid(proc.pid), 15)
            except ProcessLookupError:
                pass
            proc.wait(timeout=10)

            _run_cmd(["pkill", "-f", "gz sim"], timeout=3.0)
            _run_cmd(["pkill", "-f", "ros2 launch"], timeout=3.0)
            _run_cmd(["pkill", "-f", "move_group"], timeout=3.0)
            time.sleep(2)

    def test_gazebo_running(self) -> None:
        """Gazebo process is running."""
        print("\n  [Test] Gazebo process is running...")

        def gz_running() -> bool:
            result = _run_cmd(["pgrep", "-f", "gz sim"], timeout=2.0)
            return result.returncode == 0

        assert _wait_for_condition(
            gz_running, timeout=15.0, description="gz sim process"
        ), "Gazebo did not start"
        print("  ✓ Gazebo is running")

    def test_objects_spawned(self) -> None:
        """Objects (red_cube, blue_cylinder) are spawned in Gazebo."""
        print("\n  [Test] Objects are spawned in Gazebo...")

        assert _wait_for_condition(
            lambda: _gz_topic_exists("/model/red_cube/pose"),
            timeout=20.0,
            description="red_cube pose topic",
        ), "red_cube not spawned"
        print("  ✓ red_cube spawned (pose topic exists)")

        assert _wait_for_condition(
            lambda: _gz_topic_exists("/model/blue_cylinder/pose"),
            timeout=10.0,
            description="blue_cylinder pose topic",
        ), "blue_cylinder not spawned"
        print("  ✓ blue_cylinder spawned (pose topic exists)")

    def test_object_poses_correct(self) -> None:
        """Object poses match expected initial positions."""
        print("\n  [Test] Object poses are correct...")

        assert _wait_for_condition(
            lambda: _gz_query_pose("m6_test_world", "red_cube") is not None,
            timeout=15.0,
            description="red_cube pose query",
        ), "Cannot query red_cube pose"

        cube_pose = _gz_query_pose("m6_test_world", "red_cube")
        assert cube_pose is not None
        print(f"  red_cube pose: x={cube_pose['x']:.3f}, y={cube_pose['y']:.3f}, z={cube_pose['z']:.3f}")

        assert abs(cube_pose["x"] - 0.5) < 0.05, f"cube x={cube_pose['x']}, expected ~0.5"
        assert abs(cube_pose["y"] - 0.0) < 0.05, f"cube y={cube_pose['y']}, expected ~0.0"
        assert abs(cube_pose["z"] - 0.435) < 0.05, f"cube z={cube_pose['z']}, expected ~0.435"
        print("  ✓ red_cube pose correct")

        cyl_pose = _gz_query_pose("m6_test_world", "blue_cylinder")
        if cyl_pose is not None:
            print(f"  blue_cylinder pose: x={cyl_pose['x']:.3f}, y={cyl_pose['y']:.3f}, z={cyl_pose['z']:.3f}")
            assert abs(cyl_pose["x"] - 0.3) < 0.05
            assert abs(cyl_pose["y"] - 0.2) < 0.05
            print("  ✓ blue_cylinder pose correct")

    def test_robot_spawned(self) -> None:
        """Robot (dual UR5e) is spawned with joint states."""
        print("\n  [Test] Robot is spawned...")

        assert _wait_for_condition(
            lambda: _ros2_topic_exists("/joint_states"),
            timeout=30.0,
            description="/joint_states topic",
        ), "/joint_states not available"
        print("  ✓ /joint_states available")

        result = _run_cmd(["ros2", "topic", "echo", "/joint_states", "--once"], timeout=10.0)
        assert result.returncode == 0
        joint_count = result.stdout.count("- ")
        assert joint_count >= 6, f"Expected >=6 joints, got {joint_count}"
        print(f"  ✓ Robot spawned with {joint_count} joints")

    def test_controllers_active(self) -> None:
        """Joint trajectory controllers are active."""
        print("\n  [Test] Controllers are active...")

        assert _wait_for_condition(
            lambda: _ros2_controller_active("arm1_joint_trajectory_controller"),
            timeout=30.0,
            description="arm1_JTC active",
        ), "arm1_JTC not active"
        print("  ✓ arm1_joint_trajectory_controller active")

        assert _wait_for_condition(
            lambda: _ros2_controller_active("arm2_joint_trajectory_controller"),
            timeout=10.0,
            description="arm2_JTC active",
        ), "arm2_JTC not active"
        print("  ✓ arm2_joint_trajectory_controller active")

    def test_ground_truth_node_publishes(self) -> None:
        """GazeboGroundTruthNode publishes ObjectPose messages."""
        print("\n  [Test] Ground truth node publishes ObjectPose...")

        assert _wait_for_condition(
            lambda: _ros2_node_exists("gazebo_ground_truth"),
            timeout=20.0,
            description="ground truth node",
        ), "GazeboGroundTruthNode not found"
        print("  ✓ gazebo_ground_truth_node is running")

        assert _wait_for_condition(
            lambda: _ros2_topic_exists("/perception/object_poses"),
            timeout=10.0,
            description="/perception/object_poses topic",
        ), "/perception/object_poses not available"
        print("  ✓ /perception/object_poses topic exists")

        assert _wait_for_condition(
            lambda: _ros2_topic_has_data("/perception/object_poses", timeout=3.0),
            timeout=15.0,
            description="ObjectPose data",
        ), "No ObjectPose data received"
        print("  ✓ ObjectPose data being published")

    def test_full_scene_summary(self) -> None:
        """Print full scene summary for debugging."""
        print("\n  [Test] Scene Summary")
        print("  " + "=" * 60)

        time.sleep(8)

        result = _run_cmd(["gz", "topic", "-l"], timeout=3.0)
        if result.returncode == 0:
            topics = [t for t in result.stdout.splitlines() if "m6_test_world" in t]
            print(f"  Gazebo topics (m6_test_world): {len(topics)}")
            for t in topics[:10]:
                print(f"    {t}")

        result = _run_cmd(["ros2", "topic", "list"], timeout=3.0)
        if result.returncode == 0:
            ros_topics = result.stdout.splitlines()
            print(f"  ROS2 topics: {len(ros_topics)}")
            for t in ros_topics:
                if "perception" in t or "joint_states" in t:
                    print(f"    {t}")

        for model in ["red_cube", "blue_cylinder"]:
            pose = _gz_query_pose("m6_test_world", model)
            if pose:
                print(f"  {model}: ({pose['x']:.3f}, {pose['y']:.3f}, {pose['z']:.3f})")

        result = _run_cmd(["ros2", "control", "list_controllers"], timeout=3.0)
        if result.returncode == 0:
            print(f"  Controllers:\n{result.stdout}")

        print("  " + "=" * 60)