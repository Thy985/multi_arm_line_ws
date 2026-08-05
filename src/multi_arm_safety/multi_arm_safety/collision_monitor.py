"""CollisionMonitor for detecting arm-to-arm proximity and collisions."""

from typing import Dict, List, Optional, Tuple
import math


class CollisionMonitor:
    """Monitors potential collisions between arms and with the environment.

    Phase 1-2: Software-based proximity check using joint state subscriptions.
    Uses simplified geometric models (cylinders/spheres) for arm segments.

    Phase 3+: Will integrate MoveIt2's collision checking for accurate
    mesh-based collision detection.
    """

    ARM_SEGMENT_RADIUS = 0.06
    MIN_CLEARANCE = 0.10
    CRITICAL_CLEARANCE = 0.03

    def __init__(
        self,
        arm_configs: Optional[Dict[str, Dict]] = None,
        min_clearance: float = 0.10,
    ) -> None:
        """Initialize CollisionMonitor.

        Args:
            arm_configs: Per-arm configuration with base offset.
            min_clearance: Minimum allowed clearance between arms (m).
        """
        self._arm_configs = arm_configs or {}
        self._min_clearance = min_clearance
        self._last_joint_positions: Dict[str, List[float]] = {}

    def update_joint_positions(self, arm_name: str, positions: List[float]) -> None:
        """Update joint positions for an arm."""
        self._last_joint_positions[arm_name] = positions

    def get_approximate_points(
        self,
        arm_name: str,
        joint_positions: List[float],
    ) -> List[Tuple[float, float, float]]:
        """Get approximate 3D points along the arm for proximity checking.

        Uses simplified FK: shoulder, elbow, wrist, and end-effector points.

        Args:
            arm_name: Arm name.
            joint_positions: 6 joint positions (rad).

        Returns:
            List of (x, y, z) points along the arm.
        """
        if len(joint_positions) < 6:
            return []

        base = self._arm_configs.get(arm_name, {}).get("base_offset", (0.0, 0.0, 0.0))
        q1, q2, q3, q4, q5, q6 = joint_positions[:6]

        shoulder = (base[0], base[1], base[2] + 0.14)

        l_upper = 0.425
        l_forearm = 0.392
        l_wrist = 0.09

        elbow_x = shoulder[0] + l_upper * math.cos(q1) * math.sin(q2)
        elbow_y = shoulder[1] + l_upper * math.sin(q1) * math.sin(q2)
        elbow_z = shoulder[2] + l_upper * math.cos(q2)
        elbow = (elbow_x, elbow_y, elbow_z)

        wrist_angle = q2 + q3
        wrist_x = elbow_x + l_forearm * math.cos(q1) * math.sin(wrist_angle)
        wrist_y = elbow_y + l_forearm * math.sin(q1) * math.sin(wrist_angle)
        wrist_z = elbow_z + l_forearm * math.cos(wrist_angle)
        wrist = (wrist_x, wrist_y, wrist_z)

        ee_angle = wrist_angle + q4
        ee_x = wrist_x + l_wrist * math.cos(q1) * math.sin(ee_angle)
        ee_y = wrist_y + l_wrist * math.sin(q1) * math.sin(ee_angle)
        ee_z = wrist_z + l_wrist * math.cos(ee_angle)
        ee = (ee_x, ee_y, ee_z)

        return [shoulder, elbow, wrist, ee]

    @staticmethod
    def _point_distance(p1: Tuple[float, float, float],
                        p2: Tuple[float, float, float]) -> float:
        """Euclidean distance between two 3D points."""
        return math.sqrt(
            (p1[0] - p2[0]) ** 2
            + (p1[1] - p2[1]) ** 2
            + (p1[2] - p2[2]) ** 2
        )

    def check_arm_proximity(
        self,
        arm_a: str,
        arm_b: str,
    ) -> Tuple[float, bool]:
        """Check proximity between two arms.

        Args:
            arm_a: First arm name.
            arm_b: Second arm name.

        Returns:
            Tuple of (min_distance, is_collision).
        """
        pos_a = self._last_joint_positions.get(arm_a)
        pos_b = self._last_joint_positions.get(arm_b)

        if pos_a is None or pos_b is None:
            return float("inf"), False

        points_a = self.get_approximate_points(arm_a, pos_a)
        points_b = self.get_approximate_points(arm_b, pos_b)

        if not points_a or not points_b:
            return float("inf"), False

        min_dist = float("inf")
        for pa in points_a:
            for pb in points_b:
                d = self._point_distance(pa, pb)
                min_dist = min(min_dist, d)

        is_collision = min_dist < self.CRITICAL_CLEARANCE
        return min_dist, is_collision

    def check_all_pairs(
        self,
        arm_names: List[str],
    ) -> List[Dict]:
        """Check proximity between all arm pairs.

        Args:
            arm_names: List of arm names to check.

        Returns:
            List of dicts with arm_a, arm_b, distance, is_collision, is_warning.
        """
        results = []
        for i, arm_a in enumerate(arm_names):
            for arm_b in arm_names[i + 1:]:
                dist, is_collision = self.check_arm_proximity(arm_a, arm_b)
                results.append({
                    "arm_a": arm_a,
                    "arm_b": arm_b,
                    "distance": dist,
                    "is_collision": is_collision,
                    "is_warning": dist < self._min_clearance and not is_collision,
                })
        return results