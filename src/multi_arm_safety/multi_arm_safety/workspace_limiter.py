"""WorkspaceLimiter for checking workspace boundary violations."""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import math


@dataclass
class WorkspaceBounds:
    """Axis-aligned workspace boundary box."""
    x_min: float = -0.8
    x_max: float = 0.8
    y_min: float = -0.8
    y_max: float = 0.8
    z_min: float = 0.0
    z_max: float = 1.2

    def contains(self, x: float, y: float, z: float) -> bool:
        """Check if a point is within the workspace bounds."""
        return (
            self.x_min <= x <= self.x_max
            and self.y_min <= y <= self.y_max
            and self.z_min <= z <= self.z_max
        )

    def distance_to_boundary(self, x: float, y: float, z: float) -> float:
        """Compute minimum distance to workspace boundary.

        Returns:
            Negative if outside, positive if inside.
        """
        distances = [
            x - self.x_min, self.x_max - x,
            y - self.y_min, self.y_max - y,
            z - self.z_min, self.z_max - z,
        ]
        return min(distances)



class WorkspaceLimiter:
    """Checks if arm end-effector positions are within workspace bounds.

    Each arm can have its own workspace bounds configured via YAML.
    In Phase 1-2, this is a software check using forward kinematics
    approximation or subscribed joint states.
    """

    def __init__(
        self,
        bounds: Optional[Dict[str, WorkspaceBounds]] = None,
    ) -> None:
        """Initialize WorkspaceLimiter.

        Args:
            bounds: Per-arm workspace bounds. If None, default bounds are used.
        """
        self._bounds: Dict[str, WorkspaceBounds] = bounds or {}

    def set_bounds(self, arm_name: str, bounds: WorkspaceBounds) -> None:
        """Set workspace bounds for an arm."""
        self._bounds[arm_name] = bounds

    def get_bounds(self, arm_name: str) -> WorkspaceBounds:
        """Get workspace bounds for an arm (default if not set)."""
        return self._bounds.get(arm_name, WorkspaceBounds())

    def check_position(
        self, arm_name: str, x: float, y: float, z: float
    ) -> Tuple[bool, float]:
        """Check if a position is within the arm's workspace.

        Args:
            arm_name: Arm name.
            x, y, z: Position coordinates.

        Returns:
            Tuple of (within_bounds, distance_to_boundary).
        """
        bounds = self.get_bounds(arm_name)
        within = bounds.contains(x, y, z)
        distance = bounds.distance_to_boundary(x, y, z)
        return within, distance

    def check_joint_positions(
        self,
        arm_name: str,
        joint_positions: List[float],
        arm_base_offset: Optional[Tuple[float, float, float]] = None,
    ) -> Tuple[bool, float]:
        """Estimate end-effector position and check workspace bounds.

        Uses a simplified forward kinematics approximation for UR5e.
        For accurate checks, use MoveIt2's FK service in Phase 3+.

        Args:
            arm_name: Arm name.
            joint_positions: 6 joint positions (rad).
            arm_base_offset: (x, y, z) offset of arm base in world frame.

        Returns:
            Tuple of (within_bounds, distance_to_boundary).
        """
        if len(joint_positions) < 6:
            return True, 0.0

        offset = arm_base_offset or (0.0, 0.0, 0.0)

        reach = 0.85
        q1, q2, q3 = joint_positions[0], joint_positions[1], joint_positions[2]

        ee_x = offset[0] + reach * math.cos(q1) * math.cos(q2 + q3)
        ee_y = offset[1] + reach * math.sin(q1) * math.cos(q2 + q3)
        ee_z = offset[2] + reach * math.sin(q2 + q3) + 0.1

        return self.check_position(arm_name, ee_x, ee_y, ee_z)

    @classmethod
    def from_yaml_config(cls, config: Dict) -> "WorkspaceLimiter":
        """Create WorkspaceLimiter from YAML config dict.

        Args:
            config: Dict with robot safety workspace_bounds.

        Returns:
            Configured WorkspaceLimiter.
        """
        limiter = cls()
        for robot_cfg in config.get("robots", []):
            arm_name = robot_cfg["name"]
            safety = robot_cfg.get("safety", {})
            wb = safety.get("workspace_bounds")
            if wb and len(wb) == 3 and len(wb[0]) == 2:
                limiter.set_bounds(
                    arm_name,
                    WorkspaceBounds(
                        x_min=wb[0][0], x_max=wb[0][1],
                        y_min=wb[1][0], y_max=wb[1][1],
                        z_min=wb[2][0], z_max=wb[2][1],
                    ),
                )
        return limiter