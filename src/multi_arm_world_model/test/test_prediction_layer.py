"""Tests for PredictionLayer."""

import pytest

from multi_arm_world_model.history_layer import HistoryLayer
from multi_arm_world_model.prediction_layer import PredictionLayer, PredictionResult


class TestPredictionLayer:
    """Tests for PredictionLayer."""

    def test_predict_no_history(self) -> None:
        history = HistoryLayer()
        pred = PredictionLayer(history)
        result = pred.predict_position("cube")
        assert result.confidence == 0.0

    def test_predict_static(self) -> None:
        history = HistoryLayer()
        history.record("cube", {"position": [0.5, 0.0, 0.1], "velocity": [0, 0, 0]})
        pred = PredictionLayer(history)
        result = pred.predict_position("cube", dt=0.5)
        assert result.predicted_position == pytest.approx([0.5, 0.0, 0.1])

    def test_predict_moving(self) -> None:
        history = HistoryLayer()
        history.record("cube", {"position": [0.0, 0.0, 0.0], "velocity": [1.0, 0.0, 0.0]})
        pred = PredictionLayer(history)
        result = pred.predict_position("cube", dt=2.0)
        assert result.predicted_position[0] == pytest.approx(2.0)

    def test_predict_confidence_decreases(self) -> None:
        history = HistoryLayer()
        history.record("cube", {"position": [0, 0, 0], "velocity": [0, 0, 0]})
        pred = PredictionLayer(history)
        r1 = pred.predict_position("cube", dt=0.1)
        r2 = pred.predict_position("cube", dt=1.0)
        assert r1.confidence > r2.confidence

    def test_collision_risk_no_obstacles(self) -> None:
        history = HistoryLayer()
        pred = PredictionLayer(history)
        risk = pred.estimate_collision_risk("cube", [1.0, 0.0, 0.0])
        assert risk == 0.0

    def test_collision_risk_with_obstacle(self) -> None:
        history = HistoryLayer()
        history.record("cube", {"position": [0.0, 0.0, 0.0]})
        pred = PredictionLayer(history)
        risk = pred.estimate_collision_risk(
            "cube", [1.0, 0.0, 0.0],
            obstacles={"obs": [0.5, 0.0, 0.0]},
            threshold=0.1,
        )
        assert risk > 0.0

    def test_arrival_time_no_movement(self) -> None:
        history = HistoryLayer()
        history.record("cube", {"position": [0, 0, 0], "velocity": [0, 0, 0]})
        pred = PredictionLayer(history)
        time = pred.estimate_arrival_time("cube", [0, 0, 0])
        assert time == 0.0

    def test_arrival_time_moving(self) -> None:
        history = HistoryLayer()
        history.record("cube", {"position": [0, 0, 0], "velocity": [1.0, 0, 0]})
        pred = PredictionLayer(history)
        time = pred.estimate_arrival_time("cube", [2.0, 0, 0])
        assert time == pytest.approx(2.0)

    def test_predict_all(self) -> None:
        history = HistoryLayer()
        history.record("a", {"position": [0, 0, 0], "velocity": [1, 0, 0]})
        history.record("b", {"position": [1, 0, 0], "velocity": [0, 1, 0]})
        pred = PredictionLayer(history)
        results = pred.predict_all(["a", "b"], dt=1.0)
        assert "a" in results
        assert "b" in results
        assert results["a"].predicted_position[0] == pytest.approx(1.0)