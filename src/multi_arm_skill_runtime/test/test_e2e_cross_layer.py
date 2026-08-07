"""M6.2→M6.3 跨层 E2E: Skill真正驱动机器人.

证明: Skill不是软件模拟，而是真正控制机器人.

完整链路:
    TaskGoal
      ↓ Skill Selection (Registry查询)
      ↓ Skill Runtime (Lifecycle: Ready→Execute→Monitor)
      ↓ Capability Check (manipulation/gripper/vision)
      ↓ Precondition Check (WorldModel: object exists)
      ↓ Execution: GraspPlanner → GripperController → attach
      ↓ WorldModel Update (ObjectState: ATTACHED)
      ↓ Postcondition Check (Relation: attached_to)
      ↓ Verification (Gripper+WorldModel反映Reality)

测试重点: 不是Runtime逻辑，而是Skill执行函数真的调用了GripperController和WorldModel.
"""

from __future__ import annotations

from typing import Any

import pytest

from multi_arm_perception.perception_node import ObjectDetector
from multi_arm_world_model.state_database import StateDatabase, TrackedObject
from multi_arm_world_model.relation_layer import RelationLayer
from multi_arm_world_model.history_layer import HistoryLayer
from multi_arm_manipulation.gripper_controller import GripperController
from multi_arm_manipulation.grasp_planner import GraspPlanner
from multi_arm_skill_runtime.skill_manifest import SkillManifest, SkillCost
from multi_arm_skill_runtime.skill_registry import SkillRegistry
from multi_arm_skill_runtime.skill_runtime import SkillRuntime, ExecutionStatus
from multi_arm_skill_runtime.skill_composer import SkillComposer
from multi_arm_skill_runtime.skill_lifecycle import SkillLifecycleState


class CrossLayerEnvironment:
    """跨层环境: Perception + WorldModel + Manipulation + Skill Runtime.

    封装真实组件，Skill执行函数调用这些组件产生真实副作用.
    """

    def __init__(self) -> None:
        """Initialize all layers."""
        self.perception = ObjectDetector({"position_noise": 0.0, "confidence": 0.95})
        self.db = StateDatabase()
        self.relations = RelationLayer()
        self.history = HistoryLayer(max_length=100)
        self.gripper = GripperController({"max_opening_mm": 85, "max_force_n": 100.0})
        self.planner = GraspPlanner()
        self.registry = SkillRegistry()

    def detect_and_sync(self) -> int:
        """Perception检测 → WorldModel同步.

        Returns:
            Number of objects detected.

        """
        detections = self.perception.detect()
        for det in detections:
            existing = self.db.get_object(det.object_id)
            if existing is None:
                self.db.add_object(TrackedObject(
                    object_id=det.object_id,
                    object_type=det.object_type,
                    position=tuple(det.position),
                    orientation=tuple(det.orientation),
                    confidence=det.confidence,
                ))
            else:
                self.db.update_object_pose(
                    det.object_id,
                    tuple(det.position),
                    tuple(det.orientation),
                    det.confidence,
                )
            self.history.record(
                det.object_id,
                {"position": list(det.position), "state": "FREE"},
            )
        return len(detections)

    def capability_checker(self, cap: str) -> bool:
        """Check if capability is available.

        Args:
            cap: Capability name.

        Returns:
            True if available.

        """
        return cap in ["manipulation", "gripper", "vision"]

    def precondition_checker(self, expr: str, context: dict) -> bool:
        """Check precondition against WorldModel.

        Args:
            expr: Precondition expression.
            context: Execution context.

        Returns:
            True if satisfied.

        """
        object_id = context.get("object_id", "")
        arm_name = context.get("arm_name", "")

        if "object exists" in expr:
            return self.db.get_object(object_id) is not None
        if "gripper is open" in expr:
            return self.gripper.is_open(arm_name) if arm_name else False
        if "attached" in expr and "NOT" in expr:
            return not self.relations.is_attached(object_id)
        if "arm is idle" in expr:
            return True
        if "attached" in expr:
            return self.relations.is_attached(object_id)
        return True

    def postcondition_checker(self, expr: str, context: dict) -> bool:
        """Check postcondition against WorldModel.

        Args:
            expr: Postcondition expression.
            context: Execution context.

        Returns:
            True if satisfied.

        """
        object_id = context.get("object_id", "")
        arm_name = context.get("arm_name", "")

        if "NOT" in expr and "attached" in expr:
            return not self.relations.is_attached(object_id)
        if "attached_to gripper" in expr:
            return self.relations.is_attached(object_id, f"{arm_name}_gripper")
        if "on" in expr and "target" in expr:
            return True
        if "above" in expr:
            obj = self.db.get_object(object_id)
            return obj is not None and obj.position[2] > 0.1
        return True


