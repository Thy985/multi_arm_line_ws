"""Unit tests for Robot Runtime API Node."""

import time

import pytest
import rclpy
from rclpy.action import ActionServer
from rclpy.action.server import ServerGoalHandle
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor

from multi_arm_interfaces.action import ExecuteSkill, SubmitTaskGoals
from multi_arm_interfaces.msg import TaskConstraint, TaskGoal
from multi_arm_interfaces.srv import (
    GetCapability,
    ListSkills,
    ManageSkill,
    QueryExperience,
    QueryWorld,
)

from multi_arm_runtime_api.runtime_api_node import (
    ACTION_TYPE_TO_SKILL,
    RuntimeApiNode,
)


class TestActionTypeMapping:
    """Tests for action_type to skill_name mapping."""

    def test_pick_place_mapping(self) -> None:
        """Test pick_place maps to pick_object."""
        assert ACTION_TYPE_TO_SKILL["pick_place"] == "pick_object"

    def test_pick_mapping(self) -> None:
        """Test pick maps to pick_object."""
        assert ACTION_TYPE_TO_SKILL["pick"] == "pick_object"

    def test_place_mapping(self) -> None:
        """Test place maps to place_object."""
        assert ACTION_TYPE_TO_SKILL["place"] == "place_object"

    def test_move_mapping(self) -> None:
        """Test move maps to move_object."""
        assert ACTION_TYPE_TO_SKILL["move"] == "move_object"

    def test_grasp_mapping(self) -> None:
        """Test grasp maps to pick_object."""
        assert ACTION_TYPE_TO_SKILL["grasp"] == "pick_object"

    def test_lift_mapping(self) -> None:
        """Test lift maps to move_object."""
        assert ACTION_TYPE_TO_SKILL["lift"] == "move_object"

    def test_retract_mapping(self) -> None:
        """Test retract maps to move_object."""
        assert ACTION_TYPE_TO_SKILL["retract"] == "move_object"

    def test_inspect_mapping(self) -> None:
        """Test inspect maps to move_object."""
        assert ACTION_TYPE_TO_SKILL["inspect"] == "move_object"

    def test_all_actions_mapped(self) -> None:
        """Test that all expected action types are mapped."""
        expected = {"pick_place", "pick", "place", "move", "grasp", "lift", "retract", "inspect"}
        assert expected.issubset(ACTION_TYPE_TO_SKILL.keys())


class TestTaskGoalReference:
    """Tests verifying TaskGoal is properly referenced (M5.7 Freeze)."""

    def test_submit_task_goals_uses_task_goal(self) -> None:
        """Test that SubmitTaskGoals action references TaskGoal."""
        goal_fields = SubmitTaskGoals.Goal._fields_and_field_types
        assert "goals" in goal_fields
        assert "TaskGoal" in goal_fields["goals"]

    def test_execute_skill_uses_task_goal(self) -> None:
        """Test that ExecuteSkill action references TaskGoal."""
        goal_fields = ExecuteSkill.Goal._fields_and_field_types
        assert "task_goal" in goal_fields
        assert "TaskGoal" in goal_fields["task_goal"]

    def test_task_goal_has_required_fields(self) -> None:
        """Test TaskGoal has all M5.7 frozen fields."""
        fields = TaskGoal._fields_and_field_types
        assert "action_type" in fields
        assert "arm_name" in fields
        assert "zone_name" in fields
        assert "position_name" in fields
        assert "object_id" in fields
        assert "approach" in fields
        assert "constraints" in fields

    def test_task_constraint_has_required_fields(self) -> None:
        """Test TaskConstraint has all M5.7 frozen fields."""
        fields = TaskConstraint._fields_and_field_types
        assert "max_time" in fields
        assert "safety_level" in fields
        assert "priority" in fields
        assert "allow_recovery" in fields
        assert "max_retries" in fields


