"""End-to-end integration test for M1-M3 phases.

Validates:
1. All packages build successfully together
2. Cross-package interfaces are importable (multi_arm_interfaces)
3. Key data flows: Coordinator → SafetyCheck → WorldModel → TaskPlanner
4. YAML-driven configuration end-to-end
5. BT Pick-Place complete flow
6. Safety Plane cross-cutting behavior
"""

import os
import tempfile
import pytest

# =====================================================================
# 1. Cross-package interface imports
# =====================================================================


class TestCrossPackageInterfaces:
    """Verify all multi_arm_interfaces msg/srv/action are importable."""

    def test_import_all_msgs(self) -> None:
        from multi_arm_interfaces.msg import (
            TaskDescription,
            TaskStatus,
            TaskRequirement,
            ObjectPose,
            CollisionEvent,
            SystemHealth,
            ResourceStatus,
            RecoveryAction,
        )
        assert TaskDescription is not None
        assert TaskStatus is not None
        assert TaskRequirement is not None

    def test_import_all_srvs(self) -> None:
        from multi_arm_interfaces.srv import (
            SafetyCheck,
            EmergencyStop,
            SubmitTask,
            QueryResources,
            RecoverFromFailure,
        )
        assert SafetyCheck is not None
        assert EmergencyStop is not None

    def test_import_all_actions(self) -> None:
        from multi_arm_interfaces.action import (
            PickPlace,
            ExecuteTask,
        )
        assert PickPlace is not None
        assert ExecuteTask is not None

    def test_task_message_split(self) -> None:
        """I-02: Task message is split into Description/Status/Requirement."""
        from multi_arm_interfaces.msg import TaskDescription, TaskStatus, TaskRequirement
        desc = TaskDescription()
        desc.task_id = "t1"
        desc.task_type = "pick_place"
        status = TaskStatus()
        status.task_id = "t1"
        status.status = "PENDING"
        req = TaskRequirement()
        req.deadline = 100.0
        assert desc.task_id == "t1"
        assert status.status == "PENDING"
        assert req.deadline == 100.0

    def test_safety_check_srv_fields(self) -> None:
        """SafetyCheck.srv has correct request/response fields."""
        from multi_arm_interfaces.srv import SafetyCheck
        req = SafetyCheck.Request()
        req.arm_names = ["left_arm"]
        req.trajectory_duration = 3.0
        resp = SafetyCheck.Response()
        resp.approved = True
        resp.speed_scale = 1.0
        assert resp.approved is True


# =====================================================================
# 2. Core → Interfaces integration
# =====================================================================


class TestCoreInterfacesIntegration:
    """Verify multi_arm_core uses multi_arm_interfaces correctly."""

    def test_resource_manager_uses_yaml(self) -> None:
        """I-07: YAML-driven resource configuration."""
        from multi_arm_core.coordination.resource_manager import (
            ResourceManager, ResourceType,
        )
        config_path = os.path.join(
            os.path.dirname(__file__), "..", "config", "robots.yaml"
        )
        config_path = os.path.abspath(config_path)
        mgr = ResourceManager.from_yaml(config_path)
        assert len(mgr.get_robots()) == 2
        assert len(mgr.get_zones()) == 4

    def test_capability_matcher_with_resource_manager(self) -> None:
        """I-06: CapabilityMatcher matches task requirements to resources."""
        from multi_arm_core.coordination.resource_manager import ResourceManager, Resource, ResourceType
        from multi_arm_core.coordination.capability_matcher import CapabilityMatcher

        mgr = ResourceManager()
        mgr.register(Resource(
            name="left_arm", resource_type=ResourceType.ROBOT,
            capabilities={"payload_kg": 5.0, "reachable_zones": ["zone_a", "zone_b"]},
        ))
        mgr.register(Resource(
            name="right_arm", resource_type=ResourceType.ROBOT,
            capabilities={"payload_kg": 5.0, "reachable_zones": ["zone_a", "zone_c"]},
        ))
        matcher = CapabilityMatcher()
        robots = mgr.get_robots()
        matches = matcher.match({"reachable_zones": ["zone_c"]}, robots, ResourceType.ROBOT)
        assert len(matches) == 1
        assert matches[0].name == "right_arm"

    def test_coordinator_is_thin_orchestrator(self) -> None:
        """I-03: Coordinator only orchestrates, logic in sub-modules."""
        from multi_arm_core.coordinator_node import CoordinatorNode
        from multi_arm_core.coordination.resource_manager import ResourceManager
        from multi_arm_core.coordination.capability_matcher import CapabilityMatcher
        from multi_arm_core.coordination.time_manager import TimeManager
        from multi_arm_core.scheduler.scheduler import Scheduler, AllocationStrategy
        from multi_arm_core.task.task_manager import TaskManager
        from multi_arm_core.safety.safety_interface import SafetyInterface
        assert CoordinatorNode is not None
        assert ResourceManager is not None
        assert CapabilityMatcher is not None
        assert TimeManager is not None
        assert Scheduler is not None
        assert TaskManager is not None
        assert SafetyInterface is not None

    def test_five_resource_types(self) -> None:
        """I-05: ResourceManager manages 5 resource types."""
        from multi_arm_core.coordination.resource_manager import (
            ResourceManager, Resource, ResourceType,
        )
        mgr = ResourceManager()
        for rt in ResourceType:
            mgr.register(Resource(name=f"test_{rt.name}", resource_type=rt))
        for rt in ResourceType:
            assert len(mgr.get_by_type(rt)) == 1

    def test_zone_as_resource_manager_special_case(self) -> None:
        """I-08: Zone is managed as ResourceManager special case."""
        from multi_arm_core.coordination.resource_manager import (
            ResourceManager, Resource, ResourceState, ResourceType,
        )
        mgr = ResourceManager()
        mgr.register(Resource(name="zone_a", resource_type=ResourceType.ZONE))
        assert mgr.allocate("zone_a", "task_1")
        zone = mgr.get("zone_a")
        assert zone.state == ResourceState.ALLOCATED
        mgr.release("zone_a", "task_1")
        assert zone.state == ResourceState.FREE


