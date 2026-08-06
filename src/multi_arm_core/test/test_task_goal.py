"""Tests for M5.3 Task Message Upgrade — structured TaskGoal and backward compatibility."""

import os
import pytest

os.environ.setdefault("ROS_HOME", "/tmp/ros_home")
os.environ.setdefault("ROS_LOG_DIR", "/tmp/ros_home/log")


class TestTaskGoalMsg:
    """Test TaskGoal message definition and construction."""

    def test_task_goal_import(self) -> None:
        from multi_arm_interfaces.msg import TaskGoal
        goal = TaskGoal()
        assert goal is not None

    def test_task_goal_fields(self) -> None:
        from multi_arm_interfaces.msg import TaskGoal
        goal = TaskGoal()
        goal.action_type = "move"
        goal.arm_name = "arm1"
        goal.zone_name = "zone_a"
        goal.position_name = "ready"
        goal.object_id = "red_cube"
        goal.approach = "top"
        assert goal.action_type == "move"
        assert goal.arm_name == "arm1"
        assert goal.zone_name == "zone_a"
        assert goal.position_name == "ready"
        assert goal.object_id == "red_cube"
        assert goal.approach == "top"

    def test_task_goal_defaults(self) -> None:
        from multi_arm_interfaces.msg import TaskGoal
        goal = TaskGoal()
        assert goal.action_type == ""
        assert goal.arm_name == ""
        assert goal.zone_name == ""
        assert goal.position_name == ""
        assert goal.object_id == ""
        assert goal.approach == ""

    def test_task_goal_with_constraints(self) -> None:
        from multi_arm_interfaces.msg import TaskGoal, TaskConstraint
        goal = TaskGoal()
        goal.action_type = "pick_place"
        goal.arm_name = "arm2"
        goal.constraints = TaskConstraint()
        goal.constraints.max_time = 30.0
        goal.constraints.safety_level = 1
        goal.constraints.priority = 2
        goal.constraints.allow_recovery = True
        goal.constraints.max_retries = 3
        assert goal.constraints.max_time == 30.0
        assert goal.constraints.safety_level == 1
        assert goal.constraints.priority == 2
        assert goal.constraints.allow_recovery is True
        assert goal.constraints.max_retries == 3


class TestTaskConstraintMsg:
    """Test TaskConstraint message definition."""

    def test_task_constraint_import(self) -> None:
        from multi_arm_interfaces.msg import TaskConstraint
        c = TaskConstraint()
        assert c is not None

    def test_task_constraint_fields(self) -> None:
        from multi_arm_interfaces.msg import TaskConstraint
        c = TaskConstraint()
        c.max_time = 60.0
        c.safety_level = 2
        c.priority = 3
        c.allow_recovery = False
        c.max_retries = 0
        assert c.max_time == 60.0
        assert c.safety_level == 2
        assert c.priority == 3
        assert c.allow_recovery is False
        assert c.max_retries == 0

    def test_task_constraint_defaults(self) -> None:
        from multi_arm_interfaces.msg import TaskConstraint
        c = TaskConstraint()
        assert c.max_time == 0.0
        assert c.safety_level == 0
        assert c.priority == 0
        assert c.allow_recovery is False
        assert c.max_retries == 0


class TestMotionRequestMsg:
    """Test MotionRequest message definition."""

    def test_motion_request_import(self) -> None:
        from multi_arm_interfaces.msg import MotionRequest
        req = MotionRequest()
        assert req is not None

    def test_motion_request_named_target(self) -> None:
        from multi_arm_interfaces.msg import MotionRequest
        req = MotionRequest()
        req.arm_name = "arm1"
        req.target_position = "ready"
        req.use_named_target = True
        req.speed_scale = 0.5
        req.collision_check = True
        assert req.arm_name == "arm1"
        assert req.target_position == "ready"
        assert req.use_named_target is True
        assert req.speed_scale == 0.5
        assert req.collision_check is True

    def test_motion_request_joint_positions(self) -> None:
        from multi_arm_interfaces.msg import MotionRequest
        req = MotionRequest()
        req.arm_name = "arm2"
        req.use_named_target = False
        req.joint_positions = [0.0, -1.57, 1.57, 0.0, 1.57, 0.0]
        req.speed_scale = 0.3
        req.collision_check = True
        req.max_velocity = 1.5
        assert len(req.joint_positions) == 6
        assert req.speed_scale == 0.3
        assert req.max_velocity == 1.5


class TestExecuteTaskWithGoal:
    """Test ExecuteTask action with TaskGoal field."""

    def test_execute_task_has_goal_field(self) -> None:
        from multi_arm_interfaces.action import ExecuteTask
        goal = ExecuteTask.Goal()
        goal.task_id = "test_001"
        goal.task_type = "move"
        goal.description = "arm1:zone_a:ready"
        assert hasattr(goal, 'goal'), "ExecuteTask.Goal should have 'goal' field"

    def test_execute_task_with_structured_goal(self) -> None:
        from multi_arm_interfaces.action import ExecuteTask
        from multi_arm_interfaces.msg import TaskGoal, TaskConstraint
        goal = ExecuteTask.Goal()
        goal.task_id = "test_002"
        goal.task_type = "pick_place"
        goal.description = "arm2:zone_b:ready"
        task_goal = TaskGoal()
        task_goal.action_type = "pick_place"
        task_goal.arm_name = "arm2"
        task_goal.zone_name = "zone_b"
        task_goal.position_name = "ready"
        task_goal.object_id = "blue_box"
        task_goal.approach = "side"
        task_goal.constraints = TaskConstraint()
        task_goal.constraints.priority = 2
        goal.goal = task_goal
        assert goal.goal.arm_name == "arm2"
        assert goal.goal.zone_name == "zone_b"
        assert goal.goal.object_id == "blue_box"
        assert goal.goal.constraints.priority == 2

    def test_execute_task_backward_compat(self) -> None:
        from multi_arm_interfaces.action import ExecuteTask
        goal = ExecuteTask.Goal()
        goal.task_id = "test_003"
        goal.task_type = "move"
        goal.description = "arm1:zone_a:ready"
        assert goal.description == "arm1:zone_a:ready"


