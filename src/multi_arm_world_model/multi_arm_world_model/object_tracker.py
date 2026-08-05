"""ObjectTracker for associating detections with tracked objects and motion prediction."""

from typing import Dict, List, Optional, Tuple
import time as _time

from multi_arm_world_model.state_database import TrackedObject, StateDatabase


class ObjectTracker:
    """Tracks objects across detections, maintains ID associations, and predicts motion.

    Uses a simple nearest-neighbor association with configurable distance threshold.
    For more advanced tracking, integrate a perception pipeline in Phase 3+.
    """

    _id_counter = 0

    def __init__(
        self,
        association_threshold: float = 0.1,
        max_lost_frames: int = 5,
    ) -> None:
        """Initialize ObjectTracker.

        Args:
            association_threshold: Max distance (m) for associating a detection
                with an existing tracked object.
            max_lost_frames: Number of frames an object can be lost before removal.
        """
        self._association_threshold = association_threshold
        self._max_lost_frames = max_lost_frames
        self._lost_counts: Dict[str, int] = {}

    def update(
        self,
        database: StateDatabase,
        detections: List[Dict],
    ) -> List[str]:
        """Process new detections and update tracked objects.

        Args:
            database: StateDatabase to update.
            detections: List of detection dicts with keys:
                object_type, position (x,y,z), orientation (optional),
                confidence (optional), id (optional).

        Returns:
            List of assigned object IDs.
        """
        assigned_ids = []
        used_detections = set()

        for det in detections:
            det_pos = det.get("position", (0.0, 0.0, 0.0))
            det_type = det.get("object_type", "unknown")
            det_id = det.get("id")

            best_id = None
            best_dist = self._association_threshold

            if det_id and database.get_object(det_id):
                best_id = det_id
                best_dist = 0.0
            else:
                for obj in database.get_all_objects():
                    if obj.object_type != det_type:
                        continue
                    dx = obj.position[0] - det_pos[0]
                    dy = obj.position[1] - det_pos[1]
                    dz = obj.position[2] - det_pos[2]
                    dist = (dx * dx + dy * dy + dz * dz) ** 0.5
                    if dist < best_dist:
                        best_dist = dist
                        best_id = obj.object_id

            if best_id:
                database.update_object_pose(
                    best_id,
                    det_pos,
                    det.get("orientation"),
                    det.get("confidence", 1.0),
                )
                self._lost_counts.pop(best_id, None)
                assigned_ids.append(best_id)
                used_detections.add(id(det))
            else:
                new_id = det_id or f"obj_{ObjectTracker._id_counter}"
                ObjectTracker._id_counter += 1
                obj = TrackedObject(
                    object_id=new_id,
                    object_type=det_type,
                    position=det_pos,
                    orientation=det.get("orientation", (0.0, 0.0, 0.0, 1.0)),
                    confidence=det.get("confidence", 1.0),
                )
                database.add_object(obj)
                assigned_ids.append(new_id)

        existing_ids = {o.object_id for o in database.get_all_objects()}
        tracked_ids = set(assigned_ids)
        for oid in existing_ids - tracked_ids:
            self._lost_counts[oid] = self._lost_counts.get(oid, 0) + 1
            if self._lost_counts[oid] >= self._max_lost_frames:
                database.remove_object(oid)
                self._lost_counts.pop(oid, None)

        for oid in assigned_ids:
            self._lost_counts.pop(oid, None)

        return assigned_ids

    def predict_positions(
        self,
        database: StateDatabase,
        dt: float = 0.5,
    ) -> Dict[str, Tuple[float, float, float]]:
        """Predict future positions for all tracked objects.

        Args:
            database: StateDatabase with tracked objects.
            dt: Seconds into the future.

        Returns:
            Dict mapping object_id to predicted (x, y, z).
        """
        predictions = {}
        for obj in database.get_all_objects():
            predictions[obj.object_id] = obj.predicted_position(dt)
        return predictions