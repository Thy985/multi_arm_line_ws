"""Smoke tests for M3 packages."""

import pytest
import os


def test_import_state_database() -> None:
    from multi_arm_world_model.state_database import (
        StateDatabase, TrackedObject, CachedRobotState, TaskContext
    )
    db = StateDatabase()
    assert db is not None


def test_import_object_tracker() -> None:
    from multi_arm_world_model.object_tracker import ObjectTracker
    tracker = ObjectTracker()
    assert tracker is not None


def test_import_world_model_node() -> None:
    from multi_arm_world_model.world_model_node import WorldModelNode
    assert WorldModelNode is not None


def test_import_behavior_tree() -> None:
    from multi_arm_task_planner.behavior_tree import (
        BehaviorTree, Blackboard, Sequence, Selector, NodeStatus
    )
    bt = BehaviorTree()
    assert bt is not None


def test_import_plugins() -> None:
    from multi_arm_task_planner.bt_plugins.pick_place_plugins import PLUGIN_REGISTRY
    assert len(PLUGIN_REGISTRY) >= 6


def test_import_task_planner_node() -> None:
    from multi_arm_task_planner.task_planner_node import TaskPlannerNode
    assert TaskPlannerNode is not None


def test_bt_xml_files_exist() -> None:
    xml_dir = os.path.join(
        os.path.dirname(__file__), "..", "..", "multi_arm_task_planner",
        "multi_arm_task_planner", "bt_xml"
    )
    xml_dir = os.path.abspath(xml_dir)
    assert os.path.exists(os.path.join(xml_dir, "pick_place.xml"))
    assert os.path.exists(os.path.join(xml_dir, "assembly.xml"))
    assert os.path.exists(os.path.join(xml_dir, "inspection.xml"))


def test_world_model_config_exists() -> None:
    config_path = os.path.join(
        os.path.dirname(__file__), "..", "config", "world_model_config.yaml"
    )
    config_path = os.path.abspath(config_path)
    assert os.path.exists(config_path)


def test_gripper_config_exists() -> None:
    config_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "..", "src", "ur_simulation_gz",
        "ur_simulation_gz", "config", "gripper_controllers.yaml"
    )
    config_path = os.path.abspath(config_path)
    assert os.path.exists(config_path), f"Gripper config not found at {config_path}"


def test_world_model_ownership_boundary() -> None:
    """Verify WorldModel does NOT own real-time control state."""
    from multi_arm_world_model.state_database import CachedRobotState
    state = CachedRobotState(arm_name="arm1")
    assert state.last_updated > 0
    assert not state.is_stale(max_age=1.0)