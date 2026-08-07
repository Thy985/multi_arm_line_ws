"""Domain Randomization — randomize lighting, texture, position, physics."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class RandomizationConfig:
    """Configuration for domain randomization."""

    lighting: dict[str, Any] = field(default_factory=lambda: {
        "intensity": [0.5, 1.5],
        "direction": "random",
    })
    texture: dict[str, Any] = field(default_factory=lambda: {
        "pool": ["wood", "metal", "plastic"],
    })
    object_position: dict[str, Any] = field(default_factory=lambda: {
        "jitter": 0.05,
    })
    physics: dict[str, Any] = field(default_factory=lambda: {
        "friction": [0.3, 0.8],
        "mass": [0.1, 2.0],
    })
    camera: dict[str, Any] = field(default_factory=lambda: {
        "position_jitter": 0.1,
        "angle_jitter": 0.1,
    })

    @classmethod
    def from_yaml(cls, yaml_path: str | Path) -> "RandomizationConfig":
        """Load config from YAML file.

        Args:
            yaml_path: Path to YAML config.

        Returns:
            RandomizationConfig instance.

        """
        with open(yaml_path) as f:
            data = yaml.safe_load(f)
        return cls(
            lighting=data.get("lighting", cls().lighting),
            texture=data.get("texture", cls().texture),
            object_position=data.get("object_position", cls().object_position),
            physics=data.get("physics", cls().physics),
            camera=data.get("camera", cls().camera),
        )


class DomainRandomizer:
    """Apply domain randomization to simulation parameters.

    Randomizes lighting, textures, object positions, and physics
    properties to improve sim-to-real transfer.
    """

    def __init__(
        self,
        config: RandomizationConfig | None = None,
        seed: int | None = None,
    ) -> None:
        """Initialize domain randomizer.

        Args:
            config: Randomization configuration.
            seed: Random seed.

        """
        self._config = config or RandomizationConfig()
        self._rng = random.Random(seed)

    def randomize_lighting(self) -> dict[str, Any]:
        """Randomize lighting parameters.

        Returns:
            Dict with intensity and direction.

        """
        intensity_range = self._config.lighting.get("intensity", [0.5, 1.5])
        return {
            "intensity": self._rng.uniform(*intensity_range),
            "direction": [
                self._rng.uniform(-1.0, 1.0),
                self._rng.uniform(-1.0, 1.0),
                -1.0,
            ],
            "ambient": self._rng.uniform(0.1, 0.4),
        }

    def randomize_texture(self) -> str:
        """Randomly select a texture from pool.

        Returns:
            Selected texture name.

        """
        pool = self._config.texture.get("pool", ["default"])
        return self._rng.choice(pool)

    def randomize_position(self, base_position: list[float]) -> list[float]:
        """Apply position jitter to a base position.

        Args:
            base_position: [x, y, z] base position.

        Returns:
            Jittered position.

        """
        jitter = self._config.object_position.get("jitter", 0.05)
        return [
            base_position[0] + self._rng.uniform(-jitter, jitter),
            base_position[1] + self._rng.uniform(-jitter, jitter),
            base_position[2] + self._rng.uniform(-jitter, jitter),
        ]

    def randomize_physics(self) -> dict[str, float]:
        """Randomize physics parameters.

        Returns:
            Dict with friction and mass.

        """
        friction_range = self._config.physics.get("friction", [0.3, 0.8])
        mass_range = self._config.physics.get("mass", [0.1, 2.0])
        return {
            "friction": self._rng.uniform(*friction_range),
            "mass": self._rng.uniform(*mass_range),
        }

    def randomize_camera(self, base_pose: list[float]) -> list[float]:
        """Apply jitter to camera pose.

        Args:
            base_pose: [x, y, z, roll, pitch, yaw] base camera pose.

        Returns:
            Jittered camera pose.

        """
        pos_jitter = self._config.camera.get("position_jitter", 0.1)
        ang_jitter = self._config.camera.get("angle_jitter", 0.1)
        return [
            base_pose[0] + self._rng.uniform(-pos_jitter, pos_jitter),
            base_pose[1] + self._rng.uniform(-pos_jitter, pos_jitter),
            base_pose[2] + self._rng.uniform(-pos_jitter, pos_jitter),
            base_pose[3] + self._rng.uniform(-ang_jitter, ang_jitter),
            base_pose[4] + self._rng.uniform(-ang_jitter, ang_jitter),
            base_pose[5] + self._rng.uniform(-ang_jitter, ang_jitter),
        ]

    def randomize_all(self, base_positions: list[list[float]] | None = None) -> dict[str, Any]:
        """Apply all randomizations at once.

        Args:
            base_positions: List of base positions for objects.

        Returns:
            Complete randomization parameters.

        """
        result: dict[str, Any] = {
            "lighting": self.randomize_lighting(),
            "texture": self.randomize_texture(),
            "physics": self.randomize_physics(),
        }

        if base_positions:
            result["positions"] = [
                self.randomize_position(pos) for pos in base_positions
            ]

        return result