"""Tests for ResourceManager."""

import pytest
import tempfile
import os

from multi_arm_core.coordination.resource_manager import (
    Resource,
    ResourceManager,
    ResourceState,
    ResourceType,
)


class TestResource:
    """Tests for the Resource dataclass."""

    def test_initial_state_is_free(self) -> None:
        r = Resource(name="arm1", resource_type=ResourceType.ROBOT)
        assert r.state == ResourceState.FREE
        assert r.allocated_to is None
        assert r.is_available()

    def test_allocate_success(self) -> None:
        r = Resource(name="zone_a", resource_type=ResourceType.ZONE)
        assert r.allocate("task_1")
        assert r.state == ResourceState.ALLOCATED
        assert r.allocated_to == "task_1"
        assert not r.is_available()

    def test_allocate_queued_when_busy(self) -> None:
        r = Resource(name="zone_a", resource_type=ResourceType.ZONE)
        r.allocate("task_1")
        assert not r.allocate("task_2")
        assert "task_2" in r.waiting_queue

    def test_release_grants_next(self) -> None:
        r = Resource(name="zone_a", resource_type=ResourceType.ZONE)
        r.allocate("task_1")
        r.allocate("task_2")
        next_task = r.release("task_1")
        assert next_task == "task_2"
        assert r.allocated_to == "task_2"
        assert r.state == ResourceState.ALLOCATED

    def test_release_becomes_free(self) -> None:
        r = Resource(name="zone_a", resource_type=ResourceType.ZONE)
        r.allocate("task_1")
        next_task = r.release("task_1")
        assert next_task is None
        assert r.state == ResourceState.FREE
        assert r.allocated_to is None

    def test_reserve(self) -> None:
        r = Resource(name="tool_1", resource_type=ResourceType.TOOL)
        assert r.reserve("task_1")
        assert r.state == ResourceState.RESERVED
        assert r.allocated_to == "task_1"

    def test_cancel_reservation(self) -> None:
        r = Resource(name="tool_1", resource_type=ResourceType.TOOL)
        r.reserve("task_1")
        assert r.cancel_reservation("task_1")
        assert r.state == ResourceState.FREE

    def test_cancel_from_queue(self) -> None:
        r = Resource(name="zone_a", resource_type=ResourceType.ZONE)
        r.allocate("task_1")
        r.allocate("task_2")
        assert r.cancel_reservation("task_2")
        assert "task_2" not in r.waiting_queue


class TestResourceManager:
    """Tests for the ResourceManager class."""

    def test_register_and_get(self) -> None:
        mgr = ResourceManager()
        r = Resource(name="arm1", resource_type=ResourceType.ROBOT)
        mgr.register(r)
        assert mgr.get("arm1") is r
        assert mgr.get("nonexistent") is None

    def test_get_by_type(self) -> None:
        mgr = ResourceManager()
        mgr.register(Resource(name="arm1", resource_type=ResourceType.ROBOT))
        mgr.register(Resource(name="arm2", resource_type=ResourceType.ROBOT))
        mgr.register(Resource(name="zone_a", resource_type=ResourceType.ZONE))
        robots = mgr.get_robots()
        assert len(robots) == 2
        zones = mgr.get_zones()
        assert len(zones) == 1

    def test_allocate_and_release(self) -> None:
        mgr = ResourceManager()
        mgr.register(Resource(name="zone_a", resource_type=ResourceType.ZONE))
        assert mgr.allocate("zone_a", "task_1")
        assert mgr.get("zone_a").state == ResourceState.ALLOCATED
        mgr.release("zone_a", "task_1")
        assert mgr.get("zone_a").state == ResourceState.FREE

    def test_allocate_nonexistent(self) -> None:
        mgr = ResourceManager()
        assert not mgr.allocate("nonexistent", "task_1")

    def test_from_yaml(self) -> None:
        yaml_content = """
robots:
  - name: arm1
    type: ur5e
    namespace: /arm1
    capabilities:
      payload_kg: 5.0
      gripper: robotiq_2f85
      reachable_zones: [zone_a, zone_b, home]
  - name: arm2
    type: ur5e
    namespace: /arm2
    capabilities:
      payload_kg: 5.0
      gripper: robotiq_2f85
      reachable_zones: [zone_a, zone_c, home]
resources:
  zones: [zone_a, zone_b, zone_c, home]
  tools: []
  sensors: []
  fixtures: []
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            yaml_path = f.name

        try:
            mgr = ResourceManager.from_yaml(yaml_path)
            assert len(mgr.get_robots()) == 2
            assert len(mgr.get_zones()) == 4
            assert mgr.get("arm1").capabilities["payload_kg"] == 5.0
            assert mgr.get("arm2").capabilities["reachable_zones"] == [
                "zone_a",
                "zone_c",
                "home",
            ]
        finally:
            os.unlink(yaml_path)

    def test_from_yaml_with_detailed_resources(self) -> None:
        yaml_content = """
robots:
  - name: arm1
    type: ur5e
    capabilities:
      payload_kg: 5.0
resources:
  zones: [zone_a]
  tools:
    - name: gripper_1
      capabilities:
        type: robotiq_2f85
  sensors: []
  fixtures: []
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            yaml_path = f.name

        try:
            mgr = ResourceManager.from_yaml(yaml_path)
            assert len(mgr.get_robots()) == 1
            tool = mgr.get("gripper_1")
            assert tool is not None
            assert tool.resource_type == ResourceType.TOOL
            assert tool.capabilities["type"] == "robotiq_2f85"
        finally:
            os.unlink(yaml_path)

    def test_get_all_status(self) -> None:
        mgr = ResourceManager()
        mgr.register(Resource(name="arm1", resource_type=ResourceType.ROBOT))
        status = mgr.get_all_status()
        assert "arm1" in status
        assert status["arm1"]["type"] == "ROBOT"
        assert status["arm1"]["state"] == "FREE"

    def test_five_resource_types(self) -> None:
        mgr = ResourceManager()
        mgr.register(Resource(name="arm1", resource_type=ResourceType.ROBOT))
        mgr.register(Resource(name="zone_a", resource_type=ResourceType.ZONE))
        mgr.register(Resource(name="gripper", resource_type=ResourceType.TOOL))
        mgr.register(Resource(name="camera", resource_type=ResourceType.SENSOR))
        mgr.register(Resource(name="fixture_1", resource_type=ResourceType.FIXTURE))
        assert len(mgr) == 5
        assert len(mgr.get_by_type(ResourceType.ROBOT)) == 1
        assert len(mgr.get_by_type(ResourceType.ZONE)) == 1
        assert len(mgr.get_by_type(ResourceType.TOOL)) == 1
        assert len(mgr.get_by_type(ResourceType.SENSOR)) == 1
        assert len(mgr.get_by_type(ResourceType.FIXTURE)) == 1

    def test_resource_names(self) -> None:
        mgr = ResourceManager()
        mgr.register(Resource(name="arm1", resource_type=ResourceType.ROBOT))
        mgr.register(Resource(name="zone_a", resource_type=ResourceType.ZONE))
        assert sorted(mgr.resource_names) == ["arm1", "zone_a"]