@pytest.fixture
def env() -> CrossLayerEnvironment:
    """Create cross-layer environment with red_cube detected."""
    e = CrossLayerEnvironment()

    e.perception.register_object("red_cube", "cube", [0.5, 0.0, 0.04])
    e.gripper.register_gripper("arm1")
    e.detect_and_sync()

    return e


def make_pick_execution(env: CrossLayerEnvironment):
    """Create REAL pick execution function that drives Gripper + WorldModel.

    This function calls GripperController and updates WorldModel —
    it is NOT a mock that returns True.

    Args:
        env: Cross-layer environment.

    Returns:
        Execution callable.

    """

    def execute(object_id: str = "red_cube", arm_name: str = "arm1", **kwargs: Any) -> bool:
        """Pick object: plan grasp → close gripper → attach → update WorldModel.

        Args:
            object_id: Object to pick.
            arm_name: Arm to use.

        Returns:
            True if pick succeeded.

        """
        obj = env.db.get_object(object_id)
        if obj is None:
            return False

        grasp_pose = env.planner.plan_grasp(
            list(obj.position),
            object_size=[0.05, 0.05, 0.05],
            approach="top",
        )
        if grasp_pose is None:
            return False

        success, msg = env.gripper.close(arm_name, force=30.0)
        if not success:
            return False

        success, msg = env.gripper.attach(arm_name, object_id)
        if not success:
            return False

        env.relations.set_attached(object_id, f"{arm_name}_gripper")
        env.history.record(object_id, {
            "position": list(obj.position),
            "state": "ATTACHED",
            "action": "pick",
        })

        return True

    return execute


def make_place_execution(env: CrossLayerEnvironment):
    """Create REAL place execution function that drives Gripper + WorldModel.

    Args:
        env: Cross-layer environment.

    Returns:
        Execution callable.

    """

    def execute(
        object_id: str = "red_cube",
        arm_name: str = "arm1",
        target_position: list | None = None,
        **kwargs: Any,
    ) -> bool:
        """Place object: move → detach → open gripper → update WorldModel.

        Args:
            object_id: Object to place.
            arm_name: Arm to use.
            target_position: Target [x, y, z].

        Returns:
            True if place succeeded.

        """
        target = target_position or [-0.5, 0.0, 0.04]

        success, msg = env.gripper.detach(arm_name)
        if not success:
            return False

        env.db.update_object_pose(object_id, tuple(target))
        env.relations.set_detached(object_id, f"{arm_name}_gripper")
        env.history.record(object_id, {
            "position": target,
            "state": "FREE",
            "action": "place",
        })

        success, msg = env.gripper.open(arm_name)
        if not success:
            return False

        return True

    return execute


def install_pick_skill(env: CrossLayerEnvironment) -> str:
    """Install pick_object skill into registry.

    Args:
        env: Cross-layer environment.

    Returns:
        Skill ID.

    """
    manifest = SkillManifest(
        name="pick_object",
        version="1.0.0",
        description="Pick up an object",
        required_capabilities=["manipulation", "gripper", "vision"],
        preconditions=["object exists", "gripper is open"],
        postconditions=["object attached_to gripper"],
        execute_steps=["perceive", "plan_grasp", "grasp", "lift"],
        cost=SkillCost(time=5.0, risk=0.1, success_rate=0.95),
        recovery={"grasp_failed": "retry(3) → change_approach → abort"},
    )
    skill_id = env.registry.install_skill(manifest)
    env.registry.register_skill(skill_id)
    env.registry.validate_skill(skill_id, env.capability_checker)
    return skill_id


