#!/usr/bin/env python3
"""M4.5 Test Runner: Launches simulation, waits for stability, runs MoveIt tests.

Combines launch + test in a single process to work in sandbox environments.
"""

import os
import sys
import time
import subprocess
import signal
import yaml


def run_cmd(cmd, timeout=120):
    env = os.environ.copy()
    env["PATH"] = "/opt/ros/jazzy/opt/gz_tools_vendor/bin:/opt/ros/jazzy/bin:" + env.get("PATH", "/usr/bin")
    env["ROS_HOME"] = "/tmp/ros_home"
    env["ROS_LOG_DIR"] = "/tmp/ros_home/log"
    env["GZ_SIM_SYSTEM_PLUGIN_PATH"] = "/opt/ros/jazzy/lib:/opt/ros/jazzy/opt/gz_sim_vendor/lib/gz-sim-8/plugins"
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            timeout=timeout, env=env
        )
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        return "", "TIMEOUT", -1


def check_nodes():
    stdout, stderr, rc = run_cmd(
        "source /opt/ros/jazzy/setup.bash && source /home/lenovo/multi_arm_line_ws/install/setup.bash && ros2 node list",
        timeout=10
    )
    nodes = stdout.strip().split("\n") if stdout.strip() else []
    return nodes


def check_controllers():
    stdout, stderr, rc = run_cmd(
        "source /opt/ros/jazzy/setup.bash && source /home/lenovo/multi_arm_line_ws/install/setup.bash && ros2 control list_controllers",
        timeout=10
    )
    return stdout


def check_joint_states():
    stdout, stderr, rc = run_cmd(
        "source /opt/ros/jazzy/setup.bash && source /home/lenovo/multi_arm_line_ws/install/setup.bash && timeout 3 ros2 topic echo /joint_states --once 2>/dev/null",
        timeout=10
    )
    return stdout


def run_moveit_test(group_name, target_joints):
    test_script = f"""
import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
from moveit_msgs.action import MoveGroup
from moveit_msgs.msg import (MotionPlanRequest, PlanningOptions, RobotState,
                               Constraints, JointConstraint)
from sensor_msgs.msg import JointState
import time

class Tester(Node):
    def __init__(self):
        super().__init__('m45_tester')
        self.js = {{}}
        self.js_sub = self.create_subscription(JointState, '/joint_states', self.js_cb, 10)
        self.client = ActionClient(self, MoveGroup, '/move_action')

    def js_cb(self, msg):
        for i, n in enumerate(msg.name):
            self.js[n] = msg.position[i]

    def run(self, group, target):
        if not self.client.wait_for_server(timeout_sec=10.0):
            return False, 'MoveGroup action not available'
        goal = MoveGroup.Goal()
        goal.request.group_name = group
        goal.request.num_planning_attempts = 10
        goal.request.allowed_planning_time = 10.0
        goal.request.max_velocity_scaling_factor = 0.3
        goal.request.max_acceleration_scaling_factor = 0.3
        start = RobotState()
        start.joint_state.header.stamp = self.get_clock().now().to_msg()
        jnames = list(target.keys())
        start.joint_state.name = jnames
        start.joint_state.position = [self.js.get(n, 0.0) for n in jnames]
        goal.request.start_state = start
        c = Constraints()
        c.name = f'{{group}}_target'
        for jn, jv in target.items():
            jc = JointConstraint()
            jc.joint_name = jn
            jc.position = jv
            jc.tolerance_above = 0.05
            jc.tolerance_below = 0.05
            jc.weight = 1.0
            c.joint_constraints.append(jc)
        goal.request.goal_constraints = [c]
        goal.planning_options = PlanningOptions()
        goal.planning_options.plan_only = False
        goal.planning_options.replan = True
        goal.planning_options.replan_attempts = 3
        future = self.client.send_goal_async(goal)
        rclpy.spin_until_future_complete(self, future, timeout_sec=30.0)
        if not future.result() or not future.result().accepted:
            return False, 'Goal rejected'
        rf = self.client._get_result_future(future.result().goal_id)
        rclpy.spin_until_future_complete(self, rf, timeout_sec=60.0)
        if rf.result() is None:
            return False, 'Action timed out'
        err = rf.result().result.error_code.val
        if err == 1:
            return True, 'SUCCESS'
        return False, f'Error code: {{err}}'

rclpy.init()
node = Tester()
t0 = time.time()
while len(node.js) < 6 and time.time() - t0 < 10:
    rclpy.spin_once(node, timeout_sec=0.5)
group = '{group_name}'
target = {target_joints}
ok, msg = node.run(group, target)
print(f'RESULT:{{"PASS" if ok else "FAIL"}}|{{group}}|{{msg}}')
rclpy.shutdown()
"""
    stdout, stderr, rc = run_cmd(
        f"source /opt/ros/jazzy/setup.bash && source /home/lenovo/multi_arm_line_ws/install/setup.bash && python3 -c '{test_script}'",
        timeout=90
    )
    return stdout, stderr, rc


