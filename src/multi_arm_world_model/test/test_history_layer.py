"""Tests for HistoryLayer."""

import time

import pytest

from multi_arm_world_model.history_layer import HistoryLayer, HistoryEntry


class TestHistoryLayer:
    """Tests for HistoryLayer."""

    def test_record_and_get(self) -> None:
        layer = HistoryLayer(max_length=10)
        layer.record("cube", {"position": [0.5, 0.5, 0.1]})
        history = layer.get_history("cube")
        assert len(history) == 1
        assert history[0].data["position"] == [0.5, 0.5, 0.1]

    def test_max_length(self) -> None:
        layer = HistoryLayer(max_length=3)
        for i in range(5):
            layer.record("cube", {"i": i})
        history = layer.get_history("cube")
        assert len(history) == 3
        assert history[0].data["i"] == 2

    def test_get_latest(self) -> None:
        layer = HistoryLayer()
        layer.record("cube", {"position": [0.0, 0.0, 0.0]})
        layer.record("cube", {"position": [0.1, 0.0, 0.0]})
        latest = layer.get_latest("cube")
        assert latest is not None
        assert latest.data["position"] == [0.1, 0.0, 0.0]

    def test_get_latest_nonexistent(self) -> None:
        layer = HistoryLayer()
        assert layer.get_latest("nonexistent") is None

    def test_get_trend(self) -> None:
        layer = HistoryLayer()
        for i in range(5):
            layer.record("cube", {"x": float(i)})
        trend = layer.get_trend("cube", "x")
        assert trend == pytest.approx(1.0)

    def test_get_trend_no_data(self) -> None:
        layer = HistoryLayer()
        trend = layer.get_trend("cube", "x")
        assert trend == 0.0

    def test_clear(self) -> None:
        layer = HistoryLayer()
        layer.record("cube", {"position": [0, 0, 0]})
        layer.clear("cube")
        assert len(layer.get_history("cube")) == 0

    def test_clear_all(self) -> None:
        layer = HistoryLayer()
        layer.record("a", {"x": 1})
        layer.record("b", {"x": 2})
        layer.clear_all()
        assert layer.get_entity_ids() == []

    def test_get_entity_ids(self) -> None:
        layer = HistoryLayer()
        layer.record("a", {"x": 1})
        layer.record("b", {"x": 2})
        ids = layer.get_entity_ids()
        assert "a" in ids
        assert "b" in ids

    def test_get_entry_count(self) -> None:
        layer = HistoryLayer()
        for i in range(3):
            layer.record("cube", {"i": i})
        assert layer.get_entry_count("cube") == 3

    def test_get_history_last_n(self) -> None:
        layer = HistoryLayer()
        for i in range(5):
            layer.record("cube", {"i": i})
        history = layer.get_history("cube", last_n=2)
        assert len(history) == 2
        assert history[0].data["i"] == 3