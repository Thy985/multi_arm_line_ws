"""Tests for GraspPlanner."""

import math

import pytest

from multi_arm_manipulation.grasp_planner import GraspPlanner, GraspPose


class TestGraspPlanner:
    """Tests for GraspPlanner."""

    def test_plan_grasp_top(self) -> None:
        planner = GraspPlanner()
        pose = planner.plan_grasp([0.5, 0.0, 0.05], approach="top")
        assert pose.approach == "top"
        assert pose.approach_position[2] > pose.grasp_position[2]
        assert pose.retreat_position[2] > pose.grasp_position[2]

    def test_plan_grasp_side(self) -> None:
        planner = GraspPlanner()
        pose = planner.plan_grasp([0.5, 0.0, 0.05], approach="side")
        assert pose.approach == "side"
        assert pose.approach_position[0] > pose.grasp_position[0]

    def test_plan_grasp_front(self) -> None:
        planner = GraspPlanner()
        pose = planner.plan_grasp([0.5, 0.0, 0.05], approach="front")
        assert pose.approach == "front"
        assert pose.approach_position[1] > pose.grasp_position[1]

    def test_plan_grasp_invalid_approach(self) -> None:
        planner = GraspPlanner()
        pose = planner.plan_grasp([0.5, 0.0, 0.05], approach="invalid")
        assert pose.approach == "top"

    def test_plan_grasp_with_size(self) -> None:
        planner = GraspPlanner()
        pose = planner.plan_grasp(
            [0.5, 0.0, 0.0], object_size=[0.1, 0.1, 0.1], approach="top"
        )
        assert pose.grasp_position[2] == pytest.approx(0.05)

    def test_plan_pick_place(self) -> None:
        planner = GraspPlanner()
        result = planner.plan_pick_place(
            pick_position=[0.5, 0.0, 0.05],
            place_position=[-0.5, 0.0, 0.05],
            approach="top",
        )
        assert "pick" in result
        assert "place" in result
        assert result["pick"].grasp_position != result["place"].grasp_position

    def test_approach_distance_config(self) -> None:
        planner = GraspPlanner({"approach_distance": 0.2})
        pose = planner.plan_grasp([0, 0, 0], object_size=[0, 0, 0], approach="top")
        assert pose.approach_position[2] == pytest.approx(0.2)

    def test_retreat_distance(self) -> None:
        planner = GraspPlanner()
        pose = planner.plan_grasp([0, 0, 0], approach="top")
        assert pose.retreat_position[2] > pose.approach_position[2]

    def test_side_orientation(self) -> None:
        planner = GraspPlanner()
        pose = planner.plan_grasp([0, 0, 0], approach="side")
        assert pose.orientation != [0.0, 0.0, 0.0, 1.0]

    def test_top_orientation(self) -> None:
        planner = GraspPlanner()
        pose = planner.plan_grasp([0, 0, 0], approach="top")
        assert pose.orientation == [0.0, 0.0, 0.0, 1.0]