def main():
    print("=== M4.5 Motion + Coordination Validation ===")
    results = {}

    # Step 1: Launch simulation
    print("\n[1/6] Launching m4_5_motion.launch.py...")
    env = os.environ.copy()
    env["PATH"] = "/opt/ros/jazzy/opt/gz_tools_vendor/bin:/opt/ros/jazzy/bin:" + env.get("PATH", "/usr/bin")
    env["ROS_HOME"] = "/tmp/ros_home"
    env["ROS_LOG_DIR"] = "/tmp/ros_home/log"
    env["GZ_SIM_SYSTEM_PLUGIN_PATH"] = "/opt/ros/jazzy/lib:/opt/ros/jazzy/opt/gz_sim_vendor/lib/gz-sim-8/plugins"

    launch_proc = subprocess.Popen(
        "source /opt/ros/jazzy/setup.bash && source /home/lenovo/multi_arm_line_ws/install/setup.bash && "
        "ros2 launch multi_arm_moveit_config m4_5_motion.launch.py gazebo_gui:=false launch_rviz:=false",
        shell=True, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
    )

    # Step 2: Wait for nodes
    print("[2/6] Waiting for nodes to start (30s)...")
    time.sleep(30)

    # Step 3: Check nodes
    print("[3/6] Checking ROS2 nodes...")
    nodes = check_nodes()
    has_move_group = any("move_group" in n for n in nodes)
    has_wm = any("world_model" in n for n in nodes)
    has_safety = any("safety" in n for n in nodes)
    results["3_nodes_visible"] = "PASS" if (has_move_group or len(nodes) > 3) else "FAIL"
    print(f"  Nodes: {nodes[:10]}...")
    print(f"  move_group: {has_move_group}, world_model: {has_wm}, safety: {has_safety}")

    # Step 4: Check controllers
    print("[4/6] Checking controllers...")
    ctrl_output = check_controllers()
    has_left_arm_jtc = "left_arm_joint_trajectory_controller" in ctrl_output and "active" in ctrl_output
    has_right_arm_jtc = "right_arm_joint_trajectory_controller" in ctrl_output and "active" in ctrl_output
    has_jsb = "joint_state_broadcaster" in ctrl_output and "active" in ctrl_output
    results["4_controllers_active"] = "PASS" if (has_left_arm_jtc and has_right_arm_jtc and has_jsb) else "FAIL"
    print(f"  JSB: {has_jsb}, left_arm_JTC: {has_left_arm_jtc}, right_arm_JTC: {has_right_arm_jtc}")

    # Step 5: Check joint states
    print("[5/6] Checking joint_states...")
    js_output = check_joint_states()
    has_js = len(js_output) > 50
    results["5_joint_states"] = "PASS" if has_js else "FAIL"
    print(f"  Joint states received: {has_js} ({len(js_output)} bytes)")

    # Step 6: MoveIt planning test
    print("[6/6] Testing MoveIt left_arm planning (home -> ready)...")
    left_arm_ready = {
        "left_arm_shoulder_pan_joint": 0.0,
        "left_arm_shoulder_lift_joint": -1.57,
        "left_arm_elbow_joint": 1.57,
        "left_arm_wrist_1_joint": 0.0,
        "left_arm_wrist_2_joint": 0.0,
        "left_arm_wrist_3_joint": 0.0,
    }
    stdout, stderr, rc = run_moveit_test("left_arm", left_arm_ready)
    test_result = "FAIL"
    for line in stdout.split("\n"):
        if line.startswith("RESULT:"):
            parts = line.split("|")
            test_result = parts[0].replace("RESULT:", "")
            detail = parts[2] if len(parts) > 2 else ""
            print(f"  left_arm plan+execute: {test_result} ({detail})")
    results["6_left_arm_moveit_plan"] = test_result

    # Cleanup
    print("\nCleaning up...")
    launch_proc.terminate()
    try:
        launch_proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        launch_proc.kill()

    # Summary
    print("\n=== M4.5 Test Results ===")
    all_pass = True
    for k, v in results.items():
        print(f"  {k}: {v}")
        if v == "FAIL":
            all_pass = False
    print(f"\nOverall: {'ALL PASS' if all_pass else 'SOME FAILED'}")
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()