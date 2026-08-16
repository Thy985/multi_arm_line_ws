"""
Arm state machine and zone definitions for multi-arm coordination.
"""

from enum import Enum, auto
from dataclasses import dataclass, field
from typing import List, Optional
import time


class ArmState(Enum):
    """State machine for each arm."""
    IDLE = auto()       # 空闲，可接收任务
    REQUESTING = auto() # 已发送请求，等待授权
    QUEUED = auto()     # 排队等待（zone被占用）
    WORKING = auto()    # 执行中
    ERROR = auto()      # 故障/超时


class ZoneType(Enum):
    """Zone classification."""
    SHARED = auto()      # 共享区域，多臂不能同时进入
    EXCLUSIVE = auto()   # 独占区域，同一时刻只允许一臂


@dataclass
class Zone:
    """Represents a shared workspace zone."""
    name: str
    zone_type: ZoneType = ZoneType.SHARED
    occupied_by: Optional[str] = None  # arm name or None
    waiting_queue: List[str] = field(default_factory=list)  # arm names waiting
    created_at: float = field(default_factory=time.time)

    def is_free(self) -> bool:
        return self.occupied_by is None

    def request_entry(self, arm_name: str) -> bool:
        """Request to enter zone. Returns True if granted immediately."""
        if self.is_free():
            self.occupied_by = arm_name
            return True
        else:
            if arm_name not in self.waiting_queue:
                self.waiting_queue.append(arm_name)
            return False

    def release(self, arm_name: str):
        """Release zone, grant to next in queue if any."""
        if self.occupied_by == arm_name:
            self.occupied_by = None
            # Remove the releasing arm from queue if present
            if arm_name in self.waiting_queue:
                self.waiting_queue.remove(arm_name)
            if self.waiting_queue:
                next_arm = self.waiting_queue.pop(0)
                self.occupied_by = next_arm
                return next_arm
        return None

    def cancel_request(self, arm_name: str):
        """Cancel a queued request."""
        if arm_name in self.waiting_queue:
            self.waiting_queue.remove(arm_name)


@dataclass
class ArmStatus:
    """Runtime status of an arm."""
    name: str
    state: ArmState = ArmState.IDLE
    current_zone: Optional[str] = None  # zone currently in
    requested_zone: Optional[str] = None  # zone requested to enter
    requested_position: Optional[str] = None  # position requested (preserved for queued trigger)
    goal_start_time: Optional[float] = None
    error_message: Optional[str] = None

    def reset(self):
        """Reset to idle state."""
        self.state = ArmState.IDLE
        self.current_zone = None
        self.requested_zone = None
        self.requested_position = None
        self.goal_start_time = None
        self.error_message = None


# Predefined workspace zones
# 这些坐标对应 UR5e 工作空间的不同区域
DEFAULT_ZONES = {
    "zone_a": Zone(name="zone_a", zone_type=ZoneType.SHARED),  # 中央焊接区
    "zone_b": Zone(name="zone_b", zone_type=ZoneType.SHARED),  # 左侧工位
    "zone_c": Zone(name="zone_c", zone_type=ZoneType.SHARED),  # 右侧工位
    "home": Zone(name="home", zone_type=ZoneType.EXCLUSIVE),   # 归位区（安全）
}


# Joint names for each arm (with prefix)
ARM_JOINT_NAMES = {
    "left_arm": [
        "left_arm_shoulder_pan_joint",
        "left_arm_shoulder_lift_joint",
        "left_arm_elbow_joint",
        "left_arm_wrist_1_joint",
        "left_arm_wrist_2_joint",
        "left_arm_wrist_3_joint",
    ],
    "right_arm": [
        "right_arm_shoulder_pan_joint",
        "right_arm_shoulder_lift_joint",
        "right_arm_elbow_joint",
        "right_arm_wrist_1_joint",
        "right_arm_wrist_2_joint",
        "right_arm_wrist_3_joint",
    ],
}


# Preset joint trajectories (for testing)
PRESET_POSITIONS = {
    "home": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    "ready": [0.0, -1.57, 1.57, 0.0, 0.0, 0.0],
    "extended": [0.0, -0.5, 2.5, 0.5, 0.5, 0.0],
    "left": [-1.57, -1.0, 1.5, 0.0, 0.5, 0.0],
    "right": [1.57, -1.0, 1.5, 0.0, 0.5, 0.0],
}