"""Gripper Controller — open/close/attach/detach for Robotiq 2F-85."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class GripperState(Enum):
    """Gripper state."""

    OPEN = "open"
    CLOSED = "closed"
    MOVING = "moving"
    UNKNOWN = "unknown"


@dataclass
class GripperStatus:
    """Status of a gripper."""

    arm_name: str
    state: GripperState = GripperState.UNKNOWN
    position: float = 0.0
    force: float = 0.0
    attached_object: str = ""
    max_opening: float = 0.085
    temperature: float = 25.0


class GripperController:
    """Controller for Robotiq 2F-85 gripper.

    Provides:
    - open/close: gripper finger control
    - attach/detach: Gazebo物理附着 (object ↔ gripper)
    - force feedback: grip force monitoring
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """Initialize gripper controller.

        Args:
            config: Configuration dict with max_opening, max_force, etc.

        """
        self._config = config or {}
        self._max_opening = self._config.get("max_opening_mm", 85) / 1000.0
        self._max_force = self._config.get("max_force_n", 100.0)
        self._close_threshold = self._config.get("close_threshold", 0.01)
        self._grippers: dict[str, GripperStatus] = {}

    def register_gripper(self, arm_name: str) -> None:
        """Register a gripper for an arm.

        Args:
            arm_name: Arm name (e.g., "arm1").

        """
        self._grippers[arm_name] = GripperStatus(
            arm_name=arm_name,
            state=GripperState.OPEN,
            position=self._max_opening,
            max_opening=self._max_opening,
        )

    def open(self, arm_name: str) -> tuple[bool, str]:
        """Open the gripper.

        Args:
            arm_name: Arm name.

        Returns:
            Tuple of (success, message).

        """
        status = self._grippers.get(arm_name)
        if status is None:
            return False, f"Gripper not registered: {arm_name}"

        if status.attached_object:
            return False, f"Object attached: {status.attached_object}. Detach first."

        status.state = GripperState.OPEN
        status.position = self._max_opening
        status.force = 0.0
        return True, "Gripper opened"

    def close(self, arm_name: str, force: float = 0.0) -> tuple[bool, str]:
        """Close the gripper.

        Args:
            arm_name: Arm name.
            force: Closing force in Newton.

        Returns:
            Tuple of (success, message).

        """
        status = self._grippers.get(arm_name)
        if status is None:
            return False, f"Gripper not registered: {arm_name}"

        actual_force = min(force, self._max_force)
        status.state = GripperState.CLOSED
        status.position = 0.0
        status.force = actual_force
        return True, f"Gripper closed with {actual_force}N"

    def attach(
        self, arm_name: str, object_id: str
    ) -> tuple[bool, str]:
        """Attach object to gripper (Gazebo物理附着).

        Args:
            arm_name: Arm name.
            object_id: Object to attach.

        Returns:
            Tuple of (success, message).

        """
        status = self._grippers.get(arm_name)
        if status is None:
            return False, f"Gripper not registered: {arm_name}"

        if status.state != GripperState.CLOSED:
            return False, "Gripper must be closed before attach"

        if status.attached_object:
            return False, f"Already attached: {status.attached_object}"

        status.attached_object = object_id
        return True, f"Object {object_id} attached to {arm_name}"

    def detach(self, arm_name: str) -> tuple[bool, str]:
        """Detach object from gripper.

        Args:
            arm_name: Arm name.

        Returns:
            Tuple of (success, message).

        """
        status = self._grippers.get(arm_name)
        if status is None:
            return False, f"Gripper not registered: {arm_name}"

        if not status.attached_object:
            return False, "No object attached"

        obj = status.attached_object
        status.attached_object = ""
        return True, f"Object {obj} detached from {arm_name}"

    def get_status(self, arm_name: str) -> GripperStatus | None:
        """Get gripper status.

        Args:
            arm_name: Arm name.

        Returns:
            GripperStatus or None.

        """
        return self._grippers.get(arm_name)

    def is_open(self, arm_name: str) -> bool:
        """Check if gripper is open.

        Args:
            arm_name: Arm name.

        Returns:
            True if open.

        """
        status = self._grippers.get(arm_name)
        return status is not None and status.state == GripperState.OPEN

    def is_closed(self, arm_name: str) -> bool:
        """Check if gripper is closed.

        Args:
            arm_name: Arm name.

        Returns:
            True if closed.

        """
        status = self._grippers.get(arm_name)
        return status is not None and status.state == GripperState.CLOSED

    def has_object(self, arm_name: str) -> bool:
        """Check if gripper has an attached object.

        Args:
            arm_name: Arm name.

        Returns:
            True if object attached.

        """
        status = self._grippers.get(arm_name)
        return status is not None and bool(status.attached_object)

    def get_attached_object(self, arm_name: str) -> str:
        """Get the attached object ID.

        Args:
            arm_name: Arm name.

        Returns:
            Object ID or empty string.

        """
        status = self._grippers.get(arm_name)
        return status.attached_object if status else ""