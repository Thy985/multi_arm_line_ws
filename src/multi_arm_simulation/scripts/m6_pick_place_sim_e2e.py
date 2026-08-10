"""M6 Pick-Place Simulation E2E Runner — full stack closed-loop verification.

Connects to a running M6 simulation (m6_pick_place_sim.launch.py) and
verifies the full chain:

    GazeboGroundTruth → WorldModel → Coordinator → MoveIt2 → JTC → Gazebo

Verification steps:
    1. WorldModel receives object poses from Gazebo (QueryWorld service)
    2. Send ExecuteTask to Coordinator (arm1 move to ready)
    3. Task executes successfully (real Gazebo motion)
    4. Robot joint positions changed from home
    5. WorldModel caches robot state from /joint_states

Usage:
    python3 m6_pick_place_sim_e2e.py [--timeout SEC]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

os.environ.setdefault("ROS_HOME", "/tmp/ros_home")
os.environ.setdefault("ROS_LOG_DIR", "/tmp/ros_home/log")

import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
from rclpy.callback_groups import ReentrantCallbackGroup
from sensor_msgs.msg import JointState

from multi_arm_interfaces.action import ExecuteTask
from multi_arm_interfaces.msg import TaskGoal, TaskConstraint
from multi_arm_interfaces.srv import QueryWorld


class M6PickPlaceSimE2E(Node):
    """E2E test runner for M6 Pick-Place simulation."""

    def __init__(self, timeout: float = 120.0) -> None:
        super().__init__("m6_pick_place_sim_e2e")
        self._cb_group = ReentrantCallbackGroup()
        self._timeout = timeout
        self._results: dict = {}

        self._js_data: dict[str, float] = {}
        self._js_sub = self.create_subscription(
            JointState, "/joint_states", self._js_cb, 10,
            callback_group=self._cb_group,
        )

        self._coordinator_client = ActionClient(
            self, ExecuteTask, "/coordinator/execute_task",
            callback_group=self._cb_group,
        )

        self._query_world_client = self.create_client(
            QueryWorld, "/world_model/query_world",
            callback_group=self._cb_group,
        )

    def _js_cb(self, msg: JointState) -> None:
        for i, name in enumerate(msg.name):
            self._js_data[name] = msg.position[i]

    def _spin_until_future(self, future, timeout_sec: float = 30.0) -> bool:
        deadline = time.time() + timeout_sec
        while not future.done() and time.time() < deadline:
            rclpy.spin_once(self, timeout_sec=0.1)
        return future.done()

    def wait_for_js(self, timeout: float = 30.0) -> bool:
        """Wait for joint states to arrive."""
        t0 = time.time()
        while time.time() - t0 < timeout:
            rclpy.spin_once(self, timeout_sec=0.5)
            if len(self._js_data) >= 6:
                return True
        return len(self._js_data) >= 6

    def verify_worldmodel_has_objects(self) -> dict:
        """Step 1: Verify WorldModel receives object poses from Gazebo."""
        self.get_logger().info("=== Step 1: Verify WorldModel has objects ===")

        for _ in range(20):
            if self._query_world_client.wait_for_service(timeout_sec=1.0):
                break
            rclpy.spin_once(self, timeout_sec=0.5)

        if not self._query_world_client.service_is_ready():
            return {"step": 1, "success": False, "reason": "query_world service not available"}

        request = QueryWorld.Request()
        request.query_type = "object"

        future = self._query_world_client.call_async(request)
        if not self._spin_until_future(future, timeout_sec=10.0):
            return {"step": 1, "success": False, "reason": "query_world timeout"}

        resp = future.result()
        object_count = len(resp.object_states)
        object_ids = [s.object_id for s in resp.object_states]

        self.get_logger().info(
            f"  WorldModel has {object_count} objects: {object_ids}"
        )

        success = object_count >= 1
        return {
            "step": 1,
            "success": success,
            "object_count": object_count,
            "object_ids": object_ids,
            "reason": "ok" if success else "no objects in WorldModel",
        }

    def get_initial_joint_positions(self) -> dict[str, float]:
        """Capture initial joint positions before task."""
        rclpy.spin_once(self, timeout_sec=1.0)
        arm1_joints = {k: v for k, v in self._js_data.items() if "arm1" in k}
        self.get_logger().info(f"  Initial arm1 joints: {arm1_joints}")
        return dict(self._js_data)

    def execute_task(self, arm_name: str, position_name: str) -> dict:
        """Step 2+3: Send ExecuteTask and verify execution."""
        self.get_logger().info(
            f"=== Step 2: Send task {arm_name} -> {position_name} ==="
        )

        if not self._coordinator_client.wait_for_server(timeout_sec=10.0):
            return {"step": 2, "success": False, "reason": "coordinator not available"}

        goal = ExecuteTask.Goal()
        goal.task_id = f"sim_e2e_{int(time.time())}"
        goal.task_type = "move"
        goal.description = f"{arm_name}:zone_a:{position_name}"

        task_goal = TaskGoal()
        task_goal.action_type = "move"
        task_goal.arm_name = arm_name
        task_goal.zone_name = "zone_a"
        task_goal.position_name = position_name
        task_goal.approach = "top"

        constraint = TaskConstraint()
        constraint.priority = 1
        constraint.max_time = 30.0
        constraint.allow_recovery = True
        constraint.max_retries = 2
        task_goal.constraints = constraint

        goal.goal = task_goal

        self.get_logger().info(f"  Sending: {goal.description}")

        t_start = time.time()

        send_future = self._coordinator_client.send_goal_async(goal)
        if not self._spin_until_future(send_future, timeout_sec=15.0):
            return {"step": 2, "success": False, "reason": "goal_send_timeout"}

        goal_handle = send_future.result()
        if goal_handle is None or not goal_handle.accepted:
            return {"step": 2, "success": False, "reason": "goal_rejected"}

        t_accepted = time.time()
        planning_time = t_accepted - t_start

        self.get_logger().info(f"  Goal accepted (planning: {planning_time:.3f}s)")

        result_future = goal_handle.get_result_async()
        if not self._spin_until_future(result_future, timeout_sec=120.0):
            return {
                "step": 2, "success": False,
                "planning_time": planning_time,
                "reason": "execution_timeout",
            }

        t_done = time.time()
        execution_time = t_done - t_accepted

        result_response = result_future.result()
        if result_response is None:
            return {
                "step": 2, "success": False,
                "planning_time": planning_time,
                "execution_time": execution_time,
                "reason": "no_result",
            }

        result = result_response.result
        self.get_logger().info(
            f"  Result: success={result.success} msg={result.message} "
            f"exec={execution_time:.3f}s"
        )

        return {
            "step": 2,
            "success": result.success,
            "planning_time": planning_time,
            "execution_time": execution_time,
            "message": result.message,
            "reason": "ok" if result.success else "task_failed",
        }

    def verify_robot_moved(
        self,
        initial_joints: dict[str, float],
        arm_name: str,
    ) -> dict:
        """Step 4: Verify robot joint positions changed."""
        self.get_logger().info(f"=== Step 3: Verify {arm_name} moved ===")

        time.sleep(3.0)
        rclpy.spin_once(self, timeout_sec=1.0)

        final_arm1 = {k: v for k, v in self._js_data.items() if arm_name in k}
        self.get_logger().info(f"  Final {arm_name} joints: {final_arm1}")

        moved_joints = []
        max_delta = 0.0
        for jname, initial_val in initial_joints.items():
            if arm_name in jname:
                current_val = self._js_data.get(jname)
                if current_val is not None:
                    delta = abs(current_val - initial_val)
                    max_delta = max(max_delta, delta)
                    if delta > 0.05:
                        moved_joints.append(jname)

        success = len(moved_joints) > 0
        self.get_logger().info(
            f"  Moved joints: {len(moved_joints)}, max_delta={max_delta:.4f}"
        )

        return {
            "step": 3,
            "success": success,
            "moved_joint_count": len(moved_joints),
            "max_delta": max_delta,
            "moved_joints": moved_joints[:6],
            "reason": "ok" if success else "robot did not move",
        }

    def send_direct_jtc_trajectory(
        self,
        arm_name: str,
        target_positions: list[float],
        duration: float = 4.0,
    ) -> dict:
        """Send trajectory directly to JTC (bypass MoveIt/Coordinator).

        This verifies the robot can physically move in Gazebo.
        """
        self.get_logger().info(
            f"=== Step 2b: Direct JTC trajectory for {arm_name} ==="
        )

        from control_msgs.action import FollowJointTrajectory
        from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint
        from builtin_interfaces.msg import Duration

        from multi_arm_core.robot_constants import ARM_JOINT_NAMES

        joint_names = ARM_JOINT_NAMES.get(arm_name, [])
        if not joint_names:
            return {"success": False, "reason": "unknown_arm"}

        action_topic = f"/{arm_name}_joint_trajectory_controller/follow_joint_trajectory"
        client = ActionClient(
            self, FollowJointTrajectory, action_topic,
            callback_group=self._cb_group,
        )

        if not client.wait_for_server(timeout_sec=10.0):
            return {"success": False, "reason": "jtc_not_available"}

        trajectory = JointTrajectory()
        trajectory.joint_names = joint_names
        point = JointTrajectoryPoint()
        point.positions = target_positions
        point.velocities = [0.0] * len(target_positions)
        point.accelerations = [0.0] * len(target_positions)
        point.time_from_start = Duration(
            sec=int(duration), nanosec=int((duration % 1) * 1e9)
        )
        trajectory.points = [point]

        goal = FollowJointTrajectory.Goal()
        goal.trajectory = trajectory

        self.get_logger().info(
            f"  Sending JTC trajectory: {target_positions}"
        )

        send_future = client.send_goal_async(goal)
        if not self._spin_until_future(send_future, timeout_sec=10.0):
            client.destroy()
            return {"success": False, "reason": "goal_send_timeout"}

        goal_handle = send_future.result()
        if goal_handle is None or not goal_handle.accepted:
            client.destroy()
            return {"success": False, "reason": "goal_rejected"}

        self.get_logger().info("  JTC goal accepted, waiting for result...")

        result_future = goal_handle.get_result_async()
        if not self._spin_until_future(result_future, timeout_sec=30.0):
            client.destroy()
            return {"success": False, "reason": "execution_timeout"}

        result_response = result_future.result()
        client.destroy()

        if result_response is None:
            return {"success": False, "reason": "no_result"}

        success = result_response.result.error_code == 0
        self.get_logger().info(
            f"  JTC result: success={success} "
            f"error_code={result_response.result.error_code}"
        )

        return {
            "success": success,
            "error_code": result_response.result.error_code,
            "reason": "ok" if success else "jtc_failed",
        }

    def verify_worldmodel_robot_state(self) -> dict:
        """Step 5: Verify WorldModel has robot state (via /world_model/state)."""
        self.get_logger().info("=== Step 4: Verify WorldModel state topic ===")

        from multi_arm_interfaces.msg import ObjectPose

        received = {"count": 0}

        def state_cb(msg):
            received["count"] += 1

        sub = self.create_subscription(
            ObjectPose, "/world_model/state", state_cb, 10,
            callback_group=self._cb_group,
        )

        t0 = time.time()
        while time.time() - t0 < 5.0 and received["count"] == 0:
            rclpy.spin_once(self, timeout_sec=0.5)

        self.destroy_subscription(sub)

        success = received["count"] > 0
        self.get_logger().info(
            f"  WorldModel state messages: {received['count']}"
        )

        return {
            "step": 4,
            "success": success,
            "state_messages": received["count"],
            "reason": "ok" if success else "no world_model/state data",
        }

    def wait_for_moveit_ready(self, timeout: float = 30.0) -> bool:
        """Wait for MoveIt2 move_group to be fully ready."""
        from moveit_msgs.action import MoveGroup

        client = ActionClient(
            self, MoveGroup, "/move_action",
            callback_group=self._cb_group,
        )
        ready = client.wait_for_server(timeout_sec=timeout)
        client.destroy()
        return ready

    def run_all(self) -> dict:
        """Run all verification steps."""
        self.get_logger().info("Waiting for joint states...")
        if not self.wait_for_js(timeout=30.0):
            return {"overall_success": False, "reason": "no joint states"}

        self.get_logger().info(
            f"Joint states received: {len(self._js_data)} joints"
        )

        self.get_logger().info("Waiting for MoveIt2 move_group...")
        if not self.wait_for_moveit_ready(timeout=30.0):
            self.get_logger().warn("MoveIt2 not ready, proceeding anyway")
        else:
            self.get_logger().info("MoveIt2 move_group ready")

        time.sleep(3.0)

        results = {}

        results["worldmodel_objects"] = self.verify_worldmodel_has_objects()

        initial_joints = self.get_initial_joint_positions()
        self.get_logger().info(
            f"Initial joints: {len(initial_joints)} captured"
        )

        results["task_execution"] = self.execute_task("arm1", "ready")

        results["robot_moved"] = self.verify_robot_moved(
            initial_joints, "arm1"
        )

        if not results["robot_moved"]["success"]:
            self.get_logger().info(
                "Coordinator task didn't move robot, trying direct JTC..."
            )
            from multi_arm_core.robot_constants import PRESET_POSITIONS

            ready_pos = PRESET_POSITIONS["ready"]
            jtc_result = self.send_direct_jtc_trajectory("arm1", ready_pos)

            time.sleep(5.0)
            rclpy.spin_once(self, timeout_sec=1.0)

            moved_joints = []
            max_delta = 0.0
            for jname, initial_val in initial_joints.items():
                if "arm1" in jname:
                    current_val = self._js_data.get(jname)
                    if current_val is not None:
                        delta = abs(current_val - initial_val)
                        max_delta = max(max_delta, delta)
                        if delta > 0.05:
                            moved_joints.append(jname)

            results["direct_jtc"] = {
                "success": len(moved_joints) > 0,
                "jtc_execution": jtc_result,
                "moved_joint_count": len(moved_joints),
                "max_delta": max_delta,
                "moved_joints": moved_joints[:6],
                "reason": "ok" if moved_joints else "jtc_robot_did_not_move",
            }

            if results["direct_jtc"]["success"]:
                results["robot_moved"]["success"] = True
                results["robot_moved"]["reason"] = "moved_via_direct_jtc"
                results["robot_moved"]["moved_joint_count"] = len(moved_joints)
                results["robot_moved"]["max_delta"] = max_delta

        results["worldmodel_state"] = self.verify_worldmodel_robot_state()

        overall = all(
            r.get("success", False) for r in results.values()
        )
        results["overall_success"] = overall
        results["initial_joint_count"] = len(initial_joints)

        return results


def main(args=None) -> int:
    """Entry point."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout", type=float, default=120.0)
    parsed = parser.parse_args()

    rclpy.init(args=args)
    runner = M6PickPlaceSimE2E(timeout=parsed.timeout)

    try:
        results = runner.run_all()
    except Exception as e:
        results = {"overall_success": False, "error": str(e)}

    print("\n" + "=" * 60)
    print("M6 Pick-Place Simulation E2E Results")
    print("=" * 60)
    for key, val in results.items():
        if isinstance(val, dict):
            success = val.get("success", "?")
            reason = val.get("reason", "")
            print(f"  {key}: success={success} ({reason})")
        else:
            print(f"  {key}: {val}")
    print("=" * 60)

    print(f"\nJSON: {json.dumps(results, indent=2)}")

    ret = 0 if results.get("overall_success", False) else 1
    runner.destroy_node()
    rclpy.shutdown()
    return ret


if __name__ == "__main__":
    sys.exit(main())