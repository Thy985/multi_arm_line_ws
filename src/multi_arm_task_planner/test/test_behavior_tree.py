"""Tests for BehaviorTree framework."""

import os
import pytest
import tempfile

from multi_arm_task_planner.behavior_tree import (
    BehaviorTree,
    Blackboard,
    BTNode,
    ConditionNode,
    Inverter,
    NodeStatus,
    RetryNode,
    Selector,
    Sequence,
    ActionNode,
)
from multi_arm_task_planner.bt_plugins.pick_place_plugins import PLUGIN_REGISTRY


class TestBlackboard:
    """Tests for Blackboard."""

    def test_set_and_get(self) -> None:
        bb = Blackboard()
        bb.set("key", "value")
        assert bb.get("key") == "value"

    def test_default_value(self) -> None:
        bb = Blackboard()
        assert bb.get("missing", "default") == "default"

    def test_has(self) -> None:
        bb = Blackboard()
        bb.set("key", 1)
        assert bb.has("key")
        assert not bb.has("missing")

    def test_remove(self) -> None:
        bb = Blackboard()
        bb.set("key", 1)
        bb.remove("key")
        assert not bb.has("key")


class TestSequence:
    """Tests for Sequence node."""

    def test_all_succeed(self) -> None:
        seq = Sequence(name="test")
        seq.add_child(ActionNode(action_fn=lambda: NodeStatus.SUCCESS))
        seq.add_child(ActionNode(action_fn=lambda: NodeStatus.SUCCESS))
        assert seq.tick() == NodeStatus.SUCCESS

    def test_first_fails(self) -> None:
        seq = Sequence(name="test")
        seq.add_child(ActionNode(action_fn=lambda: NodeStatus.FAILURE))
        seq.add_child(ActionNode(action_fn=lambda: NodeStatus.SUCCESS))
        assert seq.tick() == NodeStatus.FAILURE

    def test_running(self) -> None:
        seq = Sequence(name="test")
        seq.add_child(ActionNode(action_fn=lambda: NodeStatus.RUNNING))
        assert seq.tick() == NodeStatus.RUNNING


class TestSelector:
    """Tests for Selector node."""

    def test_first_succeeds(self) -> None:
        sel = Selector(name="test")
        sel.add_child(ActionNode(action_fn=lambda: NodeStatus.SUCCESS))
        sel.add_child(ActionNode(action_fn=lambda: NodeStatus.FAILURE))
        assert sel.tick() == NodeStatus.SUCCESS

    def test_all_fail(self) -> None:
        sel = Selector(name="test")
        sel.add_child(ActionNode(action_fn=lambda: NodeStatus.FAILURE))
        sel.add_child(ActionNode(action_fn=lambda: NodeStatus.FAILURE))
        assert sel.tick() == NodeStatus.FAILURE

    def test_fallback(self) -> None:
        sel = Selector(name="test")
        sel.add_child(ActionNode(action_fn=lambda: NodeStatus.FAILURE))
        sel.add_child(ActionNode(action_fn=lambda: NodeStatus.SUCCESS))
        assert sel.tick() == NodeStatus.SUCCESS


class TestInverter:
    """Tests for Inverter decorator."""

    def test_invert_success(self) -> None:
        inv = Inverter(name="test")
        inv.add_child(ActionNode(action_fn=lambda: NodeStatus.SUCCESS))
        assert inv.tick() == NodeStatus.FAILURE

    def test_invert_failure(self) -> None:
        inv = Inverter(name="test")
        inv.add_child(ActionNode(action_fn=lambda: NodeStatus.FAILURE))
        assert inv.tick() == NodeStatus.SUCCESS


class TestRetryNode:
    """Tests for RetryNode decorator."""

    def test_succeeds_on_retry(self) -> None:
        call_count = [0]
        def action():
            call_count[0] += 1
            return NodeStatus.SUCCESS if call_count[0] >= 2 else NodeStatus.FAILURE

        retry = RetryNode(name="test", max_retries=3)
        retry.add_child(ActionNode(action_fn=action))
        assert retry.tick() == NodeStatus.SUCCESS

    def test_exhausts_retries(self) -> None:
        retry = RetryNode(name="test", max_retries=2)
        retry.add_child(ActionNode(action_fn=lambda: NodeStatus.FAILURE))
        assert retry.tick() == NodeStatus.FAILURE


