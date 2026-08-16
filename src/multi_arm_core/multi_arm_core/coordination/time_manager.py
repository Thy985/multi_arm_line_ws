"""TimeManager for multi-arm time-window scheduling and conflict detection."""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Optional
import time as _time


class WindowStatus(Enum):
    """Status of a time window."""
    SCHEDULED = auto()
    EXECUTING = auto()
    COMPLETED = auto()
    CANCELLED = auto()


@dataclass
class TimeWindow:
    """Represents a time interval during which an arm occupies a zone."""
    arm_name: str
    zone_name: str
    start_time: float
    duration: float
    position_name: str = ""
    status: WindowStatus = WindowStatus.SCHEDULED
    scheduled_id: int = 0

    @property
    def end_time(self) -> float:
        return self.start_time + self.duration

    def overlaps(self, other: "TimeWindow") -> bool:
        """Check if this window overlaps with another in the same zone."""
        if self.zone_name != other.zone_name:
            return False
        return self.start_time < other.end_time and other.start_time < self.end_time

    def is_active(self) -> bool:
        """Whether this window is currently active."""
        return self.status in (WindowStatus.SCHEDULED, WindowStatus.EXECUTING)


@dataclass
class Conflict:
    """Describes a time-window conflict between two arms."""
    arm_a: str
    arm_b: str
    zone_name: str
    overlap_start: float
    overlap_duration: float
    window_a: TimeWindow
    window_b: TimeWindow


@dataclass
class ScheduleResult:
    """Result of scheduling a new time window."""
    granted: bool
    window: Optional[TimeWindow] = None
    conflict: Optional[Conflict] = None
    suggested_delay: float = 0.0
    message: str = ""


SAFETY_MARGIN = 0.5

POSITION_DURATIONS = {
    "home": 3.0,
    "ready": 3.0,
    "extended": 4.0,
    "left": 3.5,
    "right": 3.5,
}


def predict_duration(position_name: str, base_duration: float = 3.0) -> float:
    """Predict trajectory duration including safety margin.

    Args:
        position_name: Target position name.
        base_duration: Default duration if position not in lookup table.

    Returns:
        Predicted duration in seconds (including safety margin).
    """
    duration = POSITION_DURATIONS.get(position_name, base_duration)
    return duration + SAFETY_MARGIN


class TimeManager:
    """Manages time windows for zone occupancy and conflict detection.

    Core responsibilities:
    1. Schedule new time windows for arm movements
    2. Detect conflicts when two arms target the same zone simultaneously
    3. Suggest delay durations to avoid conflicts
    4. Track window lifecycle (scheduled -> executing -> completed)
    """

    def __init__(self) -> None:
        self._windows: List[TimeWindow] = []
        self._next_id = 1

    def now(self) -> float:
        """Get current time (overridable for testing)."""
        return _time.time()

    def schedule(
        self,
        arm_name: str,
        zone_name: str,
        duration: float = 3.0,
        position_name: str = "",
        start_delay: float = 0.0,
    ) -> ScheduleResult:
        """Schedule a new time window for an arm to occupy a zone.

        Args:
            arm_name: Which arm (e.g. 'left_arm').
            zone_name: Target zone (e.g. 'zone_a').
            duration: How long the arm will occupy the zone.
            position_name: Target position (for duration estimation).
            start_delay: Seconds from now when the window starts.

        Returns:
            ScheduleResult with granted status, conflict info, and suggested delay.
        """
        start_time = self.now() + start_delay

        new_window = TimeWindow(
            arm_name=arm_name,
            zone_name=zone_name,
            start_time=start_time,
            duration=duration,
            position_name=position_name,
            status=WindowStatus.SCHEDULED,
            scheduled_id=self._next_id,
        )
        self._next_id += 1

        conflict = self._detect_conflict(new_window)

        if conflict:
            conflicting_window = conflict.window_b
            suggested_delay = conflicting_window.end_time - start_time + SAFETY_MARGIN

            return ScheduleResult(
                granted=False,
                window=new_window,
                conflict=conflict,
                suggested_delay=max(0.0, suggested_delay),
                message=f"Conflict with {conflicting_window.arm_name} in {zone_name}",
            )

        self._windows.append(new_window)
        return ScheduleResult(
            granted=True,
            window=new_window,
            message=f"Scheduled {arm_name} in {zone_name}",
        )

    def cancel(self, arm_name: str) -> bool:
        """Cancel all scheduled (non-executing) windows for an arm."""
        cancelled = False
        for w in self._windows:
            if w.arm_name == arm_name and w.status == WindowStatus.SCHEDULED:
                w.status = WindowStatus.CANCELLED
                cancelled = True
        return cancelled

    def start_executing(self, arm_name: str) -> None:
        """Mark the scheduled window for an arm as executing."""
        for w in self._windows:
            if (
                w.arm_name == arm_name
                and w.status == WindowStatus.SCHEDULED
                and w.start_time <= self.now()
            ):
                w.status = WindowStatus.EXECUTING

    def complete(self, arm_name: str) -> None:
        """Mark the executing window for an arm as completed."""
        for w in self._windows:
            if w.arm_name == arm_name and w.status == WindowStatus.EXECUTING:
                w.status = WindowStatus.COMPLETED

    def get_active_windows(self, zone_name: Optional[str] = None) -> List[TimeWindow]:
        """Get all active windows, optionally filtered by zone."""
        result = []
        for w in self._windows:
            if w.is_active():
                if zone_name is None or w.zone_name == zone_name:
                    result.append(w)
        return sorted(result, key=lambda w: w.start_time)

    def get_zone_end_time(self, zone_name: str) -> float:
        """Get the earliest time when a zone will be free."""
        active = self.get_active_windows(zone_name)
        if not active:
            return self.now()
        return max(w.end_time for w in active)

    def get_arm_end_time(self, arm_name: str) -> float:
        """Get the earliest time when an arm will be free."""
        active = [w for w in self._windows if w.is_active() and w.arm_name == arm_name]
        if not active:
            return self.now()
        return max(w.end_time for w in active)

    def cleanup(self) -> None:
        """Remove completed/cancelled windows older than 60 seconds."""
        cutoff = self.now() - 60.0
        self._windows = [
            w for w in self._windows if w.is_active() or w.start_time > cutoff
        ]

    def _detect_conflict(self, new_window: TimeWindow) -> Optional[Conflict]:
        """Check if a new window conflicts with any existing active window."""
        for existing in self._windows:
            if not existing.is_active():
                continue
            if existing.zone_name != new_window.zone_name:
                continue
            if existing.arm_name == new_window.arm_name:
                continue

            if new_window.overlaps(existing):
                overlap_start = max(new_window.start_time, existing.start_time)
                overlap_end = min(new_window.end_time, existing.end_time)
                overlap_duration = overlap_end - overlap_start

                return Conflict(
                    arm_a=new_window.arm_name,
                    arm_b=existing.arm_name,
                    zone_name=new_window.zone_name,
                    overlap_start=overlap_start,
                    overlap_duration=overlap_duration,
                    window_a=new_window,
                    window_b=existing,
                )

        return None