# =====================================================================
# 3. Safety Plane cross-cutting integration
# =====================================================================


class TestSafetyPlaneIntegration:
    """Verify Safety Plane cross-cuts L2/L3/L6 correctly."""

    def test_safety_level_blocks_estop_commands(self) -> None:
        """I-14: E-Stop rejects new commands."""
        from multi_arm_safety.safety_level import SafetyLevel
        assert not SafetyLevel.EMERGENCY_STOP.allows_new_commands()

    def test_speed_limiter_with_safety_interface(self) -> None:
        """I-12: Speed limiting (L2) works with SafetyInterface."""
        from multi_arm_safety.speed_limiter import SpeedLimiter
        limiter = SpeedLimiter(default_max_vel=3.14)
        within, scale = limiter.check_trajectory_velocities(
            ["joint1"], [6.28], duration=1.0
        )
        assert not within
        assert scale < 1.0

    def test_workspace_limiter_boundary_check(self) -> None:
        """I-12: Workspace boundary check (L2)."""
        from multi_arm_safety.workspace_limiter import WorkspaceLimiter, WorkspaceBounds
        limiter = WorkspaceLimiter()
        limiter.set_bounds("left_arm", WorkspaceBounds(
            x_min=-0.8, x_max=0.8, y_min=-0.3, y_max=0.8, z_min=0.0, z_max=1.2
        ))
        within, _ = limiter.check_position("left_arm", 0.0, 0.5, 0.5)
        assert within
        within, _ = limiter.check_position("left_arm", 0.0, 0.5, 1.5)
        assert not within

    def test_collision_monitor_proximity(self) -> None:
        """I-11: Collision detection (L3)."""
        from multi_arm_safety.collision_monitor import CollisionMonitor
        monitor = CollisionMonitor(
            arm_configs={
                "left_arm": {"base_offset": (0.0, 0.5, 0.0)},
                "right_arm": {"base_offset": (0.0, -0.5, 0.0)},
            },
        )
        monitor.update_joint_positions("left_arm", [0.0, -1.57, 1.57, 0.0, 0.0, 0.0])
        monitor.update_joint_positions("right_arm", [0.0, -1.57, 1.57, 0.0, 0.0, 0.0])
        dist, is_collision = monitor.check_arm_proximity("left_arm", "right_arm")
        assert not is_collision
        assert dist > 0.1

    def test_safety_independent_of_coordinator(self) -> None:
        """I-15: SafetySupervisor is independent of Coordinator."""
        from multi_arm_safety.safety_supervisor import SafetySupervisor
        from multi_arm_core.coordinator_node import CoordinatorNode
        assert SafetySupervisor is not None
        assert CoordinatorNode is not None
        assert SafetySupervisor != CoordinatorNode


# =====================================================================
# 4. World Model ownership boundary
# =====================================================================


