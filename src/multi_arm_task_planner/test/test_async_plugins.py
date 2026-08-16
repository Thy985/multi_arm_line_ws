"""Unit tests for async ROS2 BT plugins."""

import pytest
from unittest.mock import MagicMock, PropertyMock
from concurrent.futures import Future

from multi_arm_task_planner.behavior_tree import (
    AsyncActionNode,
    Blackboard,
    NodeStatus,
)
from multi_arm_task_planner.bt_plugins.async_ros2_plugins import (
    ASYNC_PLUGIN_REGISTRY,
    AsyncMoveToNode,
    AsyncRetractNode,
    AsyncCheckSafetyNode,
    AsyncQueryWorldNode,
    AsyncGraspNode,
    AsyncPlaceNode,
    AsyncLiftNode,
    AsyncRecoverNode,
)


class TestAsyncActionNode:
    """Tests for AsyncActionNode base class."""

    def test_first_tick_returns_running(self):
        bb = Blackboard()
        node = AsyncActionNode(name="test", blackboard=bb)
        node._send_request = lambda: "future"
        status = node.tick()
        assert status == NodeStatus.RUNNING

    def test_returns_running_while_pending(self):
        bb = Blackboard()
        node = AsyncActionNode(name="test", blackboard=bb)
        future = Future()
        node._send_request = lambda: future
        node.tick()
        status = node.tick()
        assert status == NodeStatus.RUNNING

    def test_returns_success_when_future_done(self):
        bb = Blackboard()
        node = AsyncActionNode(name="test", blackboard=bb)
        node._check_result = lambda f: NodeStatus.SUCCESS
        future = Future()
        future.set_result("done")
        node._send_request = lambda: future
        node.tick()
        status = node.tick()
        assert status == NodeStatus.SUCCESS

    def test_returns_failure_when_send_returns_none(self):
        bb = Blackboard()
        node = AsyncActionNode(name="test", blackboard=bb)
        node._send_request = lambda: None
        status = node.tick()
        assert status == NodeStatus.FAILURE

    def test_reset_clears_state(self):
        bb = Blackboard()
        node = AsyncActionNode(name="test", blackboard=bb)
        node._send_request = lambda: "future"
        node.tick()
        assert node._request_sent is True
        node.reset()
        assert node._request_sent is False
        assert node._pending_future is None

    def test_set_ros2_node(self):
        bb = Blackboard()
        node = AsyncActionNode(name="test", blackboard=bb)
        mock_node = MagicMock()
        node.set_ros2_node(mock_node)
        assert node._ros2_node is mock_node


class TestAsyncGraspNode:
    """Tests for AsyncGraspNode (simplified)."""

    def test_immediate_success(self):
        bb = Blackboard()
        bb.set("arm_name", "left_arm")
        node = AsyncGraspNode(name="grasp", blackboard=bb)
        status1 = node.tick()
        assert status1 == NodeStatus.RUNNING
        status2 = node.tick()
        assert status2 == NodeStatus.SUCCESS

    def test_failure_no_arm(self):
        bb = Blackboard()
        node = AsyncGraspNode(name="grasp", blackboard=bb)
        status = node.tick()
        assert status == NodeStatus.FAILURE


class TestAsyncPlaceNode:
    """Tests for AsyncPlaceNode (simplified)."""

    def test_immediate_success(self):
        bb = Blackboard()
        bb.set("arm_name", "left_arm")
        bb.set("target_zone", "zone_a")
        node = AsyncPlaceNode(name="place", blackboard=bb)
        node.tick()
        status = node.tick()
        assert status == NodeStatus.SUCCESS


class TestAsyncLiftNode:
    """Tests for AsyncLiftNode (simplified)."""

    def test_immediate_success(self):
        bb = Blackboard()
        bb.set("arm_name", "left_arm")
        node = AsyncLiftNode(name="lift", blackboard=bb)
        node.tick()
        status = node.tick()
        assert status == NodeStatus.SUCCESS