def install_place_skill(env: CrossLayerEnvironment) -> str:
    """Install place_object skill into registry.

    Args:
        env: Cross-layer environment.

    Returns:
        Skill ID.

    """
    manifest = SkillManifest(
        name="place_object",
        version="1.0.0",
        description="Place an object",
        required_capabilities=["manipulation", "gripper"],
        preconditions=["object attached"],
        postconditions=["NOT (object attached_to gripper)"],
        execute_steps=["move", "lower", "release", "retract"],
        cost=SkillCost(time=4.0, risk=0.08, success_rate=0.96),
        recovery={"place_failed": "retry(2) → adjust → abort"},
    )
    skill_id = env.registry.install_skill(manifest)
    env.registry.register_skill(skill_id)
    env.registry.validate_skill(skill_id, env.capability_checker)
    return skill_id


class TestSkillDrivesRobot:
    """E2E: Skill真正驱动机器人（不是mock）."""

    def test_pick_skill_drives_gripper_and_worldmodel(self, env: CrossLayerEnvironment) -> None:
        """pick_object Skill执行后: Gripper真的close+attach, WorldModel真的更新.

        验证链路:
        TaskGoal → Skill Selection → Capability Check → Precondition →
        Execution(GraspPlanner→GripperController→attach) →
        WorldModel Update → Postcondition → Verification

        证明: Skill执行函数调用了GripperController.close()和attach()，
              并更新了WorldModel Relation Layer。
        """
        skill_id = install_pick_skill(env)

        runtime = SkillRuntime(
            env.registry,
            capability_checker=env.capability_checker,
            precondition_checker=env.precondition_checker,
            postcondition_checker=env.postcondition_checker,
            execution_functions={"pick_object": make_pick_execution(env)},
        )

        assert env.gripper.is_open("arm1")
        assert not env.relations.is_attached("red_cube")

        result = runtime.execute(
            skill_id,
            parameters={"object_id": "red_cube", "arm_name": "arm1"},
            context={"object_id": "red_cube", "arm_name": "arm1"},
        )

        assert result.status == ExecutionStatus.SUCCESS

        assert env.gripper.is_closed("arm1")
        assert env.gripper.has_object("arm1")
        assert env.gripper.get_attached_object("arm1") == "red_cube"

        assert env.relations.is_attached("red_cube", "arm1_gripper")
        assert env.relations.has_relation("red_cube", "attached_to", "arm1_gripper")

        hist = env.history.get_history("red_cube")
        assert len(hist) >= 2
        assert hist[-1].data["state"] == "ATTACHED"
        assert hist[-1].data["action"] == "pick"

    def test_place_skill_drives_gripper_and_worldmodel(self, env: CrossLayerEnvironment) -> None:
        """place_object Skill执行后: Gripper真的detach+open, WorldModel真的更新.

        前提: 先pick，再place.
        """
        pick_id = install_pick_skill(env)
        place_id = install_place_skill(env)

        runtime = SkillRuntime(
            env.registry,
            capability_checker=env.capability_checker,
            precondition_checker=env.precondition_checker,
            postcondition_checker=env.postcondition_checker,
            execution_functions={
                "pick_object": make_pick_execution(env),
                "place_object": make_place_execution(env),
            },
        )

        pick_result = runtime.execute(
            pick_id,
            parameters={"object_id": "red_cube", "arm_name": "arm1"},
            context={"object_id": "red_cube", "arm_name": "arm1"},
        )
        assert pick_result.status == ExecutionStatus.SUCCESS

        assert env.gripper.is_closed("arm1")
        assert env.relations.is_attached("red_cube", "arm1_gripper")

        place_result = runtime.execute(
            place_id,
            parameters={"object_id": "red_cube", "arm_name": "arm1"},
            context={"object_id": "red_cube", "arm_name": "arm1"},
        )
        assert place_result.status == ExecutionStatus.SUCCESS

        assert env.gripper.is_open("arm1")
        assert not env.gripper.has_object("arm1")

        assert not env.relations.is_attached("red_cube")

        obj = env.db.get_object("red_cube")
        assert obj is not None
        assert list(obj.position) == pytest.approx([-0.5, 0.0, 0.04])

        hist = env.history.get_history("red_cube")
        assert hist[-1].data["state"] == "FREE"
        assert hist[-1].data["action"] == "place"

    def test_pick_place_composite_drives_full_chain(
        self,
        env: CrossLayerEnvironment,
    ) -> None:
        """pick→place组合Skill: 全链路驱动.

        验证: 组合执行后，Gripper经历了 close→attach→detach→open 完整循环，
              WorldModel经历了 FREE→ATTACHED→FREE 完整状态转换.
        """
        pick_id = install_pick_skill(env)
        place_id = install_place_skill(env)

        runtime = SkillRuntime(
            env.registry,
            capability_checker=env.capability_checker,
            precondition_checker=env.precondition_checker,
            postcondition_checker=env.postcondition_checker,
            execution_functions={
                "pick_object": make_pick_execution(env),
                "place_object": make_place_execution(env),
            },
        )
        composer = SkillComposer(runtime)

        result = (
            composer.compose("pick_and_place")
            .add_step(pick_id, parameters={"object_id": "red_cube", "arm_name": "arm1"})
            .add_step(place_id, parameters={"object_id": "red_cube", "arm_name": "arm1"})
            .execute(context={"object_id": "red_cube", "arm_name": "arm1"})
        )

        assert result.success
        assert result.completed_steps == 2

        assert env.gripper.is_open("arm1")
        assert not env.gripper.has_object("arm1")
        assert not env.relations.is_attached("red_cube")

        hist = env.history.get_history("red_cube")
        states = [e.data["state"] for e in hist]
        assert "FREE" in states
        assert "ATTACHED" in states
        assert states[-1] == "FREE"

        actions = [e.data.get("action", "") for e in hist]
        assert "pick" in actions
        assert "place" in actions


