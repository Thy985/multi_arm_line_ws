"""Scene Generator — random diverse scene generation for simulation."""

from __future__ import annotations

import random
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class SceneObject:
    """An object placed in a simulation scene."""

    name: str
    type: str
    position: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    orientation: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0, 1.0])
    size: list[float] = field(default_factory=lambda: [0.05, 0.05, 0.05])
    color: list[float] = field(default_factory=lambda: [0.8, 0.2, 0.2, 1.0])
    mass: float = 0.5
    friction: float = 0.5

    def to_sdf(self) -> str:
        """Convert to SDF model string for Gazebo.

        Returns:
            SDF model XML string.

        """
        return (
            f'    <model name="{self.name}">\n'
            f'      <static>false</static>\n'
            f'      <link name="link">\n'
            f'        <pose>{self.position[0]} {self.position[1]} {self.position[2]} '
            f'{self.orientation[0]} {self.orientation[1]} {self.orientation[2]}</pose>\n'
            f'        <inertial>\n'
            f'          <mass>{self.mass}</mass>\n'
            f'        </inertial>\n'
            f'        <collision name="collision">\n'
            f'          <geometry>\n'
            f'            <box><size>{self.size[0]} {self.size[1]} {self.size[2]}</size></box>\n'
            f'          </geometry>\n'
            f'          <surface>\n'
            f'            <friction>\n'
            f'              <ode><mu>{self.friction}</mu></ode>\n'
            f'            </friction>\n'
            f'          </surface>\n'
            f'        </collision>\n'
            f'        <visual name="visual">\n'
            f'          <geometry>\n'
            f'            <box><size>{self.size[0]} {self.size[1]} {self.size[2]}</size></box>\n'
            f'          </geometry>\n'
            f'          <material>\n'
            f'            <ambient>{self.color[0]} {self.color[1]} {self.color[2]} {self.color[3]}</ambient>\n'
            f'          </material>\n'
            f'        </visual>\n'
            f'      </link>\n'
            f'    </model>\n'
        )


