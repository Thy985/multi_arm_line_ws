#!/usr/bin/env python3
"""Launch smoke test — verifies ROS2 nodes can start and respond.

Tests that core nodes can be launched and are alive within a timeout.
Does NOT require Gazebo — uses minimal node startup only.
"""

import os
import subprocess
import sys
import time

os.environ.setdefault("ROS_HOME", "/tmp/ros_home")
os.environ.setdefault("ROS_LOG_DIR", "/tmp/ros_home/log")

LAUNCH_TIMEOUT = 30
CHECK_INTERVAL = 1.0


def check_node_alive(node_name: str, timeout: float = 10.0) -> bool:
    """Check if a ROS2 node is alive using ros2 node list."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            result = subprocess.run(
                ["ros2", "node", "list"],
                capture_output=True, text=True, timeout=5.0,
                env={**os.environ, "PATH": "/usr/bin:/usr/local/bin:/opt/ros/jazzy/bin:"
                     + os.environ.get("PATH", "")}
            )
            if node_name in result.stdout:
                return True
        except (subprocess.TimeoutExpired, Exception):
            pass
        time.sleep(CHECK_INTERVAL)
    return False


def test_coordinator_node() -> bool:
    """Test CoordinatorNode can start and be discovered."""
    print("  Testing CoordinatorNode launch...")
    proc = None
    try:
        env = {**os.environ}
        env["PATH"] = "/usr/bin:/usr/local/bin:/opt/ros/jazzy/bin:" + env.get("PATH", "")
        proc = subprocess.Popen(
            ["ros2", "run", "multi_arm_core", "coordinator_node"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env
        )
        alive = check_node_alive("coordinator_node", timeout=15.0)
        if alive:
            print("    CoordinatorNode: ALIVE")
            return True
        else:
            print("    CoordinatorNode: NOT FOUND")
            return False
    except Exception as e:
        print(f"    CoordinatorNode: ERROR - {e}")
        return False
    finally:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                proc.kill()


def test_safety_node() -> bool:
    """Test SafetySupervisorNode can start and be discovered."""
    print("  Testing SafetySupervisorNode launch...")
    proc = None
    try:
        env = {**os.environ}
        env["PATH"] = "/usr/bin:/usr/local/bin:/opt/ros/jazzy/bin:" + env.get("PATH", "")
        proc = subprocess.Popen(
            ["ros2", "run", "multi_arm_safety", "safety_supervisor_node"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env
        )
        alive = check_node_alive("safety_supervisor_node", timeout=15.0)
        if alive:
            print("    SafetySupervisorNode: ALIVE")
            return True
        else:
            print("    SafetySupervisorNode: NOT FOUND")
            return False
    except Exception as e:
        print(f"    SafetySupervisorNode: ERROR - {e}")
        return False
    finally:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                proc.kill()


def test_world_model_node() -> bool:
    """Test WorldModelNode can start and be discovered."""
    print("  Testing WorldModelNode launch...")
    proc = None
    try:
        env = {**os.environ}
        env["PATH"] = "/usr/bin:/usr/local/bin:/opt/ros/jazzy/bin:" + env.get("PATH", "")
        proc = subprocess.Popen(
            ["ros2", "run", "multi_arm_world_model", "world_model_node"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env
        )
        alive = check_node_alive("world_model_node", timeout=15.0)
        if alive:
            print("    WorldModelNode: ALIVE")
            return True
        else:
            print("    WorldModelNode: NOT FOUND")
            return False
    except Exception as e:
        print(f"    WorldModelNode: ERROR - {e}")
        return False
    finally:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                proc.kill()


def main() -> int:
    results = {}

    tests = [
        ("coordinator", test_coordinator_node),
        ("safety", test_safety_node),
        ("world_model", test_world_model_node),
    ]

    for name, test_fn in tests:
        try:
            results[name] = test_fn()
        except Exception as e:
            print(f"  {name}: EXCEPTION - {e}")
            results[name] = False

    print("\n=== Launch Smoke Test Results ===")
    all_pass = True
    for name, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  {name}: {status}")
        if not passed:
            all_pass = False

    print(f"\nOverall: {'ALL PASS' if all_pass else 'SOME FAILED'}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())