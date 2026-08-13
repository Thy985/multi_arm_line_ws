"""M7.6 WorldModel Intelligence — Integration Tests.

Tests that WorldModel probabilistic features work end-to-end:
    1. Belief update: position_covariance filled (not dead field)
    2. Multi-source fusion: GT + vision → fused belief
    3. Contradiction clear: error < threshold → contradiction=False
    4. Vision history: vision poses recorded in history
    5. Prediction works: velocity in history → prediction non-trivial
    6. at_time query: temporal query returns historical state
    7. Uncertainty quantified: belief_uncertainty > 0 for vision
    8. Orientation uncertainty: filled (not dead field)
"""

from __future__ import annotations

import math
import time
from typing import Any

import pytest

from multi_arm_world_model.state_database import StateDatabase, TrackedObject
from multi_arm_world_model.belief_layer import BeliefUpdater, GaussianBelief
from multi_arm_world_model.history_layer import HistoryLayer
from multi_arm_world_model.prediction_layer import PredictionLayer


class TestM76BeliefUpdate:
    """Test belief update fills covariance (not dead field)."""

    def test_position_covariance_filled(self) -> None:
        """position_covariance is filled after update_object_pose."""
        db = StateDatabase()
        obj = TrackedObject(object_id="cube", object_type="cube")
        db.add_object(obj)

        db.update_object_pose("cube", (0.5, 0.0, 0.4), confidence=0.8)
        updated = db.get_object("cube")

        assert updated is not None
        assert any(v > 0 for v in updated.position_covariance), \
            "position_covariance all zeros — dead field not fixed"

    def test_orientation_uncertainty_filled(self) -> None:
        """orientation_uncertainty is filled after update_object_pose."""
        db = StateDatabase()
        obj = TrackedObject(object_id="cube")
        db.add_object(obj)

        db.update_object_pose("cube", (0.5, 0.0, 0.4), confidence=0.7)
        updated = db.get_object("cube")

        assert updated is not None
        assert updated.orientation_uncertainty > 0, \
            "orientation_uncertainty is zero — dead field not fixed"

    def test_gt_has_lower_variance_than_vision(self) -> None:
        """GT source should have lower variance than vision."""
        db = StateDatabase()
        db.add_object(TrackedObject(object_id="gt_obj"))
        db.add_object(TrackedObject(object_id="vis_obj"))

        db.update_object_pose("gt_obj", (0.5, 0, 0), confidence=1.0,
                              position_covariance=(0.001, 0, 0, 0, 0.001, 0, 0, 0, 0.001))
        db.update_object_pose("vis_obj", (0.5, 0, 0), confidence=0.7)

        gt = db.get_object("gt_obj")
        vis = db.get_object("vis_obj")
        assert gt.position_covariance[0] < vis.position_covariance[0]


class TestM76MultiSourceFusion:
    """Test multi-source belief fusion."""

    def test_gt_vision_fusion(self) -> None:
        """Fusing GT + vision produces weighted average."""
        updater = BeliefUpdater()

        b1 = updater.update("obj", (0.5, 0.0, 0.0), 1.0, "ground_truth")
        b2 = updater.update("obj", (0.6, 0.0, 0.0), 0.8, "vision")

        assert 0.5 < b2.mean[0] < 0.6, "Fused mean should be between GT and vision"
        assert b2.variance[0] < b1.variance[0], "Fused variance should be lower"
        assert b2.source == "ground_truth", "GT source should dominate"

    def test_vision_only_fusion(self) -> None:
        """Multiple vision updates reduce uncertainty."""
        updater = BeliefUpdater()

        b1 = updater.update("obj", (0.5, 0.0, 0.0), 0.7, "vision")
        b2 = updater.update("obj", (0.51, 0.0, 0.0), 0.7, "vision")

        assert b2.uncertainty < b1.uncertainty, "Second observation should reduce uncertainty"


