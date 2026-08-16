"""Tests for CollisionMonitor."""

import pytest

from multi_arm_safety.collision_monitor import CollisionMonitor


class TestCollisionMonitor:
    """Tests for the CollisionMonitor class."""

    def test_no_collision_when_far(self) -> None:
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

    def test_check_all_pairs(self) -> None:
        monitor = CollisionMonitor(
            arm_configs={
                "left_arm": {"base_offset": (0.0, 0.5, 0.0)},
                "right_arm": {"base_offset": (0.0, -0.5, 0.0)},
            },
        )
        monitor.update_joint_positions("left_arm", [0.0, -1.57, 1.57, 0.0, 0.0, 0.0])
        monitor.update_joint_positions("right_arm", [0.0, -1.57, 1.57, 0.0, 0.0, 0.0])
        results = monitor.check_all_pairs(["left_arm", "right_arm"])
        assert len(results) == 1
        assert results[0]["arm_a"] == "left_arm"
        assert results[0]["arm_b"] == "right_arm"

    def test_missing_arm_returns_inf(self) -> None:
        monitor = CollisionMonitor()
        dist, is_collision = monitor.check_arm_proximity("left_arm", "right_arm")
        assert dist == float("inf")
        assert not is_collision

    def test_insufficient_joints(self) -> None:
        monitor = CollisionMonitor()
        points = monitor.get_approximate_points("left_arm", [0.0, 0.0])
        assert len(points) == 0

    def test_approximate_points_count(self) -> None:
        monitor = CollisionMonitor(
            arm_configs={"left_arm": {"base_offset": (0.0, 0.5, 0.0)}}
        )
        points = monitor.get_approximate_points(
            "left_arm", [0.0, -1.57, 1.57, 0.0, 0.0, 0.0]
        )
        assert len(points) == 4

    def test_three_arms_pairs(self) -> None:
        monitor = CollisionMonitor(
            arm_configs={
                "left_arm": {"base_offset": (0.0, 0.5, 0.0)},
                "right_arm": {"base_offset": (0.0, -0.5, 0.0)},
                "arm3": {"base_offset": (0.5, 0.0, 0.0)},
            },
        )
        for arm in ["left_arm", "right_arm", "arm3"]:
            monitor.update_joint_positions(arm, [0.0, -1.57, 1.57, 0.0, 0.0, 0.0])
        results = monitor.check_all_pairs(["left_arm", "right_arm", "arm3"])
        assert len(results) == 3