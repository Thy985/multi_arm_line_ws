"""Tests for CapabilityMatcher."""

import pytest

from multi_arm_core.coordination.resource_manager import Resource, ResourceType
from multi_arm_core.coordination.capability_matcher import CapabilityMatcher


class TestCapabilityMatcher:
    """Tests for the CapabilityMatcher class."""

    def setup_method(self) -> None:
        self.matcher = CapabilityMatcher()
        self.robots = [
            Resource(
                name="arm1",
                resource_type=ResourceType.ROBOT,
                capabilities={
                    "payload_kg": 5.0,
                    "gripper": "robotiq_2f85",
                    "precision_mm": 0.1,
                    "reachable_zones": ["zone_a", "zone_b", "home"],
                },
            ),
            Resource(
                name="arm2",
                resource_type=ResourceType.ROBOT,
                capabilities={
                    "payload_kg": 5.0,
                    "gripper": "robotiq_2f85",
                    "precision_mm": 0.02,
                    "reachable_zones": ["zone_a", "zone_c", "home"],
                },
            ),
        ]

    def test_match_by_numeric_capability(self) -> None:
        requirements = {"payload_kg": 3.0}
        matches = self.matcher.match(requirements, self.robots, ResourceType.ROBOT)
        assert len(matches) == 2

    def test_match_by_numeric_too_high(self) -> None:
        requirements = {"payload_kg": 10.0}
        matches = self.matcher.match(requirements, self.robots, ResourceType.ROBOT)
        assert len(matches) == 0

    def test_match_by_string_capability(self) -> None:
        requirements = {"gripper": "robotiq_2f85"}
        matches = self.matcher.match(requirements, self.robots, ResourceType.ROBOT)
        assert len(matches) == 2

    def test_match_by_string_no_match(self) -> None:
        requirements = {"gripper": "schunk"}
        matches = self.matcher.match(requirements, self.robots, ResourceType.ROBOT)
        assert len(matches) == 0

    def test_match_by_zone(self) -> None:
        requirements = {"reachable_zones": ["zone_b"]}
        matches = self.matcher.match(requirements, self.robots, ResourceType.ROBOT)
        assert len(matches) == 1
        assert matches[0].name == "arm1"

    def test_match_by_zone_c(self) -> None:
        requirements = {"reachable_zones": ["zone_c"]}
        matches = self.matcher.match(requirements, self.robots, ResourceType.ROBOT)
        assert len(matches) == 1
        assert matches[0].name == "arm2"

    def test_match_by_shared_zone(self) -> None:
        requirements = {"reachable_zones": ["zone_a"]}
        matches = self.matcher.match(requirements, self.robots, ResourceType.ROBOT)
        assert len(matches) == 2

    def test_higher_precision_scores_better(self) -> None:
        requirements = {"payload_kg": 3.0, "precision_mm": 0.05}
        matches = self.matcher.match(requirements, self.robots, ResourceType.ROBOT)
        assert len(matches) == 1
        assert matches[0].name == "arm2"

    def test_missing_capability_disqualifies(self) -> None:
        requirements = {"nonexistent_cap": True}
        matches = self.matcher.match(requirements, self.robots, ResourceType.ROBOT)
        assert len(matches) == 0

    def test_find_best_robot(self) -> None:
        requirements = {"reachable_zones": ["zone_c"], "payload_kg": 3.0}
        best = self.matcher.find_best_robot(requirements, self.robots)
        assert best is not None
        assert best.name == "arm2"

    def test_find_best_robot_no_match(self) -> None:
        requirements = {"reachable_zones": ["zone_x"]}
        best = self.matcher.find_best_robot(requirements, self.robots)
        assert best is None

    def test_filter_by_type(self) -> None:
        zones = [
            Resource(name="zone_a", resource_type=ResourceType.ZONE),
        ]
        requirements = {"payload_kg": 3.0}
        matches = self.matcher.match(requirements, self.robots + zones, ResourceType.ROBOT)
        assert all(r.resource_type == ResourceType.ROBOT for r in matches)

    def test_combined_requirements(self) -> None:
        requirements = {
            "payload_kg": 5.0,
            "gripper": "robotiq_2f85",
            "reachable_zones": ["zone_b"],
        }
        matches = self.matcher.match(requirements, self.robots, ResourceType.ROBOT)
        assert len(matches) == 1
        assert matches[0].name == "arm1"