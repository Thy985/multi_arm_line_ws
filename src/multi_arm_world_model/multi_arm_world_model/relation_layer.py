"""Relation Layer — maintain spatial relationships between entities.

Relations: on, near, inside, attached_to, above, below
This is the key dependency for Skill precondition/postcondition checking.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RelationType(Enum):
    """Types of spatial relations."""

    ON = "on"
    NEAR = "near"
    INSIDE = "inside"
    ATTACHED_TO = "attached_to"
    ABOVE = "above"
    BELOW = "below"


@dataclass
class Relation:
    """A spatial relation between two entities."""

    subject: str
    predicate: str
    object: str
    confidence: float = 1.0
    distance: float = 0.0
    timestamp: float = 0.0

    def matches(
        self,
        subject: str = "",
        predicate: str = "",
        object: str = "",
    ) -> bool:
        """Check if relation matches query criteria.

        Args:
            subject: Subject filter (empty = any).
            predicate: Predicate filter (empty = any).
            object: Object filter (empty = any).

        Returns:
            True if matches all non-empty criteria.

        """
        if subject and self.subject != subject:
            return False
        if predicate and self.predicate != predicate:
            return False
        if object and self.object != object:
            return False
        return True


class RelationLayer:
    """Relation Layer of WorldModel — maintains entity relationships.

    Key dependency for Skill precondition/postcondition:
        Skill: place_object(object, location)
        precondition: Relation(object, "attached_to", gripper) exists
       ?       postcondition: Relation(object, "on", location) exists
    """

    def __init__(self) -> None:
        """Initialize relation layer."""
        self._relations: dict[str, Relation] = {}
        self._near_threshold: float = 0.15
        self._on_threshold: float = 0.02

    def _make_key(self, subject: str, predicate: str, object: str) -> str:
        """Create unique key for relation.

        Args:
            subject: Subject entity.
            predicate: Relation type.
            object: Object entity.

        Returns:
            Unique key string.

        """
        return f"{subject}:{predicate}:{object}"

    def add_relation(
        self,
        subject: str,
        predicate: str,
        object: str,
        confidence: float = 1.0,
        distance: float = 0.0,
        timestamp: float = 0.0,
    ) -> None:
        """Add or update a relation.

        Args:
            subject: Subject entity ID.
            predicate: Relation type (on/near/inside/attached_to/above/below).
            object: Object entity ID.
            confidence: Confidence score.
            distance: Distance value (for near/inside).
            timestamp: Timestamp.

        """
        key = self._make_key(subject, predicate, object)
        self._relations[key] = Relation(
            subject=subject,
            predicate=predicate,
            object=object,
            confidence=confidence,
            distance=distance,
            timestamp=timestamp,
        )

    def remove_relation(
        self, subject: str, predicate: str, object: str
    ) -> bool:
        """Remove a relation.

        Args:
            subject: Subject entity.
            predicate: Relation type.
            object: Object entity.

        Returns:
            True if relation was removed.

        """
        key = self._make_key(subject, predicate, object)
        return self._relations.pop(key, None) is not None

    def has_relation(
        self, subject: str, predicate: str, object: str
    ) -> bool:
        """Check if a relation exists.

        Args:
            subject: Subject entity.
            predicate: Relation type.
            object: Object entity.

        Returns:
            True if relation exists.

        """
        key = self._make_key(subject, predicate, object)
        return key in self._relations

    def query(
        self,
        subject: str = "",
        predicate: str = "",
        object: str = "",
    ) -> list[Relation]:
        """Query relations by criteria.

        Args:
            subject: Subject filter (empty = any).
            predicate: Predicate filter (empty = any).
            object: Object filter (empty = any).

        Returns:
            List of matching relations.

        """
        return [
            r for r in self._relations.values()
            if r.matches(subject, predicate, object)
        ]

    def get_all_relations(self) -> list[Relation]:
        """Get all relations.

        Returns:
            List of all relations.

        """
        return list(self._relations.values())

    def clear_relations_for_entity(self, entity_id: str) -> int:
        """Remove all relations involving an entity.

        Args:
            entity_id: Entity to remove.

        Returns:
            Number of removed relations.

        """
        to_remove = [
            key for key, rel in self._relations.items()
            if rel.subject == entity_id or rel.object == entity_id
        ]
        for key in to_remove:
            del self._relations[key]
        return len(to_remove)

    def compute_spatial_relations(
        self,
        objects: dict[str, dict[str, Any]],
        surfaces: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        """Automatically compute on/near/above/below relations from positions.

        Args:
            objects: Dict of object_id -> {position: [x,y,z], ...}.
            surfaces: Dict of surface_id -> {position: [x,y,z], ...}.

        """
        surfaces = surfaces or {}
        obj_ids = list(objects.keys())

        for i, oid in enumerate(obj_ids):
            pos_i = objects[oid].get("position", [0, 0, 0])

            for j, ojd in enumerate(obj_ids):
                if i == j:
                    continue
                pos_j = objects[ojd].get("position", [0, 0, 0])

                dx = pos_i[0] - pos_j[0]
                dy = pos_i[1] - pos_j[1]
                dz = pos_i[2] - pos_j[2]
                dist = (dx * dx + dy * dy + dz * dz) ** 0.5

                if dist < self._near_threshold:
                    self.add_relation(oid, "near", ojd, confidence=0.9, distance=dist)

                if dz > self._on_threshold and abs(dx) < 0.1 and abs(dy) < 0.1:
                    self.add_relation(oid, "above", ojd, confidence=0.8, distance=abs(dz))

                if dz < -self._on_threshold and abs(dx) < 0.1 and abs(dy) < 0.1:
                    self.add_relation(oid, "below", ojd, confidence=0.8, distance=abs(dz))

            for sid, sdata in surfaces.items():
                s_pos = sdata.get("position", [0, 0, 0])
                dx = pos_i[0] - s_pos[0]
                dy = pos_i[1] - s_pos[1]
                dz = pos_i[2] - s_pos[2]
                dist = (dx * dx + dy * dy + dz * dz) ** 0.5

                if abs(dz) < 0.05 and abs(dx) < 0.15 and abs(dy) < 0.15:
                    self.add_relation(oid, "on", sid, confidence=0.95, distance=dist)

    def set_attached(self, object_id: str, gripper_id: str) -> None:
        """Mark object as attached to gripper.

        Args:
            object_id: Object ID.
            gripper_id: Gripper ID.

        """
        self.add_relation(object_id, "attached_to", gripper_id, confidence=1.0)

    def set_detached(self, object_id: str, gripper_id: str) -> None:
        """Mark object as detached from gripper.

        Args:
            object_id: Object ID.
            gripper_id: Gripper ID.

        """
        self.remove_relation(object_id, "attached_to", gripper_id)

    def is_attached(self, object_id: str, gripper_id: str = "") -> bool:
        """Check if object is attached to a gripper.

        Args:
            object_id: Object ID.
            gripper_id: Gripper ID (empty = any gripper).

        Returns:
            True if attached.

        """
        if gripper_id:
            return self.has_relation(object_id, "attached_to", gripper_id)
        return len(self.query(subject=object_id, predicate="attached_to")) > 0