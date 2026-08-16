"""M6 Full-Chain E2E: All M6 components working together with visualization.

This is the definitive proof that M6 is not just a collection of modules,
but a working robot operating system runtime.

Full chain:
    Perception → WorldModel(5 layers) → SkillRuntime → Manipulation → Experience
        ↓ detect      ↓ sync           ↓ execute      ↓ gripper     ↓ record
                      ↓ query          ↓ lifecycle    ↓ attach      ↓ episode
                      ↓ relation       ↓ recovery     ↓ detach      ↓ dataset
                      ↓ history
                      ↓ prediction

Unlike test_e2e_cross_layer.py which tests Skill→Robot,
this test proves the ENTIRE M6 stack works as one system:
    - Perception detects objects → WorldModel syncs
    - SkillRuntime executes pick/place via real execution functions
    - Manipulation (GripperController + GraspPlanner) performs physical actions
    - WorldModel 5 layers (State + Relation + History + Prediction) all update
    - ExperienceRecorder captures every step as structured Episode
    - DatasetExporter exports to SQLite + JSON
    - Visualizer renders ASCII state evolution

Visualization output shows:
    - Scene state table (objects, positions, states, relations)
    - Operation timeline (step sequence with durations)
    - State transition diagram (FREE → ATTACHED → FREE)
    - Episode summary (success/failure/recovery)
    - WorldModel before vs after comparison
"""

from __future__ import annotations

import io
import time
from typing import Any

import pytest

from multi_arm_perception.perception_node import ObjectDetector
from multi_arm_world_model.state_database import StateDatabase, TrackedObject
from multi_arm_world_model.relation_layer import RelationLayer
from multi_arm_world_model.history_layer import HistoryLayer
from multi_arm_world_model.prediction_layer import PredictionLayer
from multi_arm_manipulation.gripper_controller import GripperController
from multi_arm_manipulation.grasp_planner import GraspPlanner
from multi_arm_skill_runtime.skill_manifest import SkillManifest, SkillCost
from multi_arm_skill_runtime.skill_registry import SkillRegistry
from multi_arm_skill_runtime.skill_runtime import (
    SkillRuntime,
    ExecutionStatus,
    SkillResult,
)
from multi_arm_skill_runtime.skill_composer import SkillComposer
from multi_arm_experience.experience_recorder import ExperienceRecorder
from multi_arm_experience.episode import Episode, WorldStateSnapshot
from multi_arm_experience.dataset_exporter import DatasetExporter


# ============================================================================
# Visualization
# ============================================================================