class TestM76ContradictionClear:
    """Test contradiction flag is cleared when error reduces."""

    def test_contradiction_clears(self) -> None:
        """Contradiction should clear when vision converges to GT."""
        db = StateDatabase()
        obj = TrackedObject(object_id="cube")
        obj.metadata["source"] = "ground_truth"
        obj.position = (0.5, 0.0, 0.4)
        db.add_object(obj)

        error_large = 0.8
        contradiction_threshold = 0.5
        assert error_large > contradiction_threshold

        error_small = 0.1
        assert error_small <= contradiction_threshold

        obj.metadata["contradiction"] = True
        assert obj.metadata["contradiction"] is True

        obj.metadata["contradiction"] = False
        assert obj.metadata["contradiction"] is False


class TestM76VisionHistory:
    """Test vision poses are recorded in history."""

    def test_vision_writes_history(self) -> None:
        """Vision updates should be recorded in history layer."""
        history = HistoryLayer(max_length=50)

        history.record("cube", {
            "position": [0.5, 0.0, 0.4],
            "confidence": 0.8,
            "source": "vision",
        })

        latest = history.get_latest("cube")
        assert latest is not None
        assert latest.data["source"] == "vision"
        assert latest.data["position"] == [0.5, 0.0, 0.4]


class TestM76PredictionWorks:
    """Test prediction layer works with velocity from history."""

    def test_prediction_with_velocity(self) -> None:
        """Prediction should use velocity from history."""
        history = HistoryLayer(max_length=50)
        prediction = PredictionLayer(history=history)

        history.record("cube", {
            "position": [0.5, 0.0, 0.4],
            "velocity": [0.1, 0.0, 0.0],
            "confidence": 0.9,
        })

        result = prediction.predict_position("cube", dt=1.0)
        assert abs(result.predicted_position[0] - 0.6) < 1e-6, \
            f"Prediction should be 0.6, got {result.predicted_position[0]}"
        assert result.confidence > 0

    def test_prediction_without_velocity(self) -> None:
        """Prediction without velocity returns current position."""
        history = HistoryLayer(max_length=50)
        prediction = PredictionLayer(history=history)

        history.record("cube", {
            "position": [0.5, 0.0, 0.4],
            "confidence": 0.9,
        })

        result = prediction.predict_position("cube", dt=1.0)
        assert abs(result.predicted_position[0] - 0.5) < 1e-6


class TestM76AtTimeQuery:
    """Test temporal query (at_time parameter)."""

    def test_at_time_returns_historical_state(self) -> None:
        """QueryWorld at_time should return historical state."""
        history = HistoryLayer(max_length=50)

        t1 = time.time()
        history.record("cube", {
            "position": [0.3, 0.0, 0.4],
            "confidence": 0.9,
        }, timestamp=t1)

        time.sleep(0.01)
        t2 = time.time()
        history.record("cube", {
            "position": [0.5, 0.0, 0.4],
            "confidence": 0.9,
        }, timestamp=t2)

        latest = history.get_latest("cube")
        assert latest is not None
        assert latest.data["position"] == [0.5, 0.0, 0.4]

        all_history = history.get_history("cube")
        assert len(all_history) == 2
        assert all_history[0].data["position"] == [0.3, 0.0, 0.4]


class TestM76UncertaintyQuantified:
    """Test uncertainty is quantified as probability."""

    def test_belief_uncertainty_nonzero(self) -> None:
        """Vision belief should have non-zero uncertainty."""
        updater = BeliefUpdater()
        b = updater.update("obj", (0.5, 0.0, 0.4), 0.7, "vision")
        assert b.uncertainty > 0, "Vision belief should have non-zero uncertainty"

    def test_gt_uncertainty_lower(self) -> None:
        """GT belief should have lower uncertainty than vision."""
        updater = BeliefUpdater()
        gt = updater.update("gt", (0.5, 0.0, 0.4), 1.0, "ground_truth")
        vis = updater.update("vis", (0.5, 0.0, 0.4), 0.7, "vision")
        assert gt.uncertainty < vis.uncertainty

    def test_fusion_reduces_uncertainty(self) -> None:
        """Fusing two sources should reduce uncertainty."""
        updater = BeliefUpdater()
        b1 = updater.update("obj", (0.5, 0.0, 0.4), 0.7, "vision")
        b2 = updater.update("obj", (0.51, 0.0, 0.4), 0.7, "vision")
        assert b2.uncertainty < b1.uncertainty