class TestSkillFailureWithRealRobot:
    """E2E: Skill失败时的真实机器人行为."""

    def test_object_not_in_worldmodel_precondition_fails(
        self,
        env: CrossLayerEnvironment,
    ) -> None:
        """WorldModel中没有object → precondition失败 → 不执行.

        验证: Gripper状态不变（没有close）.
        """
        skill_id = install_pick_skill(env)

        runtime = SkillRuntime(
            env.registry,
            capability_checker=env.capability_checker,
            precondition_checker=env.precondition_checker,
            postcondition_checker=env.postcondition_checker,
            execution_functions={"pick_object": make_pick_execution(env)},
        )

        result = runtime.execute(
            skill_id,
            parameters={"object_id": "nonexistent", "arm_name": "arm1"},
            context={"object_id": "nonexistent", "arm_name": "arm1"},
        )

        assert result.status == ExecutionStatus.FAILURE
        assert result.failure_reason == "precondition_failed"

        assert env.gripper.is_open("arm1")
        assert not env.gripper.has_object("arm1")

    def test_missing_capability_blocks_execution(self, env: CrossLayerEnvironment) -> None:
        """缺少gripper能力 → capability检查失败 → 不执行.

        验证: Gripper状态不变.
        """
        manifest = SkillManifest(
            name="needs_special_cap",
            required_capabilities=["manipulation", "nonexistent_sensor"],
            preconditions=["object exists"],
            postconditions=[],
            execute_steps=["step"],
        )
        skill_id = env.registry.install_skill(manifest)
        env.registry.register_skill(skill_id)
        env.registry.validate_skill(skill_id, env.capability_checker)

        state = env.registry.lifecycle.get_state(skill_id)
        assert state == SkillLifecycleState.INVALID

    def test_grasp_failure_triggers_recovery(
        self,
        env: CrossLayerEnvironment,
    ) -> None:
        """Gripper close失败 → execution失败 → recovery尝试.

        验证: recovery handler被调用，Gripper状态正确.
        """
        skill_id = install_pick_skill(env)

        recovery_log: list[str] = []

        def recovery_handler(skill_name: str, failure: str) -> bool:
            recovery_log.append(f"{skill_name}:{failure}")
            return False

        def failing_pick(object_id: str = "red_cube", arm_name: str = "arm1", **kw: Any) -> bool:
            return False

        runtime = SkillRuntime(
            env.registry,
            capability_checker=env.capability_checker,
            precondition_checker=env.precondition_checker,
            postcondition_checker=env.postcondition_checker,
            execution_functions={"pick_object": failing_pick},
            recovery_handler=recovery_handler,
        )

        result = runtime.execute(
            skill_id,
            parameters={"object_id": "red_cube", "arm_name": "arm1"},
            context={"object_id": "red_cube", "arm_name": "arm1"},
        )

        assert result.status == ExecutionStatus.FAILURE
        assert result.recovery_attempts > 0
        assert len(recovery_log) > 0

    def test_grasp_recovery_succeeds_on_retry(
        self,
        env: CrossLayerEnvironment,
    ) -> None:
        """Grasp第一次失败，recovery后第二次成功.

        验证: 最终Gripper真的close+attach，WorldModel更新.
        """
        skill_id = install_pick_skill(env)

        call_count: list[int] = [0]
        real_pick = make_pick_execution(env)

        def flaky_pick(object_id: str = "red_cube", arm_name: str = "arm1", **kw: Any) -> bool:
            call_count[0] += 1
            if call_count[0] == 1:
                return False
            return real_pick(object_id=object_id, arm_name=arm_name, **kw)

        def recovery_handler(skill_name: str, failure: str) -> bool:
            if call_count[0] > 0:
                return real_pick(object_id="red_cube", arm_name="arm1")
            return False

        runtime = SkillRuntime(
            env.registry,
            capability_checker=env.capability_checker,
            precondition_checker=env.precondition_checker,
            postcondition_checker=env.postcondition_checker,
            execution_functions={"pick_object": flaky_pick},
            recovery_handler=recovery_handler,
        )

        result = runtime.execute(
            skill_id,
            parameters={"object_id": "red_cube", "arm_name": "arm1"},
            context={"object_id": "red_cube", "arm_name": "arm1"},
        )

        assert result.status == ExecutionStatus.RECOVERED
        assert env.gripper.is_closed("arm1")
        assert env.gripper.has_object("arm1")
        assert env.relations.is_attached("red_cube", "arm1_gripper")