class M6Visualizer:
    """ASCII visualizer for M6 full-chain state evolution.

    Renders system state at each phase of execution, producing
    a human-readable trace of what happened across all M6 layers.
    """

    def __init__(self) -> None:
        """Initialize visualizer with output buffer."""
        self._buffer = io.StringIO()
        self._phase = 0

    def _write(self, text: str) -> None:
        """Write text to buffer."""
        self._buffer.write(text + "\n")

    def header(self, title: str) -> None:
        """Render section header."""
        line = "=" * 70
        self._write("")
        self._write(line)
        self._write(f"  {title}")
        self._write(line)

    def phase(self, name: str) -> None:
        """Render phase marker."""
        self._phase += 1
        self._write("")
        self._write(f"  [Phase {self._phase}] {name}")
        self._write(f"  {'-' * 60}")

    def scene_table(self, env: M6FullChainEnvironment) -> None:
        """Render scene state as table.

        Args:
            env: Full-chain environment.

        """
        self._write("")
        self._write("  ┌────────────────┬────────────────────┬───────────┬──────────┐")
        self._write("  │ Object ID      │ Position (x,y,z)   │ State     │ Arm      │")
        self._write("  ├────────────────┼────────────────────┼───────────┼──────────┤")

        for obj in env.db.get_all_objects():
            pos = f"({obj.position[0]:.2f},{obj.position[1]:.2f},{obj.position[2]:.2f})"
            attached_to = ""
            for arm in env._arms:
                if env.gripper.get_attached_object(arm) == obj.object_id:
                    attached_to = arm
                    break
            state = "ATTACHED" if env.relations.is_attached(obj.object_id) else "FREE"
            self._write(
                f"  │ {obj.object_id:<14} │ {pos:<18} │ {state:<9} │ {attached_to:<8} │"
            )

        self._write("  └────────────────┴────────────────────┴───────────┴──────────┘")

    def gripper_states(self, env: M6FullChainEnvironment) -> None:
        """Render gripper states.

        Args:
            env: Full-chain environment.

        """
        self._write("")
        for arm in env._arms:
            state = "CLOSED" if env.gripper.is_closed(arm) else "OPEN"
            held = env.gripper.get_attached_object(arm) or "—"
            self._write(f"  Gripper[{arm}]: {state}, holding: {held}")

    def step_timeline(self, episode: Episode) -> None:
        """Render execution step timeline.

        Args:
            episode: Completed episode.

        """
        self._write("")
        self._write("  Step Timeline:")
        self._write("  ┌────┬──────────────────┬───────┬──────────┐")
        self._write("  │ #  │ Step             │ OK?   │ Duration │")
        self._write("  ├────┼──────────────────┼───────┼──────────┤")
        for i, step in enumerate(episode.execution_steps):
            ok = "✓" if step.success else "✗"
            self._write(
                f"  │ {i:<2} │ {step.step_name:<16} │   {ok}   │ {step.duration:.3f}s  │"
            )
        self._write("  └────┴──────────────────┴───────┴──────────┘")

    def state_transitions(self, episode: Episode, object_id: str) -> None:
        """Render state transition diagram for an object.

        Args:
            episode: Episode with history.
            object_id: Object to trace.

        """
        self._write("")
        self._write(f"  State Transitions [{object_id}]:")

        states = []
        for step in episode.execution_steps:
            state = step.details.get("object_state", "")
            if state:
                states.append(state)

        if not states:
            self._write("  (no state changes recorded)")
            return

        arrow = " → "
        chain = arrow.join(states)
        self._write(f"  {chain}")

    def episode_summary(self, episode: Episode) -> None:
        """Render episode summary.

        Args:
            episode: Completed episode.

        """
        self._write("")
        self._write(f"  Episode: {episode.episode_id}")
        self._write(f"    Task:   {episode.task_type}")
        self._write(f"    Skill:  {episode.skill_name}")
        self._write(f"    Robot:  {episode.robot_id}")
        self._write(f"    Result: {episode.result}")
        self._write(f"    Duration: {episode.duration:.3f}s")
        self._write(f"    Steps: {len(episode.execution_steps)}")
        self._write(f"    Recovery attempts: {episode.recovery_count}")

    def worldmodel_diff(
        self,
        before: WorldStateSnapshot,
        after: WorldStateSnapshot,
    ) -> None:
        """Render WorldModel before vs after comparison.

        Args:
            before: Initial world state.
            after: Final world state.

        """
        self._write("")
        self._write("  WorldModel Change:")
        self._write("    Before:")
        for oid, data in before.objects.items():
            self._write(f"      {oid}: pos={data.get('position', '?')}, state={data.get('state', '?')}")
        self._write("    After:")
        for oid, data in after.objects.items():
            self._write(f"      {oid}: pos={data.get('position', '?')}, state={data.get('state', '?')}")

    def footer(self, success: bool, total_duration: float) -> None:
        """Render footer with overall result.

        Args:
            success: Overall success.
            total_duration: Total execution time.

        """
        line = "=" * 70
        self._write("")
        self._write(line)
        status = "✓ ALL PASS" if success else "✗ FAILED"
        self._write(f"  Result: {status}  |  Total: {total_duration:.3f}s")
        self._write(line)

    def get_output(self) -> str:
        """Get full visualization text."""
        return self._buffer.getvalue()


# ============================================================================
# Full-Chain Environment
# ============================================================================

