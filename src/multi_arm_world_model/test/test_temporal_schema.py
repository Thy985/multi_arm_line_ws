"""Tests for M7.0.2 WorldModel Schema — temporal + uncertainty fields.

Verifies that:
1. TrackedObject has temporal fields (observed_at, updated_at, ttl)
2. TrackedObject has uncertainty fields (position_covariance, orientation_uncertainty)
3. is_stale() respects ttl
4. Relation has ttl field
5. ObjectState msg has temporal + uncertainty fields
6. Relation msg has ttl field
7. QueryWorld srv has at_time field
8. update_object_pose populates temporal fields
"""

import time

import pytest

from multi_arm_world_model.state_database import TrackedObject, StateDatabase
from multi_arm_world_model.relation_layer import Relation, RelationLayer, RelationType


class TestTrackedObjectTemporal:
    """Test temporal fields on TrackedObject."""

    def test_default_temporal_fields(self):
        obj = TrackedObject(object_id="test")
        assert obj.observed_at == 0.0
        assert obj.updated_at > 0.0
        assert obj.ttl == 5.0

    def test_default_uncertainty_fields(self):
        obj = TrackedObject(object_id="test")
        assert obj.position_covariance == (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        assert obj.orientation_uncertainty == 0.0

    def test_ttl_makes_object_stale(self):
        obj = TrackedObject(object_id="test", ttl=0.1)
        assert not obj.is_stale()
        time.sleep(0.15)
        assert obj.is_stale()

    def test_ttl_zero_never_expires(self):
        obj = TrackedObject(object_id="test", ttl=0.0)
        assert not obj.is_stale(max_age=0.0)

    def test_ttl_overrides_max_age(self):
        obj = TrackedObject(object_id="test", ttl=100.0)
        assert not obj.is_stale(max_age=0.01)

    def test_observed_at_can_be_set(self):
        t = time.time()
        obj = TrackedObject(object_id="test", observed_at=t)
        assert obj.observed_at == t

    def test_position_covariance_can_be_set(self):
        cov = (0.01, 0.0, 0.0, 0.0, 0.01, 0.0, 0.0, 0.0, 0.01)
        obj = TrackedObject(object_id="test", position_covariance=cov)
        assert obj.position_covariance == cov

    def test_orientation_uncertainty_can_be_set(self):
        obj = TrackedObject(object_id="test", orientation_uncertainty=0.05)
        assert obj.orientation_uncertainty == 0.05


class TestRelationTemporal:
    """Test temporal fields on Relation."""

    def test_default_ttl(self):
        rel = Relation(subject="a", predicate="on", object="b")
        assert rel.ttl == 0.0

    def test_ttl_can_be_set(self):
        rel = Relation(subject="a", predicate="on", object="b", ttl=5.0)
        assert rel.ttl == 5.0


class TestStateDatabaseTemporal:
    """Test temporal field updates in StateDatabase."""

    def test_update_object_pose_sets_updated_at(self):
        db = StateDatabase()
        obj = TrackedObject(object_id="test", position=(0.0, 0.0, 0.0))
        db.add_object(obj)
        original_last_seen = obj.last_seen
        time.sleep(0.01)
        db.update_object_pose("test", (1.0, 0.0, 0.0))
        updated = db.get_object("test")
        assert updated.updated_at > original_last_seen

    def test_update_object_pose_sets_observed_at_on_first_update(self):
        db = StateDatabase()
        obj = TrackedObject(object_id="test", observed_at=0.0)
        db.add_object(obj)
        db.update_object_pose("test", (1.0, 0.0, 0.0))
        updated = db.get_object("test")
        assert updated.observed_at > 0.0

    def test_cleanup_respects_ttl(self):
        db = StateDatabase()
        obj = TrackedObject(object_id="expiring", ttl=0.05)
        db.add_object(obj)
        time.sleep(0.1)
        removed = db.cleanup_stale(object_max_age=100.0)
        assert removed == 1


class TestMessageFields:
    """Test that ROS2 messages have the new fields."""

    def test_object_state_has_temporal_fields(self):
        from multi_arm_interfaces.msg import ObjectState
        msg = ObjectState()
        assert hasattr(msg, "observed_at")
        assert hasattr(msg, "updated_at")
        assert hasattr(msg, "ttl")
        assert msg.observed_at == 0.0
        assert msg.updated_at == 0.0
        assert msg.ttl == 0.0

    def test_object_state_has_uncertainty_fields(self):
        from multi_arm_interfaces.msg import ObjectState
        msg = ObjectState()
        assert hasattr(msg, "position_covariance")
        assert hasattr(msg, "orientation_uncertainty")
        assert len(msg.position_covariance) == 9
        assert msg.orientation_uncertainty == 0.0

    def test_relation_has_ttl(self):
        from multi_arm_interfaces.msg import Relation
        msg = Relation()
        assert hasattr(msg, "ttl")
        assert msg.ttl == 0.0

    def test_query_world_has_at_time(self):
        from multi_arm_interfaces.srv import QueryWorld
        req = QueryWorld.Request()
        assert hasattr(req, "at_time")
        assert req.at_time == 0.0

    def test_object_state_backward_compat(self):
        from multi_arm_interfaces.msg import ObjectState
        msg = ObjectState()
        assert hasattr(msg, "object_id")
        assert hasattr(msg, "object_type")
        assert hasattr(msg, "pose")
        assert hasattr(msg, "velocity")
        assert hasattr(msg, "attached_to")
        assert hasattr(msg, "grasp_state")
        assert hasattr(msg, "confidence")

    def test_relation_backward_compat(self):
        from multi_arm_interfaces.msg import Relation
        msg = Relation()
        assert hasattr(msg, "subject")
        assert hasattr(msg, "predicate")
        assert hasattr(msg, "object")
        assert hasattr(msg, "confidence")
        assert hasattr(msg, "distance")