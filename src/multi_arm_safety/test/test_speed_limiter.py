"""Tests for SpeedLimiter."""

import pytest

from multi_arm_safety.speed_limiter import SpeedLimiter


class TestSpeedLimiter:
    """Tests for the SpeedLimiter class."""

    def test_within_limits(self) -> None:
        limiter = SpeedLimiter(default_max_vel=3.14)
        within, scale, violations = limiter.check_velocities(
            ["joint1"], [1.0]
        )
        assert within
        assert scale == 1.0
        assert len(violations) == 0

    def test_exceeds_limits(self) -> None:
        limiter = SpeedLimiter(default_max_vel=3.14)
        within, scale, violations = limiter.check_velocities(
            ["joint1"], [5.0]
        )
        assert not within
        assert scale < 1.0
        assert len(violations) == 1

    def test_per_joint_limits(self) -> None:
        limiter = SpeedLimiter(max_velocity={"joint1": 1.0, "joint2": 2.0})
        within, _, _ = limiter.check_velocities(["joint1"], [0.5])
        assert within
        within, _, _ = limiter.check_velocities(["joint1"], [1.5])
        assert not within

    def test_trajectory_velocity_check(self) -> None:
        limiter = SpeedLimiter(default_max_vel=3.14)
        within, scale = limiter.check_trajectory_velocities(
            ["joint1"], [1.57], duration=1.0
        )
        assert within
        assert scale == 1.0

    def test_trajectory_too_fast(self) -> None:
        limiter = SpeedLimiter(default_max_vel=3.14)
        within, scale = limiter.check_trajectory_velocities(
            ["joint1"], [6.28], duration=1.0
        )
        assert not within
        assert scale < 1.0

    def test_compute_speed_scale(self) -> None:
        limiter = SpeedLimiter(default_max_vel=3.14)
        scale = limiter.compute_speed_scale(
            ["joint1"], [1.57], duration=1.0
        )
        assert scale == 1.0

    def test_zero_duration(self) -> None:
        limiter = SpeedLimiter(default_max_vel=3.14)
        within, scale = limiter.check_trajectory_velocities(
            ["joint1"], [1.0], duration=0.0
        )
        assert not within
        assert scale == 0.0

    def test_multiple_joints_mixed(self) -> None:
        limiter = SpeedLimiter(default_max_vel=3.14)
        within, scale, violations = limiter.check_velocities(
            ["j1", "j2", "j3"], [1.0, 5.0, 2.0]
        )
        assert not within
        assert len(violations) == 1