class TestRuntimeApiNodeInterfaces:
    """Tests for RuntimeApiNode ROS2 interface availability."""

    @classmethod
    def setup_class(cls) -> None:
        """Setup ROS2 context for test class."""
        rclpy.init()
        cls.executor = MultiThreadedExecutor(num_threads=4)
        cls.node = RuntimeApiNode()
        cls.executor.add_node(cls.node)
        import threading
        cls._spin_thread = threading.Thread(
            target=cls.executor.spin, daemon=True
        )
        cls._spin_thread.start()
        time.sleep(1.0)

    @classmethod
    def teardown_class(cls) -> None:
        """Cleanup ROS2 context."""
        cls.executor.shutdown()
        cls.node.destroy_node()
        rclpy.shutdown()

    def test_node_created(self) -> None:
        """Test that node is created successfully."""
        assert self.node is not None

    def test_submit_task_goals_action_server(self) -> None:
        """Test SubmitTaskGoals action server exists."""
        client = rclpy.action.ActionClient(
            self.node, SubmitTaskGoals, "/runtime/submit_task_goals"
        )
        assert client.wait_for_server(timeout_sec=2.0)
        client.destroy()

    def test_proxy_query_world_service(self) -> None:
        """Test /runtime/query_world proxy service exists."""
        client = self.node.create_client(QueryWorld, "/runtime/query_world")
        assert client.wait_for_service(timeout_sec=2.0)
        client.destroy()

    def test_proxy_get_capability_service(self) -> None:
        """Test /runtime/get_capability proxy service exists."""
        client = self.node.create_client(GetCapability, "/runtime/get_capability")
        assert client.wait_for_service(timeout_sec=2.0)
        client.destroy()

    def test_proxy_list_skills_service(self) -> None:
        """Test /runtime/list_skills proxy service exists."""
        client = self.node.create_client(ListSkills, "/runtime/list_skills")
        assert client.wait_for_service(timeout_sec=2.0)
        client.destroy()

    def test_proxy_manage_skill_service(self) -> None:
        """Test /runtime/manage_skill proxy service exists."""
        client = self.node.create_client(ManageSkill, "/runtime/manage_skill")
        assert client.wait_for_service(timeout_sec=2.0)
        client.destroy()

    def test_proxy_query_experience_service(self) -> None:
        """Test /runtime/query_experience proxy service exists."""
        client = self.node.create_client(QueryExperience, "/runtime/query_experience")
        assert client.wait_for_service(timeout_sec=2.0)
        client.destroy()

    def test_all_seven_apis_available(self) -> None:
        """Test all 7 Robot Runtime APIs are available.

        1. SubmitTaskGoals (action)
        2. QueryWorld (proxy)
        3. GetCapability (proxy)
        4. ListSkills (proxy)
        5. ManageSkill (proxy)
        6. QueryExperience (proxy)
        7. ExecuteSkill (action client to /skill/execute)
        """
        action_client = rclpy.action.ActionClient(
            self.node, SubmitTaskGoals, "/runtime/submit_task_goals"
        )
        assert action_client.wait_for_server(timeout_sec=2.0)
        action_client.destroy()

        assert self.node._execute_skill_client is not None
        assert self.node._query_world_client is not None
        assert self.node._get_capability_client is not None
        assert self.node._list_skills_client is not None
        assert self.node._manage_skill_client is not None
        assert self.node._query_experience_client is not None


