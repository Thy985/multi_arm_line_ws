"""TaskPlannerNode - ROS2 node for behavior tree-based task planning (L6)."""

import os
from typing import Dict, Optional

import rclpy
from rclpy.action import ActionServer
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node

from multi_arm_task_planner.behavior_tree import BehaviorTree, Blackboard, NodeStatus
from multi_arm_task_planner.bt_plugins.pick_place_plugins import PLUGIN_REGISTRY
from multi_arm_task_planner.bt_plugins.ros2_plugins import ROS2_PLUGIN_REGISTRY

TASK_XML_MAP: Dict[str, str] = {
    "pick_place": "pick_place.xml",
    "pick_place_ros2": "pick_place_ros2.xml",
    "assembly": "assembly.xml",
    "inspection": "inspection.xml",
}


class TaskPlannerNode(Node):
    """Task planner node using Behavior Trees.

    Loads BT XML definitions and executes them using registered Python plugins.
    XML format is compatible with BehaviorTree.CPP / Groot for visualization.

    Supports both mock plugins (for unit testing) and ROS2 plugins
    (for real service calls). The plugin set is selected based on
    the 'use_ros2_plugins' parameter.
    """

    def __init__(self) -> None:
        super().__init__("task_planner_node")

        cb_group = ReentrantCallbackGroup()

        use_ros2 = self.declare_parameter("use_ros2_plugins", False).value

        if use_ros2:
            merged_registry = {**PLUGIN_REGISTRY, **ROS2_PLUGIN_REGISTRY}
            self.get_logger().info("Using ROS2-enabled BT plugins")
        else:
            merged_registry = dict(PLUGIN_REGISTRY)
            self.get_logger().info("Using mock BT plugins")

        self._bt = BehaviorTree(blackboard=Blackboard())
        self._bt.register_plugins(merged_registry)
        self._current_tree_name: Optional[str] = None

        self._init_services(cb_group)

        self.get_logger().info("TaskPlanner node started")
        self.get_logger().info(f"Registered plugins: {list(merged_registry.keys())}")

    def _init_services(self, cb_group: ReentrantCallbackGroup) -> None:
        """Initialize action servers."""
        try:
            from multi_arm_interfaces.action import ExecuteTask

            self._execute_task_server = ActionServer(
                self,
                ExecuteTask,
                "/task_planner/execute_task",
                self._on_execute_task,
                callback_group=cb_group,
            )
        except ImportError:
            self.get_logger().warn("multi_arm_interfaces not available, action server disabled")
            self._execute_task_server = None

    def _resolve_xml_path(self, task_type: str) -> Optional[str]:
        """Resolve task_type to an XML file path.

        Args:
            task_type: Task type string (e.g. 'pick_place').

        Returns:
            Absolute path to the BT XML file, or None if not found.
        """
        xml_name = TASK_XML_MAP.get(task_type)
        if xml_name is None:
            self.get_logger().warn(f"No XML mapping for task_type: {task_type}")
            return None

        xml_dir = os.path.join(os.path.dirname(__file__), "bt_xml")
        xml_path = os.path.join(xml_dir, xml_name)

        if os.path.exists(xml_path):
            return xml_path

        try:
            from ament_index_python.packages import get_package_share_directory
            pkg_dir = get_package_share_directory("multi_arm_task_planner")
            xml_path = os.path.join(pkg_dir, "bt_xml", xml_name)
            if os.path.exists(xml_path):
                return xml_path
        except Exception:
            pass

        self.get_logger().error(f"BT XML not found: {xml_name}")
        return None

    def load_tree(self, xml_path: str) -> bool:
        """Load a behavior tree from XML file.

        Args:
            xml_path: Path to the BT XML file.

        Returns:
            True if loaded successfully.
        """
        if not os.path.exists(xml_path):
            self.get_logger().error(f"BT XML not found: {xml_path}")
            return False

        try:
            self._bt.load_xml(xml_path)
            self._current_tree_name = os.path.basename(xml_path)
            self.get_logger().info(f"Loaded BT: {self._current_tree_name}")
            return True
        except Exception as e:
            self.get_logger().error(f"Failed to load BT XML: {e}")
            return False

    async def _on_execute_task(self, goal_handle) -> object:
        """Handle ExecuteTask action.

        Resolves task_type to BT XML, loads it, and executes the tree.
        """
        from multi_arm_interfaces.action import ExecuteTask

        goal = goal_handle.request
        self.get_logger().info(f"Executing task: {goal.task_id} ({goal.task_type})")

        xml_path = self._resolve_xml_path(goal.task_type)
        if xml_path is None:
            goal_handle.abort()
            result = ExecuteTask.Result()
            result.success = False
            result.message = f"No BT XML for task_type: {goal.task_type}"
            return result

        if not self.load_tree(xml_path):
            goal_handle.abort()
            result = ExecuteTask.Result()
            result.success = False
            result.message = f"Failed to load BT for: {goal.task_type}"
            return result

        self._bt.blackboard.set("task_id", goal.task_id)
        self._bt.blackboard.set("task_type", goal.task_type)
        self._bt.blackboard.set("arm_name", "arm1")
        self._bt.blackboard.set("target_zone", "zone_a")
        self._bt.blackboard.set("target_position", "ready")
        self._bt.blackboard.set("object_id", "red_cube")

        self._bt.reset()
        max_ticks = 100
        for i in range(max_ticks):
            status = self._bt.tick()

            if goal_handle.is_cancel_requested:
                goal_handle.abort()
                result = ExecuteTask.Result()
                result.success = False
                result.message = "Task cancelled"
                return result

            if status == NodeStatus.SUCCESS:
                goal_handle.succeed()
                result = ExecuteTask.Result()
                result.success = True
                result.message = "Task completed successfully"
                return result
            if status == NodeStatus.FAILURE:
                goal_handle.abort()
                result = ExecuteTask.Result()
                result.success = False
                result.message = "Task failed"
                return result

        goal_handle.abort()
        result = ExecuteTask.Result()
        result.success = False
        result.message = "Task timed out (max ticks reached)"
        return result

    @property
    def behavior_tree(self) -> BehaviorTree:
        """Access the behavior tree (for testing)."""
        return self._bt


def main(args=None) -> None:
    """Entry point for the task planner node."""
    rclpy.init(args=args)
    node = TaskPlannerNode()
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
    main()