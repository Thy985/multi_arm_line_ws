"""Prediction Layer — motion and collision prediction."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from .history_layer import HistoryLayer


@dataclass
class PredictionResult:
    """Result of a prediction."""

    entity_id: str
    predicted_position: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    confidence: float = 0.5
    collision_risk: float = 0.0
    estimated_arrival_time: float = 0.0


class PredictionLayer:
    """Prediction Layer of WorldModel — motion and collision prediction.

    Uses History Layer data to predict future states:
    - Linear motion prediction (position extrapolation)
    - Collision risk estimation
    - Arrival time estimation
    """

    def __init__(self, history: HistoryLayer | None = None) -> None:
        """Initialize prediction layer.

        Args:
            history: History layer for trend data.

        """
        self._history = history or HistoryLayer()

    def predict_position(
        self,
        entity_id: str,
        dt: float = 0.5,
    ) -> PredictionResult:
        """Predict future position using linear extrapolation.

        Args:
            entity_id: Entity ID.
            dt: Time horizon in seconds.

        Returns:
            Prediction result with predicted position.

        """
        latest = self._history.get_latest(entity_id)
        if latest is None:
            return PredictionResult(entity_id=entity_id, confidence=0.0)

        current_pos = latest.data.get("position", [0.0, 0.0, 0.0])
        velocity = latest.data.get("velocity", [0.0, 0.0, 0.0])

        predicted = [
            current_pos[0] + velocity[0] * dt,
            current_pos[1] + velocity[1] * dt,
            current_pos[2] + velocity[2] * dt,
        ]

        confidence = max(0.0, 1.0 - dt * 0.5)

        return PredictionResult(
            entity_id=entity_id,
            predicted_position=predicted,
            confidence=confidence,
        )

    def estimate_collision_risk(
        self,
        entity_id: str,
        target_position: list[float],
        obstacles: dict[str, list[float]] | None = None,
        threshold: float = 0.1,
    ) -> float:
        """Estimate collision risk for moving to target.

        Args:
            entity_id: Entity ID.
            target_position: Target [x, y, z].
            obstacles: Dict of obstacle_id -> position.
            threshold: Collision distance threshold.

        Returns:
            Collision risk (0.0 = safe, 1.0 = certain collision).

        """
        if not obstacles:
            return 0.0

        latest = self._history.get_latest(entity_id)
        if latest is None:
            return 0.0

        current_pos = latest.data.get("position", [0.0, 0.0, 0.0])

        max_risk = 0.0
        for obs_pos in obstacles.values():
            for t in [0.25, 0.5, 0.75]:
                interp = [
                    current_pos[i] + (target_position[i] - current_pos[i]) * t
                    for i in range(3)
                ]
                dist = sum(
                    (interp[i] - obs_pos[i]) ** 2 for i in range(3)
                ) ** 0.5

                if dist < threshold:
                    risk = 1.0
                else:
                    risk = max(0.0, 1.0 - dist / (threshold * 5.0))

                max_risk = max(max_risk, risk)

        return max_risk

    def estimate_arrival_time(
        self,
        entity_id: str,
        target_position: list[float],
    ) -> float:
        """Estimate time to reach target position.

        Args:
            entity_id: Entity ID.
            target_position: Target [x, y, z].

        Returns:
            Estimated arrival time in seconds (0 if already there).

        """
        latest = self._history.get_latest(entity_id)
        if latest is None:
            return 0.0

        current_pos = latest.data.get("position", [0.0, 0.0, 0.0])
        velocity = latest.data.get("velocity", [0.0, 0.0, 0.0])

        distance = sum(
            (target_position[i] - current_pos[i]) ** 2 for i in range(3)
        ) ** 0.5

        speed = sum(v * v for v in velocity) ** 0.5
        if speed < 0.001:
            return float("inf") if distance > 0.001 else 0.0

        return distance / speed

    def predict_all(
        self,
        entity_ids: list[str],
        dt: float = 0.5,
    ) -> dict[str, PredictionResult]:
        """Predict positions for multiple entities.

        Args:
            entity_ids: List of entity IDs.
            dt: Time horizon.

        Returns:
            Dict of entity_id -> PredictionResult.

        """
        return {
            eid: self.predict_position(eid, dt) for eid in entity_ids
        }