@dataclass
class Scene:
    """A complete simulation scene."""

    name: str
    objects: list[SceneObject] = field(default_factory=list)
    lighting: dict[str, Any] = field(default_factory=dict)
    camera_pose: list[float] = field(
        default_factory=lambda: [2.0, 2.0, 2.0, 0.0, 0.0, 0.0]
    )

    def to_sdf(self) -> str:
        """Convert entire scene to SDF.

        Returns:
            SDF XML string.

        """
        lines = [
            '<?xml version="1.0"?>',
            '<sdf version="1.9">',
            '  <world name="default">',
        ]
        for obj in self.objects:
            lines.append(obj.to_sdf())
        lines.extend([
            '  </world>',
            '</sdf>',
        ])
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Convert scene to dictionary for YAML serialization.

        Returns:
            Scene as dictionary.

        """
        return {
            "name": self.name,
            "objects": [
                {
                    "name": o.name,
                    "type": o.type,
                    "position": o.position,
                    "orientation": o.orientation,
                    "size": o.size,
                    "color": o.color,
                    "mass": o.mass,
                    "friction": o.friction,
                }
                for o in self.objects
            ],
            "lighting": self.lighting,
            "camera_pose": self.camera_pose,
        }


class SceneGenerator:
    """Random scene generator for diverse simulation scenarios.

    Generates scenes with random objects, positions, sizes, colors,
    and physical properties for robust testing and training.
    """

    OBJECT_TYPES = ["cube", "cylinder", "box", "sphere"]
    COLORS = {
        "red": [0.8, 0.2, 0.2, 1.0],
        "green": [0.2, 0.8, 0.2, 1.0],
        "blue": [0.2, 0.2, 0.8, 1.0],
        "yellow": [0.8, 0.8, 0.2, 1.0],
        "white": [0.9, 0.9, 0.9, 1.0],
        "black": [0.1, 0.1, 0.1, 1.0],
    }

    def __init__(
        self,
        seed: int | None = None,
        workspace_bounds: list[list[float]] | None = None,
    ) -> None:
        """Initialize scene generator.

        Args:
            seed: Random seed for reproducibility.
            workspace_bounds: [[x_min, x_max], [y_min, y_max], [z_min, z_max]]
                for object placement.

        """
        self._rng = random.Random(seed)
        self._workspace = workspace_bounds or [
            [-0.5, 0.5],
            [-0.5, 0.5],
            [0.05, 0.3],
        ]

    def generate_scene(
        self,
        name: str = "random_scene",
        num_objects: int = 5,
        object_types: list[str] | None = None,
    ) -> Scene:
        """Generate a random scene.

        Args:
            name: Scene name.
            num_objects: Number of objects to place.
            object_types: Allowed object types (default: all).

        Returns:
            Generated Scene.

        """
        types = object_types or self.OBJECT_TYPES
        objects: list[SceneObject] = []

        for i in range(num_objects):
            obj_type = self._rng.choice(types)
            color_name = self._rng.choice(list(self.COLORS.keys()))

            position = [
                self._rng.uniform(*self._workspace[0]),
                self._rng.uniform(*self._workspace[1]),
                self._rng.uniform(*self._workspace[2]),
            ]

            size = [
                self._rng.uniform(0.03, 0.10),
                self._rng.uniform(0.03, 0.10),
                self._rng.uniform(0.03, 0.10),
            ]

            yaw = self._rng.uniform(0.0, 6.283)

            obj = SceneObject(
                name=f"{color_name}_{obj_type}_{i}",
                type=obj_type,
                position=position,
                orientation=[0.0, 0.0, yaw],
                size=size,
                color=self.COLORS[color_name],
                mass=self._rng.uniform(0.1, 2.0),
                friction=self._rng.uniform(0.3, 0.8),
            )
            objects.append(obj)

        lighting = {
            "intensity": self._rng.uniform(0.5, 1.5),
            "direction": [
                self._rng.uniform(-1.0, 1.0),
                self._rng.uniform(-1.0, 1.0),
                -1.0,
            ],
        }

        return Scene(name=name, objects=objects, lighting=lighting)

    def generate_batch(
        self,
        count: int,
        output_dir: str | Path,
        prefix: str = "scene",
    ) -> list[Path]:
        """Generate a batch of random scenes and save to YAML.

        Args:
            count: Number of scenes to generate.
            output_dir: Output directory.
            prefix: Filename prefix.

        Returns:
            List of generated file paths.

        """
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        paths: list[Path] = []
        for i in range(count):
            scene = self.generate_scene(name=f"{prefix}_{i:04d}")
            path = out / f"{prefix}_{i:04d}.yaml"
            with open(path, "w") as f:
                yaml.dump(scene.to_dict(), f, default_flow_style=False)
            paths.append(path)

        return paths

    def load_scene(self, yaml_path: str | Path) -> Scene:
        """Load a scene from YAML file.

        Args:
            yaml_path: Path to scene YAML.

        Returns:
            Loaded Scene.

        Raises:
            FileNotFoundError: If file not found.

        """
        path = Path(yaml_path)
        if not path.exists():
            raise FileNotFoundError(f"Scene YAML not found: {yaml_path}")

        with open(path) as f:
            data = yaml.safe_load(f)

        objects = [
            SceneObject(
                name=o["name"],
                type=o["type"],
                position=o.get("position", [0, 0, 0]),
                orientation=o.get("orientation", [0, 0, 0, 1]),
                size=o.get("size", [0.05, 0.05, 0.05]),
                color=o.get("color", [0.8, 0.2, 0.2, 1.0]),
                mass=o.get("mass", 0.5),
                friction=o.get("friction", 0.5),
            )
            for o in data.get("objects", [])
        ]

        return Scene(
            name=data.get("name", "loaded_scene"),
            objects=objects,
            lighting=data.get("lighting", {}),
            camera_pose=data.get("camera_pose", [2.0, 2.0, 2.0, 0, 0, 0]),
        )


def main(args: list[str] | None = None) -> None:
    """CLI entry point for scene generator.

    Args:
        args: Command line arguments.

    """
    if args is None:
        args = sys.argv[1:]

    count = int(args[0]) if len(args) > 0 else 10
    output = args[1] if len(args) > 1 else "generated_scenes"
    seed = int(args[2]) if len(args) > 2 else None

    gen = SceneGenerator(seed=seed)
    paths = gen.generate_batch(count, output)
    print(f"Generated {len(paths)} scenes in {output}/")


if __name__ == "__main__":
    main()