class TestProxyBackendUnavailable:
    """Tests for proxy behavior when backend is unavailable."""

    @classmethod
    def setup_class(cls) -> None:
        """Setup ROS2 context."""
        rclpy.init()
        cls.executor = MultiThreadedExecutor(num_threads=4)
        cls.node = RuntimeApiNode()
        cls.executor.add_node(cls.node)
        import threading
        cls._spin_thread = threading.Thread(
            target=cls.executor.spin, daemon=True
        )
        cls._spin_thread.start()
        time.sleep(1.0)

    @classmethod
    def teardown_class(cls) -> None:
        """Cleanup."""
        cls.executor.shutdown()
        cls.node.destroy_node()
        rclpy.shutdown()

    def test_proxy_query_world_returns_empty_when_no_backend(self) -> None:
        """Test proxy returns empty response when backend unavailable."""
        client = self.node.create_client(QueryWorld, "/runtime/query_world")
        client.wait_for_service(timeout_sec=2.0)

        req = QueryWorld.Request()
        req.query_type = "all"

        future = client.call_async(req)
        rclpy.spin_until_future_complete(self.node, future, timeout_sec=5.0)

        assert future.done()
        response = future.result()
        assert response is not None
        assert len(response.object_states) == 0
        client.destroy()

    def test_proxy_list_skills_returns_empty_when_no_backend(self) -> None:
        """Test proxy returns empty list when backend unavailable."""
        client = self.node.create_client(ListSkills, "/runtime/list_skills")
        client.wait_for_service(timeout_sec=2.0)

        req = ListSkills.Request()

        future = client.call_async(req)
        rclpy.spin_until_future_complete(self.node, future, timeout_sec=5.0)

        assert future.done()
        response = future.result()
        assert response is not None
        assert len(response.skills) == 0
        client.destroy()

    def test_proxy_get_capability_returns_empty_when_no_backend(self) -> None:
        """Test proxy returns empty capabilities when backend unavailable."""
        client = self.node.create_client(GetCapability, "/runtime/get_capability")
        client.wait_for_service(timeout_sec=2.0)

        req = GetCapability.Request()
        req.capability_name = "all"

        future = client.call_async(req)
        rclpy.spin_until_future_complete(self.node, future, timeout_sec=5.0)

        assert future.done()
        response = future.result()
        assert response is not None
        assert len(response.capabilities) == 0
        client.destroy()

    def test_proxy_query_experience_returns_empty_when_no_backend(self) -> None:
        """Test proxy returns empty when backend unavailable."""
        client = self.node.create_client(QueryExperience, "/runtime/query_experience")
        client.wait_for_service(timeout_sec=2.0)

        req = QueryExperience.Request()
        req.data_type = "episode"

        future = client.call_async(req)
        rclpy.spin_until_future_complete(self.node, future, timeout_sec=5.0)

        assert future.done()
        response = future.result()
        assert response is not None
        assert response.count == 0
        client.destroy()


