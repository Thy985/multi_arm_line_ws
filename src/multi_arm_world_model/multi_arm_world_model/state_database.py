"""StateDatabase for WorldModel - in-memory store for objects and environment."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import time as _time


@dataclass
class TrackedObject:
    """A tracked object in the world model.

    M7.0.2: Added temporal (observed_at/updated_at/ttl) and uncertainty
    (position_covariance/orientation_uncertainty) fields.
    """
    object_id: str
    object_type: str = "unknown"
    position: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    orientation: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)
    confidence: float = 1.0
    velocity: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    last_seen: float = field(default_factory=_time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)
    observed_at: float = 0.0
    updated_at: float = field(default_factory=_time.time)
    ttl: float = 5.0
    position_covariance: Tuple[float, float, float, float, float, float, float, float, float] = \
        (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    orientation_uncertainty: float = 0.0

    def is_stale(self, max_age: float = 5.0) -> bool:
        """Check if object data is stale.

        Uses ttl if > 0, otherwise falls back to max_age parameter.
        """
        effective_ttl = self.ttl if self.ttl > 0.0 else max_age
        if effective_ttl == 0.0:
            return False
        return (_time.time() - self.last_seen) > effective_ttl

    def predicted_position(self, dt: float = 0.0) -> Tuple[float, float, float]:
        """Predict future position based on velocity.

        Args:
            dt: Seconds into the future to predict.

        Returns:
            Predicted (x, y, z) position.
        """
        return (
            self.position[0] + self.velocity[0] * dt,
            self.position[1] + self.velocity[1] * dt,
            self.position[2] + self.velocity[2] * dt,
        )


@dataclass
class EnvironmentInfo:
    """Static environment information."""
    workspace_bounds: Dict[str, List[float]] = field(default_factory=lambda: {
        "x": [-0.8, 0.8], "y": [-0.8, 0.8], "z": [0.0, 1.2]
    })
    obstacles: List[Dict[str, Any]] = field(default_factory=list)
    zones: Dict[str, Dict[str, Any]] = field(default_factory=dict)


@dataclass
class TaskContext:
    """Task-related environment snapshot."""
    task_id: str = ""
    target_object_id: str = ""
    target_zone: str = ""
    approach: str = "top"
    timestamp: float = field(default_factory=_time.time)


@dataclass
class CachedRobotState:
    """Cached robot state (non-owning, 1-10Hz update).

    WorldModel caches robot state for upper-layer queries.
    500Hz joint_states from ros2_control do NOT enter WorldModel.
    """
    arm_name: str
    joint_positions: List[float] = field(default_factory=lambda: [0.0] * 6)
    joint_velocities: List[float] = field(default_factory=lambda: [0.0] * 6)
    ee_position: Optional[Tuple[float, float, float]] = None
    ee_orientation: Optional[Tuple[float, float, float, float]] = None
    last_updated: float = field(default_factory=_time.time)

    def is_stale(self, max_age: float = 1.0) -> bool:
        """Check if cached state is stale (default 1s for 1-10Hz)."""
        return (_time.time() - self.last_updated) > max_age


class StateDatabase:
    """In-memory database for WorldModel.

    Ownership model:
    - OWNS: Objects, Environment, TaskContext
    - CACHES (non-owning): RobotState (from /joint_states, 1-10Hz)
    - DOES NOT OWN: Real-time control state (ros2_control, 100-500Hz)
    """

    def __init__(self) -> None:
        self._objects: Dict[str, TrackedObject] = {}
        self._environment = EnvironmentInfo()
        self._task_contexts: Dict[str, TaskContext] = {}
        self._robot_states: Dict[str, CachedRobotState] = {}

    # === Objects (OWNED) ===

    def add_object(self, obj: TrackedObject) -> None:
        """Add or update a tracked object."""
        self._objects[obj.object_id] = obj

    def get_object(self, object_id: str) -> Optional[TrackedObject]:
        """Get object by ID."""
        return self._objects.get(object_id)

    def remove_object(self, object_id: str) -> bool:
        """Remove an object."""
        return self._objects.pop(object_id, None) is not None

    def get_all_objects(self) -> List[TrackedObject]:
        """Get all tracked objects."""
        return list(self._objects.values())

    def get_objects_by_type(self, object_type: str) -> List[TrackedObject]:
        """Get objects filtered by type."""
        return [o for o in self._objects.values() if o.object_type == object_type]

    def update_object_pose(
        self,
        object_id: str,
        position: Tuple[float, float, float],
        orientation: Optional[Tuple[float, float, float, float]] = None,
        confidence: float = 1.0,
    ) -> bool:
        """Update object pose with velocity estimation.

        Args:
            object_id: Object ID.
            position: New position (x, y, z).
            orientation: New orientation (qx, qy, qz, qw).
            confidence: Detection confidence.

        Returns:
            True if object was found and updated.
        """
        obj = self._objects.get(object_id)
        if obj is None:
            return False

        now = _time.time()
        dt = now - obj.last_seen
        if dt > 0.001:
            obj.velocity = (
                (position[0] - obj.position[0]) / dt,
                (position[1] - obj.position[1]) / dt,
                (position[2] - obj.position[2]) / dt,
            )

        obj.position = position
        if orientation is not None:
            obj.orientation = orientation
        obj.confidence = confidence
        obj.last_seen = now
        obj.updated_at = now
        if obj.observed_at == 0.0:
            obj.observed_at = now
        return True

    # === Environment (OWNED) ===

    @property
    def environment(self) -> EnvironmentInfo:
        """Get environment info."""
        return self._environment

    def add_obstacle(self, obstacle: Dict[str, Any]) -> None:
        """Add a static obstacle."""
        self._environment.obstacles.append(obstacle)

    def add_zone(self, name: str, zone_info: Dict[str, Any]) -> None:
        """Add a workspace zone."""
        self._environment.zones[name] = zone_info

    # === TaskContext (OWNED) ===

    def set_task_context(self, context: TaskContext) -> None:
        """Set current task context."""
        self._task_contexts[context.task_id] = context

    def get_task_context(self, task_id: str) -> Optional[TaskContext]:
        """Get task context by task ID."""
        return self._task_contexts.get(task_id)

    def clear_task_context(self, task_id: str) -> None:
        """Clear a task context."""
        self._task_contexts.pop(task_id, None)

    # === RobotState (CACHED, NON-OWNING) ===

    def update_robot_state(
        self,
        arm_name: str,
        joint_positions: List[float],
        joint_velocities: Optional[List[float]] = None,
        ee_position: Optional[Tuple[float, float, float]] = None,
        ee_orientation: Optional[Tuple[float, float, float, float]] = None,
    ) -> None:
        """Update cached robot state (1-10Hz).

        500Hz joint_states from ros2_control do NOT enter here.
        This is a downsampled cache for upper-layer queries only.
        """
        self._robot_states[arm_name] = CachedRobotState(
            arm_name=arm_name,
            joint_positions=joint_positions,
            joint_velocities=joint_velocities or [0.0] * 6,
            ee_position=ee_position,
            ee_orientation=ee_orientation,
            last_updated=_time.time(),
        )

    def get_robot_state(self, arm_name: str) -> Optional[CachedRobotState]:
        """Get cached robot state for an arm."""
        return self._robot_states.get(arm_name)

    def get_all_robot_states(self) -> Dict[str, CachedRobotState]:
        """Get all cached robot states."""
        return dict(self._robot_states)

    # === Cleanup ===

    def cleanup_stale(self, object_max_age: float = 10.0) -> int:
        """Remove stale objects and task contexts.

        Args:
            object_max_age: Max age in seconds for objects.

        Returns:
            Number of items removed.
        """
        stale_ids = [
            oid for oid, obj in self._objects.items() if obj.is_stale(object_max_age)
        ]
        for oid in stale_ids:
            del self._objects[oid]
        return len(stale_ids)