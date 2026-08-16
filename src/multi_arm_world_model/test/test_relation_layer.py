"""Tests for RelationLayer."""

import pytest

from multi_arm_world_model.relation_layer import RelationLayer, Relation, RelationType


class TestRelationLayer:
    """Tests for RelationLayer."""

    def test_add_and_has_relation(self) -> None:
        layer = RelationLayer()
        layer.add_relation("red_cube", "on", "table")
        assert layer.has_relation("red_cube", "on", "table")

    def test_remove_relation(self) -> None:
        layer = RelationLayer()
        layer.add_relation("red_cube", "on", "table")
        assert layer.remove_relation("red_cube", "on", "table")
        assert not layer.has_relation("red_cube", "on", "table")

    def test_remove_nonexistent(self) -> None:
        layer = RelationLayer()
        assert not layer.remove_relation("a", "b", "c")

    def test_query_all(self) -> None:
        layer = RelationLayer()
        layer.add_relation("cube", "on", "table")
        layer.add_relation("cube", "near", "cylinder")
        layer.add_relation("cylinder", "on", "table")
        all_rels = layer.query()
        assert len(all_rels) == 3

    def test_query_by_subject(self) -> None:
        layer = RelationLayer()
        layer.add_relation("cube", "on", "table")
        layer.add_relation("cylinder", "on", "table")
        rels = layer.query(subject="cube")
        assert len(rels) == 1
        assert rels[0].subject == "cube"

    def test_query_by_predicate(self) -> None:
        layer = RelationLayer()
        layer.add_relation("cube", "on", "table")
        layer.add_relation("cube", "near", "cylinder")
        rels = layer.query(predicate="on")
        assert len(rels) == 1

    def test_set_attached(self) -> None:
        layer = RelationLayer()
        layer.set_attached("red_cube", "left_arm_gripper")
        assert layer.is_attached("red_cube")
        assert layer.is_attached("red_cube", "left_arm_gripper")

    def test_set_detached(self) -> None:
        layer = RelationLayer()
        layer.set_attached("red_cube", "left_arm_gripper")
        layer.set_detached("red_cube", "left_arm_gripper")
        assert not layer.is_attached("red_cube")

    def test_clear_relations_for_entity(self) -> None:
        layer = RelationLayer()
        layer.add_relation("cube", "on", "table")
        layer.add_relation("cylinder", "near", "cube")
        removed = layer.clear_relations_for_entity("cube")
        assert removed == 2
        assert len(layer.get_all_relations()) == 0

    def test_compute_spatial_near(self) -> None:
        layer = RelationLayer()
        layer._near_threshold = 0.2
        objects = {
            "cube": {"position": [0.0, 0.0, 0.1]},
            "cylinder": {"position": [0.05, 0.0, 0.1]},
        }
        layer.compute_spatial_relations(objects)
        near_rels = layer.query(predicate="near")
        assert len(near_rels) >= 1

    def test_compute_spatial_on_surface(self) -> None:
        layer = RelationLayer()
        objects = {"cube": {"position": [0.0, 0.0, 0.02]}}
        surfaces = {"table": {"position": [0.0, 0.0, 0.0]}}
        layer.compute_spatial_relations(objects, surfaces)
        on_rels = layer.query(predicate="on")
        assert len(on_rels) >= 1