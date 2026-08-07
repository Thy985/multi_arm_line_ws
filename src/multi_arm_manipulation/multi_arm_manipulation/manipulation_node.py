"""Manipulation Node — ROS2 node for gripper control and grasping.

Provides:
    - /manipulation/control_gripper (ControlGripper.srv)
    - /manipulation/grasp_object (GraspObject.action)

Integrates with WorldModel:
    - Updates State Layer (attached_to, grasp_state)
    - Updates Relation Layer (attached_to, on relations)
"""

from __future__ import annotations

import sys
import time

import rclpy
from rclpy.node import Node
from rclpy.action import ActionServer, GoalResponse, CancelResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor

from multi_arm_interfaces.srv import ControlGripper
from multi_arm_interfaces.action import GraspObject

from .gripper_controller import GripperController, GripperState
from .grasp_planner import GraspPlanner


class ManipulationNode(Node):
    """ROS2 node for manipulation operations.

    Services:
        - /manipulation/control_gripper: Open/close/attach/detach gripper

    Actions:
        - /manipulation/grasp_object: Full grasp sequence

    WorldModel integration:
        - Calls /world_model/query_world to get object position
        - Updates relations via internal RelationLayer reference
    """

    def __init__(self) -> None:
        """Initialize manipulation node."""
        super().__init__("manipulation_node")

        cb_group = ReentrantCallbackGroup()

        self.declare_parameter("arm_names", ["arm1", "arm2"])

        arm_names = list(self.get_parameter("arm_names").value)
        self._gripper = GripperController()
        self._grasp_planner = GraspPlanner()

        for arm in arm_names:
            self._gripper.register_gripper(arm)

        self._control_srv = self.create_service(
            ControlGripper,
            "/manipulation/control_gripper",
            self._handle_control_gripper,
            callback_group=cb_group,
        )

        self._grasp_action = ActionServer(
            self,
            GraspObject,
            "/manipulation/grasp_object",
            self._execute_grasp_callback,
            goal_callback=self._grasp_goal_callback,
            cancel_callback=self._grasp_cancel_callback,
            callback_group=cb_group,
        )

        self.get_logger().info(
            f"ManipulationNode started for arms: {arm_names}"
        )

    def _handle_control_gripper(
        self,
        request: ControlGripper.Request,
        response: ControlGripper.Response,
    ) -> ControlGripper.Response:
        """Handle ControlGripper service request.

        Args:
            request: Service request.
            response: Service response.

        Returns:
            Filled response.

        """
        arm = request.arm_name
        cmd = request.command
        obj = request.object_id
        force = request.force

        self.get_logger().info(
            f"Gripper control: arm={arm}, cmd={cmd}, obj={obj}, force={force}"
        )

        if cmd == "open":
            success, msg = self._gripper.open(arm)
        elif cmd == "close":
            success, msg = self._gripper.close(arm, force)
        elif cmd == "attach":
            success, msg = self._gripper.attach(arm, obj)
        elif cmd == "detach":
            success, msg = self._gripper.detach(arm)
        else:
            success = False
            msg = f"Unknown command: {cmd}"

        response.success = success
        response.message = msg
        return response

    def _grasp_goal_callback(self, goal_request) -> GoalResponse:
        """Accept grasp goals.

        Args:
            goal_request: Goal request.

        Returns:
            GoalResponse.ACCEPT.

        """
        self.get_logger().info(
            f"Grasp request: arm={goal_request.arm_name}, "
            f"object={goal_request.object_id}, approach={goal_request.approach}"
        )
        return GoalResponse.ACCEPT

    def _grasp_cancel_callback(self, goal_handle) -> CancelResponse:
        """Accept cancel requests.

        Args:
            goal_handle: Goal handle.

        Returns:
            CancelResponse.ACCEPT.

        """
        self.get_logger().info("Grasp cancel requested")
        return CancelResponse.ACCEPT

    def _execute_grasp_callback(self, goal_handle) -> GraspObject.Result:
        """Execute grasp action.

        Args:
            goal_handle: Action goal handle.

        Returns:
            GraspObject result.

        """
        request = goal_handle.request
        arm = request.arm_name
        obj = request.object_id
        approach = request.approach

        result = GraspObject.Result()
        feedback = GraspObject.Feedback()

        feedback.status = "closing_gripper"
        feedback.progress = 0.1
        goal_handle.publish_feedback(feedback)

        success, msg = self._gripper.close(arm, force=20.0)
        if not success:
            result.success = False
            result.message = f"Close failed: {msg}"
            result.attached = False
            goal_handle.abort()
            return result

        time.sleep(0.1)

        feedback.status = "attaching_object"
        feedback.progress = 0.5
        goal_handle.publish_feedback(feedback)

        success, msg = self._gripper.attach(arm, obj)
        if not success:
            result.success = False
            result.message = f"Attach failed: {msg}"
            result.attached = False
            goal_handle.abort()
            return result

        feedback.status = "grasp_complete"
        feedback.progress = 1.0
        goal_handle.publish_feedback(feedback)

        goal_handle.succeed()

        result.success = True
        result.message = f"Object {obj} grasped by {arm}"
        result.attached = True
        return result


def main(args: list[str] | None = None) -> None:
    """Entry point for manipulation node.

    Args:
        args: Command line arguments.

    """
    rclpy.init(args=args)
    node = ManipulationNode()
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main(sys.argv)