class TestAsyncRecoverNode:
    """Tests for AsyncRecoverNode (simplified)."""

    def test_immediate_success(self):
        bb = Blackboard()
        bb.set("arm_name", "left_arm")
        bb.set("failure_type", "planning")
        node = AsyncRecoverNode(name="recover", blackboard=bb)
        node.tick()
        status = node.tick()
        assert status == NodeStatus.SUCCESS


class TestAsyncCheckSafetyNode:
    """Tests for AsyncCheckSafetyNode."""

    def test_no_ros2_node_defaults_success(self):
        bb = Blackboard()
        bb.set("arm_name", "left_arm")
        node = AsyncCheckSafetyNode(name="safety", blackboard=bb)
        status = node.tick()
        assert status == NodeStatus.SUCCESS

    def test_reset_clears_state(self):
        bb = Blackboard()
        node = AsyncCheckSafetyNode(name="safety", blackboard=bb)
        node._request_sent = True
        node.reset()
        assert node._request_sent is False


class TestAsyncPluginRegistry:
    """Tests for the async plugin registry."""

    def test_all_eight_plugins_registered(self):
        expected = {"MoveTo", "Grasp", "Place", "Lift", "Retract",
                    "CheckSafety", "QueryWorld", "Recover"}
        assert set(ASYNC_PLUGIN_REGISTRY.keys()) == expected

    def test_move_to_is_async(self):
        assert ASYNC_PLUGIN_REGISTRY["MoveTo"] is AsyncMoveToNode

    def test_retract_is_async(self):
        assert ASYNC_PLUGIN_REGISTRY["Retract"] is AsyncRetractNode

    def test_check_safety_is_async(self):
        assert ASYNC_PLUGIN_REGISTRY["CheckSafety"] is AsyncCheckSafetyNode

    def test_query_world_is_async(self):
        assert ASYNC_PLUGIN_REGISTRY["QueryWorld"] is AsyncQueryWorldNode

    def test_grasp_is_async(self):
        assert ASYNC_PLUGIN_REGISTRY["Grasp"] is AsyncGraspNode

    def test_place_is_async(self):
        assert ASYNC_PLUGIN_REGISTRY["Place"] is AsyncPlaceNode

    def test_lift_is_async(self):
        assert ASYNC_PLUGIN_REGISTRY["Lift"] is AsyncLiftNode

    def test_recover_is_async(self):
        assert ASYNC_PLUGIN_REGISTRY["Recover"] is AsyncRecoverNode


class TestAsyncMoveToNodeWithMock:
    """Tests for AsyncMoveToNode with mock ROS2 node."""

    def test_no_ros2_node_returns_failure(self):
        bb = Blackboard()
        bb.set("arm_name", "left_arm")
        node = AsyncMoveToNode(name="move", blackboard=bb)
        status = node.tick()
        assert status == NodeStatus.FAILURE

    def test_no_arm_returns_failure(self):
        bb = Blackboard()
        node = AsyncMoveToNode(name="move", blackboard=bb)
        status = node.tick()
        assert status == NodeStatus.FAILURE

    def test_reset_clears_result_future(self):
        bb = Blackboard()
        node = AsyncMoveToNode(name="move", blackboard=bb)
        node._result_future = "something"
        node.reset()
        assert node._result_future is None


class TestAsyncRetractNodeWithMock:
    """Tests for AsyncRetractNode with mock ROS2 node."""

    def test_no_ros2_node_returns_failure(self):
        bb = Blackboard()
        bb.set("arm_name", "left_arm")
        node = AsyncRetractNode(name="retract", blackboard=bb)
        status = node.tick()
        assert status == NodeStatus.FAILURE

    def test_reset_clears_result_future(self):
        bb = Blackboard()
        node = AsyncRetractNode(name="retract", blackboard=bb)
        node._result_future = "something"
        node.reset()
        assert node._result_future is None