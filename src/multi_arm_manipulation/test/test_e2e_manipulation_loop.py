"""M6.2 E2E: Perception-driven manipulation closed-loop test.

验证: Reality → WorldModel → Action → Reality Update 闭环是否成立.

完整链路:
    Gazebo → Camera → Perception → WorldModel → TaskGoal
        → Skill Runtime → Manipulation → Gripper → Object State Update
        → WorldModel反馈

验收标准: 不是看机械臂有没有动，而是看闭环是否成立.
"""

from __future__ import annotations

import pytest

from multi_arm_perception.perception_node import ObjectDetector
from multi_arm_world_model.state_database import StateDatabase, TrackedObject
from multi_arm_world_model.relation_layer import RelationLayer
from multi_arm_world_model.history_layer import HistoryLayer
from multi_arm_world_model.prediction_layer import PredictionLayer
from multi_arm_manipulation.gripper_controller import GripperController, GripperState
from multi_arm_manipulation.grasp_planner import GraspPlanner, GraspPose


@pytest.fixture
def e2e_setup():
    """Setup all layers for E2E closed-loop test.

    Returns:
        Dict with all layer instances.

    """
    return {
        "perception": ObjectDetector({"position_noise": 0.0, "confidence": 0.95}),
        "world_model": StateDatabase(),
        "relations": RelationLayer(),
        "history": HistoryLayer(max_length=100),
        "prediction": None,
        "gripper": GripperController({"max_opening_mm": 85, "max_force_n": 100.0}),
        "grasp_planner": GraspPlanner(),
    }


def sync_perception_to_db(
    detections: list,
    db: StateDatabase,
    history: HistoryLayer | None = None,
) -> None:
    """Sync perception detections into WorldModel StateDatabase.

    Objects must be added before update_object_pose can work.

    Args:
        detections: List of DetectedObject from perception.
        db: StateDatabase instance.
        history: Optional HistoryLayer for recording.

    """
    for det in detections:
        existing = db.get_object(det.object_id)
        if existing is None:
            db.add_object(TrackedObject(
                object_id=det.object_id,
                object_type=det.object_type,
                position=tuple(det.position),
                orientation=tuple(det.orientation),
                confidence=det.confidence,
            ))
        else:
            db.update_object_pose(
                det.object_id,
                tuple(det.position),
                tuple(det.orientation),
                det.confidence,
            )
        if history:
            history.record(
                det.object_id,
                {"position": list(det.position), "state": "FREE", "confidence": det.confidence},
            )