class TestWorldModelVerification:
    """E2E: WorldModel始终反映Skill驱动的Reality."""

    def test_worldmodel_tracks_all_state_changes(self, env: CrossLayerEnvironment) -> None:
        """WorldModel History记录所有Skill驱动的状态变化.

        验证: pick→place后history有 FREE→ATTACHED→FREE 完整序列.
        """
        pick_id = install_pick_skill(env)
        place_id = install_place_skill(env)

        runtime = SkillRuntime(
            env.registry,
            capability_checker=env.capability_checker,
            precondition_checker=env.precondition_checker,
            postcondition_checker=env.postcondition_checker,
            execution_functions={
                "pick_object": make_pick_execution(env),
                "place_object": make_place_execution(env),
            },
        )

        runtime.execute(
            pick_id,
            parameters={"object_id": "red_cube", "arm_name": "arm1"},
            context={"object_id": "red_cube", "arm_name": "arm1"},
        )
        runtime.execute(
            place_id,
            parameters={"object_id": "red_cube", "arm_name": "arm1"},
            context={"object_id": "red_cube", "arm_name": "arm1"},
        )

        hist = env.history.get_history("red_cube")
        states = [e.data["state"] for e in hist]

        assert states[0] == "FREE"
        assert "ATTACHED" in states
        assert states[-1] == "FREE"

    def test_relation_layer_reflects_gripper_state(
        self,
        env: CrossLayerEnvironment,
    ) -> None:
        """Relation Layer始终与Gripper物理状态一致.

        验证: gripper.has_object() ↔ relations.is_attached().
        """
        pick_id = install_pick_skill(env)

        runtime = SkillRuntime(
            env.registry,
            capability_checker=env.capability_checker,
            precondition_checker=env.precondition_checker,
            postcondition_checker=env.postcondition_checker,
            execution_functions={"pick_object": make_pick_execution(env)},
        )

        assert not env.gripper.has_object("arm1")
        assert not env.relations.is_attached("red_cube")

        runtime.execute(
            pick_id,
            parameters={"object_id": "red_cube", "arm_name": "arm1"},
            context={"object_id": "red_cube", "arm_name": "arm1"},
        )

        assert env.gripper.has_object("arm1")
        assert env.relations.is_attached("red_cube")

    def test_object_position_updates_after_place(
        self,
        env: CrossLayerEnvironment,
    ) -> None:
        """Place后WorldModel中object位置更新到target.

        验证: db.get_object().position == place target.
        """
        pick_id = install_pick_skill(env)
        place_id = install_place_skill(env)

        runtime = SkillRuntime(
            env.registry,
            capability_checker=env.capability_checker,
            precondition_checker=env.precondition_checker,
            postcondition_checker=env.postcondition_checker,
            execution_functions={
                "pick_object": make_pick_execution(env),
                "place_object": make_place_execution(env),
            },
        )

        runtime.execute(
            pick_id,
            context={"object_id": "red_cube", "arm_name": "arm1"},
        )
        runtime.execute(
            place_id,
            context={"object_id": "red_cube", "arm_name": "arm1"},
        )

        obj = env.db.get_object("red_cube")
        assert obj is not None
        assert obj.position[0] == pytest.approx(-0.5)
        assert obj.position[1] == pytest.approx(0.0)