class M6FullChainEnvironment:
    """Complete M6 environment: all layers wired together.

    Layers:
        Perception: ObjectDetector
        WorldModel: StateDatabase + RelationLayer + HistoryLayer + PredictionLayer
        Manipulation: GripperController + GraspPlanner
        SkillRuntime: SkillRegistry + SkillRuntime
        Experience: ExperienceRecorder + DatasetExporter

    Unlike CrossLayerEnvironment, this includes:
        - PredictionLayer (WorldModel 5th layer)
        - ExperienceRecorder (automatic episode recording)
        - Visualizer (state evolution rendering)
    """

    def __init__(self) -> None:
        """Initialize all M6 layers."""
        self.perception = ObjectDetector(
            {"position_noise": 0.0, "confidence": 0.95}
        )
        self.db = StateDatabase()
        self.relations = RelationLayer()
        self.history = HistoryLayer(max_length=200)
        self.prediction = PredictionLayer(self.history)
        self.gripper = GripperController(
            {"max_opening_mm": 85, "max_force_n": 100.0}
        )
        self.planner = GraspPlanner()
        self.registry = SkillRegistry()
        self.recorder = ExperienceRecorder()
        self.visualizer = M6Visualizer()
        self._arms: list[str] = []

    def register_arm(self, arm_name: str) -> None:
        """Register a robot arm with gripper.

        Args:
            arm_name: Arm identifier.

        """
        self.gripper.register_gripper(arm_name)
        self._arms.append(arm_name)

    def register_object(
        self,
        object_id: str,
        object_type: str,
        position: list[float],
    ) -> None:
        """Register an object in perception.

        Args:
            object_id: Object identifier.
            object_type: Object type.
            position: [x, y, z] position.

        """
        self.perception.register_object(object_id, object_type, position)

    def detect_and_sync(self) -> int:
        """Perception detect → WorldModel sync all layers.

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
                {
                    "position": list(det.position),
                    "state": "FREE",
                    "source": "perception",
                },
            )
        return len(detections)

    def capture_world_snapshot(self) -> WorldStateSnapshot:
        """Capture current WorldModel state as snapshot.

        Returns:
            WorldStateSnapshot with all objects and relations.

        """
        objects = {}
        for obj in self.db.get_all_objects():
            state = "ATTACHED" if self.relations.is_attached(obj.object_id) else "FREE"
            objects[obj.object_id] = {
                "position": list(obj.position),
                "type": obj.object_type,
                "state": state,
            }

        relations = []
        for obj in self.db.get_all_objects():
            if self.relations.is_attached(obj.object_id):
                for arm in self._arms:
                    if self.relations.is_attached(obj.object_id, f"{arm}_gripper"):
                        relations.append({
                            "subject": obj.object_id,
                            "predicate": "attached_to",
                            "object": f"{arm}_gripper",
                        })

        return self.recorder.capture_world_snapshot(
            objects=objects,
            relations=relations,
        )

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


# ============================================================================
# Instrumented Execution Functions
# ============================================================================

def make_instrumented_pick(env: M6FullChainEnvironment, episode: Episode):
    """Create pick execution function with experience recording.

    This function drives:
        GraspPlanner → GripperController → RelationLayer → HistoryLayer
    AND records each step to ExperienceRecorder.

    Args:
        env: Full-chain environment.
        episode: Episode to record into.

    Returns:
        Execution callable.

    """

    def execute(
        object_id: str = "red_cube",
        arm_name: str = "left_arm",
        **kwargs: Any,
    ) -> bool:
        """Pick: plan → close → attach → update WorldModel → record.

        Args:
            object_id: Object to pick.
            arm_name: Arm to use.

        Returns:
            True if pick succeeded.

        """
        t0 = time.time()

        obj = env.db.get_object(object_id)
        if obj is None:
            env.recorder.record_step(
                episode, "query_object", success=False,
                duration=time.time() - t0,
                object_id=object_id, error="not_found",
            )
            return False

        env.recorder.record_step(
            episode, "query_object", success=True,
            duration=time.time() - t0,
            object_id=object_id, position=list(obj.position),
        )

        t1 = time.time()
        grasp_pose = env.planner.plan_grasp(
            list(obj.position),
            object_size=[0.05, 0.05, 0.05],
            approach="top",
        )
        env.recorder.record_step(
            episode, "plan_grasp", success=grasp_pose is not None,
            duration=time.time() - t1,
            approach="top",
            grasp_pos=list(grasp_pose.grasp_position) if grasp_pose else None,
        )
        if grasp_pose is None:
            return False

        t2 = time.time()
        success, _ = env.gripper.close(arm_name, force=30.0)
        env.recorder.record_step(
            episode, "gripper_close", success=success,
            duration=time.time() - t2,
            arm=arm_name, force=30.0,
        )
        if not success:
            return False

        t3 = time.time()
        success, _ = env.gripper.attach(arm_name, object_id)
        env.recorder.record_step(
            episode, "gripper_attach", success=success,
            duration=time.time() - t3,
            arm=arm_name, object_id=object_id,
        )
        if not success:
            return False

        t4 = time.time()
        env.relations.set_attached(object_id, f"{arm_name}_gripper")
        env.history.record(object_id, {
            "position": list(obj.position),
            "state": "ATTACHED",
            "action": "pick",
            "arm": arm_name,
        })
        env.recorder.record_step(
            episode, "worldmodel_update", success=True,
            duration=time.time() - t4,
            object_id=object_id, object_state="ATTACHED",
            relation="attached_to",
        )

        return True

    return execute


def make_instrumented_place(env: M6FullChainEnvironment, episode: Episode):
    """Create place execution function with experience recording.

    Args:
        env: Full-chain environment.
        episode: Episode to record into.

    Returns:
        Execution callable.

    """

    def execute(
        object_id: str = "red_cube",
        arm_name: str = "left_arm",
        target_position: list | None = None,
        **kwargs: Any,
    ) -> bool:
        """Place: detach → update pose → detach relation → open → record.

        Args:
            object_id: Object to place.
            arm_name: Arm to use.
            target_position: Target [x, y, z].

        Returns:
            True if place succeeded.

        """
        target = target_position or [-0.5, 0.0, 0.04]

        t0 = time.time()
        success, _ = env.gripper.detach(arm_name)
        env.recorder.record_step(
            episode, "gripper_detach", success=success,
            duration=time.time() - t0,
            arm=arm_name,
        )
        if not success:
            return False

        t1 = time.time()
        env.db.update_object_pose(object_id, tuple(target))
        env.relations.set_detached(object_id, f"{arm_name}_gripper")
        env.history.record(object_id, {
            "position": target,
            "state": "FREE",
            "action": "place",
            "arm": arm_name,
        })
        env.recorder.record_step(
            episode, "worldmodel_update", success=True,
            duration=time.time() - t1,
            object_id=object_id, object_state="FREE",
            new_position=target,
        )

        t2 = time.time()
        success, _ = env.gripper.open(arm_name)
        env.recorder.record_step(
            episode, "gripper_open", success=success,
            duration=time.time() - t2,
            arm=arm_name,
        )

        return success

    return execute


# ============================================================================
# Skill Installation
# ============================================================================

def install_pick_skill(env: M6FullChainEnvironment) -> str:
    """Install pick_object skill.

    Args:
        env: Full-chain environment.

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
        execute_steps=["query_object", "plan_grasp", "gripper_close", "gripper_attach", "worldmodel_update"],
        cost=SkillCost(time=5.0, risk=0.1, success_rate=0.95),
        recovery={"grasp_failed": "retry(3) → change_approach → abort"},
    )
    skill_id = env.registry.install_skill(manifest)
    env.registry.register_skill(skill_id)
    env.registry.validate_skill(skill_id, env.capability_checker)
    return skill_id


