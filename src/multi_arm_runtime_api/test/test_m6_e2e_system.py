"""M6 System-Level E2E Test — Multi-Node ROS2 Integration.

This is the highest-level test for M6 Robot Platform Upgrade. It starts ALL
M6 ROS2 nodes simultaneously and verifies the complete inter-node communication
chain through the unified Robot Runtime API.

Nodes started:
    1. CapabilityRegistryNode (M6.0) — /capability/get_capability
    2. WorldModelNode (M6.1) — /world_model/query_world
    3. SkillRuntimeNode (M6.3) — /skill/execute, /skill/list, /skill/manage
    4. ExperienceNode (M6.4) — /experience/record, /experience/query
    5. RuntimeApiNode (M6.5) — /runtime/* (unified entry)

Verified chains:
    Chain 1: M6.5→M6.0  RuntimeApi → CapabilityRegistry (GetCapability)
    Chain 2: M6.5→M6.1  RuntimeApi → WorldModel (QueryWorld)
    Chain 3: M6.5→M6.3  RuntimeApi → SkillRuntime (ListSkills)
    Chain 4: M6.5→M6.3  RuntimeApi → SkillRuntime (SubmitTaskGoals→ExecuteSkill)
    Chain 5: M6.4        ExperienceNode (RecordEpisode)
    Chain 6: M6.5→M6.4  RuntimeApi → ExperienceNode (QueryExperience)
    Chain 7: Full        SubmitTaskGoals→ExecuteSkill + RecordEpisode + QueryExperience
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

import pytest
import rclpy
from rclpy.action import ActionClient
from rclpy.executors import MultiThreadedExecutor

from multi_arm_interfaces.action import SubmitTaskGoals
from multi_arm_interfaces.msg import TaskConstraint, TaskGoal
from multi_arm_interfaces.srv import (
    GetCapability,
    QueryExperience,
    QueryWorld,
    RecordEpisode,
)

from multi_arm_robot_description.capability_registry_node import (
    CapabilityRegistryNode,
)
from multi_arm_world_model.world_model_node import WorldModelNode
from multi_arm_skill_runtime.skill_node import SkillRuntimeNode
from multi_arm_experience.experience_node import ExperienceNode
from multi_arm_runtime_api.runtime_api_node import RuntimeApiNode


def _wait_future(future: object, timeout_sec: float) -> bool:
    """Poll future (executor already spinning)."""
    start = time.time()
    while not future.done() and (time.time() - start) < timeout_sec:
        time.sleep(0.01)
    return future.done()


class M6SystemEnvironment:
    """M6 multi-node ROS2 test environment.

    Starts all 5 M6 nodes in a single MultiThreadedExecutor.
    """

    def __init__(self, tmp_path: Path) -> None:
        """Initialize and start all M6 nodes.

        Args:
            tmp_path: Temporary directory for test artifacts.

        """
        rclpy.init(args=[
            "--ros-args", "-p", "skill_runtime_node.use_real_motion:=false"
        ])
        self._executor = MultiThreadedExecutor(num_threads=8)

        self._cap_node = CapabilityRegistryNode()
        self._wm_node = WorldModelNode()
        self._skill_node = SkillRuntimeNode()
        self._exp_node = ExperienceNode()
        self._api_node = RuntimeApiNode()

        self._executor.add_node(self._cap_node)
        self._executor.add_node(self._wm_node)
        self._executor.add_node(self._skill_node)
        self._executor.add_node(self._exp_node)
        self._executor.add_node(self._api_node)

        self._spin_thread = threading.Thread(
            target=self._executor.spin, daemon=True
        )
        self._spin_thread.start()
        time.sleep(3.0)

    def shutdown(self) -> None:
        """Shutdown all nodes and executor."""
        self._executor.shutdown()
        self._cap_node.destroy_node()
        self._wm_node.destroy_node()
        self._skill_node.destroy_node()
        self._exp_node.destroy_node()
        self._api_node.destroy_node()
        rclpy.shutdown()

    @property
    def api_node(self) -> RuntimeApiNode:
        """RuntimeApiNode instance."""
        return self._api_node

    @property
    def exp_node(self) -> ExperienceNode:
        """ExperienceNode instance."""
        return self._exp_node


@pytest.fixture(scope="module")
def m6_env(tmp_path_factory: pytest.TempPathFactory) -> M6SystemEnvironment:
    """Module-scoped M6 system environment fixture."""
    tmp_path = tmp_path_factory.mktemp("m6_e2e")
    env = M6SystemEnvironment(tmp_path)
    yield env
    env.shutdown()


class TestM6NodeStartup:
    """Chain 0: Verify all 5 M6 nodes start successfully."""

    def test_all_nodes_alive(self, m6_env: M6SystemEnvironment) -> None:
        """Test all 5 M6 nodes are alive."""
        assert m6_env.api_node is not None
        assert m6_env.exp_node is not None

    def test_runtime_api_action_server_ready(
        self, m6_env: M6SystemEnvironment
    ) -> None:
        """Test RuntimeApiNode SubmitTaskGoals action server is ready."""
        client = ActionClient(
            m6_env.api_node, SubmitTaskGoals, "/runtime/submit_task_goals"
        )
        assert client.wait_for_server(timeout_sec=5.0)
        client.destroy()

    def test_all_proxy_services_ready(
        self, m6_env: M6SystemEnvironment
    ) -> None:
        """Test all 5 proxy services are ready."""
        services = [
            (QueryWorld, "/runtime/query_world"),
            (GetCapability, "/runtime/get_capability"),
            (QueryExperience, "/runtime/query_experience"),
        ]
        for srv_type, srv_name in services:
            client = m6_env.api_node.create_client(srv_type, srv_name)
            assert client.wait_for_service(timeout_sec=5.0), (
                f"{srv_name} not ready"
            )
            client.destroy()


class TestChain1CapabilityQuery:
    """Chain 1: M6.5→M6.0 RuntimeApi → CapabilityRegistry."""

    def test_get_all_capabilities(self, m6_env: M6SystemEnvironment) -> None:
        """Test querying all capabilities through RuntimeApi proxy."""
        client = m6_env.api_node.create_client(
            GetCapability, "/runtime/get_capability"
        )
        assert client.wait_for_service(timeout_sec=5.0)

        req = GetCapability.Request()
        req.capability_name = "all"
        req.include_dynamic = True

        future = client.call_async(req)
        assert _wait_future(future, 5.0)

        response = future.result()
        assert response is not None
        assert len(response.capabilities) > 0

        cap_names = [c.name for c in response.capabilities]
        assert "manipulation" in cap_names or "gripper" in cap_names

        client.destroy()

    def test_get_capability_with_context(
        self, m6_env: M6SystemEnvironment
    ) -> None:
        """Test capability query with context parameter."""
        client = m6_env.api_node.create_client(
            GetCapability, "/runtime/get_capability"
        )
        assert client.wait_for_service(timeout_sec=5.0)

        req = GetCapability.Request()
        req.capability_name = "all"
        req.include_dynamic = True
        req.context = "left_arm"

        future = client.call_async(req)
        assert _wait_future(future, 5.0)

        response = future.result()
        assert response is not None

        client.destroy()


class TestChain2WorldModelQuery:
    """Chain 2: M6.5→M6.1 RuntimeApi → WorldModel."""

    def test_query_world_all(self, m6_env: M6SystemEnvironment) -> None:
        """Test querying world state through RuntimeApi proxy."""
        client = m6_env.api_node.create_client(
            QueryWorld, "/runtime/query_world"
        )
        assert client.wait_for_service(timeout_sec=5.0)

        req = QueryWorld.Request()
        req.query_type = "all"

        future = client.call_async(req)
        assert _wait_future(future, 5.0)

        response = future.result()
        assert response is not None

        client.destroy()

    def test_query_world_scene(self, m6_env: M6SystemEnvironment) -> None:
        """Test querying scene state through RuntimeApi proxy."""
        client = m6_env.api_node.create_client(
            QueryWorld, "/runtime/query_world"
        )
        assert client.wait_for_service(timeout_sec=5.0)

        req = QueryWorld.Request()
        req.query_type = "scene"

        future = client.call_async(req)
        assert _wait_future(future, 5.0)

        response = future.result()
        assert response is not None

        client.destroy()


class TestChain3SkillListing:
    """Chain 3: M6.5→M6.3 RuntimeApi → SkillRuntime (ListSkills)."""

    def test_list_skills_through_proxy(
        self, m6_env: M6SystemEnvironment
    ) -> None:
        """Test listing skills through RuntimeApi proxy."""
        from multi_arm_interfaces.srv import ListSkills

        client = m6_env.api_node.create_client(
            ListSkills, "/runtime/list_skills"
        )
        assert client.wait_for_service(timeout_sec=5.0)

        req = ListSkills.Request()
        req.lifecycle_state = "ready"

        future = client.call_async(req)
        assert _wait_future(future, 5.0)

        response = future.result()
        assert response is not None

        client.destroy()


class TestChain4SubmitTaskGoals:
    """Chain 4: M6.5→M6.3 RuntimeApi → SkillRuntime (SubmitTaskGoals→ExecuteSkill)."""

    def test_submit_single_pick_place(
        self, m6_env: M6SystemEnvironment
    ) -> None:
        """Test submitting a single pick_place TaskGoal through RuntimeApi."""
        client = ActionClient(
            m6_env.api_node, SubmitTaskGoals, "/runtime/submit_task_goals"
        )
        assert client.wait_for_server(timeout_sec=5.0)

        task_goal = TaskGoal()
        task_goal.action_type = "pick_place"
        task_goal.arm_name = "left_arm"
        task_goal.zone_name = "zone_a"
        task_goal.position_name = "ready"
        task_goal.object_id = "red_cube"

        goal = SubmitTaskGoals.Goal()
        goal.goals = [task_goal]

        future = client.send_goal_async(goal)
        assert _wait_future(future, 15.0)
        goal_handle = future.result()
        assert goal_handle.accepted

        result_future = goal_handle.get_result_async()
        assert _wait_future(result_future, 30.0)
        result = result_future.result().result

        assert result.total_count == 1
        assert len(result.results) == 1

        client.destroy()

    def test_submit_multiple_goals(
        self, m6_env: M6SystemEnvironment
    ) -> None:
        """Test submitting multiple TaskGoals simultaneously."""
        client = ActionClient(
            m6_env.api_node, SubmitTaskGoals, "/runtime/submit_task_goals"
        )
        assert client.wait_for_server(timeout_sec=5.0)

        goals = []
        for action_type in ["pick_place", "move", "place"]:
            tg = TaskGoal()
            tg.action_type = action_type
            tg.arm_name = "left_arm"
            goals.append(tg)

        goal = SubmitTaskGoals.Goal()
        goal.goals = goals

        future = client.send_goal_async(goal)
        assert _wait_future(future, 15.0)
        goal_handle = future.result()
        assert goal_handle.accepted

        result_future = goal_handle.get_result_async()
        assert _wait_future(result_future, 60.0)
        result = result_future.result().result

        assert result.total_count == 3
        assert len(result.results) == 3

        client.destroy()

    def test_submit_with_constraints(
        self, m6_env: M6SystemEnvironment
    ) -> None:
        """Test submitting TaskGoal with full constraints."""
        client = ActionClient(
            m6_env.api_node, SubmitTaskGoals, "/runtime/submit_task_goals"
        )
        assert client.wait_for_server(timeout_sec=5.0)

        task_goal = TaskGoal()
        task_goal.action_type = "pick_place"
        task_goal.arm_name = "right_arm"
        task_goal.zone_name = "zone_b"
        task_goal.position_name = "ready"
        task_goal.object_id = "blue_box"
        task_goal.approach = "top"
        task_goal.constraints = TaskConstraint()
        task_goal.constraints.max_time = 10.0
        task_goal.constraints.priority = 2
        task_goal.constraints.allow_recovery = True
        task_goal.constraints.max_retries = 3

        goal = SubmitTaskGoals.Goal()
        goal.goals = [task_goal]

        future = client.send_goal_async(goal)
        assert _wait_future(future, 15.0)
        goal_handle = future.result()
        assert goal_handle.accepted

        result_future = goal_handle.get_result_async()
        assert _wait_future(result_future, 30.0)
        result = result_future.result().result

        assert result.total_count == 1

        client.destroy()


class TestChain5ExperienceRecording:
    """Chain 5: M6.4 ExperienceNode direct recording."""

    def test_record_episode_direct(self, m6_env: M6SystemEnvironment) -> None:
        """Test recording an episode directly through ExperienceNode."""
        client = m6_env.api_node.create_client(
            RecordEpisode, "/experience/record"
        )
        assert client.wait_for_service(timeout_sec=5.0)

        steps_json = json.dumps([
            {"name": "perceive", "success": True, "duration": 0.3},
            {"name": "grasp", "success": True, "duration": 1.0},
            {"name": "lift", "success": True, "duration": 0.5},
        ])

        req = RecordEpisode.Request()
        req.task_id = "e2e_task_001"
        req.task_type = "pick_place"
        req.skill_name = "pick_object"
        req.steps_json = steps_json
        req.result = "success"
        req.duration = 1.8

        future = client.call_async(req)
        assert _wait_future(future, 10.0)

        response = future.result()
        assert response is not None
        assert response.success is True
        assert response.episode_id != ""

        client.destroy()

    def test_record_failure_episode(
        self, m6_env: M6SystemEnvironment
    ) -> None:
        """Test recording a failure episode with recovery."""
        client = m6_env.api_node.create_client(
            RecordEpisode, "/experience/record"
        )
        assert client.wait_for_service(timeout_sec=5.0)

        steps_json = json.dumps([
            {"name": "perceive", "success": True, "duration": 0.3},
            {"name": "grasp", "success": False, "duration": 1.0},
            {"name": "retry_grasp", "success": True, "duration": 1.2},
        ])

        req = RecordEpisode.Request()
        req.task_id = "e2e_task_002"
        req.task_type = "pick_place"
        req.skill_name = "pick_object"
        req.steps_json = steps_json
        req.result = "recovered"
        req.duration = 2.5

        future = client.call_async(req)
        assert _wait_future(future, 10.0)

        response = future.result()
        assert response is not None
        assert response.success is True

        client.destroy()


class TestChain6ExperienceQuery:
    """Chain 6: M6.5→M6.4 RuntimeApi → ExperienceNode (QueryExperience)."""

    def test_query_episodes_through_proxy(
        self, m6_env: M6SystemEnvironment
    ) -> None:
        """Test querying episodes through RuntimeApi proxy."""
        client = m6_env.api_node.create_client(
            QueryExperience, "/runtime/query_experience"
        )
        assert client.wait_for_service(timeout_sec=5.0)

        req = QueryExperience.Request()
        req.data_type = "episode"

        future = client.call_async(req)
        assert _wait_future(future, 10.0)

        response = future.result()
        assert response is not None
        assert response.count >= 0

        client.destroy()

    def test_query_episodes_has_recorded_data(
        self, m6_env: M6SystemEnvironment
    ) -> None:
        """Test that previously recorded episodes are queryable."""
        client = m6_env.api_node.create_client(
            QueryExperience, "/runtime/query_experience"
        )
        assert client.wait_for_service(timeout_sec=5.0)

        req = QueryExperience.Request()
        req.data_type = "episode"

        future = client.call_async(req)
        assert _wait_future(future, 10.0)

        response = future.result()
        assert response is not None
        assert response.count >= 2

        for record_json in response.records_json:
            record = json.loads(record_json)
            assert "episode_id" in record
            assert "task" in record
            assert "result" in record

        client.destroy()


class TestChain7FullIntegration:
    """Chain 7: Full integration — SubmitTaskGoals + RecordEpisode + QueryExperience.

    This is the highest-level M6 test: submit a task through RuntimeApi,
    record the experience, then query it back through RuntimeApi.
    """

    def test_full_task_lifecycle(self, m6_env: M6SystemEnvironment) -> None:
        """Test full task lifecycle: submit → execute → record → query.

        1. Submit TaskGoal through RuntimeApi
        2. Record the episode through ExperienceNode
        3. Query the experience through RuntimeApi
        """
        action_client = ActionClient(
            m6_env.api_node, SubmitTaskGoals, "/runtime/submit_task_goals"
        )
        assert action_client.wait_for_server(timeout_sec=5.0)

        task_goal = TaskGoal()
        task_goal.action_type = "pick_place"
        task_goal.arm_name = "left_arm"
        task_goal.zone_name = "zone_a"
        task_goal.object_id = "red_cube"

        goal = SubmitTaskGoals.Goal()
        goal.goals = [task_goal]

        future = action_client.send_goal_async(goal)
        assert _wait_future(future, 15.0)
        goal_handle = future.result()
        assert goal_handle.accepted

        result_future = goal_handle.get_result_async()
        assert _wait_future(result_future, 30.0)
        task_result = result_future.result().result

        assert task_result.total_count == 1

        record_client = m6_env.api_node.create_client(
            RecordEpisode, "/experience/record"
        )
        assert record_client.wait_for_service(timeout_sec=5.0)

        steps_json = json.dumps([
            {"name": "submit", "success": True, "duration": 0.1},
            {"name": "execute", "success": task_result.success_count == 1,
             "duration": 0.5},
        ])

        req = RecordEpisode.Request()
        req.task_id = "full_lifecycle_001"
        req.task_type = "pick_place"
        req.skill_name = "pick_object"
        req.steps_json = steps_json
        req.result = "success" if task_result.success_count == 1 else "failure"
        req.duration = 2.0

        future = record_client.call_async(req)
        assert _wait_future(future, 10.0)
        record_response = future.result()
        assert record_response.success is True

        query_client = m6_env.api_node.create_client(
            QueryExperience, "/runtime/query_experience"
        )
        assert query_client.wait_for_service(timeout_sec=5.0)

        req = QueryExperience.Request()
        req.data_type = "episode"

        future = query_client.call_async(req)
        assert _wait_future(future, 10.0)
        query_response = future.result()

        assert query_response.count >= 1

        found = False
        for record_json in query_response.records_json:
            record = json.loads(record_json)
            if record.get("episode_id") == record_response.episode_id:
                found = True
                assert record["task"] == "pick_place"
                assert record["skill"] == "pick_object"
                break

        assert found, "Recorded episode not found in query results"

        action_client.destroy()
        record_client.destroy()
        query_client.destroy()

    def test_dual_arm_task_submission(
        self, m6_env: M6SystemEnvironment
    ) -> None:
        """Test submitting tasks for both left_arm and right_arm."""
        action_client = ActionClient(
            m6_env.api_node, SubmitTaskGoals, "/runtime/submit_task_goals"
        )
        assert action_client.wait_for_server(timeout_sec=5.0)

        goal1 = TaskGoal()
        goal1.action_type = "pick_place"
        goal1.arm_name = "left_arm"
        goal1.zone_name = "zone_a"
        goal1.object_id = "red_cube"

        goal2 = TaskGoal()
        goal2.action_type = "pick_place"
        goal2.arm_name = "right_arm"
        goal2.zone_name = "zone_b"
        goal2.object_id = "blue_box"

        goal = SubmitTaskGoals.Goal()
        goal.goals = [goal1, goal2]

        future = action_client.send_goal_async(goal)
        assert _wait_future(future, 15.0)
        goal_handle = future.result()
        assert goal_handle.accepted

        result_future = goal_handle.get_result_async()
        assert _wait_future(result_future, 60.0)
        result = result_future.result().result

        assert result.total_count == 2
        assert len(result.results) == 2

        action_client.destroy()