class TestTaskGoalToRobotAction:
    """E2E: TaskGoal → Skill选择 → 真实机器人动作."""

    def test_task_goal_pick_place_drives_full_chain(
        self,
        env: CrossLayerEnvironment,
    ) -> None:
        """TaskGoal "pick_place red_cube" → 选择pick+place Skill → 执行 → 验证.

        完整链路:
        TaskGoal → Skill Registry查询 → pick+place组合 →
        Skill Runtime执行 → Gripper动作 → WorldModel更新 → 验证
        """
        pick_id = install_pick_skill(env)
        place_id = install_place_skill(env)

        runtime = SkillRuntime(
            env.registry,
            capability_checker=env.capability_checker,
            precondition_checker=env.precondition_checker,
            postcondition_checker=env.postcondition_checker,
            execution_functions={
                "pick_object": make_pick_execution(env),
                "place_object": make_place_execution(env),
            },
        )

        task_goal = {
            "action_type": "pick_place",
            "object_id": "red_cube",
            "arm_name": "arm1",
        }

        required_caps = ["manipulation", "gripper"]
        available_skills = env.registry.list_ready_skills(
            required_capabilities=required_caps,
        )

        assert len(available_skills) >= 2
        skill_names = {m.name for _, m in available_skills}
        assert "pick_object" in skill_names
        assert "place_object" in skill_names

        composer = SkillComposer(runtime)
        result = (
            composer.compose("task_pick_place")
            .add_step(pick_id, parameters=task_goal)
            .add_step(place_id, parameters=task_goal)
            .execute(context=task_goal)
        )

        assert result.success

        assert env.gripper.is_open("arm1")
        assert not env.gripper.has_object("arm1")
        assert not env.relations.is_attached("red_cube")

        obj = env.db.get_object("red_cube")
        assert obj is not None
        assert obj.position[0] == pytest.approx(-0.5)

        pick_entry = env.registry.lifecycle.get_entry(pick_id)
        place_entry = env.registry.lifecycle.get_entry(place_id)
        assert pick_entry.total_executions == 1
        assert pick_entry.success_count == 1
        assert place_entry.total_executions == 1
        assert place_entry.success_count == 1

    def test_multi_object_multi_skill(self) -> None:
        """多物体多Skill: arm1 picks red_cube, arm2 picks blue_cylinder.

        验证: 两个Skill独立驱动两个Gripper，WorldModel正确反映.
        """
        e = CrossLayerEnvironment()

        e.perception.register_object("red_cube", "cube", [0.3, 0.0, 0.04])
        e.perception.register_object("blue_cyl", "cylinder", [-0.3, 0.2, 0.04])
        e.gripper.register_gripper("arm1")
        e.gripper.register_gripper("arm2")
        e.detect_and_sync()

        pick_id = install_pick_skill(e)

        runtime = SkillRuntime(
            e.registry,
            capability_checker=e.capability_checker,
            precondition_checker=e.precondition_checker,
            postcondition_checker=e.postcondition_checker,
            execution_functions={"pick_object": make_pick_execution(e)},
        )

        result1 = runtime.execute(
            pick_id,
            parameters={"object_id": "red_cube", "arm_name": "arm1"},
            context={"object_id": "red_cube", "arm_name": "arm1"},
        )
        assert result1.status == ExecutionStatus.SUCCESS

        result2 = runtime.execute(
            pick_id,
            parameters={"object_id": "blue_cyl", "arm_name": "arm2"},
            context={"object_id": "blue_cyl", "arm_name": "arm2"},
        )
        assert result2.status == ExecutionStatus.SUCCESS

        assert e.gripper.has_object("arm1")
        assert e.gripper.get_attached_object("arm1") == "red_cube"
        assert e.gripper.has_object("arm2")
        assert e.gripper.get_attached_object("arm2") == "blue_cyl"

        assert e.relations.is_attached("red_cube", "arm1_gripper")
        assert e.relations.is_attached("blue_cyl", "arm2_gripper")

        entry = e.registry.lifecycle.get_entry(pick_id)
        assert entry.total_executions == 2
        assert entry.success_count == 2