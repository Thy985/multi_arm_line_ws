#!/usr/bin/env python3
"""M4.5 Test 2+3: Dual-arm planning + Resource coordination."""

import sys
import time
import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
from moveit_msgs.action import MoveGroup
from moveit_msgs.msg import PlanningOptions, RobotState, Constraints, JointConstraint
from moveit_msgs.srv import GetMotionPlan
from sensor_msgs.msg import JointState


class M45DualArmTest(Node):

    def __init__(self):
        super().__init__("m45_dual_arm_test")
        self.js_data = {}
        self.js_sub = self.create_subscription(
            JointState, "/joint_states", self._js_cb, 10
        )
        self.move_client = ActionClient(self, MoveGroup, "/move_action")
        self.plan_cli = self.create_client(GetMotionPlan, "/plan_kinematic_path")

    def _js_cb(self, msg):
        for i, name in enumerate(msg.name):
            self.js_data[name] = msg.position[i]

    def wait_for_js(self, timeout=15.0):
        t0 = time.time()
        while time.time() - t0 < timeout:
            rclpy.spin_once(self, timeout_sec=0.5)
            if len(self.js_data) >= 6:
                return True
        return len(self.js_data) >= 6

    def plan_only(self, group_name, target_joints):
        if not self.plan_cli.wait_for_service(timeout_sec=5.0):
            return False, "no_service"
        req = GetMotionPlan.Request()
        req.motion_plan_request.group_name = group_name
        req.motion_plan_request.num_planning_attempts = 10
        req.motion_plan_request.allowed_planning_time = 10.0
        start = RobotState()
        start.joint_state.name = list(target_joints.keys())
        start.joint_state.position = [
            self.js_data.get(n, 0.0) for n in start.joint_state.name
        ]
        req.motion_plan_request.start_state = start
        c = Constraints()
        for jn, jv in target_joints.items():
            jc = JointConstraint()
            jc.joint_name = jn
            jc.position = jv
            jc.tolerance_above = 0.05
            jc.tolerance_below = 0.05
            jc.weight = 1.0
            c.joint_constraints.append(jc)
        req.motion_plan_request.goal_constraints = [c]
        future = self.plan_cli.call_async(req)
        rclpy.spin_until_future_complete(self, future, timeout_sec=30.0)
        result = future.result()
        if result and result.motion_plan_response.error_code.val == 1:
            pts = len(result.motion_plan_response.trajectory.joint_trajectory.points)
            return True, f"pts={pts}"
        ec = result.motion_plan_response.error_code.val if result else -999
        return False, f"error_{ec}"

    def check_service(self, srv_type, srv_name, req):
        cli = self.create_client(srv_type, srv_name)
        available = cli.wait_for_service(timeout_sec=5.0)
        if not available:
            return False, "no_service"
        future = cli.call_async(req)
        rclpy.spin_until_future_complete(self, future, timeout_sec=5.0)
        result = future.result()
        if result:
            return True, str(result)
        return False, "no_result"


def main():
    rclpy.init()
    node = M45DualArmTest()
    results = {}

    node.get_logger().info("=== M4.5 Test 2: Dual-Arm Planning ===")

    if not node.wait_for_js(timeout=15.0):
        node.get_logger().error("No joint_states!")
        results["2.0_js_available"] = "FAIL"
        _print_results(results)
        rclpy.shutdown()
        sys.exit(1)

    arm1_home = {
        "arm1_shoulder_pan_joint": 0.0, "arm1_shoulder_lift_joint": 0.0,
        "arm1_elbow_joint": 0.0, "arm1_wrist_1_joint": 0.0,
        "arm1_wrist_2_joint": 0.0, "arm1_wrist_3_joint": 0.0,
    }
    arm2_home = {
        "arm2_shoulder_pan_joint": 0.0, "arm2_shoulder_lift_joint": 0.0,
        "arm2_elbow_joint": 0.0, "arm2_wrist_1_joint": 0.0,
        "arm2_wrist_2_joint": 0.0, "arm2_wrist_3_joint": 0.0,
    }

    ok, msg = node.plan_only("arm1", arm1_home)
    results["2.1_arm1_plan"] = "PASS" if ok else "FAIL"
    node.get_logger().info(f"arm1 plan: {msg}")

    ok2, msg2 = node.plan_only("arm2", arm2_home)
    results["2.2_arm2_plan"] = "PASS" if ok2 else "FAIL"
    node.get_logger().info(f"arm2 plan: {msg2}")

    dual_home = {**arm1_home, **arm2_home}
    ok3, msg3 = node.plan_only("dual_arm", dual_home)
    results["2.3_dual_arm_plan"] = "PASS" if ok3 else "FAIL"
    node.get_logger().info(f"dual_arm plan: {msg3}")

    node.get_logger().info("=== M4.5 Test 3: Resource Coordination ===")

    try:
        from multi_arm_interfaces.srv import SafetyCheck, ResourceRequest
        ok_s, msg_s = node.check_service(
            SafetyCheck, "/safety/safety_check",
            SafetyCheck.Request(arm_id="arm1", velocity_scale=0.5)
        )
        results["3.1_safety_check"] = "PASS" if ok_s else "FAIL"
        node.get_logger().info(f"SafetyCheck: {msg_s}")

        ok_r, msg_r = node.check_service(
            ResourceRequest, "/coordinator/resource_request",
            ResourceRequest.Request(arm_id="arm1", resource_id="zone_a", action="acquire")
        )
        results["3.2_resource_request"] = "PASS" if ok_r else "FAIL"
        node.get_logger().info(f"ResourceRequest: {msg_r}")
    except ImportError:
        node.get_logger().warn("multi_arm_interfaces not available for service test")
        results["3.1_safety_check"] = "SKIP"
        results["3.2_resource_request"] = "SKIP"

    _print_results(results)
    rclpy.shutdown()
    all_pass = all(v in ("PASS", "SKIP") for v in results.values())
    sys.exit(0 if all_pass else 1)


def _print_results(results):
    print("\n=== M4.5 Test 2+3 Results ===")
    all_pass = True
    for k, v in results.items():
        print(f"  {k}: {v}")
        if v == "FAIL":
            all_pass = False
    print(f"Overall: {'ALL PASS' if all_pass else 'SOME FAILED'}")


if __name__ == "__main__":
    main()
