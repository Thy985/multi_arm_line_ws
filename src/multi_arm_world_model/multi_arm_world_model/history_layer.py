"""History Layer — store state time series for trend analysis."""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any


@dataclass
class HistoryEntry:
    """A single history entry."""

    timestamp: float
    data: dict[str, Any] = field(default_factory=dict)


class HistoryLayer:
    """History Layer of WorldModel — state time series storage.

    Stores position/joint history for trend analysis and debugging.
    Uses ring buffer (deque) for memory efficiency.
    """

    def __init__(self, max_length: int = 100) -> None:
        """Initialize history layer.

        Args:
            max_length: Maximum entries per entity.

        """
        self._max_length = max_length
        self._histories: dict[str, deque[HistoryEntry]] = {}

    def record(
        self,
        entity_id: str,
        data: dict[str, Any],
        timestamp: float | None = None,
    ) -> None:
        """Record a state snapshot for an entity.

        Args:
            entity_id: Entity ID.
            data: State data dict.
            timestamp: Timestamp (default: now).

        """
        if entity_id not in self._histories:
            self._histories[entity_id] = deque(maxlen=self._max_length)

        ts = timestamp if timestamp is not None else time.time()
        self._histories[entity_id].append(HistoryEntry(timestamp=ts, data=data))

    def get_history(
        self,
        entity_id: str,
        last_n: int = 0,
    ) -> list[HistoryEntry]:
        """Get history for an entity.

        Args:
            entity_id: Entity ID.
            last_n: Return last N entries (0 = all).

        Returns:
            List of history entries.

        """
        history = self._histories.get(entity_id, deque())
        if last_n > 0:
            return list(history)[-last_n:]
        return list(history)

    def get_latest(self, entity_id: str) -> HistoryEntry | None:
        """Get latest history entry for an entity.

        Args:
            entity_id: Entity ID.

        Returns:
            Latest entry or None.

        """
        history = self._histories.get(entity_id, deque())
        return history[-1] if history else None

    def get_trend(
        self,
        entity_id: str,
        key: str,
        window: int = 10,
    ) -> float:
        """Calculate trend (rate of change) for a numeric value.

        Args:
            entity_id: Entity ID.
            key: Data key to analyze.
            window: Number of entries to consider.

        Returns:
            Trend value (positive = increasing).

        """
        history = self.get_history(entity_id, last_n=window + 1)
        if len(history) < 2:
            return 0.0

        values: list[float] = []
        for entry in history:
            val = entry.data.get(key)
            if isinstance(val, (int, float)):
                values.append(float(val))

        if len(values) < 2:
            return 0.0

        return (values[-1] - values[0]) / (len(values) - 1)

    def clear(self, entity_id: str) -> None:
        """Clear history for an entity.

        Args:
            entity_id: Entity ID.

        """
        self._histories.pop(entity_id, None)

    def clear_all(self) -> None:
        """Clear all histories."""
        self._histories.clear()

    def get_entity_ids(self) -> list[str]:
        """Get all entity IDs with history.

        Returns:
            List of entity IDs.

        """
        return list(self._histories.keys())

    def get_entry_count(self, entity_id: str) -> int:
        """Get number of history entries for an entity.

        Args:
            entity_id: Entity ID.

        Returns:
            Entry count.

        """
        return len(self._histories.get(entity_id, deque()))