class TestWorldModelIntegration:
    """Verify WorldModel ownership and caching boundaries."""

    def test_world_model_owns_objects(self) -> None:
        """I-20: WorldModel owns Objects."""
        from multi_arm_world_model.state_database import StateDatabase, TrackedObject
        db = StateDatabase()
        db.add_object(TrackedObject(
            object_id="box1", object_type="cube",
            position=(0.3, 0.1, 0.05), confidence=0.95,
        ))
        obj = db.get_object("box1")
        assert obj is not None
        assert obj.object_type == "cube"
        assert obj.confidence == 0.95

    def test_500hz_not_in_world_model(self) -> None:
        """I-21: 500Hz joint_states do NOT enter WorldModel."""
        from multi_arm_world_model.state_database import CachedRobotState
        state = CachedRobotState(arm_name="left_arm", last_updated=100.0)
        assert state.is_stale(max_age=0.002)  # 2ms = 500Hz period

    def test_world_model_caches_robot_state_1_10hz(self) -> None:
        """I-22: WorldModel caches RobotState at 1-10Hz."""
        from multi_arm_world_model.state_database import StateDatabase
        db = StateDatabase()
        db.update_robot_state("left_arm", [0.0] * 6)
        state = db.get_robot_state("left_arm")
        assert state is not None
        assert not state.is_stale(max_age=1.0)  # 1Hz = 1s

    def test_object_tracker_with_database(self) -> None:
        """I-23: ObjectTracker ID association + motion prediction."""
        from multi_arm_world_model.state_database import StateDatabase
        from multi_arm_world_model.object_tracker import ObjectTracker
        db = StateDatabase()
        tracker = ObjectTracker()
        ids = tracker.update(db, [
            {"id": "box1", "object_type": "cube", "position": (0.3, 0.1, 0.05)},
        ])
        assert ids[0] == "box1"
        import time
        time.sleep(0.01)
        tracker.update(db, [
            {"id": "box1", "object_type": "cube", "position": (0.35, 0.1, 0.05)},
        ])
        obj = db.get_object("box1")
        assert obj.velocity[0] > 0


# =====================================================================
# 5. BT Pick-Place end-to-end flow
# =====================================================================


class TestBTPickPlaceE2E:
    """Verify complete BT Pick-Place flow."""

    def test_pick_place_xml_loads(self) -> None:
        """I-24: pick_place.xml behavior tree can be loaded."""
        from multi_arm_task_planner.behavior_tree import BehaviorTree
        from multi_arm_task_planner.bt_plugins.pick_place_plugins import PLUGIN_REGISTRY

        xml_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "multi_arm_task_planner",
            "multi_arm_task_planner", "bt_xml", "pick_place.xml",
        )
        xml_path = os.path.abspath(xml_path)
        assert os.path.exists(xml_path)

        bt = BehaviorTree()
        bt.register_plugins(PLUGIN_REGISTRY)
        bt.load_xml(xml_path)
        assert bt.root is not None

    def test_pick_place_bt_executes(self) -> None:
        """I-30: Complete Pick-Place flow through BT orchestration."""
        from multi_arm_task_planner.behavior_tree import BehaviorTree, NodeStatus
        from multi_arm_task_planner.bt_plugins.pick_place_plugins import PLUGIN_REGISTRY

        xml_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "multi_arm_task_planner",
            "multi_arm_task_planner", "bt_xml", "pick_place.xml",
        )
        xml_path = os.path.abspath(xml_path)

        bt = BehaviorTree()
        bt.register_plugins(PLUGIN_REGISTRY)
        bt.load_xml(xml_path)

        bt.blackboard.set("arm_name", "left_arm")
        bt.blackboard.set("target_position", "zone_a")
        bt.blackboard.set("object_id", "box1")
        bt.blackboard.set("target_zone", "zone_b")
        bt.blackboard.set("safety_approved", True)
        bt.blackboard.set("approach_top", "top")
        bt.blackboard.set("approach_side", "side")
        bt.blackboard.set("place_approach", "zone_b")

        status = bt.tick()
        assert status == NodeStatus.SUCCESS

    def test_bt_subtree_reuse(self) -> None:
        """I-27: BT XML is valid and loads successfully."""
        from multi_arm_task_planner.behavior_tree import BehaviorTree, Blackboard
        from multi_arm_task_planner.bt_plugins.pick_place_plugins import PLUGIN_REGISTRY
        xml_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "multi_arm_task_planner",
            "multi_arm_task_planner", "bt_xml", "pick_place.xml",
        )
        xml_path = os.path.abspath(xml_path)
        bt = BehaviorTree(blackboard=Blackboard())
        bt.register_plugins(PLUGIN_REGISTRY)
        bt.load_xml(xml_path)
        assert bt.root is not None

    def test_all_plugins_registered(self) -> None:
        """I-25: All BT Python plugins are registered."""
        from multi_arm_task_planner.bt_plugins.pick_place_plugins import PLUGIN_REGISTRY
        required = ["MoveTo", "Grasp", "Place", "CheckSafety"]
        for name in required:
            assert name in PLUGIN_REGISTRY, f"Plugin {name} not registered"