class TestBehaviorTreeXML:
    """Tests for XML loading."""

    def test_load_pick_place_xml(self) -> None:
        xml_dir = os.path.join(
            os.path.dirname(__file__), "..", "multi_arm_task_planner", "bt_xml"
        )
        xml_path = os.path.join(xml_dir, "pick_place.xml")
        xml_path = os.path.abspath(xml_path)

        if not os.path.exists(xml_path):
            pytest.skip(f"XML not found at {xml_path}")

        bt = BehaviorTree()
        bt.register_plugins(PLUGIN_REGISTRY)
        bt.load_xml(xml_path)
        assert bt.root is not None

    def test_xml_tree_ticks(self) -> None:
        xml_content = """<?xml version="1.0"?>
<root BTCPP_format="4">
  <BehaviorTree ID="Test">
    <Sequence name="test_seq">
      <MoveTo name="move"/>
      <Grasp name="grasp"/>
    </Sequence>
  </BehaviorTree>
</root>"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
            f.write(xml_content)
            xml_path = f.name

        try:
            bt = BehaviorTree()
            bt.register_plugins(PLUGIN_REGISTRY)
            bt.load_xml(xml_path)
            assert bt.root is not None

            bt.blackboard.set("arm_name", "left_arm")
            bt.blackboard.set("target_position", "zone_a")
            bt.blackboard.set("object_id", "box1")

            status = bt.tick()
            assert status == NodeStatus.SUCCESS
        finally:
            os.unlink(xml_path)


class TestPlugins:
    """Tests for BT plugins."""

    def test_move_to_plugin(self) -> None:
        from multi_arm_task_planner.bt_plugins.pick_place_plugins import MoveToNode
        bb = Blackboard()
        bb.set("arm_name", "left_arm")
        bb.set("target_position", "zone_a")
        node = MoveToNode(name="test", blackboard=bb)
        assert node.tick() == NodeStatus.SUCCESS

    def test_grasp_plugin(self) -> None:
        from multi_arm_task_planner.bt_plugins.pick_place_plugins import GraspNode
        bb = Blackboard()
        bb.set("arm_name", "left_arm")
        bb.set("object_id", "box1")
        node = GraspNode(name="test", blackboard=bb)
        assert node.tick() == NodeStatus.SUCCESS

    def test_place_plugin(self) -> None:
        from multi_arm_task_planner.bt_plugins.pick_place_plugins import PlaceNode
        bb = Blackboard()
        bb.set("arm_name", "left_arm")
        bb.set("target_zone", "zone_b")
        node = PlaceNode(name="test", blackboard=bb)
        assert node.tick() == NodeStatus.SUCCESS

    def test_check_safety_plugin(self) -> None:
        from multi_arm_task_planner.bt_plugins.pick_place_plugins import CheckSafetyNode
        bb = Blackboard()
        bb.set("arm_name", "left_arm")
        bb.set("safety_approved", True)
        node = CheckSafetyNode(name="test", blackboard=bb)
        assert node.tick() == NodeStatus.SUCCESS

    def test_check_safety_rejects(self) -> None:
        from multi_arm_task_planner.bt_plugins.pick_place_plugins import CheckSafetyNode
        bb = Blackboard()
        bb.set("arm_name", "left_arm")
        bb.set("safety_approved", False)
        node = CheckSafetyNode(name="test", blackboard=bb)
        assert node.tick() == NodeStatus.FAILURE

    def test_plugin_registry(self) -> None:
        assert "MoveTo" in PLUGIN_REGISTRY
        assert "Grasp" in PLUGIN_REGISTRY
        assert "Place" in PLUGIN_REGISTRY
        assert "CheckSafety" in PLUGIN_REGISTRY
        assert "Recover" in PLUGIN_REGISTRY