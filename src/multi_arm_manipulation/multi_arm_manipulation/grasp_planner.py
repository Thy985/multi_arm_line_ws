"""Grasp Planner — compute grasp poses for objects."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


@dataclass
class GraspPose:
    """A computed grasp pose."""

    approach_position: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    grasp_position: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    retreat_position: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    orientation: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0, 1.0])
    approach: str = "top"


class GraspPlanner:
    """Plan grasp poses for objects.

    Computes approach, grasp, and retreat positions
    based on object position and approach direction.
    """

    APPROACH_DISTANCE = 0.10
    RETREAT_DISTANCE = 0.15

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """Initialize grasp planner.

        Args:
            config: Configuration dict.

        """
        self._config = config or {}
        self._approach_dist = self._config.get("approach_distance", self.APPROACH_DISTANCE)
        self._retreat_dist = self._config.get("retreat_distance", self.RETREAT_DISTANCE)

    def plan_grasp(
        self,
        object_position: list[float],
        object_size: list[float] | None = None,
        approach: str = "top",
    ) -> GraspPose:
        """Plan a grasp pose for an object.

        Args:
            object_position: [x, y, z] object position.
            object_size: [w, h, d] object size (optional).
            approach: "top"|"side"|"front".

        Returns:
            Computed GraspPose.

        """
        obj_size = object_size or [0.05, 0.05, 0.05]
        grasp_z_offset = obj_size[2] / 2.0

        if approach == "top":
            grasp_pos = [
                object_position[0],
                object_position[1],
                object_position[2] + grasp_z_offset,
            ]
            approach_pos = [
                grasp_pos[0],
                grasp_pos[1],
                grasp_pos[2] + self._approach_dist,
            ]
            retreat_pos = [
                grasp_pos[0],
                grasp_pos[1],
                grasp_pos[2] + self._retreat_dist,
            ]
            orientation = [0.0, 0.0, 0.0, 1.0]

        elif approach == "side":
            grasp_pos = [
                object_position[0],
                object_position[1],
                object_position[2],
            ]
            approach_pos = [
                grasp_pos[0] + self._approach_dist,
                grasp_pos[1],
                grasp_pos[2],
            ]
            retreat_pos = [
                grasp_pos[0] + self._retreat_dist,
                grasp_pos[1],
                grasp_pos[2],
            ]
            yaw = -math.pi / 2
            orientation = [0.0, 0.0, math.sin(yaw / 2), math.cos(yaw / 2)]

        elif approach == "front":
            grasp_pos = [
                object_position[0],
                object_position[1],
                object_position[2],
            ]
            approach_pos = [
                grasp_pos[0],
                grasp_pos[1] + self._approach_dist,
                grasp_pos[2],
            ]
            retreat_pos = [
                grasp_pos[0],
                grasp_pos[1] + self._retreat_dist,
                grasp_pos[2],
            ]
            orientation = [0.0, 0.0, 0.0, 1.0]

        else:
            return self.plan_grasp(object_position, obj_size, "top")

        return GraspPose(
            approach_position=approach_pos,
            grasp_position=grasp_pos,
            retreat_position=retreat_pos,
            orientation=orientation,
            approach=approach,
        )

    def plan_pick_place(
        self,
        pick_position: list[float],
        place_position: list[float],
        approach: str = "top",
    ) -> dict[str, GraspPose]:
        """Plan complete pick-and-place trajectory.

        Args:
            pick_position: Object pickup position.
            place_position: Object placement position.
            approach: Grasp approach direction.

        Returns:
            Dict with "pick" and "place" GraspPoses.

        """
        pick_grasp = self.plan_grasp(pick_position, approach=approach)

        place_grasp = GraspPose(
            approach_position=[
                place_position[0],
                place_position[1],
                place_position[2] + self._approach_dist,
            ],
            grasp_position=[
                place_position[0],
                place_position[1],
                place_position[2],
            ],
            retreat_position=[
                place_position[0],
                place_position[1],
                place_position[2] + self._retreat_dist,
            ],
            orientation=pick_grasp.orientation,
            approach=approach,
        )

        return {"pick": pick_grasp, "place": place_grasp}