class TestPerceptionDrivenManipulationLoop:
    """E2E: 感知驱动的操作闭环测试."""

    def test_full_pick_place_closed_loop(self, e2e_setup: dict) -> None:
        """完整Pick-Place闭环: Perception→WorldModel→Manipulation→反馈.

        验证链路:
        1. Perception检测物体 → WorldModel更新State
        2. WorldModel查询 → 确认object存在, state=FREE
        3. GraspPlanner生成抓取姿态
        4. Gripper close → attach → WorldModel更新Relation
        5. 验证: WorldModel反映ATTACHED状态
        6. Lift → 移动到新位置
        7. Detach → open → WorldModel更新Relation
        8. 验证: WorldModel反映FREE状态, 新位置
        """
        perception = e2e_setup["perception"]
        db = e2e_setup["world_model"]
        relations = e2e_setup["relations"]
        history = e2e_setup["history"]
        gripper = e2e_setup["gripper"]
        planner = e2e_setup["grasp_planner"]

        # === Phase 1: Gazebo场景设置 ===
        perception.register_object("red_cube", "cube", [0.5, 0.0, 0.04])
        gripper.register_gripper("left_arm")

        # === Phase 2: Perception → WorldModel ===
        detections = perception.detect()
        assert len(detections) == 1
        assert detections[0].object_id == "red_cube"

        sync_perception_to_db(detections, db, history)

        # === Phase 3: 验证WorldModel反映Reality ===
        obj = db.get_object("red_cube")
        assert obj is not None
        assert obj.object_id == "red_cube"
        assert obj.object_type == "cube"
        assert obj.confidence == pytest.approx(0.95)

        # 计算spatial relations
        objects = {o.object_id: {"position": list(o.position)} for o in db.get_all_objects()}
        surfaces = {"table": {"position": [0.5, 0.0, 0.0]}}
        relations.compute_spatial_relations(objects, surfaces)

        # 验证: red_cube on table, NOT attached
        assert relations.has_relation("red_cube", "on", "table")
        assert not relations.is_attached("red_cube")

        # === Phase 4: Skill Runtime → pick_object ===
        # 4a. GraspPlanner生成抓取姿态
        grasp_pose = planner.plan_grasp(
            list(obj.position), object_size=[0.05, 0.05, 0.05], approach="top"
        )
        assert grasp_pose.approach == "top"
        assert grasp_pose.approach_position[2] > grasp_pose.grasp_position[2]

        # 4b. Gripper close
        success, msg = gripper.close("left_arm", force=30.0)
        assert success, f"Gripper close failed: {msg}"
        assert gripper.is_closed("left_arm")

        # 4c. Attach (Gazebo物理附着)
        success, msg = gripper.attach("left_arm", "red_cube")
        assert success, f"Attach failed: {msg}"

        # 4d. WorldModel更新: Relation Layer反馈
        relations.set_attached("red_cube", "left_arm_gripper")
        history.record("red_cube", {"position": list(obj.position), "state": "ATTACHED"})

        # === Phase 5: 验证闭环 — WorldModel反映ATTACHED ===
        # Reality: gripper holds red_cube
        assert gripper.has_object("left_arm")
        assert gripper.get_attached_object("left_arm") == "red_cube"

        # WorldModel: relation reflects reality
        assert relations.is_attached("red_cube")
        assert relations.is_attached("red_cube", "left_arm_gripper")
        assert relations.has_relation("red_cube", "attached_to", "left_arm_gripper")

        # === Phase 6: Lift — 物体位置变化 ===
        lifted_position = [0.5, 0.0, 0.5]
        db.update_object_pose("red_cube", tuple(lifted_position))
        history.record("red_cube", {"position": lifted_position, "state": "ATTACHED"})

        # Prediction: 预测未来位置
        prediction = PredictionLayer(history)
        pred = prediction.predict_position("red_cube", dt=0.1)
        assert pred.entity_id == "red_cube"

        # === Phase 7: Place — 移动到放置位 ===
        place_position = [-0.5, 0.0, 0.04]

        # 7a. Detach
        success, msg = gripper.detach("left_arm")
        assert success, f"Detach failed: {msg}"

        # 7b. WorldModel更新: 物体在新位置, state=FREE
        db.update_object_pose("red_cube", tuple(place_position))
        relations.set_detached("red_cube", "left_arm_gripper")
        history.record("red_cube", {"position": place_position, "state": "FREE"})

        # 7c. Gripper open
        success, msg = gripper.open("left_arm")
        assert success, f"Gripper open failed: {msg}"

        # === Phase 8: 验证闭环 — WorldModel反映新的Reality ===
        # Reality: gripper empty
        assert not gripper.has_object("left_arm")
        assert gripper.is_open("left_arm")

        # WorldModel: relation reflects reality
        assert not relations.is_attached("red_cube")
        assert not relations.has_relation("red_cube", "attached_to", "left_arm_gripper")

        # WorldModel: object at new position
        obj_after = db.get_object("red_cube")
        assert obj_after is not None
        assert list(obj_after.position) == pytest.approx(place_position)

        # 重新计算spatial relations (新位置)
        objects_after = {
            obj_after.object_id: {"position": list(obj_after.position)}
        }
        surfaces_after = {"table2": {"position": [-0.5, 0.0, 0.0]}}
        relations.compute_spatial_relations(objects_after, surfaces_after)

        # 验证: red_cube on table2 (新表面)
        assert relations.has_relation("red_cube", "on", "table2")

    def test_state_transition_free_to_attached_to_free(self, e2e_setup: dict) -> None:
        """验证Object State转换: FREE → ATTACHED → FREE."""
        perception = e2e_setup["perception"]
        db = e2e_setup["world_model"]
        relations = e2e_setup["relations"]
        gripper = e2e_setup["gripper"]

        perception.register_object("blue_cylinder", "cylinder", [0.3, 0.2, 0.04])
        gripper.register_gripper("left_arm")

        # State: FREE
        sync_perception_to_db(perception.detect(), db)

        def get_grasp_state(object_id: str) -> str:
            """Get grasp state from WorldModel relations."""
            if relations.is_attached(object_id):
                return "ATTACHED"
            return "FREE"

        assert get_grasp_state("blue_cylinder") == "FREE"

        # Transition: FREE → ATTACHED
        gripper.close("left_arm")
        gripper.attach("left_arm", "blue_cylinder")
        relations.set_attached("blue_cylinder", "left_arm_gripper")

        assert get_grasp_state("blue_cylinder") == "ATTACHED"

        # Transition: ATTACHED → FREE
        gripper.detach("left_arm")
        relations.set_detached("blue_cylinder", "left_arm_gripper")
        gripper.open("left_arm")

        assert get_grasp_state("blue_cylinder") == "FREE"

    def test_relation_layer_drives_skill_precondition(self, e2e_setup: dict) -> None:
        """验证Relation Layer是Skill precondition判断的关键依赖.

        Skill: place_object(object, location)
            precondition: object attached_to gripper
            postcondition: object on location
        """
        perception = e2e_setup["perception"]
        db = e2e_setup["world_model"]
        relations = e2e_setup["relations"]
        gripper = e2e_setup["gripper"]

        perception.register_object("green_box", "box", [0.0, -0.3, 0.04])
        gripper.register_gripper("right_arm")

        # Perception → WorldModel
        sync_perception_to_db(perception.detect(), db)

        # Skill: place_object precondition check
        def check_precondition(object_id: str) -> bool:
            """precondition: object attached_to gripper."""
            return relations.is_attached(object_id)

        def check_postcondition(object_id: str, location: str) -> bool:
            """postcondition: object on location."""
            return relations.has_relation(object_id, "on", location)

        # Before grasp: precondition NOT met
        assert not check_precondition("green_box")

        # Grasp
        gripper.close("right_arm")
        gripper.attach("right_arm", "green_box")
        relations.set_attached("green_box", "right_arm_gripper")

        # After grasp: precondition met
        assert check_precondition("green_box")

        # Place
        place_pos = [0.0, 0.3, 0.04]
        db.update_object_pose("green_box", tuple(place_pos))
        gripper.detach("right_arm")
        relations.set_detached("green_box", "right_arm_gripper")
        gripper.open("right_arm")

        # Update relations for new position
        objects = {"green_box": {"position": place_pos}}
        surfaces = {"shelf": {"position": [0.0, 0.3, 0.0]}}
        relations.compute_spatial_relations(objects, surfaces)

        # After place: postcondition met
        assert check_postcondition("green_box", "shelf")

    def test_history_tracks_state_evolution(self, e2e_setup: dict) -> None:
        """验证History Layer记录状态演化."""
        perception = e2e_setup["perception"]
        db = e2e_setup["world_model"]
        history = e2e_setup["history"]
        gripper = e2e_setup["gripper"]

        perception.register_object("red_cube", "cube", [0.5, 0.0, 0.04])
        gripper.register_gripper("left_arm")

        # Phase 1: detected, FREE
        for det in perception.detect():
            db.add_object(TrackedObject(
                object_id=det.object_id,
                object_type=det.object_type,
                position=tuple(det.position),
            ))
            history.record("red_cube", {"position": det.position, "state": "FREE"})

        # Phase 2: grasped, ATTACHED
        gripper.close("left_arm")
        gripper.attach("left_arm", "red_cube")
        history.record("red_cube", {"position": [0.5, 0.0, 0.04], "state": "ATTACHED"})

        # Phase 3: lifted
        history.record("red_cube", {"position": [0.5, 0.0, 0.5], "state": "ATTACHED"})

        # Phase 4: placed, FREE
        gripper.detach("left_arm")
        gripper.open("left_arm")
        history.record("red_cube", {"position": [-0.5, 0.0, 0.04], "state": "FREE"})

        # Verify history
        full_history = history.get_history("red_cube")
        assert len(full_history) == 4

        states = [entry.data["state"] for entry in full_history]
        assert states == ["FREE", "ATTACHED", "ATTACHED", "FREE"]

        positions = [entry.data["position"] for entry in full_history]
        assert positions[0] == [0.5, 0.0, 0.04]
        assert positions[2] == [0.5, 0.0, 0.5]
        assert positions[3] == [-0.5, 0.0, 0.04]

    def test_prediction_from_history(self, e2e_setup: dict) -> None:
        """验证Prediction Layer从History预测未来状态."""

        history = e2e_setup["history"]

        # Record moving object
        for i in range(5):
            history.record("moving_cube", {
                "position": [0.1 * i, 0.0, 0.05],
                "velocity": [0.1, 0.0, 0.0],
            })

        prediction = PredictionLayer(history)

        # Predict future position
        pred = prediction.predict_position("moving_cube", dt=1.0)
        assert pred.entity_id == "moving_cube"

        latest = history.get_latest("moving_cube")
        current_x = latest.data["position"][0]
        velocity_x = latest.data["velocity"][0]

        assert pred.predicted_position[0] == pytest.approx(current_x + velocity_x * 1.0)

    def test_multi_object_scene(self, e2e_setup: dict) -> None:
        """验证多物体场景的感知和操作."""
        perception = e2e_setup["perception"]
        db = e2e_setup["world_model"]
        relations = e2e_setup["relations"]
        gripper = e2e_setup["gripper"]

        # Register multiple objects
        perception.register_object("red_cube", "cube", [0.3, 0.0, 0.04])
        perception.register_object("blue_cyl", "cylinder", [-0.3, 0.2, 0.04])
        perception.register_object("green_box", "box", [0.0, -0.3, 0.04])
        gripper.register_gripper("left_arm")
        gripper.register_gripper("right_arm")

        # Perception → WorldModel
        detections = perception.detect()
        assert len(detections) == 3

        sync_perception_to_db(detections, db)

        # Verify all objects in WorldModel
        all_objects = db.get_all_objects()
        assert len(all_objects) == 3

        object_ids = {o.object_id for o in all_objects}
        assert "red_cube" in object_ids
        assert "blue_cyl" in object_ids
        assert "green_box" in object_ids

        # left_arm picks red_cube
        gripper.close("left_arm")
        gripper.attach("left_arm", "red_cube")
        relations.set_attached("red_cube", "left_arm_gripper")

        # right_arm picks blue_cyl
        gripper.close("right_arm")
        gripper.attach("right_arm", "blue_cyl")
        relations.set_attached("blue_cyl", "right_arm_gripper")

        # Verify both attached
        assert relations.is_attached("red_cube", "left_arm_gripper")
        assert relations.is_attached("blue_cyl", "right_arm_gripper")
        assert not relations.is_attached("green_box")

        # left_arm releases
        gripper.detach("left_arm")
        relations.set_detached("red_cube", "left_arm_gripper")
        gripper.open("left_arm")

        assert not relations.is_attached("red_cube")
        assert relations.is_attached("blue_cyl", "right_arm_gripper")

    def test_grasp_planner_integration(self, e2e_setup: dict) -> None:
        """验证GraspPlanner与WorldModel集成."""
        perception = e2e_setup["perception"]
        db = e2e_setup["world_model"]
        planner = e2e_setup["grasp_planner"]

        perception.register_object("red_cube", "cube", [0.5, 0.0, 0.04])
        sync_perception_to_db(perception.detect(), db)

        obj = db.get_object("red_cube")
        assert obj is not None

        # Plan pick-place
        pick_pos = list(obj.position)
        place_pos = [-0.5, 0.0, 0.05]

        plan = planner.plan_pick_place(pick_pos, place_pos, approach="top")

        assert plan["pick"].grasp_position == pytest.approx(pick_pos, abs=0.1)
        assert plan["place"].grasp_position[0] == pytest.approx(place_pos[0])
        assert plan["pick"].approach == "top"
        assert plan["place"].approach == "top"

    def test_world_model_query_after_manipulation(self, e2e_setup: dict) -> None:
        """验证WorldModel查询在操作后返回正确状态."""
        perception = e2e_setup["perception"]
        db = e2e_setup["world_model"]
        relations = e2e_setup["relations"]
        gripper = e2e_setup["gripper"]

        perception.register_object("red_cube", "cube", [0.5, 0.0, 0.04])
        gripper.register_gripper("left_arm")

        # Initial state
        sync_perception_to_db(perception.detect(), db)

        # Query: all relations before grasp
        all_rels_before = relations.get_all_relations()
        attached_before = relations.query(predicate="attached_to")
        assert len(attached_before) == 0

        # Grasp
        gripper.close("left_arm")
        gripper.attach("left_arm", "red_cube")
        relations.set_attached("red_cube", "left_arm_gripper")

        # Query: relations after grasp
        attached_after = relations.query(predicate="attached_to")
        assert len(attached_after) == 1
        assert attached_after[0].subject == "red_cube"
        assert attached_after[0].object == "left_arm_gripper"

        # Query: specific relation
        specific = relations.query(subject="red_cube", predicate="attached_to")
        assert len(specific) == 1

        # Release
        gripper.detach("left_arm")
        relations.set_detached("red_cube", "left_arm_gripper")

        # Query: no more attached
        attached_final = relations.query(predicate="attached_to")
        assert len(attached_final) == 0