class TestSubmitTaskGoalsChain:
    """Tests for SubmitTaskGoals → ExecuteSkill chain."""

    @staticmethod
    def _wait_future(future: any, timeout_sec: float) -> bool:
        """Poll future instead of spinning (executor already spinning)."""
        start = time.time()
        while not future.done() and (time.time() - start) < timeout_sec:
            time.sleep(0.01)
        return future.done()

    @classmethod
    def setup_class(cls) -> None:
        """Setup with mock ExecuteSkill action server."""
        rclpy.init()
        cls.executor = MultiThreadedExecutor(num_threads=4)

        cls.node = RuntimeApiNode()
        cls.executor.add_node(cls.node)

        cls.mock_skill_node = rclpy.create_node("mock_skill_node")
        cls._mock_cb = ReentrantCallbackGroup()

        def mock_execute_handler(
            goal_handle: ServerGoalHandle,
        ) -> ExecuteSkill.Result:
            result = ExecuteSkill.Result()
            result.success = True
            result.message = f"Mock executed: {goal_handle.request.skill_name}"
            result.postcondition_results = [True]
            goal_handle.succeed()
            return result

        cls._mock_action_server = ActionServer(
            cls.mock_skill_node,
            ExecuteSkill,
            "/skill/execute",
            mock_execute_handler,
            callback_group=cls._mock_cb,
        )
        cls.executor.add_node(cls.mock_skill_node)

        import threading
        cls._spin_thread = threading.Thread(
            target=cls.executor.spin, daemon=True
        )
        cls._spin_thread.start()
        time.sleep(1.5)

    @classmethod
    def teardown_class(cls) -> None:
        """Cleanup."""
        cls.executor.shutdown()
        cls.node.destroy_node()
        cls.mock_skill_node.destroy_node()
        rclpy.shutdown()

    def test_empty_goals_succeeds(self) -> None:
        """Test SubmitTaskGoals with empty goal list succeeds."""
        client = rclpy.action.ActionClient(
            self.node, SubmitTaskGoals, "/runtime/submit_task_goals"
        )
        assert client.wait_for_server(timeout_sec=3.0)

        goal = SubmitTaskGoals.Goal()
        goal.goals = []

        future = client.send_goal_async(goal)
        assert self._wait_future(future, 5.0)
        goal_handle = future.result()
        assert goal_handle.accepted

        result_future = goal_handle.get_result_async()
        assert self._wait_future(result_future, 5.0)
        result = result_future.result().result

        assert result.success is True
        assert result.total_count == 0
        assert result.success_count == 0
        client.destroy()

    def test_single_pick_place_goal(self) -> None:
        """Test SubmitTaskGoals with single pick_place goal routes to ExecuteSkill."""
        client = rclpy.action.ActionClient(
            self.node, SubmitTaskGoals, "/runtime/submit_task_goals"
        )
        assert client.wait_for_server(timeout_sec=3.0)

        task_goal = TaskGoal()
        task_goal.action_type = "pick_place"
        task_goal.arm_name = "arm1"
        task_goal.zone_name = "zone_a"
        task_goal.position_name = "ready"
        task_goal.object_id = "red_cube"

        goal = SubmitTaskGoals.Goal()
        goal.goals = [task_goal]

        future = client.send_goal_async(goal)
        assert self._wait_future(future, 10.0)
        goal_handle = future.result()
        assert goal_handle.accepted

        result_future = goal_handle.get_result_async()
        assert self._wait_future(result_future, 10.0)
        result = result_future.result().result

        assert result.total_count == 1
        assert result.success_count == 1
        assert result.success is True
        assert "SUCCESS" in result.results[0]
        assert "pick_object" in result.results[0]
        client.destroy()

    def test_multiple_goals(self) -> None:
        """Test SubmitTaskGoals with multiple goals."""
        client = rclpy.action.ActionClient(
            self.node, SubmitTaskGoals, "/runtime/submit_task_goals"
        )
        assert client.wait_for_server(timeout_sec=3.0)

        goals = []
        for i in range(3):
            tg = TaskGoal()
            tg.action_type = "move"
            tg.arm_name = f"arm{(i % 2) + 1}"
            tg.position_name = "ready"
            goals.append(tg)

        goal = SubmitTaskGoals.Goal()
        goal.goals = goals

        future = client.send_goal_async(goal)
        assert self._wait_future(future, 15.0)
        goal_handle = future.result()
        assert goal_handle.accepted

        result_future = goal_handle.get_result_async()
        assert self._wait_future(result_future, 15.0)
        result = result_future.result().result

        assert result.total_count == 3
        assert result.success_count == 3
        assert result.success is True
        assert len(result.results) == 3
        client.destroy()

    def test_mixed_action_types(self) -> None:
        """Test SubmitTaskGoals with different action types."""
        client = rclpy.action.ActionClient(
            self.node, SubmitTaskGoals, "/runtime/submit_task_goals"
        )
        assert client.wait_for_server(timeout_sec=3.0)

        goals = []
        for action_type in ["pick_place", "move", "place"]:
            tg = TaskGoal()
            tg.action_type = action_type
            tg.arm_name = "arm1"
            goals.append(tg)

        goal = SubmitTaskGoals.Goal()
        goal.goals = goals

        future = client.send_goal_async(goal)
        assert self._wait_future(future, 15.0)
        goal_handle = future.result()
        assert goal_handle.accepted

        result_future = goal_handle.get_result_async()
        assert self._wait_future(result_future, 15.0)
        result = result_future.result().result

        assert result.total_count == 3
        assert result.success_count == 3
        assert "pick_object" in result.results[0]
        assert "move_object" in result.results[1]
        assert "place_object" in result.results[2]
        client.destroy()

    def test_task_goal_with_constraints(self) -> None:
        """Test TaskGoal with constraints is passed through."""
        client = rclpy.action.ActionClient(
            self.node, SubmitTaskGoals, "/runtime/submit_task_goals"
        )
        assert client.wait_for_server(timeout_sec=3.0)

        task_goal = TaskGoal()
        task_goal.action_type = "pick_place"
        task_goal.arm_name = "arm1"
        task_goal.constraints = TaskConstraint()
        task_goal.constraints.max_time = 10.0
        task_goal.constraints.priority = 2
        task_goal.constraints.allow_recovery = True
        task_goal.constraints.max_retries = 3

        goal = SubmitTaskGoals.Goal()
        goal.goals = [task_goal]

        future = client.send_goal_async(goal)
        assert self._wait_future(future, 10.0)
        goal_handle = future.result()
        assert goal_handle.accepted

        result_future = goal_handle.get_result_async()
        assert self._wait_future(result_future, 10.0)
        result = result_future.result().result

        assert result.success is True
        assert result.success_count == 1
        client.destroy()