def install_place_skill(env: M6FullChainEnvironment) -> str:
    """Install place_object skill.

    Args:
        env: Full-chain environment.

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
        execute_steps=["gripper_detach", "worldmodel_update", "gripper_open"],
        cost=SkillCost(time=4.0, risk=0.08, success_rate=0.96),
        recovery={"place_failed": "retry(2) → adjust → abort"},
    )
    skill_id = env.registry.install_skill(manifest)
    env.registry.register_skill(skill_id)
    env.registry.validate_skill(skill_id, env.capability_checker)
    return skill_id


# ============================================================================
# Full-Chain Pick-Place Runner
# ============================================================================

def run_full_chain_pick_place(
    env: M6FullChainEnvironment,
    object_id: str,
    arm_name: str,
    place_position: list[float],
    task_label: str = "pick_place",
) -> tuple[Episode, bool]:
    """Execute a complete pick-place through the full M6 chain.

    This is the core function that proves all M6 components work together:
        1. Capture initial world snapshot
        2. Start experience episode
        3. Install + execute pick skill (with instrumentation)
        4. Install + execute place skill (with instrumentation)
        5. Capture final world snapshot
        6. Finish episode
        7. Visualize all phases

    Args:
        env: Full-chain environment.
        object_id: Object to manipulate.
        arm_name: Arm to use.
        place_position: Target placement position.
        task_label: Label for the task.

    Returns:
        Tuple of (episode, success).

    """
    viz = env.visualizer
    viz.header(f"M6 Full-Chain: {task_label} ({object_id} via {arm_name})")

    viz.phase("Initial State")
    viz.scene_table(env)
    viz.gripper_states(env)

    viz.phase("Capture Initial World Snapshot")
    initial_world = env.capture_world_snapshot()
    viz._write(f"  Objects: {len(initial_world.objects)}")
    viz._write(f"  Relations: {len(initial_world.relations)}")

    viz.phase("Start Experience Episode")
    episode = env.recorder.start_episode(
        task_type=task_label,
        skill_name="pick_and_place",
        robot_id=arm_name,
        initial_world=initial_world,
    )
    viz._write(f"  Episode ID: {episode.episode_id}")

    pick_id = install_pick_skill(env)
    place_id = install_place_skill(env)

    pick_exec = make_instrumented_pick(env, episode)
    place_exec = make_instrumented_place(env, episode)

    runtime = SkillRuntime(
        env.registry,
        capability_checker=env.capability_checker,
        precondition_checker=env.precondition_checker,
        postcondition_checker=env.postcondition_checker,
        execution_functions={
            "pick_object": pick_exec,
            "place_object": place_exec,
        },
    )

    overall_success = True

    viz.phase("Execute Pick Skill")
    t_pick_start = time.time()
    pick_result = runtime.execute(
        pick_id,
        parameters={"object_id": object_id, "arm_name": arm_name},
        context={"object_id": object_id, "arm_name": arm_name},
    )
    pick_duration = time.time() - t_pick_start

    if pick_result.status == ExecutionStatus.SUCCESS:
        viz._write(f"  ✓ Pick succeeded ({pick_duration:.3f}s)")
        viz.scene_table(env)
        viz.gripper_states(env)
    else:
        viz._write(f"  ✗ Pick failed: {pick_result.failure_reason}")
        overall_success = False

    if overall_success:
        viz.phase("Execute Place Skill")
        t_place_start = time.time()
        place_result = runtime.execute(
            place_id,
            parameters={
                "object_id": object_id,
                "arm_name": arm_name,
                "target_position": place_position,
            },
            context={"object_id": object_id, "arm_name": arm_name},
        )
        place_duration = time.time() - t_place_start

        if place_result.status == ExecutionStatus.SUCCESS:
            viz._write(f"  ✓ Place succeeded ({place_duration:.3f}s)")
            viz.scene_table(env)
            viz.gripper_states(env)
        else:
            viz._write(f"  ✗ Place failed: {place_result.failure_reason}")
            overall_success = False

    viz.phase("Capture Final World Snapshot")
    final_world = env.capture_world_snapshot()
    viz.worldmodel_diff(initial_world, final_world)

    viz.phase("Finish Episode")
    total_duration = pick_duration + (place_duration if overall_success else 0.0)
    env.recorder.finish_episode(
        episode,
        result="success" if overall_success else "failure",
        duration=total_duration,
        final_world=final_world,
    )
    viz.step_timeline(episode)
    viz.state_transitions(episode, object_id)
    viz.episode_summary(episode)

    viz.footer(overall_success, total_duration)

    return episode, overall_success


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def full_env() -> M6FullChainEnvironment:
    """Create full-chain environment with one object and one arm."""
    env = M6FullChainEnvironment()
    env.register_arm("left_arm")
    env.register_object("red_cube", "cube", [0.5, 0.0, 0.04])
    env.detect_and_sync()
    return env


@pytest.fixture
def dual_arm_env() -> M6FullChainEnvironment:
    """Create full-chain environment with two arms and two objects."""
    env = M6FullChainEnvironment()
    env.register_arm("left_arm")
    env.register_arm("right_arm")
    env.register_object("red_cube", "cube", [0.5, 0.0, 0.04])
    env.register_object("blue_cyl", "cylinder", [-0.5, 0.2, 0.04])
    env.detect_and_sync()
    return env


# ============================================================================
# Tests: Full-Chain Single Object
# ============================================================================

class TestFullChainSingleObject:
    """E2E: Single object pick-place through entire M6 stack."""

    def test_pick_place_full_chain(self, full_env: M6FullChainEnvironment) -> None:
        """Complete pick-place: Perception→WorldModel→Skill→Manipulation→Experience.

        Verifies:
            - Skill execution drives real GripperController
            - WorldModel Relation Layer updates (attached→detached)
            - History Layer records state evolution
            - ExperienceRecorder captures complete episode
            - Object position changes in StateDatabase
        """
        episode, success = run_full_chain_pick_place(
            full_env,
            object_id="red_cube",
            arm_name="left_arm",
            place_position=[-0.5, 0.0, 0.04],
        )

        assert success
        assert episode.result == "success"
        assert len(episode.execution_steps) >= 7

        assert full_env.gripper.is_open("left_arm")
        assert not full_env.gripper.has_object("left_arm")

        assert not full_env.relations.is_attached("red_cube")

        obj = full_env.db.get_object("red_cube")
        assert obj is not None
        assert list(obj.position) == pytest.approx([-0.5, 0.0, 0.04])

        hist = full_env.history.get_history("red_cube")
        states = [e.data.get("state", "") for e in hist if "state" in e.data]
        assert "FREE" in states
        assert "ATTACHED" in states
        assert states[-1] == "FREE"

    def test_episode_has_structured_steps(
        self,
        full_env: M6FullChainEnvironment,
    ) -> None:
        """Episode execution steps are structured with names and durations."""
        episode, _ = run_full_chain_pick_place(
            full_env,
            object_id="red_cube",
            arm_name="left_arm",
            place_position=[-0.3, 0.1, 0.04],
        )

        step_names = [s.step_name for s in episode.execution_steps]

        assert "query_object" in step_names
        assert "plan_grasp" in step_names
        assert "gripper_close" in step_names
        assert "gripper_attach" in step_names
        assert "worldmodel_update" in step_names
        assert "gripper_detach" in step_names
        assert "gripper_open" in step_names

        for step in episode.execution_steps:
            assert step.duration >= 0.0

    def test_worldmodel_state_consistency(
        self,
        full_env: M6FullChainEnvironment,
    ) -> None:
        """Gripper state ↔ Relation state ↔ History state are consistent."""
        episode, success = run_full_chain_pick_place(
            full_env,
            object_id="red_cube",
            arm_name="left_arm",
            place_position=[0.3, -0.2, 0.04],
        )

        assert success

        gripper_holds = full_env.gripper.has_object("left_arm")
        relation_attached = full_env.relations.is_attached("red_cube")

        assert gripper_holds == relation_attached
        assert not gripper_holds
        assert not relation_attached

        hist = full_env.history.get_history("red_cube")
        last_state = hist[-1].data.get("state", "")
        assert last_state == "FREE"
        assert not relation_attached

    def test_visualization_produced(
        self,
        full_env: M6FullChainEnvironment,
    ) -> None:
        """Visualization output is non-empty and contains key sections."""
        run_full_chain_pick_place(
            full_env,
            object_id="red_cube",
            arm_name="left_arm",
            place_position=[-0.4, 0.0, 0.04],
        )

        output = full_env.visualizer.get_output()

        assert len(output) > 0
        assert "Phase" in output
        assert "Episode" in output
        assert "Step Timeline" in output
        assert "State Transitions" in output
        assert "WorldModel Change" in output
        assert "ALL PASS" in output


# ============================================================================
# Tests: Full-Chain Dual Arm
# ============================================================================

class TestFullChainDualArm:
    """E2E: Dual arm parallel pick-place through entire M6 stack."""

    def test_dual_arm_parallel_pick_place(
        self,
        dual_arm_env: M6FullChainEnvironment,
    ) -> None:
        """Two arms pick-place two objects independently.

        Verifies:
            - left_arm picks red_cube, right_arm picks blue_cyl
            - Both grippers hold different objects simultaneously
            - Both place at different target positions
            - WorldModel tracks both objects correctly
            - Two episodes recorded
        """
        ep1, success1 = run_full_chain_pick_place(
            dual_arm_env,
            object_id="red_cube",
            arm_name="left_arm",
            place_position=[0.3, 0.3, 0.04],
            task_label="pick_place_left_arm",
        )

        assert success1
        assert dual_arm_env.gripper.is_open("left_arm")
        assert not dual_arm_env.relations.is_attached("red_cube")

        ep2, success2 = run_full_chain_pick_place(
            dual_arm_env,
            object_id="blue_cyl",
            arm_name="right_arm",
            place_position=[-0.3, -0.3, 0.04],
            task_label="pick_place_right_arm",
        )

        assert success2
        assert dual_arm_env.gripper.is_open("right_arm")
        assert not dual_arm_env.relations.is_attached("blue_cyl")

        cube = dual_arm_env.db.get_object("red_cube")
        cyl = dual_arm_env.db.get_object("blue_cyl")
        assert list(cube.position) == pytest.approx([0.3, 0.3, 0.04])
        assert list(cyl.position) == pytest.approx([-0.3, -0.3, 0.04])

        assert ep1.episode_id != ep2.episode_id
        assert dual_arm_env.recorder.episode_count == 2

    def test_dual_arm_simultaneous_grasp(
        self,
        dual_arm_env: M6FullChainEnvironment,
    ) -> None:
        """Both arms hold objects simultaneously (interleaved pick)."""
        env = dual_arm_env

        episode = env.recorder.start_episode(
            task_type="dual_grasp",
            skill_name="dual_pick",
            robot_id="dual_ur5e",
            initial_world=env.capture_world_snapshot(),
        )

        pick_id = install_pick_skill(env)
        pick_exec = make_instrumented_pick(env, episode)

        runtime = SkillRuntime(
            env.registry,
            capability_checker=env.capability_checker,
            precondition_checker=env.precondition_checker,
            postcondition_checker=env.postcondition_checker,
            execution_functions={"pick_object": pick_exec},
        )

        r1 = runtime.execute(
            pick_id,
            parameters={"object_id": "red_cube", "arm_name": "left_arm"},
            context={"object_id": "red_cube", "arm_name": "left_arm"},
        )
        assert r1.status == ExecutionStatus.SUCCESS

        r2 = runtime.execute(
            pick_id,
            parameters={"object_id": "blue_cyl", "arm_name": "right_arm"},
            context={"object_id": "blue_cyl", "arm_name": "right_arm"},
        )
        assert r2.status == ExecutionStatus.SUCCESS

        assert env.gripper.has_object("left_arm")
        assert env.gripper.get_attached_object("left_arm") == "red_cube"
        assert env.gripper.has_object("right_arm")
        assert env.gripper.get_attached_object("right_arm") == "blue_cyl"

        assert env.relations.is_attached("red_cube", "left_arm_gripper")
        assert env.relations.is_attached("blue_cyl", "right_arm_gripper")

        env.recorder.finish_episode(
            episode, result="success", duration=1.0,
            final_world=env.capture_world_snapshot(),
        )

        assert episode.result == "success"


# ============================================================================
# Tests: Full-Chain Failure + Recovery
# ============================================================================

class TestFullChainFailureRecovery:
    """E2E: Failure scenarios with experience recording."""

    def test_nonexistent_object_pick_fails(
        self,
        full_env: M6FullChainEnvironment,
    ) -> None:
        """Pick nonexistent object → precondition fails → no gripper action."""
        env = full_env

        episode = env.recorder.start_episode(
            task_type="pick_nonexistent",
            skill_name="pick_object",
            robot_id="left_arm",
            initial_world=env.capture_world_snapshot(),
        )

        pick_id = install_pick_skill(env)
        pick_exec = make_instrumented_pick(env, episode)

        runtime = SkillRuntime(
            env.registry,
            capability_checker=env.capability_checker,
            precondition_checker=env.precondition_checker,
            postcondition_checker=env.postcondition_checker,
            execution_functions={"pick_object": pick_exec},
        )

        result = runtime.execute(
            pick_id,
            parameters={"object_id": "ghost", "arm_name": "left_arm"},
            context={"object_id": "ghost", "arm_name": "left_arm"},
        )

        assert result.status == ExecutionStatus.FAILURE

        assert env.gripper.is_open("left_arm")
        assert not env.gripper.has_object("left_arm")

        env.recorder.finish_episode(
            episode, result="failure", duration=0.001,

            final_world=env.capture_world_snapshot(),
        )

        assert episode.result == "failure"
        assert env.recorder.failure_count >= 1

    def test_grasp_failure_records_recovery(
        self,
        full_env: M6FullChainEnvironment,
    ) -> None:
        """Grasp failure → recovery attempt recorded in episode."""
        env = full_env

        episode = env.recorder.start_episode(
            task_type="pick_with_failure",
            skill_name="pick_object",
            robot_id="left_arm",
            initial_world=env.capture_world_snapshot(),
        )

        env.recorder.record_step(
            episode, "query_object", success=True, duration=0.001,
        )
        env.recorder.record_step(
            episode, "plan_grasp", success=False, duration=0.001,
            error="unreachable",
        )

        env.recorder.record_recovery(
            episode,
            failure_type="planning_failure",
            strategy="relax_constraints",
            success=True,
        )

        env.recorder.record_step(
            episode, "plan_grasp_retry", success=True, duration=0.002,
        )
        env.recorder.record_step(
            episode, "gripper_close", success=True, duration=0.001,
        )
        env.recorder.record_step(
            episode, "gripper_attach", success=True, duration=0.001,
        )

        env.recorder.finish_episode(
            episode, result="recovered", duration=0.006,
            final_world=env.capture_world_snapshot(),
        )

        assert episode.result == "recovered"
        assert episode.recovery_count == 1
        assert episode.success
        assert len(episode.execution_steps) == 5

        failures = env.recorder.get_failure_memory()
        assert len(failures) >= 1
        assert failures[-1]["recovery_succeeded"] is True


# ============================================================================
# Tests: Experience Dataset Export
# ============================================================================

class TestExperienceDatasetExport:
    """E2E: Experience recording → Dataset export."""

    def test_dataset_export_after_pick_place(
        self,
        full_env: M6FullChainEnvironment,
        tmp_path,
    ) -> None:
        """After pick-place, dataset exports to SQLite + JSON correctly."""
        episode, success = run_full_chain_pick_place(
            full_env,
            object_id="red_cube",
            arm_name="left_arm",
            place_position=[-0.5, 0.0, 0.04],
        )
        assert success

        db_path = tmp_path / "test_experience.db"
        json_dir = tmp_path / "json_output"

        exporter = DatasetExporter(db_path=str(db_path), json_dir=str(json_dir))
        count = exporter.export_recorder(full_env.recorder)

        assert count == 1
        assert db_path.exists()

        json_path = json_dir / "experience_dataset.json"
        assert json_path.exists()

        episodes = exporter.query(table="episodes")
        assert len(episodes) == 1
        assert episodes[0]["episode_id"] == episode.episode_id
        assert episodes[0]["result"] == "success"

        traces = exporter.query(table="skill_traces")
        assert len(traces) == len(episode.execution_steps)

        assert exporter.get_episode_count() == 1
        assert exporter.get_failure_count() == 0

    def test_multiple_episodes_dataset(
        self,
        dual_arm_env: M6FullChainEnvironment,
        tmp_path,
    ) -> None:
        """Multiple episodes (dual arm) export correctly."""
        run_full_chain_pick_place(
            dual_arm_env,
            object_id="red_cube",
            arm_name="left_arm",
            place_position=[0.3, 0.3, 0.04],
            task_label="task_a",
        )
        run_full_chain_pick_place(
            dual_arm_env,
            object_id="blue_cyl",
            arm_name="right_arm",
            place_position=[-0.3, -0.3, 0.04],
            task_label="task_b",
        )

        db_path = tmp_path / "multi.db"
        exporter = DatasetExporter(db_path=str(db_path))
        count = exporter.export_recorder(dual_arm_env.recorder)

        assert count == 2
        assert exporter.get_episode_count() == 2

        episodes = exporter.query(table="episodes")
        task_types = {ep["task_type"] for ep in episodes}
        assert "task_a" in task_types
        assert "task_b" in task_types


# ============================================================================
# Tests: Prediction Layer Integration
# ============================================================================

class TestPredictionLayerIntegration:
    """E2E: Prediction Layer uses History to forecast."""

    def test_prediction_after_pick_place(
        self,
        full_env: M6FullChainEnvironment,
    ) -> None:
        """After pick-place, PredictionLayer can predict from history."""
        episode, success = run_full_chain_pick_place(
            full_env,
            object_id="red_cube",
            arm_name="left_arm",
            place_position=[-0.5, 0.0, 0.04],
        )
        assert success

        hist = full_env.history.get_history("red_cube")
        assert len(hist) >= 3

        prediction = full_env.prediction
        pred = prediction.predict_position("red_cube", dt=0.1)
        assert pred.entity_id == "red_cube"
        assert len(pred.predicted_position) == 3


# ============================================================================
# Tests: Composite Skill Full Chain
# ============================================================================

class TestCompositeSkillFullChain:
    """E2E: Composite skill (pick→place) through full chain."""

    def test_composite_pick_place(
        self,
        full_env: M6FullChainEnvironment,
    ) -> None:
        """SkillComposer chains pick→place, all layers update."""
        env = full_env

        episode = env.recorder.start_episode(
            task_type="composite_pick_place",
            skill_name="pick_and_place",
            robot_id="left_arm",
            initial_world=env.capture_world_snapshot(),
        )

        pick_id = install_pick_skill(env)
        place_id = install_place_skill(env)

        pick_exec = make_instrumented_pick(env, episode)
        place_exec = make_instrumented_place(env, episode)

        runtime = SkillRuntime(
            env.registry,
            capability_checker=env.capability_checker,
            precondition_checker=env.precondition_checker,
            postcondition_checker=env.postcondition_checker,
            execution_functions={
                "pick_object": pick_exec,
                "place_object": place_exec,
            },
        )

        composer = SkillComposer(runtime)

        result = (
            composer.compose("pick_and_place")
            .add_step(
                pick_id,
                parameters={"object_id": "red_cube", "arm_name": "left_arm"},
            )
            .add_step(
                place_id,
                parameters={
                    "object_id": "red_cube",
                    "arm_name": "left_arm",
                    "target_position": [-0.4, 0.1, 0.04],
                },
            )
            .execute(context={"object_id": "red_cube", "arm_name": "left_arm"})
        )

        env.recorder.finish_episode(
            episode,
            result="success" if result.success else "failure",
            duration=result.total_duration,
            final_world=env.capture_world_snapshot(),
        )

        assert result.success
        assert result.completed_steps == 2

        assert env.gripper.is_open("left_arm")
        assert not env.relations.is_attached("red_cube")

        obj = env.db.get_object("red_cube")
        assert list(obj.position) == pytest.approx([-0.4, 0.1, 0.04])

        assert episode.result == "success"
        assert len(episode.execution_steps) >= 7