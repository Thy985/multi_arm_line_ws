"""M6.3 E2E: Skill Runtime Beta — lifecycle + recovery + state verification.

测试链路:
    TaskGoal → Skill Selection → Skill Execution → Recovery → Verification

测试重点: 不是动作，而是:
    - Skill生命周期 (Install→Register→Validate→Ready→Execute→Monitor→Update→Remove)
    - 失败恢复 (failure → recovery strategy → recovered/aborted)
    - 状态验证 (lifecycle state, execution stats, success rate)

示例场景:
    任务: Move red cube to blue area
    系统: Skill Registry → pick_object + move_object + place_object
    组合: pick → move → place
"""

from __future__ import annotations

import pytest

from multi_arm_skill_runtime.skill_manifest import SkillManifest, SkillCost
from multi_arm_skill_runtime.skill_registry import SkillRegistry
from multi_arm_skill_runtime.skill_runtime import (
    SkillRuntime,
    SkillResult,
    ExecutionStatus,
)
from multi_arm_skill_runtime.skill_composer import SkillComposer
from multi_arm_skill_runtime.skill_lifecycle import (
    SkillLifecycleState,
    SkillLifecycle,
)


@pytest.fixture
def skill_registry_with_skills() -> SkillRegistry:
    """Create registry with pick/move/place skills installed and ready."""
    registry = SkillRegistry()

    pick_manifest = SkillManifest(
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

    move_manifest = SkillManifest(
        name="move_object",
        version="1.0.0",
        description="Move grasped object to target",
        required_capabilities=["manipulation"],
        preconditions=["object attached_to gripper"],
        postconditions=["object at target_position"],
        execute_steps=["plan_trajectory", "execute_trajectory"],
        cost=SkillCost(time=3.0, risk=0.05, success_rate=0.98),
        recovery={"planning_failed": "relax_constraints → replan → abort"},
    )

    place_manifest = SkillManifest(
        name="place_object",
        version="1.0.0",
        description="Place object at location",
        required_capabilities=["manipulation", "gripper"],
        preconditions=["object attached_to gripper"],
        postconditions=["object on target_location", "NOT (object attached_to gripper)"],
        execute_steps=["move_to_place", "lower", "release", "retract"],
        cost=SkillCost(time=4.0, risk=0.08, success_rate=0.96),
        recovery={"place_failed": "retry(2) → adjust_position → abort"},
    )

    for manifest in [pick_manifest, move_manifest, place_manifest]:
        skill_id = registry.install_skill(manifest)
        registry.register_skill(skill_id)
        registry.validate_skill(skill_id)

    return registry


class TestSkillLifecycleE2E:
    """E2E: Skill生命周期完整流程测试."""

    def test_full_lifecycle_install_to_ready(
        self,
        skill_registry_with_skills: SkillRegistry,
    ) -> None:
        """完整生命周期: Install→Register→Validate→Ready.

        验证: 3个Skill全部到达READY状态.
        """
        registry = skill_registry_with_skills
        ready_skills = registry.list_ready_skills()

        assert len(ready_skills) == 3
        for skill_id, manifest in ready_skills:
            state = registry.lifecycle.get_state(skill_id)
            assert state == SkillLifecycleState.READY

    def test_lifecycle_execute_monitor_back_to_ready(
        self,
        skill_registry_with_skills: SkillRegistry,
    ) -> None:
        """执行后生命周期: Ready→Execute→Monitor→Ready.

        验证: 执行完成后Skill回到READY, 可再次执行.
        """
        registry = skill_registry_with_skills
        runtime = SkillRuntime(
            registry,
            execution_functions={"pick_object": lambda **kw: True},
        )

        skill_id = registry.find_by_name("pick_object")
        assert registry.lifecycle.get_state(skill_id) == SkillLifecycleState.READY

        result = runtime.execute(skill_id)
        assert result.status == ExecutionStatus.SUCCESS

        assert registry.lifecycle.get_state(skill_id) == SkillLifecycleState.READY

        result2 = runtime.execute(skill_id)
        assert result2.status == ExecutionStatus.SUCCESS

    def test_lifecycle_state_guards_execution(
        self,
        skill_registry_with_skills: SkillRegistry,
    ) -> None:
        """只有READY状态的Skill才能执行.

        验证: 非READY状态执行被拒绝.
        """
        registry = skill_registry_with_skills
        runtime = SkillRuntime(registry)

        manifest = SkillManifest(
            name="not_ready_skill",
            required_capabilities=[],
            execute_steps=["step"],
        )
        skill_id = registry.install_skill(manifest)

        assert registry.lifecycle.get_state(skill_id) == SkillLifecycleState.INSTALLED

        result = runtime.execute(skill_id)
        assert result.status == ExecutionStatus.FAILURE
        assert "not_ready" in result.failure_reason or "READY" in result.message

    def test_validation_rejects_missing_capability(self) -> None:
        """缺少required_capability的Skill验证失败.

        验证: INVALID状态, 有validation_errors.
        """
        registry = SkillRegistry()
        manifest = SkillManifest(
            name="needs_vision",
            required_capabilities=["vision", "nonexistent_sensor"],
            execute_steps=["step"],
        )

        skill_id = registry.install_skill(manifest)
        registry.register_skill(skill_id)

        def capability_checker(cap: str) -> bool:
            return cap in ["manipulation", "gripper", "vision"]

        result = registry.validate_skill(
            skill_id,
            capability_checker=capability_checker,
        )

        assert result is False
        assert registry.lifecycle.get_state(skill_id) == SkillLifecycleState.INVALID

        entry = registry.lifecycle.get_entry(skill_id)
        assert len(entry.validation_errors) > 0


class TestTaskGoalToSkillSelection:
    """E2E: TaskGoal → Skill Selection → 组合."""

    def test_task_goal_selects_correct_skills(
        self,
        skill_registry_with_skills: SkillRegistry,
    ) -> None:
        """TaskGoal "move red_cube to blue_area" → 选择pick+move+place.

        验证: Skill Registry返回正确的Skill组合.
        """
        registry = skill_registry_with_skills

        task_goal = {
            "action_type": "pick_place",
            "object_id": "red_cube",
            "target_location": "blue_area",
        }

        required_caps = ["manipulation", "gripper"]
        skills = registry.list_ready_skills(required_capabilities=required_caps)

        assert len(skills) >= 2

        skill_names = {m.name for _, m in skills}
        assert "pick_object" in skill_names
        assert "place_object" in skill_names

    def test_skill_selection_sorted_by_cost(
        self,
        skill_registry_with_skills: SkillRegistry,
    ) -> None:
        """Skill按cost排序 (time ascending).

        验证: move_object(3s) < place_object(4s) < pick_object(5s).
        """
        registry = skill_registry_with_skills
        ready = registry.list_ready_skills()

        costs = [m.cost.time for _, m in ready]
        assert costs == sorted(costs)
        assert ready[0][1].name == "move_object"
        assert ready[-1][1].name == "pick_object"

    def test_capability_filter_excludes_skills(
        self,
        skill_registry_with_skills: SkillRegistry,
    ) -> None:
        """需要vision的Skill只有pick_object.

        验证: 过滤后只剩1个Skill.
        """
        registry = skill_registry_with_skills
        skills = registry.list_ready_skills(required_capabilities=["vision"])

        assert len(skills) == 1
        assert skills[0][1].name == "pick_object"


class TestCompositeSkillExecution:
    """E2E: 组合Skill pick→move→place执行."""

    def test_pick_move_place_success(
        self,
        skill_registry_with_skills: SkillRegistry,
    ) -> None:
        """pick→move→place全部成功.

        验证: 3步全部完成, 每步lifecycle正确.
        """
        registry = skill_registry_with_skills
        runtime = SkillRuntime(
            registry,
            execution_functions={
                "pick_object": lambda **kw: True,
                "move_object": lambda **kw: True,
                "place_object": lambda **kw: True,
            },
        )
        composer = SkillComposer(runtime)

        pick_id = registry.find_by_name("pick_object")
        move_id = registry.find_by_name("move_object")
        place_id = registry.find_by_name("place_object")

        result = (
            composer.compose("transport_object")
            .add_step(pick_id)
            .add_step(move_id)
            .add_step(place_id)
            .execute()
        )

        assert result.success
        assert result.completed_steps == 3
        assert len(result.step_results) == 3

        for step_result in result.step_results:
            assert step_result.status == ExecutionStatus.SUCCESS

    def test_composition_builds_manifest(
        self,
        skill_registry_with_skills: SkillRegistry,
    ) -> None:
        """组合Skill生成composite manifest.

        验证: manifest包含所有步骤.
        """
        registry = skill_registry_with_skills
        runtime = SkillRuntime(registry)
        composer = SkillComposer(runtime)

        pick_id = registry.find_by_name("pick_object")
        place_id = registry.find_by_name("place_object")

        builder = (
            composer.compose("pick_and_place")
            .add_step(pick_id)
            .add_step(place_id)
            .require_capability("manipulation")
            .require_capability("gripper")
        )

        manifest = builder.build_manifest()
        assert manifest.name == "pick_and_place"
        assert len(manifest.execute_steps) == 2
        assert "manipulation" in manifest.required_capabilities
        assert "gripper" in manifest.required_capabilities

    def test_composition_with_optional_step(
        self,
        skill_registry_with_skills: SkillRegistry,
    ) -> None:
        """组合中optional步骤失败不中断链.

        验证: 失败的optional步骤被跳过, 链继续.
        """
        registry = skill_registry_with_skills
        runtime = SkillRuntime(
            registry,
            execution_functions={
                "pick_object": lambda **kw: True,
                "move_object": lambda **kw: False,
                "place_object": lambda **kw: True,
            },
        )
        composer = SkillComposer(runtime)

        pick_id = registry.find_by_name("pick_object")
        move_id = registry.find_by_name("move_object")
        place_id = registry.find_by_name("place_object")

        result = (
            composer.compose("transport")
            .add_step(pick_id)
            .add_step(move_id, optional=True)
            .add_step(place_id)
            .execute()
        )

        assert result.completed_steps == 2
        assert result.step_results[0].status == ExecutionStatus.FAILURE or \
            result.step_results[1].status == ExecutionStatus.FAILURE


class TestSkillFailureRecovery:
    """E2E: 失败恢复测试."""

    def test_execution_failure_triggers_recovery(
        self,
        skill_registry_with_skills: SkillRegistry,
    ) -> None:
        """Skill执行失败 → recovery handler调用 → 恢复成功.

        验证: status=RECOVERED, recovery_attempts>0.
        """
        registry = skill_registry_with_skills
        recovery_called: list[str] = []

        def recovery_handler(skill_name: str, failure: str) -> bool:
            recovery_called.append(skill_name)
            return True

        runtime = SkillRuntime(
            registry,
            execution_functions={"pick_object": lambda **kw: False},
            recovery_handler=recovery_handler,
        )

        skill_id = registry.find_by_name("pick_object")
        result = runtime.execute(skill_id)

        assert result.status == ExecutionStatus.RECOVERED
        assert result.recovery_attempts > 0
        assert len(recovery_called) > 0
        assert recovery_called[0] == "pick_object"

    def test_recovery_exhausted_aborts(
        self,
        skill_registry_with_skills: SkillRegistry,
    ) -> None:
        """所有recovery策略失败 → abort.

        验证: status=FAILURE, recovery_attempts>0.
        """
        registry = skill_registry_with_skills

        runtime = SkillRuntime(
            registry,
            execution_functions={"pick_object": lambda **kw: False},
            recovery_handler=lambda name, failure: False,
        )

        skill_id = registry.find_by_name("pick_object")
        result = runtime.execute(skill_id)

        assert result.status == ExecutionStatus.FAILURE
        assert result.recovery_attempts > 0
        assert result.failure_reason == "execution_failed"

    def test_precondition_failure_no_recovery(
        self,
        skill_registry_with_skills: SkillRegistry,
    ) -> None:
        """Precondition失败不触发recovery (recovery仅针对执行失败).

        验证: status=FAILURE, recovery_attempts=0.
        """
        registry = skill_registry_with_skills

        runtime = SkillRuntime(
            registry,
            execution_functions={"pick_object": lambda **kw: True},
            precondition_checker=lambda expr, ctx: False,
            recovery_handler=lambda name, failure: True,
        )

        skill_id = registry.find_by_name("pick_object")
        result = runtime.execute(skill_id)

        assert result.status == ExecutionStatus.FAILURE
        assert result.recovery_attempts == 0
        assert result.failure_reason == "precondition_failed"

    def test_postcondition_failure_triggers_recovery(
        self,
        skill_registry_with_skills: SkillRegistry,
    ) -> None:
        """Postcondition失败触发recovery.

        验证: recovery被调用.
        """
        registry = skill_registry_with_skills
        recovery_called: list[str] = []

        def recovery_handler(skill_name: str, failure: str) -> bool:
            recovery_called.append(skill_name)
            return True

        runtime = SkillRuntime(
            registry,
            execution_functions={"pick_object": lambda **kw: True},
            postcondition_checker=lambda expr, ctx: False,
            recovery_handler=recovery_handler,
        )

        skill_id = registry.find_by_name("pick_object")
        result = runtime.execute(skill_id)

        assert result.status == ExecutionStatus.RECOVERED
        assert len(recovery_called) > 0

    def test_composition_mid_chain_failure_recovery(
        self,
        skill_registry_with_skills: SkillRegistry,
    ) -> None:
        """组合Skill中间步骤失败 → 该步骤recovery → 链继续或停止.

        验证: 失败步骤有recovery记录.
        """
        registry = skill_registry_with_skills

        call_count: list[int] = [0]

        def move_func(**kwargs):
            call_count[0] += 1
            return False

        runtime = SkillRuntime(
            registry,
            execution_functions={
                "pick_object": lambda **kw: True,
                "move_object": move_func,
                "place_object": lambda **kw: True,
            },
            recovery_handler=lambda name, failure: False,
        )
        composer = SkillComposer(runtime)

        pick_id = registry.find_by_name("pick_object")
        move_id = registry.find_by_name("move_object")
        place_id = registry.find_by_name("place_object")

        result = (
            composer.compose("transport")
            .add_step(pick_id)
            .add_step(move_id)
            .add_step(place_id)
            .execute()
        )

        assert not result.success
        assert result.completed_steps == 1
        assert result.step_results[1].status == ExecutionStatus.FAILURE
        assert result.step_results[1].recovery_attempts > 0


class TestSkillStateVerification:
    """E2E: 状态验证测试."""

    def test_execution_stats_after_success(
        self,
        skill_registry_with_skills: SkillRegistry,
    ) -> None:
        """成功执行后验证execution stats.

        验证: total_executions=1, success_count=1, success_rate=1.0.
        """
        registry = skill_registry_with_skills
        runtime = SkillRuntime(
            registry,
            execution_functions={"pick_object": lambda **kw: True},
        )

        skill_id = registry.find_by_name("pick_object")
        runtime.execute(skill_id)

        entry = registry.lifecycle.get_entry(skill_id)
        assert entry.total_executions == 1
        assert entry.success_count == 1
        assert entry.success_rate == 1.0
        assert entry.last_executed > 0

    def test_execution_stats_after_failure(
        self,
        skill_registry_with_skills: SkillRegistry,
    ) -> None:
        """失败执行后验证execution stats.

        验证: total_executions=1, success_count=0, success_rate=0.0.
        """
        registry = skill_registry_with_skills
        runtime = SkillRuntime(
            registry,
            execution_functions={"pick_object": lambda **kw: False},
        )

        skill_id = registry.find_by_name("pick_object")
        runtime.execute(skill_id)

        entry = registry.lifecycle.get_entry(skill_id)
        assert entry.total_executions == 1
        assert entry.success_count == 0
        assert entry.success_rate == 0.0

    def test_execution_stats_mixed_results(
        self,
        skill_registry_with_skills: SkillRegistry,
    ) -> None:
        """多次执行(成功+失败)后验证混合stats.

        验证: total=5, success=3, rate=0.6.
        """
        registry = skill_registry_with_skills

        results_sequence = [True, True, False, True, False]
        call_idx: list[int] = [0]

        def exec_func(**kwargs):
            idx = call_idx[0]
            call_idx[0] += 1
            return results_sequence[idx] if idx < len(results_sequence) else True

        runtime = SkillRuntime(
            registry,
            execution_functions={"pick_object": exec_func},
        )

        skill_id = registry.find_by_name("pick_object")
        for _ in results_sequence:
            runtime.execute(skill_id)

        entry = registry.lifecycle.get_entry(skill_id)
        assert entry.total_executions == 5
        assert entry.success_count == 3
        assert entry.success_rate == pytest.approx(0.6)

    def test_lifecycle_state_after_each_phase(
        self,
        skill_registry_with_skills: SkillRegistry,
    ) -> None:
        """执行过程中验证lifecycle state变化.

        验证: Ready→(Execute内部: EXECUTING→MONITORING)→Ready.
        """
        registry = skill_registry_with_skills
        runtime = SkillRuntime(
            registry,
            execution_functions={"pick_object": lambda **kw: True},
        )

        skill_id = registry.find_by_name("pick_object")

        assert registry.lifecycle.get_state(skill_id) == SkillLifecycleState.READY

        result = runtime.execute(skill_id)
        assert result.status == ExecutionStatus.SUCCESS

        assert registry.lifecycle.get_state(skill_id) == SkillLifecycleState.READY

    def test_all_skills_ready_after_setup(
        self,
        skill_registry_with_skills: SkillRegistry,
    ) -> None:
        """所有Skill安装后全部READY.

        验证: 3个Skill全部READY.
        """
        registry = skill_registry_with_skills
        all_entries = registry.lifecycle.get_all_entries()

        assert len(all_entries) == 3
        for entry in all_entries.values():
            assert entry.state == SkillLifecycleState.READY


class TestHotUpdate:
    """E2E: 热更新测试."""

    def test_hot_update_changes_version(
        self,
        skill_registry_with_skills: SkillRegistry,
    ) -> None:
        """热更新改变版本号.

        验证: version从1.0.0变为2.0.0, state回到READY.
        """
        registry = skill_registry_with_skills
        skill_id = registry.find_by_name("pick_object")

        entry = registry.lifecycle.get_entry(skill_id)
        assert entry.version == "1.0.0"

        assert registry.lifecycle.start_update(skill_id)
        assert registry.lifecycle.get_state(skill_id) == SkillLifecycleState.UPDATING

        assert registry.lifecycle.finish_update(skill_id, "2.0.0")
        assert registry.lifecycle.get_state(skill_id) == SkillLifecycleState.READY

        entry = registry.lifecycle.get_entry(skill_id)
        assert entry.version == "2.0.0"

    def test_hot_update_preserves_execution_stats(
        self,
        skill_registry_with_skills: SkillRegistry,
    ) -> None:
        """热更新保留执行统计.

        验证: 更新后total_executions和success_count不变.
        """
        registry = skill_registry_with_skills
        runtime = SkillRuntime(
            registry,
            execution_functions={"pick_object": lambda **kw: True},
        )

        skill_id = registry.find_by_name("pick_object")
        runtime.execute(skill_id)
        runtime.execute(skill_id)

        entry_before = registry.lifecycle.get_entry(skill_id)
        assert entry_before.total_executions == 2

        registry.lifecycle.start_update(skill_id)
        registry.lifecycle.finish_update(skill_id, "2.0.0")

        entry_after = registry.lifecycle.get_entry(skill_id)
        assert entry_after.total_executions == 2
        assert entry_after.success_count == 2
        assert entry_after.version == "2.0.0"

    def test_skill_executable_after_update(
        self,
        skill_registry_with_skills: SkillRegistry,
    ) -> None:
        """更新后Skill仍可执行.

        验证: 更新后执行成功.
        """
        registry = skill_registry_with_skills
        runtime = SkillRuntime(
            registry,
            execution_functions={"pick_object": lambda **kw: True},
        )

        skill_id = registry.find_by_name("pick_object")

        registry.lifecycle.start_update(skill_id)
        registry.lifecycle.finish_update(skill_id, "2.0.0")

        result = runtime.execute(skill_id)
        assert result.status == ExecutionStatus.SUCCESS


class TestSkillRemoval:
    """E2E: Skill卸载测试."""

    def test_remove_skill(
        self,
        skill_registry_with_skills: SkillRegistry,
    ) -> None:
        """卸载Skill后不再可用.

        验证: find_by_name返回None.
        """
        registry = skill_registry_with_skills
        skill_id = registry.find_by_name("move_object")

        assert registry.remove_skill(skill_id)
        assert registry.find_by_name("move_object") is None

        ready = registry.list_ready_skills()
        assert len(ready) == 2

    def test_removed_skill_cannot_execute(
        self,
        skill_registry_with_skills: SkillRegistry,
    ) -> None:
        """已卸载的Skill不能执行.

        验证: execute返回FAILURE.
        """
        registry = skill_registry_with_skills
        runtime = SkillRuntime(registry)

        skill_id = registry.find_by_name("move_object")
        registry.remove_skill(skill_id)

        result = runtime.execute(skill_id)
        assert result.status == ExecutionStatus.FAILURE