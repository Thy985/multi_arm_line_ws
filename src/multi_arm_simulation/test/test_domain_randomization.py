"""Tests for DomainRandomizer."""

import pytest

from multi_arm_simulation.domain_randomization import (
    DomainRandomizer,
    RandomizationConfig,
)


class TestDomainRandomizer:
    """Tests for DomainRandomizer."""

    def test_randomize_lighting(self) -> None:
        dr = DomainRandomizer(seed=42)
        lighting = dr.randomize_lighting()
        assert "intensity" in lighting
        assert 0.5 <= lighting["intensity"] <= 1.5
        assert "direction" in lighting

    def test_randomize_texture(self) -> None:
        config = RandomizationConfig()
        dr = DomainRandomizer(config=config, seed=42)
        texture = dr.randomize_texture()
        assert texture in ["wood", "metal", "plastic"]

    def test_randomize_position(self) -> None:
        dr = DomainRandomizer(seed=42)
        base = [0.5, 0.5, 0.5]
        jittered = dr.randomize_position(base)
        assert abs(jittered[0] - 0.5) <= 0.05
        assert abs(jittered[1] - 0.5) <= 0.05
        assert abs(jittered[2] - 0.5) <= 0.05

    def test_randomize_physics(self) -> None:
        dr = DomainRandomizer(seed=42)
        physics = dr.randomize_physics()
        assert 0.3 <= physics["friction"] <= 0.8
        assert 0.1 <= physics["mass"] <= 2.0

    def test_randomize_camera(self) -> None:
        dr = DomainRandomizer(seed=42)
        base = [2.0, 2.0, 2.0, 0.0, 0.0, 0.0]
        jittered = dr.randomize_camera(base)
        assert abs(jittered[0] - 2.0) <= 0.1

    def test_randomize_all(self) -> None:
        dr = DomainRandomizer(seed=42)
        result = dr.randomize_all(base_positions=[[0.5, 0.5, 0.5]])
        assert "lighting" in result
        assert "texture" in result
        assert "physics" in result
        assert "positions" in result
        assert len(result["positions"]) == 1

    def test_reproducible(self) -> None:
        dr1 = DomainRandomizer(seed=42)
        dr2 = DomainRandomizer(seed=42)
        assert dr1.randomize_lighting() == dr2.randomize_lighting()

    def test_custom_config(self) -> None:
        config = RandomizationConfig()
        config.lighting = {"intensity": [10.0, 20.0], "direction": "random"}
        dr = DomainRandomizer(config=config, seed=42)
        lighting = dr.randomize_lighting()
        assert 10.0 <= lighting["intensity"] <= 20.0