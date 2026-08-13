"""M7.6 WorldModel Intelligence — Belief Layer Unit Tests.

Tests GaussianBelief and BeliefUpdater for probabilistic state estimation.
"""

from __future__ import annotations

import math
import pytest

from multi_arm_world_model.belief_layer import GaussianBelief, BeliefUpdater


class TestGaussianBelief:
    """Test GaussianBelief dataclass."""

    def test_creation(self) -> None:
        b = GaussianBelief(mean=(1.0, 2.0, 3.0), variance=(0.01, 0.02, 0.03))
        assert b.mean == (1.0, 2.0, 3.0)
        assert b.variance == (0.01, 0.02, 0.03)
        assert b.confidence == 1.0

    def test_uncertainty(self) -> None:
        b = GaussianBelief(variance=(0.03, 0.03, 0.03))
        assert abs(b.uncertainty - 0.03) < 1e-6

    def test_std_dev(self) -> None:
        b = GaussianBelief(variance=(0.04, 0.09, 0.16))
        std = b.std_dev
        assert abs(std[0] - 0.2) < 1e-6
        assert abs(std[1] - 0.3) < 1e-6
        assert abs(std[2] - 0.4) < 1e-6

    def test_predict(self) -> None:
        b = GaussianBelief(mean=(0.0, 0.0, 0.0), variance=(0.01, 0.01, 0.01))
        predicted = b.predict(velocity=(1.0, 0.0, 0.0), dt=2.0)
        assert abs(predicted.mean[0] - 2.0) < 1e-6
        assert predicted.mean[1] == 0.0
        assert predicted.variance[0] > b.variance[0]

    def test_to_covariance_flat(self) -> None:
        b = GaussianBelief(variance=(0.1, 0.2, 0.3))
        cov = b.to_covariance_flat()
        assert cov == (0.1, 0.0, 0.0, 0.0, 0.2, 0.0, 0.0, 0.0, 0.3)


class TestBeliefUpdater:
    """Test BeliefUpdater multi-source fusion."""

    def test_single_source_update(self) -> None:
        updater = BeliefUpdater()
        belief = updater.update("obj1", (1.0, 2.0, 3.0), 0.9, "vision")
        assert belief.mean == (1.0, 2.0, 3.0)
        assert belief.source == "vision"
        assert belief.confidence == 0.9

    def test_gt_has_low_variance(self) -> None:
        updater = BeliefUpdater()
        gt_belief = updater.update("obj1", (1.0, 2.0, 3.0), 1.0, "ground_truth")
        vis_belief = updater.update("obj2", (1.0, 2.0, 3.0), 0.8, "vision")
        assert gt_belief.variance[0] < vis_belief.variance[0]

    def test_multi_source_fusion(self) -> None:
        updater = BeliefUpdater()
        updater.update("obj1", (0.5, 0.0, 0.0), 1.0, "ground_truth")
        fused = updater.update("obj1", (0.6, 0.0, 0.0), 0.8, "vision")
        assert 0.5 < fused.mean[0] < 0.6
        assert fused.variance[0] < 0.01
        assert fused.source == "ground_truth"

    def test_fusion_reduces_uncertainty(self) -> None:
        updater = BeliefUpdater()
        b1 = updater.update("obj1", (1.0, 0.0, 0.0), 0.7, "vision")
        b2 = updater.update("obj1", (1.1, 0.0, 0.0), 0.7, "vision")
        assert b2.uncertainty < b1.uncertainty

    def test_confidence_zero_high_variance(self) -> None:
        updater = BeliefUpdater(base_variance=0.1)
        b = updater.update("obj1", (1.0, 0.0, 0.0), 0.0, "vision")
        assert b.variance[0] > 0.05

    def test_stats(self) -> None:
        updater = BeliefUpdater()
        updater.update("a", (0, 0, 0), 0.9, "vision")
        updater.update("b", (1, 1, 1), 0.8, "vision")
        stats = updater.stats
        assert stats["object_count"] == 2
        assert stats["fusion_count"] == 0
        assert stats["avg_uncertainty"] > 0

    def test_remove_belief(self) -> None:
        updater = BeliefUpdater()
        updater.update("obj1", (0, 0, 0), 0.9, "vision")
        assert updater.remove_belief("obj1")
        assert updater.get_belief("obj1") is None

    def test_predict_forward(self) -> None:
        updater = BeliefUpdater()
        b = updater.update("obj1", (0, 0, 0), 0.9, "vision")
        predicted = b.predict(velocity=(1, 0, 0), dt=1.0)
        assert abs(predicted.mean[0] - 1.0) < 1e-6
        assert predicted.variance[0] > b.variance[0]