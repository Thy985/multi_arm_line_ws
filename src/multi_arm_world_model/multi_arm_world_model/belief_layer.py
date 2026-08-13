"""Belief Layer — probabilistic state estimation for WorldModel.

M7.6: Upgrades WorldModel from deterministic point estimates to probabilistic
belief states with Gaussian uncertainty representation and multi-source fusion.

Components:
    GaussianBelief: 3D position belief with diagonal covariance.
    BeliefUpdater: Fuses multiple sources (GT + vision) using confidence-weighted
                   Kalman-like update. Tracks belief history for temporal reasoning.

Key formulas:
    - Single source: variance = (1 - confidence) * base_variance
    - Multi-source fusion: fused_mean = (mean1 * var2 + mean2 * var1) / (var1 + var2)
    - Fused variance: fused_var = var1 * var2 / (var1 + var2)
    - Prediction: mean += velocity * dt, variance += process_noise * dt
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class GaussianBelief:
    """3D Gaussian belief state (diagonal covariance).

    Attributes:
        mean: (x, y, z) position estimate.
        variance: (var_x, var_y, var_z) diagonal covariance.
        confidence: Belief confidence [0, 1].
        source: Source identifier ('ground_truth', 'vision', 'fused').
        updated_at: Last update timestamp.
    """

    mean: tuple[float, float, float] = (0.0, 0.0, 0.0)
    variance: tuple[float, float, float] = (0.01, 0.01, 0.01)
    confidence: float = 1.0
    source: str = "unknown"
    updated_at: float = field(default_factory=time.time)

    @property
    def uncertainty(self) -> float:
        """Overall uncertainty (trace of covariance / 3)."""
        return (self.variance[0] + self.variance[1] + self.variance[2]) / 3.0

    @property
    def std_dev(self) -> tuple[float, float, float]:
        """Standard deviation per axis."""
        return (
            math.sqrt(self.variance[0]),
            math.sqrt(self.variance[1]),
            math.sqrt(self.variance[2]),
        )

    def predict(self, velocity: tuple[float, float, float], dt: float,
                process_noise: float = 0.001) -> GaussianBelief:
        """Predict belief forward by dt seconds.

        Args:
            velocity: (vx, vy, vz) velocity estimate.
            dt: Time delta in seconds.
            process_noise: Process noise per second (added to variance).

        Returns:
            Predicted belief (does not modify self).
        """
        return GaussianBelief(
            mean=(
                self.mean[0] + velocity[0] * dt,
                self.mean[1] + velocity[1] * dt,
                self.mean[2] + velocity[2] * dt,
            ),
            variance=(
                self.variance[0] + process_noise * dt,
                self.variance[1] + process_noise * dt,
                self.variance[2] + process_noise * dt,
            ),
            confidence=max(0.0, self.confidence - 0.1 * dt),
            source=self.source,
            updated_at=self.updated_at + dt,
        )

    def to_covariance_flat(self) -> tuple[float, float, float, float, float, float, float, float, float]:
        """Convert to 3x3 flat covariance (row-major, diagonal only)."""
        return (
            self.variance[0], 0.0, 0.0,
            0.0, self.variance[1], 0.0,
            0.0, 0.0, self.variance[2],
        )


class BeliefUpdater:
    """Multi-source belief fusion for WorldModel objects.

    Maintains a GaussianBelief per object, fusing updates from multiple
    sources (ground_truth, vision) using confidence-weighted Kalman-like update.

    Attributes:
        _beliefs: Object ID -> GaussianBelief.
        _base_variance: Base variance for confidence=0 sources.
        _gt_variance: Variance for ground truth (very low).
        _fusion_count: Number of fusions performed (for stats).
    """

    def __init__(
        self,
        base_variance: float = 0.05,
        gt_variance: float = 0.001,
    ) -> None:
        """Initialize belief updater.

        Args:
            base_variance: Base variance for confidence=0 (m^2).
            gt_variance: Variance for ground truth sources (m^2).
        """
        self._beliefs: dict[str, GaussianBelief] = {}
        self._base_variance = base_variance
        self._gt_variance = gt_variance
        self._fusion_count = 0

    def update(
        self,
        object_id: str,
        position: tuple[float, float, float],
        confidence: float,
        source: str,
    ) -> GaussianBelief:
        """Update belief for an object with a new observation.

        Args:
            object_id: Object identifier.
            position: Observed (x, y, z) position.
            confidence: Observation confidence [0, 1].
            source: Source name ('ground_truth', 'vision', etc.).

        Returns:
            Updated GaussianBelief.
        """
        obs_variance = self._compute_observation_variance(confidence, source)

        if object_id not in self._beliefs:
            belief = GaussianBelief(
                mean=position,
                variance=(obs_variance, obs_variance, obs_variance),
                confidence=confidence,
                source=source,
            )
            self._beliefs[object_id] = belief
            return belief

        belief = self._beliefs[object_id]
        fused_mean, fused_var = self._fuse(
            belief.mean, belief.variance,
            position, (obs_variance, obs_variance, obs_variance),
        )

        fused_confidence = max(belief.confidence, confidence)
        if source == "ground_truth":
            fused_source = "ground_truth"
        elif belief.source == "ground_truth":
            fused_source = "ground_truth"
        elif source == "vision" and belief.source == "vision":
            fused_source = "vision"
        else:
            fused_source = "fused"

        updated = GaussianBelief(
            mean=fused_mean,
            variance=fused_var,
            confidence=fused_confidence,
            source=fused_source,
        )
        self._beliefs[object_id] = updated
        self._fusion_count += 1
        return updated

    def _compute_observation_variance(self, confidence: float, source: str) -> float:
        """Compute observation variance from confidence and source.

        Ground truth has very low variance. Vision variance scales
        inversely with confidence.
        """
        if source == "ground_truth":
            return self._gt_variance
        return self._base_variance * (1.0 - confidence) + self._gt_variance

    @staticmethod
    def _fuse(
        mean1: tuple[float, float, float],
        var1: tuple[float, float, float],
        mean2: tuple[float, float, float],
        var2: tuple[float, float, float],
    ) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        """Fuse two Gaussian estimates (per-axis Kalman update).

        For each axis i:
            fused_mean[i] = (mean1[i] * var2[i] + mean2[i] * var1[i]) / (var1[i] + var2[i])
            fused_var[i] = var1[i] * var2[i] / (var1[i] + var2[i])
        """
        fused_mean = []
        fused_var = []
        for i in range(3):
            v1, v2 = var1[i], var2[i]
            denom = v1 + v2
            if denom < 1e-10:
                fm = (mean1[i] + mean2[i]) / 2.0
                fv = max(v1, v2) * 0.5
            else:
                fm = (mean1[i] * v2 + mean2[i] * v1) / denom
                fv = v1 * v2 / denom
            fused_mean.append(fm)
            fused_var.append(fv)
        return tuple(fused_mean), tuple(fused_var)

    def get_belief(self, object_id: str) -> GaussianBelief | None:
        """Get current belief for an object."""
        return self._beliefs.get(object_id)

    def get_all_beliefs(self) -> dict[str, GaussianBelief]:
        """Get all current beliefs."""
        return dict(self._beliefs)

    def remove_belief(self, object_id: str) -> bool:
        """Remove belief for an object."""
        return self._beliefs.pop(object_id, None) is not None

    @property
    def stats(self) -> dict[str, Any]:
        """Get belief updater statistics."""
        return {
            "object_count": len(self._beliefs),
            "fusion_count": self._fusion_count,
            "avg_uncertainty": (
                sum(b.uncertainty for b in self._beliefs.values()) / len(self._beliefs)
                if self._beliefs else 0.0
            ),
        }