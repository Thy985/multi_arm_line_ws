"""RandomTaskGenerator — generates random task parameters for stress testing.

Tests whether the BT + Coordinator + MoveIt pipeline generalizes
across different objects, locations, and approaches, not just
hardcoded "left_arm:zone_a:ready".
"""

import random
from typing import Any, Dict, List, Optional, Tuple


OBJECTS: List[Dict[str, Any]] = [
    {"object_id": "red_cube", "object_type": "cube", "weight": 0.5},
    {"object_id": "blue_cylinder", "object_type": "cylinder", "weight": 0.8},
    {"object_id": "green_box", "object_type": "box", "weight": 1.2},
    {"object_id": "yellow_sphere", "object_type": "sphere", "weight": 0.3},
    {"object_id": "orange_cylinder", "object_type": "cylinder", "weight": 0.6},
]

ZONES: List[str] = ["zone_a", "zone_b", "zone_c"]

POSITIONS: List[str] = ["home", "ready", "scan", "inspect", "place_high", "place_low"]

ARMS: List[str] = ["left_arm", "right_arm"]

APPROACHES: List[str] = ["top", "side", "front"]

ACTION_TYPES: List[str] = ["move", "pick_place", "inspect"]


class RandomTaskGenerator:
    """Generates random task parameters for stress testing.

    Usage:
        gen = RandomTaskGenerator(seed=42)
        for _ in range(100):
            task = gen.generate()
            # task = {"arm_name": "right_arm", "action_type": "pick_place", ...}
    """

    def __init__(self, seed: Optional[int] = None) -> None:
        self._rng = random.Random(seed)
        self._task_counter = 0

    def generate(self) -> Dict[str, Any]:
        """Generate a single random task.

        Returns:
            Dict with task parameters matching TaskGoal fields.
        """
        self._task_counter += 1
        obj = self._rng.choice(OBJECTS)
        arm = self._rng.choice(ARMS)
        pick_zone = self._rng.choice(ZONES)
        place_zone = self._rng.choice([z for z in ZONES if z != pick_zone])
        position = self._rng.choice(POSITIONS)
        approach = self._rng.choice(APPROACHES)
        action_type = self._rng.choice(ACTION_TYPES)

        return {
            "task_id": f"stress_{self._task_counter:04d}",
            "arm_name": arm,
            "action_type": action_type,
            "zone_name": pick_zone,
            "position_name": position,
            "object_id": obj["object_id"],
            "object_type": obj["object_type"],
            "approach": approach,
            "place_zone": place_zone,
            "description": f"{arm}:{pick_zone}:{position}",
            "timeout": 30.0,
        }

    def generate_batch(self, count: int) -> List[Dict[str, Any]]:
        """Generate a batch of random tasks.

        Args:
            count: Number of tasks to generate.

        Returns:
            List of task dicts.
        """
        return [self.generate() for _ in range(count)]

    def generate_unreachable_task(self) -> Dict[str, Any]:
        """Generate a task with unreachable target pose.

        Used for failure injection testing (Level 3).
        """
        self._task_counter += 1
        return {
            "task_id": f"unreachable_{self._task_counter:04d}",
            "arm_name": self._rng.choice(ARMS),
            "action_type": "move",
            "zone_name": "zone_invalid",
            "position_name": "unreachable_pose",
            "object_id": "",
            "object_type": "",
            "approach": "top",
            "place_zone": "",
            "description": "left_arm:zone_invalid:unreachable_pose",
            "timeout": 10.0,
            "inject_failure": "planning_failure",
        }

    def generate_safety_violation_task(self) -> Dict[str, Any]:
        """Generate a task that triggers safety violation.

        Used for failure injection testing (Level 3).
        """
        self._task_counter += 1
        return {
            "task_id": f"safety_violation_{self._task_counter:04d}",
            "arm_name": self._rng.choice(ARMS),
            "action_type": "move",
            "zone_name": self._rng.choice(ZONES),
            "position_name": "ready",
            "object_id": "",
            "object_type": "",
            "approach": "top",
            "place_zone": "",
            "description": f"left_arm:{self._rng.choice(ZONES)}:ready",
            "timeout": 10.0,
            "inject_failure": "safety_violation",
            "velocity_scale": 2.0,
        }

    def generate_multi_task_queue(self, count: int = 3) -> List[Dict[str, Any]]:
        """Generate a multi-task queue with priorities.

        Used for Level 4 multi-task scheduling testing.
        """
        tasks = []
        priorities = list(range(count, 0, -1))
        self._rng.shuffle(priorities)

        for i in range(count):
            self._task_counter += 1
            arm = self._rng.choice(ARMS)
            zone = self._rng.choice(ZONES)
            action = self._rng.choice(ACTION_TYPES)
            obj = self._rng.choice(OBJECTS)

            tasks.append({
                "task_id": f"multi_{self._task_counter:04d}",
                "arm_name": arm,
                "action_type": action,
                "zone_name": zone,
                "position_name": self._rng.choice(POSITIONS),
                "object_id": obj["object_id"] if action == "pick_place" else "",
                "object_type": obj["object_type"] if action == "pick_place" else "",
                "approach": self._rng.choice(APPROACHES),
                "place_zone": self._rng.choice([z for z in ZONES if z != zone]),
                "description": f"{arm}:{zone}:ready",
                "timeout": 30.0,
                "priority": priorities[i],
            })

        return tasks

    @property
    def task_counter(self) -> int:
        return self._task_counter