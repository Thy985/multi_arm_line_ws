#!/usr/bin/env python3
"""M4.6 Autonomous Task Loop Test - Standalone (no Gazebo dependency).

Tests the M4.6 code changes using pure Python + ROS2 node mocking.
This validates the architecture without requiring Gazebo simulation.

Test categories:
1. MoveItInterface - construction and method signatures
2. Coordinator ExecuteTask action server - parse_task logic
3. ROS2 BT plugins - registry and class structure
4. TaskPlanner task_type mapping - XML resolution
5. robot_constants - shared constants
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

results = {}


def test_robot_constants():
    """Test shared robot constants module."""
    from multi_arm_core.robot_constants import ARM_JOINT_NAMES, PRESET_POSITIONS

    assert "arm1" in ARM_JOINT_NAMES, "arm1 not in ARM_JOINT_NAMES"
    assert "arm2" in ARM_JOINT_NAMES, "arm2 not in ARM_JOINT_NAMES"
    assert len(ARM_JOINT_NAMES["arm1"]) == 6, "arm1 should have 6 joints"
    assert "home" in PRESET_POSITIONS, "home not in PRESET_POSITIONS"
    assert "ready" in PRESET_POSITIONS, "ready not in PRESET_POSITIONS"
    assert len(PRESET_POSITIONS["home"]) == 6, "home should have 6 positions"
    results["1.1_robot_constants"] = "PASS"


def test_moveit_interface_import():
    """Test MoveItInterface can be imported and constructed."""
    from multi_arm_core.moveit_interface import MoveItInterface

    assert hasattr(MoveItInterface, "plan_and_execute"), "Missing plan_and_execute"
    assert hasattr(MoveItInterface, "move_to_preset"), "Missing move_to_preset"
    assert hasattr(MoveItInterface, "is_available"), "Missing is_available"
    assert hasattr(MoveItInterface, "update_joint_states"), "Missing update_joint_states"
    results["2.1_moveit_interface_import"] = "PASS"


def test_coordinator_parse_task():
    """Test Coordinator._parse_task logic."""
    from multi_arm_core.coordinator_node import CoordinatorNode

    arm, zone, pos = CoordinatorNode._parse_task(None, "move", "arm1:zone_a:ready")
    assert arm == "arm1", f"Expected arm1, got {arm}"
    assert zone == "zone_a", f"Expected zone_a, got {zone}"
    assert pos == "ready", f"Expected ready, got {pos}"

    arm, zone, pos = CoordinatorNode._parse_task(None, "move", "arm2:zone_b:home")
    assert arm == "arm2", f"Expected arm2, got {arm}"
    assert zone == "zone_b", f"Expected zone_b, got {zone}"
    assert pos == "home", f"Expected home, got {pos}"

    arm, zone, pos = CoordinatorNode._parse_task(None, "pick_place", "")
    assert arm == "arm1", f"Default arm should be arm1, got {arm}"

    results["3.1_coordinator_parse_task"] = "PASS"


def test_async_plugin_registry():
    """Test Async ROS2 BT plugin registry."""
    from multi_arm_task_planner.bt_plugins.async_ros2_plugins import ASYNC_PLUGIN_REGISTRY

    expected = ["MoveTo", "Grasp", "Place", "Lift", "Retract", "CheckSafety", "QueryWorld", "Recover"]
    for name in expected:
        assert name in ASYNC_PLUGIN_REGISTRY, f"Missing plugin: {name}"

    results["4.1_async_plugin_registry"] = "PASS"


def test_async_plugin_classes():
    """Test Async ROS2 BT plugin classes are correct types."""
    from multi_arm_task_planner.bt_plugins.async_ros2_plugins import (
        AsyncMoveToNode,
        AsyncGraspNode,
        AsyncPlaceNode,
        AsyncLiftNode,
        AsyncRetractNode,
        AsyncCheckSafetyNode,
        AsyncQueryWorldNode,
        AsyncRecoverNode,
    )
    from multi_arm_task_planner.behavior_tree import AsyncActionNode, ConditionNode

    assert issubclass(AsyncMoveToNode, AsyncActionNode), "MoveTo should be AsyncActionNode"
    assert issubclass(AsyncCheckSafetyNode, ConditionNode), "CheckSafety should be ConditionNode"
    assert issubclass(AsyncQueryWorldNode, AsyncActionNode), "QueryWorld should be AsyncActionNode"

    results["4.2_async_plugin_classes"] = "PASS"


def test_async_plugins_tick():
    """Test Async ROS2 BT plugins can tick (with blackboard only, no ROS2 calls)."""
    from multi_arm_task_planner.behavior_tree import Blackboard, NodeStatus
    from multi_arm_task_planner.bt_plugins.async_ros2_plugins import (
        AsyncGraspNode,
        AsyncPlaceNode,
        AsyncLiftNode,
        AsyncRecoverNode,
        AsyncQueryWorldNode,
    )

    bb = Blackboard()
    bb.set("arm_name", "arm1")
    bb.set("object_id", "red_cube")
    bb.set("target_zone", "zone_a")

    grasp = AsyncGraspNode(name="test_grasp", blackboard=bb)
    status = grasp.tick()
    assert status == NodeStatus.RUNNING, f"Grasp 1st tick should be RUNNING, got {status}"
    status = grasp.tick()
    assert status == NodeStatus.SUCCESS, f"Grasp 2nd tick should succeed, got {status}"

    place = AsyncPlaceNode(name="test_place", blackboard=bb)
    place.tick()
    status = place.tick()
    assert status == NodeStatus.SUCCESS, f"Place should succeed, got {status}"

    lift = AsyncLiftNode(name="test_lift", blackboard=bb)
    lift.tick()
    status = lift.tick()
    assert status == NodeStatus.SUCCESS, f"Lift should succeed, got {status}"

    recover = AsyncRecoverNode(name="test_recover", blackboard=bb)
    recover.tick()
    status = recover.tick()
    assert status == NodeStatus.SUCCESS, f"Recover should succeed, got {status}"

    query = AsyncQueryWorldNode(name="test_query", blackboard=bb)
    query.tick()
    status = query.tick()
    assert status == NodeStatus.SUCCESS, f"QueryWorld should succeed, got {status}"

    results["4.3_async_plugins_tick"] = "PASS"


def test_task_xml_map():
    """Test TASK_XML_MAP in task_planner_node."""
    from multi_arm_task_planner.task_planner_node import TASK_XML_MAP

    assert "pick_place" in TASK_XML_MAP, "pick_place not in TASK_XML_MAP"
    assert "pick_place_ros2" in TASK_XML_MAP, "pick_place_ros2 not in TASK_XML_MAP"
    assert TASK_XML_MAP["pick_place"] == "pick_place.xml"
    assert TASK_XML_MAP["pick_place_ros2"] == "pick_place_ros2.xml"

    results["5.1_task_xml_map"] = "PASS"


def test_pick_place_ros2_xml_exists():
    """Test pick_place_ros2.xml file exists and is valid."""
    xml_path = os.path.join(
        os.path.dirname(__file__),
        "..", "..", "..", "src", "multi_arm_task_planner",
        "multi_arm_task_planner", "bt_xml", "pick_place_ros2.xml",
    )
    xml_path = os.path.abspath(xml_path)
    assert os.path.exists(xml_path), f"XML not found: {xml_path}"

    import xml.etree.ElementTree as ET
    tree = ET.parse(xml_path)
    root = tree.getroot()
    bt_elements = root.findall("BehaviorTree")
    assert len(bt_elements) >= 1, "No BehaviorTree elements found"

    results["5.2_pick_place_ros2_xml"] = "PASS"


def test_pick_place_ros2_xml_loadable():
    """Test pick_place_ros2.xml can be loaded by BehaviorTree."""
    from multi_arm_task_planner.behavior_tree import BehaviorTree, Blackboard
    from multi_arm_task_planner.bt_plugins.async_ros2_plugins import ASYNC_PLUGIN_REGISTRY

    xml_path = os.path.join(
        os.path.dirname(__file__),
        "..", "..", "..", "src", "multi_arm_task_planner",
        "multi_arm_task_planner", "bt_xml", "pick_place_ros2.xml",
    )
    xml_path = os.path.abspath(xml_path)

    bt = BehaviorTree(blackboard=Blackboard())
    bt.register_plugins(ASYNC_PLUGIN_REGISTRY)
    bt.load_xml(xml_path)

    assert bt.root is not None, "BT root is None after loading"

    results["5.3_pick_place_ros2_xml_loadable"] = "PASS"


def test_coordinator_has_execute_task():
    """Test CoordinatorNode has ExecuteTask-related methods."""
    from multi_arm_core.coordinator_node import CoordinatorNode

    assert hasattr(CoordinatorNode, "_on_execute_task"), "Missing _on_execute_task"
    assert hasattr(CoordinatorNode, "_parse_task"), "Missing _parse_task"
    assert hasattr(CoordinatorNode, "_parse_task_goal"), "Missing _parse_task_goal"
    assert hasattr(CoordinatorNode, "_send_trajectory_sync"), "Missing _send_trajectory_sync"
    assert hasattr(CoordinatorNode, "_init_action_server"), "Missing _init_action_server"

    results["6.1_coordinator_execute_task"] = "PASS"


def test_task_goal_msg():
    """Test TaskGoal message can be constructed."""
    from multi_arm_interfaces.msg import TaskGoal, TaskConstraint

    goal = TaskGoal()
    goal.action_type = "move"
    goal.arm_name = "arm1"
    goal.zone_name = "zone_a"
    goal.position_name = "ready"
    goal.object_id = "red_cube"
    goal.approach = "top"
    goal.constraints = TaskConstraint()
    goal.constraints.priority = 1
    goal.constraints.allow_recovery = True
    goal.constraints.max_retries = 3
    assert goal.arm_name == "arm1"
    assert goal.constraints.priority == 1

    results["8.1_task_goal_msg"] = "PASS"


def test_motion_request_msg():
    """Test MotionRequest message can be constructed."""
    from multi_arm_interfaces.msg import MotionRequest

    req = MotionRequest()
    req.arm_name = "arm1"
    req.target_position = "ready"
    req.use_named_target = True
    req.speed_scale = 0.5
    req.collision_check = True
    assert req.arm_name == "arm1"
    assert req.use_named_target is True

    results["8.2_motion_request_msg"] = "PASS"


def test_execute_task_with_goal():
    """Test ExecuteTask.Goal has goal field for TaskGoal."""
    from multi_arm_interfaces.action import ExecuteTask
    from multi_arm_interfaces.msg import TaskGoal

    goal = ExecuteTask.Goal()
    goal.task_id = "test_m53"
    goal.task_type = "move"
    goal.description = "arm1:zone_a:ready"
    task_goal = TaskGoal()
    task_goal.arm_name = "arm1"
    task_goal.zone_name = "zone_a"
    task_goal.position_name = "ready"
    goal.goal = task_goal
    assert goal.goal.arm_name == "arm1"

    results["8.3_execute_task_with_goal"] = "PASS"


def test_coordinator_parse_task_goal():
    """Test Coordinator._parse_task_goal with structured TaskGoal."""
    from multi_arm_core.coordinator_node import CoordinatorNode
    from multi_arm_interfaces.msg import TaskGoal

    task_goal = TaskGoal()
    task_goal.arm_name = "arm2"
    task_goal.zone_name = "zone_b"
    task_goal.position_name = "home"
    arm, zone, pos = CoordinatorNode._parse_task_goal(None, task_goal)
    assert arm == "arm2", f"Expected arm2, got {arm}"
    assert zone == "zone_b", f"Expected zone_b, got {zone}"
    assert pos == "home", f"Expected home, got {pos}"

    results["8.4_coordinator_parse_task_goal"] = "PASS"


def test_no_circular_import():
    """Test no circular import between coordinator_node and moveit_interface."""
    import importlib
    import multi_arm_core.coordinator_node
    import multi_arm_core.moveit_interface
    import multi_arm_core.robot_constants

    importlib.reload(multi_arm_core.robot_constants)
    importlib.reload(multi_arm_core.moveit_interface)
    importlib.reload(multi_arm_core.coordinator_node)

    results["7.1_no_circular_import"] = "PASS"


def main():
    tests = [
        test_robot_constants,
        test_moveit_interface_import,
        test_coordinator_parse_task,
        test_async_plugin_registry,
        test_async_plugin_classes,
        test_async_plugins_tick,
        test_task_xml_map,
        test_pick_place_ros2_xml_exists,
        test_pick_place_ros2_xml_loadable,
        test_coordinator_has_execute_task,
        test_task_goal_msg,
        test_motion_request_msg,
        test_execute_task_with_goal,
        test_coordinator_parse_task_goal,
        test_no_circular_import,
    ]

    for test_fn in tests:
        try:
            test_fn()
        except Exception as e:
            name = test_fn.__name__
            results[name] = f"FAIL: {e}"
            print(f"  FAIL {name}: {e}")

    print("\n=== M4.6 Code Validation Results ===")
    all_pass = True
    for k, v in sorted(results.items()):
        status = "PASS" if v == "PASS" else v
        print(f"  {k}: {status}")
        if v != "PASS":
            all_pass = False

    print(f"\nOverall: {'ALL PASS' if all_pass else 'SOME FAILED'}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())