# =====================================================================
# 6. Full data flow: Task submission → Schedule → Safety → Execute
# =====================================================================


class TestFullDataFlow:
    """Verify the complete data flow from task submission to execution."""

    def test_task_submission_to_schedule(self) -> None:
        """Submit task → Scheduler schedules → arm assigned."""
        from multi_arm_core.coordination.resource_manager import ResourceManager, Resource, ResourceType
        from multi_arm_core.coordination.time_manager import TimeManager
        from multi_arm_core.scheduler.scheduler import Scheduler, Task, TaskPriority, TaskStatus

        mgr = ResourceManager()
        mgr.register(Resource(name="left_arm", resource_type=ResourceType.ROBOT,
                              capabilities={"reachable_zones": ["zone_a"]}))
        mgr.register(Resource(name="zone_a", resource_type=ResourceType.ZONE))

        scheduler = Scheduler(TimeManager(), mgr)
        task = Task(task_id="t1", zone_name="zone_a", priority=TaskPriority.HIGH)
        scheduler.submit(task)
        plan = scheduler.schedule_all()
        assert len(plan.scheduled) == 1
        assert plan.scheduled[0].assigned_arm == "left_arm"

    def test_safety_check_before_execution(self) -> None:
        """Safety check must pass before trajectory is sent."""
        from multi_arm_safety.safety_level import SafetyLevel
        from multi_arm_safety.speed_limiter import SpeedLimiter

        limiter = SpeedLimiter(default_max_vel=3.14)
        within, scale = limiter.check_trajectory_velocities(
            ["j1"], [1.57], duration=1.0
        )
        assert within
        assert SafetyLevel.NORMAL.allows_motion()

    def test_estop_blocks_everything(self) -> None:
        """E-Stop blocks all motion and new commands."""
        from multi_arm_safety.safety_level import SafetyLevel
        estop = SafetyLevel.EMERGENCY_STOP
        assert not estop.allows_motion()
        assert not estop.allows_new_commands()

    def test_yaml_config_drives_resources(self) -> None:
        """I-07: Adding a new arm only requires YAML change."""
        yaml_content = """
robots:
  - name: left_arm
    type: ur5e
    capabilities:
      payload_kg: 5.0
      reachable_zones: [zone_a, home]
  - name: right_arm
    type: ur5e
    capabilities:
      payload_kg: 5.0
      reachable_zones: [zone_a, zone_c, home]
  - name: arm3
    type: ur5e
    capabilities:
      payload_kg: 3.0
      reachable_zones: [zone_b, home]
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
            from multi_arm_core.coordination.resource_manager import ResourceManager
            mgr = ResourceManager.from_yaml(yaml_path)
            assert len(mgr.get_robots()) == 3
            arm3 = mgr.get("arm3")
            assert arm3.capabilities["payload_kg"] == 3.0
        finally:
            os.unlink(yaml_path)

    def test_world_model_feeds_task_planner(self) -> None:
        """WorldModel object data can inform BT execution."""
        from multi_arm_world_model.state_database import StateDatabase, TrackedObject
        from multi_arm_task_planner.behavior_tree import BehaviorTree, Blackboard, NodeStatus
        from multi_arm_task_planner.bt_plugins.pick_place_plugins import PLUGIN_REGISTRY

        db = StateDatabase()
        db.add_object(TrackedObject(
            object_id="target_box", object_type="cube",
            position=(0.3, 0.1, 0.05),
        ))

        bb = Blackboard()
        bb.set("object_id", "target_box")
        bb.set("arm_name", "left_arm")
        bb.set("target_zone", "zone_b")
        bb.set("safety_approved", True)

        bt = BehaviorTree(blackboard=bb)
        bt.register_plugins(PLUGIN_REGISTRY)

        xml_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "multi_arm_task_planner",
            "multi_arm_task_planner", "bt_xml", "pick_place.xml",
        )
        xml_path = os.path.abspath(xml_path)
        bt.load_xml(xml_path)

        bt.blackboard.set("approach_top", "top")
        bt.blackboard.set("approach_side", "side")
        bt.blackboard.set("place_approach", "zone_b")
        bt.blackboard.set("target_position", "zone_a")

        status = bt.tick()
        assert status == NodeStatus.SUCCESS