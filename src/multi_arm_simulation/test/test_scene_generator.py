"""Tests for SceneGenerator."""

from pathlib import Path

import pytest
import yaml

from multi_arm_simulation.scene_generator import (
    Scene,
    SceneGenerator,
    SceneObject,
)


class TestSceneObject:
    """Tests for SceneObject."""

    def test_creation(self) -> None:
        obj = SceneObject(name="test_cube", type="cube")
        assert obj.name == "test_cube"
        assert obj.type == "cube"
        assert obj.position == [0.0, 0.0, 0.0]

    def test_to_sdf(self) -> None:
        obj = SceneObject(name="test", type="cube", position=[0.5, 0.5, 0.1])
        sdf = obj.to_sdf()
        assert "<model name=\"test\">" in sdf
        assert "0.5 0.5 0.1" in sdf


class TestScene:
    """Tests for Scene."""

    def test_empty_scene_sdf(self) -> None:
        scene = Scene(name="empty")
        sdf = scene.to_sdf()
        assert "<sdf" in sdf
        assert "</sdf>" in sdf

    def test_scene_with_objects(self) -> None:
        obj = SceneObject(name="cube1", type="cube")
        scene = Scene(name="test", objects=[obj])
        sdf = scene.to_sdf()
        assert "cube1" in sdf

    def test_to_dict(self) -> None:
        obj = SceneObject(name="cube1", type="cube")
        scene = Scene(name="test", objects=[obj])
        d = scene.to_dict()
        assert d["name"] == "test"
        assert len(d["objects"]) == 1


class TestSceneGenerator:
    """Tests for SceneGenerator."""

    def test_generate_scene(self) -> None:
        gen = SceneGenerator(seed=42)
        scene = gen.generate_scene(num_objects=3)
        assert len(scene.objects) == 3
        assert scene.name == "random_scene"

    def test_reproducible(self) -> None:
        gen1 = SceneGenerator(seed=42)
        gen2 = SceneGenerator(seed=42)
        s1 = gen1.generate_scene(num_objects=2)
        s2 = gen2.generate_scene(num_objects=2)
        assert s1.objects[0].position == s2.objects[0].position

    def test_different_seeds(self) -> None:
        gen1 = SceneGenerator(seed=42)
        gen2 = SceneGenerator(seed=99)
        s1 = gen1.generate_scene(num_objects=1)
        s2 = gen2.generate_scene(num_objects=1)
        assert s1.objects[0].position != s2.objects[0].position

    def test_object_types_filter(self) -> None:
        gen = SceneGenerator(seed=42)
        scene = gen.generate_scene(num_objects=5, object_types=["cube"])
        for obj in scene.objects:
            assert obj.type == "cube"

    def test_generate_batch(self, tmp_path: Path) -> None:
        gen = SceneGenerator(seed=42)
        paths = gen.generate_batch(5, tmp_path)
        assert len(paths) == 5
        for p in paths:
            assert p.exists()

    def test_load_scene(self, tmp_path: Path) -> None:
        gen = SceneGenerator(seed=42)
        scene = gen.generate_scene(num_objects=2)
        path = tmp_path / "test_scene.yaml"
        with open(path, "w") as f:
            yaml.dump(scene.to_dict(), f)

        loaded = gen.load_scene(path)
        assert loaded.name == scene.name
        assert len(loaded.objects) == 2

    def test_load_nonexistent(self) -> None:
        gen = SceneGenerator()
        with pytest.raises(FileNotFoundError):
            gen.load_scene("/nonexistent/scene.yaml")

    def test_workspace_bounds(self) -> None:
        gen = SceneGenerator(
            seed=42,
            workspace_bounds=[[0.0, 0.1], [0.0, 0.1], [0.5, 0.6]],
        )
        scene = gen.generate_scene(num_objects=3)
        for obj in scene.objects:
            assert 0.0 <= obj.position[0] <= 0.1
            assert 0.0 <= obj.position[1] <= 0.1
            assert 0.5 <= obj.position[2] <= 0.6