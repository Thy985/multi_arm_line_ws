"""Tests for WorkspaceLimiter."""

import pytest

from multi_arm_safety.workspace_limiter import WorkspaceLimiter, WorkspaceBounds


class TestWorkspaceBounds:
    """Tests for WorkspaceBounds dataclass."""

    def test_default_bounds(self) -> None:
        b = WorkspaceBounds()
        assert b.contains(0.0, 0.0, 0.5)
        assert not b.contains(1.0, 0.0, 0.5)

    def test_custom_bounds(self) -> None:
        b = WorkspaceBounds(x_min=-0.5, x_max=0.5, y_min=-0.5, y_max=0.5,
                            z_min=0.0, z_max=1.0)
        assert b.contains(0.0, 0.0, 0.5)
        assert not b.contains(0.6, 0.0, 0.5)

    def test_boundary_edges(self) -> None:
        b = WorkspaceBounds()
        assert b.contains(0.8, 0.8, 1.2)
        assert b.contains(-0.8, -0.8, 0.0)

    def test_distance_inside(self) -> None:
        b = WorkspaceBounds()
        d = b.distance_to_boundary(0.0, 0.0, 0.5)
        assert d > 0

    def test_distance_outside(self) -> None:
        b = WorkspaceBounds()
        d = b.distance_to_boundary(1.0, 0.0, 0.5)
        assert d < 0


class TestWorkspaceLimiter:
    """Tests for the WorkspaceLimiter class."""

    def test_default_bounds_check(self) -> None:
        limiter = WorkspaceLimiter()
        within, dist = limiter.check_position("left_arm", 0.0, 0.0, 0.5)
        assert within

    def test_out_of_bounds(self) -> None:
        limiter = WorkspaceLimiter()
        within, dist = limiter.check_position("left_arm", 1.5, 0.0, 0.5)
        assert not within

    def test_per_arm_bounds(self) -> None:
        limiter = WorkspaceLimiter()
        limiter.set_bounds("left_arm", WorkspaceBounds(
            x_min=-0.8, x_max=0.8, y_min=-0.3, y_max=0.8, z_min=0.0, z_max=1.2
        ))
        limiter.set_bounds("right_arm", WorkspaceBounds(
            x_min=-0.8, x_max=0.8, y_min=-0.8, y_max=0.3, z_min=0.0, z_max=1.2
        ))
        within1, _ = limiter.check_position("left_arm", 0.0, 0.6, 0.5)
        within2, _ = limiter.check_position("right_arm", 0.0, 0.6, 0.5)
        assert within1
        assert not within2

    def test_joint_positions_check(self) -> None:
        limiter = WorkspaceLimiter()
        limiter.set_bounds("left_arm", WorkspaceBounds(
            x_min=-1.0, x_max=1.0, y_min=-1.0, y_max=1.0, z_min=-0.5, z_max=1.5
        ))
        within, _ = limiter.check_joint_positions(
            "left_arm", [0.0, -1.57, 1.57, 0.0, 0.0, 0.0]
        )
        assert within

    def test_from_yaml_config(self) -> None:
        config = {
            "robots": [
                {
                    "name": "left_arm",
                    "safety": {
                        "workspace_bounds": [[-0.8, 0.8], [-0.3, 0.8], [0.0, 1.2]],
                    },
                },
            ],
        }
        limiter = WorkspaceLimiter.from_yaml_config(config)
        within, _ = limiter.check_position("left_arm", 0.0, 0.5, 0.5)
        assert within