#!/usr/bin/env python3
"""
Time Manager for multi-arm coordination.

Predicts trajectory execution times and detects time-window conflicts
when multiple arms request the same zone. Enables proactive scheduling
to avoid collisions before they happen.
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Optional, Dict
import time


class WindowStatus(Enum):
    """Status of a time window."""
    SCHEDULED = auto()   # Planned but not yet executing
    EXECUTING = auto()   # Currently running
    COMPLETED = auto()   # Finished
    CANCELLED = auto()   # Cancelled by user or conflict resolution


@dataclass
class TimeWindow:
    """
    Represents a time interval during which an arm occupies a zone.
    
    Timeline:
        start_time          end_time
            |                  |
            v                  v
        ---[==== EXECUTING ====]---
            ^                  ^
        trajectory start   trajectory end
    """
    arm_name: str
    zone_name: str
    start_time: float           # Absolute timestamp (time.time())
    duration: float             # Expected duration in seconds
    position_name: str = ''     # Target position name
    status: WindowStatus = WindowStatus.SCHEDULED
    scheduled_id: int = 0       # Unique ID for tracking
    
    @property
    def end_time(self) -> float:
        return self.start_time + self.duration
    
    def overlaps(self, other: 'TimeWindow') -> bool:
        """Check if this window overlaps with another (same zone only)."""
        if self.zone_name != other.zone_name:
            return False
        return self.start_time < other.end_time and other.start_time < self.end_time
    
    def time_until_start(self) -> float:
        """Seconds until this window starts (negative if already started)."""
        return self.start_time - time.time()
    
    def remaining(self) -> float:
        """Seconds remaining in this window."""
        return max(0.0, self.end_time - time.time())
    
    def is_active(self) -> bool:
        """Whether this window is currently active (scheduled or executing)."""
        return self.status in (WindowStatus.SCHEDULED, WindowStatus.EXECUTING)
    
    def __repr__(self):
        return (f"TimeWindow({self.arm_name}→{self.zone_name} "
                f"[{self.position_name}] "
                f"{self.duration:.1f}s status={self.status.name})")


@dataclass
class Conflict:
    """Describes a time-window conflict between two arms."""
    arm_a: str
    arm_b: str
    zone_name: str
    overlap_start: float        # When the overlap begins
    overlap_duration: float     # How long the overlap lasts
    window_a: TimeWindow
    window_b: TimeWindow
    
    def __repr__(self):
        return (f"Conflict({self.arm_a}↔{self.arm_b} @{self.zone_name} "
                f"overlap={self.overlap_duration:.1f}s)")


@dataclass
class ScheduleResult:
    """Result of scheduling a new time window."""
    granted: bool
    window: Optional[TimeWindow] = None
    conflict: Optional[Conflict] = None
    suggested_delay: float = 0.0     # Seconds to delay to avoid conflict
    message: str = ''


# =====================================================================
# Trajectory Duration Estimation
# =====================================================================

# Default trajectory durations by position name (seconds)
# These can be tuned based on actual execution times
POSITION_DURATIONS = {
    'home': 3.0,
    'ready': 3.0,
    'extended': 4.0,
    'left': 3.5,
    'right': 3.5,
}

# Safety margin added to predicted duration (seconds)
SAFETY_MARGIN = 0.5


def predict_duration(position_name: str, base_duration: float = 3.0) -> float:
    """
    Predict how long a trajectory to a given position will take.
    
    Args:
        position_name: Target position name
        base_duration: Default duration if position not in lookup table
    
    Returns:
        Predicted duration in seconds (including safety margin)
    """
    duration = POSITION_DURATIONS.get(position_name, base_duration)
    return duration + SAFETY_MARGIN


# =====================================================================
# Time Manager
# =====================================================================

class TimeManager:
    """
    Manages time windows for zone occupancy.
    
    Core responsibilities:
    1. Schedule new time windows for arm movements
    2. Detect conflicts when two arms target the same zone simultaneously
    3. Suggest delay durations to avoid conflicts
    4. Track window lifecycle (scheduled -> executing -> completed)
    
    Usage:
        tm = TimeManager()
        
        # Schedule arm1 to enter zone_a in 2 seconds
        result = tm.schedule('arm1', 'zone_a', start_delay=2.0, 
                            position_name='ready', duration=3.0)
        
        if result.conflict:
            print(f"Conflict detected: {result.conflict}")
            print(f"Suggested delay: {result.suggested_delay:.1f}s")
    """
    
    def __init__(self):
        self._windows: List[TimeWindow] = []
        self._next_id = 1
        self._current_time = time.time()  # For testing/mockability
    
    def now(self) -> float:
        """Get current time (overridable for testing)."""
        return time.time()
    
    def schedule(
        self,
        arm_name: str,
        zone_name: str,
        duration: float = 3.0,
        position_name: str = '',
        start_delay: float = 0.0
    ) -> ScheduleResult:
        """
        Schedule a new time window for an arm to occupy a zone.
        
        Args:
            arm_name: Which arm (e.g. 'arm1')
            zone_name: Target zone (e.g. 'zone_a')
            duration: How long the arm will occupy the zone
            position_name: Target position (for duration estimation)
            start_delay: Seconds from now when the window starts
        
        Returns:
            ScheduleResult with granted status, conflict info, and suggested delay
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
        
        # Check for conflicts with existing active windows
        conflict = self._detect_conflict(new_window)
        
        if conflict:
            # Calculate suggested delay to avoid conflict
            conflicting_window = conflict.window_b
            suggested_delay = conflicting_window.end_time - start_time + SAFETY_MARGIN
            
            return ScheduleResult(
                granted=False,
                window=new_window,
                conflict=conflict,
                suggested_delay=max(0.0, suggested_delay),
                message=f"Conflict with {conflicting_window.arm_name} in {zone_name}"
            )
        else:
            # No conflict, add to schedule
            self._windows.append(new_window)
            return ScheduleResult(
                granted=True,
                window=new_window,
                message=f"Scheduled {arm_name} in {zone_name}"
            )
    
    def cancel(self, arm_name: str) -> bool:
        """Cancel all scheduled (non-executing) windows for an arm."""
        cancelled = False
        for w in self._windows:
            if w.arm_name == arm_name and w.status == WindowStatus.SCHEDULED:
                w.status = WindowStatus.CANCELLED
                cancelled = True
        return cancelled
    
    def start_executing(self, arm_name: str):
        """Mark the scheduled window for an arm as executing."""
        for w in self._windows:
            if (w.arm_name == arm_name and 
                w.status == WindowStatus.SCHEDULED and
                w.start_time <= self.now()):
                w.status = WindowStatus.EXECUTING
    
    def complete(self, arm_name: str):
        """Mark the executing window for an arm as completed."""
        for w in self._windows:
            if (w.arm_name == arm_name and 
                w.status == WindowStatus.EXECUTING):
                w.status = WindowStatus.COMPLETED
    
    def get_active_windows(self, zone_name: Optional[str] = None) -> List[TimeWindow]:
        """Get all active (scheduled/executing) windows, optionally filtered by zone."""
        result = []
        for w in self._windows:
            if w.is_active():
                if zone_name is None or w.zone_name == zone_name:
                    result.append(w)
        return sorted(result, key=lambda w: w.start_time)
    
    def get_zone_end_time(self, zone_name: str) -> float:
        """
        Get the earliest time when a zone will be free.
        
        Returns:
            Latest end_time of any active window in this zone,
            or current time if no active windows.
        """
        active = self.get_active_windows(zone_name)
        if not active:
            return self.now()
        return max(w.end_time for w in active)
    
    def get_arm_end_time(self, arm_name: str) -> float:
        """
        Get the earliest time when an arm will be free.
        
        Returns:
            Latest end_time of any active window for this arm,
            or current time if no active windows.
        """
        active = [w for w in self._windows if w.is_active() and w.arm_name == arm_name]
        if not active:
            return self.now()
        return max(w.end_time for w in active)
    
    def cleanup(self):
        """Remove completed/cancelled windows older than 60 seconds."""
        cutoff = self.now() - 60.0
        self._windows = [
            w for w in self._windows
            if w.is_active() or w.start_time > cutoff
        ]
    
    def print_schedule(self):
        """Print all active windows (for debugging)."""
        active = self.get_active_windows()
        if not active:
            return "  No active time windows"
        lines = []
        for w in active:
            remaining = w.remaining()
            lines.append(
                f"  {w.arm_name} → {w.zone_name} [{w.position_name}] "
                f"duration={w.duration:.1f}s remaining={remaining:.1f}s "
                f"status={w.status.name}"
            )
        return '\n'.join(lines)
    
    # =====================================================================
    # Internal: Conflict Detection
    # =====================================================================
    
    def _detect_conflict(self, new_window: TimeWindow) -> Optional[Conflict]:
        """
        Check if a new window conflicts with any existing active window in the same zone.
        
        Returns:
            Conflict object if conflict found, None otherwise
        """
        for existing in self._windows:
            if not existing.is_active():
                continue
            if existing.zone_name != new_window.zone_name:
                continue
            if existing.arm_name == new_window.arm_name:
                continue  # Same arm, no conflict
            
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
