"""SpeedLimiter for joint velocity and acceleration limiting."""

from typing import Dict, List, Optional, Tuple
import math


class SpeedLimiter:
    """Enforces joint velocity and acceleration limits.

    Checks trajectory points against configured limits and computes
    a speed scaling factor when limits would be exceeded.
    """

    def __init__(
        self,
        max_velocity: Optional[Dict[str, float]] = None,
        max_acceleration: Optional[Dict[str, float]] = None,
        default_max_vel: float = 3.14,
        default_max_acc: float = 5.0,
    ) -> None:
        """Initialize SpeedLimiter.

        Args:
            max_velocity: Per-joint max velocity (rad/s).
            max_acceleration: Per-joint max acceleration (rad/s^2).
            default_max_vel: Default max velocity if not specified.
            default_max_acc: Default max acceleration if not specified.
        """
        self._max_velocity = max_velocity or {}
        self._max_acceleration = max_acceleration or {}
        self._default_max_vel = default_max_vel
        self._default_max_acc = default_max_acc

    def get_max_velocity(self, joint_name: str) -> float:
        """Get max velocity for a joint."""
        return self._max_velocity.get(joint_name, self._default_max_vel)

    def get_max_acceleration(self, joint_name: str) -> float:
        """Get max acceleration for a joint."""
        return self._max_acceleration.get(joint_name, self._default_max_acc)

    def check_velocities(
        self,
        joint_names: List[str],
        velocities: List[float],
    ) -> Tuple[bool, float, List[str]]:
        """Check if velocities are within limits.

        Args:
            joint_names: Joint names.
            velocities: Joint velocities (rad/s).

        Returns:
            Tuple of (within_limits, speed_scale, violations).
        """
        violations = []
        max_ratio = 1.0

        for name, vel in zip(joint_names, velocities):
            limit = self.get_max_velocity(name)
            ratio = abs(vel) / limit if limit > 0 else 0.0
            if ratio > 1.0:
                violations.append(f"{name}: {abs(vel):.3f} > {limit:.3f} rad/s")
            max_ratio = max(max_ratio, ratio)

        within_limits = len(violations) == 0
        speed_scale = 1.0 / max_ratio if max_ratio > 1.0 else 1.0

        return within_limits, speed_scale, violations

    def check_trajectory_velocities(
        self,
        joint_names: List[str],
        positions: List[float],
        duration: float,
    ) -> Tuple[bool, float]:
        """Estimate velocities from positions/duration and check limits.

        Args:
            joint_names: Joint names.
            positions: Target joint positions (rad).
            duration: Trajectory duration (s).

        Returns:
            Tuple of (within_limits, speed_scale).
        """
        if duration <= 0:
            return False, 0.0

        velocities = [abs(p) / duration for p in positions]
        within, scale, _ = self.check_velocities(joint_names, velocities)
        return within, scale

    def compute_speed_scale(
        self,
        joint_names: List[str],
        positions: List[float],
        duration: float,
        global_scale: float = 1.0,
    ) -> float:
        """Compute the speed scale factor for a trajectory.

        Args:
            joint_names: Joint names.
            positions: Target joint positions.
            duration: Trajectory duration.
            global_scale: Global speed scale from safety level.

        Returns:
            Speed scale factor (0.0-1.0).
        """
        _, scale = self.check_trajectory_velocities(joint_names, positions, duration)
        return min(scale, global_scale)