class TestCoordinatorParseTaskGoal:
    """Test Coordinator._parse_task_goal with structured messages."""

    def test_parse_task_goal_basic(self) -> None:
        from multi_arm_core.coordinator_node import CoordinatorNode
        from multi_arm_interfaces.msg import TaskGoal
        task_goal = TaskGoal()
        task_goal.arm_name = "arm1"
        task_goal.zone_name = "zone_a"
        task_goal.position_name = "ready"
        arm, zone, pos = CoordinatorNode._parse_task_goal(None, task_goal)
        assert arm == "arm1"
        assert zone == "zone_a"
        assert pos == "ready"

    def test_parse_task_goal_arm2(self) -> None:
        from multi_arm_core.coordinator_node import CoordinatorNode
        from multi_arm_interfaces.msg import TaskGoal
        task_goal = TaskGoal()
        task_goal.arm_name = "arm2"
        task_goal.zone_name = "zone_b"
        task_goal.position_name = "home"
        arm, zone, pos = CoordinatorNode._parse_task_goal(None, task_goal)
        assert arm == "arm2"
        assert zone == "zone_b"
        assert pos == "home"

    def test_parse_task_goal_default_position(self) -> None:
        from multi_arm_core.coordinator_node import CoordinatorNode
        from multi_arm_interfaces.msg import TaskGoal
        task_goal = TaskGoal()
        task_goal.arm_name = "arm1"
        task_goal.zone_name = "zone_a"
        arm, zone, pos = CoordinatorNode._parse_task_goal(None, task_goal)
        assert pos == "ready"

    def test_parse_task_goal_no_arm(self) -> None:
        from multi_arm_core.coordinator_node import CoordinatorNode
        from multi_arm_interfaces.msg import TaskGoal
        task_goal = TaskGoal()
        task_goal.arm_name = ""
        arm, zone, pos = CoordinatorNode._parse_task_goal(None, task_goal)
        assert arm is None

    def test_parse_task_backward_compat(self) -> None:
        from multi_arm_core.coordinator_node import CoordinatorNode
        arm, zone, pos = CoordinatorNode._parse_task(None, "move", "arm1:zone_a:ready")
        assert arm == "arm1"
        assert zone == "zone_a"
        assert pos == "ready"

    def test_parse_task_goal_with_object(self) -> None:
        from multi_arm_core.coordinator_node import CoordinatorNode
        from multi_arm_interfaces.msg import TaskGoal
        task_goal = TaskGoal()
        task_goal.action_type = "pick_place"
        task_goal.arm_name = "arm2"
        task_goal.zone_name = "zone_b"
        task_goal.position_name = "ready"
        task_goal.object_id = "red_cube"
        task_goal.approach = "top"
        arm, zone, pos = CoordinatorNode._parse_task_goal(None, task_goal)
        assert arm == "arm2"
        assert zone == "zone_b"
        assert pos == "ready"


class TestTaskGoalBlackboardIntegration:
    """Test that TaskGoal fields propagate to BT blackboard correctly."""

    def test_blackboard_from_task_goal(self) -> None:
        from multi_arm_interfaces.msg import TaskGoal, TaskConstraint
        from multi_arm_task_planner.behavior_tree import Blackboard
        bb = Blackboard()
        task_goal = TaskGoal()
        task_goal.action_type = "pick_place"
        task_goal.arm_name = "arm2"
        task_goal.zone_name = "zone_b"
        task_goal.position_name = "scan"
        task_goal.object_id = "blue_box"
        task_goal.approach = "side"
        bb.set("arm_name", task_goal.arm_name)
        bb.set("target_zone", task_goal.zone_name)
        bb.set("target_position", task_goal.position_name)
        bb.set("object_id", task_goal.object_id)
        bb.set("approach", task_goal.approach)
        assert bb.get("arm_name") == "arm2"
        assert bb.get("target_zone") == "zone_b"
        assert bb.get("target_position") == "scan"
        assert bb.get("object_id") == "blue_box"
        assert bb.get("approach") == "side"

    def test_blackboard_fallback_without_task_goal(self) -> None:
        from multi_arm_task_planner.behavior_tree import Blackboard
        bb = Blackboard()
        bb.set("arm_name", "arm1")
        bb.set("target_zone", "zone_a")
        bb.set("target_position", "ready")
        bb.set("object_id", "red_cube")
        assert bb.get("arm_name") == "arm1"
        assert bb.get("target_zone") == "zone_a"
        assert bb.get("target_position") == "ready"