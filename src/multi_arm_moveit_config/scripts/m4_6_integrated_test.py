#!/usr/bin/env python3
"""M4.6 Integrated Test - launches simulation and runs tests in one process.

This script starts the simulation as a subprocess, waits for all nodes
to be ready, then runs the E2E tests.
"""

import subprocess
import sys
import time
import os
import signal

ENV_SETUP = """
source /opt/ros/jazzy/setup.bash
source /home/lenovo/multi_arm_line_ws/install/setup.bash
export PATH="/usr/bin:$PATH"
export ROS_HOME=/tmp/ros_home
export ROS_LOG_DIR=/tmp/ros_home/log
export GZ_SIM_SYSTEM_PLUGIN_PATH=/opt/ros/jazzy/lib:/opt/ros/jazzy/opt/gz_sim_vendor/lib/gz-sim-8/plugins
export PATH="/opt/ros/jazzy/opt/gz_tools_vendor/bin:$PATH"
"""

WORKSPACE = "/home/lenovo/multi_arm_line_ws"


def run_cmd(cmd, timeout=10):
    """Run a bash command and return output."""
    full_cmd = f"bash -c '{ENV_SETUP}\n{cmd}'"
    try:
        result = subprocess.run(
            full_cmd, shell=True, capture_output=True, text=True, timeout=timeout,
            cwd=WORKSPACE,
        )
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        return ""


def check_nodes():
    """Check if key nodes are running."""
    output = run_cmd("ros2 node list 2>&1")
    nodes = output.split("\n") if output else []
    key_nodes = ["coordinator_node", "task_planner_node", "move_group", "safety_supervisor", "world_model_node"]
    found = [n for n in key_nodes if any(n in line for line in nodes)]
    return len(found), found


def check_joint_states():
    """Check if /joint_states has data."""
    output = run_cmd("timeout 3 ros2 topic echo /joint_states --once 2>&1", timeout=10)
    return "header:" in output


def main():
    print("=== M4.6 Integrated Test ===")
    results = {}

    # Start simulation
    print("Starting simulation...")
    launch_cmd = f"""bash -c '{ENV_SETUP}
ros2 launch multi_arm_moveit_config m4_6_task_loop.launch.py &>/tmp/m46_integrated.log &
echo $!
'"""
    proc = subprocess.run(launch_cmd, shell=True, capture_output=True, text=True, cwd=WORKSPACE)
    launch_pid = proc.stdout.strip()
    print(f"Launch PID: {launch_pid}")

    # Wait for nodes
    print("Waiting for nodes to start...")
    max_wait = 90
    start = time.time()
    node_count = 0
    while time.time() - start < max_wait:
        time.sleep(5)
        node_count, found = check_nodes()
        print(f"  {time.time()-start:.0f}s: {node_count} key nodes ({found})")
        if node_count >= 3:
            break

    if node_count < 3:
        print(f"ERROR: Only {node_count} key nodes after {max_wait}s")
        results["0_simulation_ready"] = "FAIL"
        _print_results(results)
        sys.exit(1)

    results["0_simulation_ready"] = "PASS"

    # Check joint states
    print("Checking joint_states...")
    if check_joint_states():
        results["1.1_js_available"] = "PASS"
        print("  joint_states: OK")
    else:
        results["1.1_js_available"] = "FAIL"
        print("  joint_states: NOT AVAILABLE")

    # Check services
    print("Checking services...")
    services = run_cmd("ros2 service list 2>&1")
    if "/safety/safety_check" in services:
        results["2.1_safety_service"] = "PASS"
        print("  /safety/safety_check: OK")
    else:
        results["2.1_safety_service"] = "FAIL"
        print("  /safety/safety_check: NOT FOUND")

    if "/world_model/query_objects" in services:
        results["3.1_world_model_service"] = "PASS"
        print("  /world_model/query_objects: OK")
    else:
        results["3.1_world_model_service"] = "FAIL"
        print("  /world_model/query_objects: NOT FOUND")

    # Check actions
    print("Checking actions...")
    actions = run_cmd("ros2 action list 2>&1")
    if "/coordinator/execute_task" in actions:
        results["4.1_coordinator_action"] = "PASS"
        print("  /coordinator/execute_task: OK")
    else:
        results["4.1_coordinator_action"] = "FAIL"
        print("  /coordinator/execute_task: NOT FOUND")

    if "/move_action" in actions:
        results["4.2_move_action"] = "PASS"
        print("  /move_action: OK")
    else:
        results["4.2_move_action"] = "FAIL"
        print("  /move_action: NOT FOUND")

    if "/task_planner/execute_task" in actions:
        results["5.1_task_planner_action"] = "PASS"
        print("  /task_planner/execute_task: OK")
    else:
        results["5.1_task_planner_action"] = "FAIL"
        print("  /task_planner/execute_task: NOT FOUND")

    # Run Python E2E test
    print("Running Python E2E test...")
    test_output = run_cmd(
        "python3 src/multi_arm_moveit_config/scripts/m4_6_task_loop_test.py 2>&1",
        timeout=180,
    )
    print(test_output)

    if "1.1_js_available: PASS" in test_output:
        results["6.1_e2e_js"] = "PASS"
    else:
        results["6.1_e2e_js"] = "FAIL"

    if "4.1_coordinator_move: PASS" in test_output:
        results["6.2_e2e_coordinator"] = "PASS"
    else:
        results["6.2_e2e_coordinator"] = "FAIL"

    if "5.1_task_planner_bt: PASS" in test_output:
        results["6.3_e2e_task_planner"] = "PASS"
    else:
        results["6.3_e2e_task_planner"] = "FAIL"

    _print_results(results)

    # Cleanup
    print("Cleaning up...")
    run_cmd("pkill -f 'ros2 launch' 2>/dev/null; pkill -f gz 2>/dev/null; pkill -f move_group 2>/dev/null", timeout=5)

    all_pass = all(v == "PASS" for v in results.values())
    sys.exit(0 if all_pass else 1)


def _print_results(results):
    print("\n=== M4.6 Integrated Test Results ===")
    all_pass = True
    for k, v in sorted(results.items()):
        print(f"  {k}: {v}")
        if v != "PASS":
            all_pass = False
    print(f"Overall: {'ALL PASS' if all_pass else 'SOME FAILED'}")


if __name__ == "__main__":
    main()