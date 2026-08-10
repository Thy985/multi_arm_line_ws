"""Tests for SkillMotionBridge parameter extraction and TaskGoal building.

Covers the pure-Python layer of the skill→Coordinator bridge:
    - extract_execution_params (TaskGoal + legacy string fallback)
    - normalize_target (defaults)
    - build_task_goal (TaskGoal message construction)
"""

from __future__ import annotations

from types import SimpleNamespace

from multi_arm_skill_runtime.skill_motion_bridge import (
    SKILL_DEFAULT_POSITION,
    build_task_goal,
    extract_execution_params,
    normalize_target,
)


class TestExtractExecutionParams:
    """extract_execution_params behavior."""

    def test_prefers_structured_task_goal(self) -> None:
        """A populated TaskGoal takes precedence over string params."""
        task_goal = SimpleNamespace(
            arm_name="arm2",
            zone_name="zone_b",
            position_name="place_low",
            object_id="blue_box",
            action_type="place",
        )
        params = extract_execution_params(task_goal, ("arm1", "zone_a"))
        assert params["arm_name"] == "arm2"
        assert params["zone_name"] == "zone_b"
        assert params["position_name"] == "place_low"
        assert params["object_id"] == "blue_box"
        assert params["action_type"] == "place"

    def test_empty_task_goal_falls_back_to_string_params(self) -> None:
        """An unpopulated TaskGoal falls back to the legacy string protocol."""
        empty = SimpleNamespace(arm_name="", zone_name="", position_name="",
                                object_id="", action_type="")
        params = extract_execution_params(empty, ("arm1:zone_a:ready:red_cube",))
        assert params["arm_name"] == "arm1"
        assert params["zone_name"] == "zone_a"
        assert params["position_name"] == "ready"
        assert params["object_id"] == "red_cube"

    def test_string_params_multiple_elements(self) -> None:
        """String list with 3 elements maps arm/zone/position."""
        params = extract_execution_params(None, ("arm1", "zone_a", "scan"))
        assert params["arm_name"] == "arm1"
        assert params["zone_name"] == "zone_a"
        assert params["position_name"] == "scan"

    def test_no_params_returns_empty(self) -> None:
        """Missing inputs produce an all-empty dict."""
        params = extract_execution_params(None, None)
        assert params["arm_name"] == ""
        assert params["position_name"] == ""


class TestNormalizeTarget:
    """normalize_target default-filling behavior."""

    def test_fills_default_position_by_skill(self) -> None:
        """Missing position is filled from the skill default."""
        out = normalize_target({"arm_name": "arm1"}, "pick_object")
        assert out["position_name"] == SKILL_DEFAULT_POSITION["pick_object"]

    def test_fills_default_arm(self) -> None:
        """Missing arm defaults to arm1."""
        out = normalize_target({}, "move_object")
        assert out["arm_name"] == "arm1"
        assert out["position_name"] == SKILL_DEFAULT_POSITION["move_object"]

    def test_preserves_explicit_target(self) -> None:
        """Explicit values are never overwritten."""
        out = normalize_target(
            {"arm_name": "arm2", "position_name": "home"}, "place_object"
        )
        assert out["arm_name"] == "arm2"
        assert out["position_name"] == "home"


class TestBuildTaskGoal:
    """build_task_goal message construction."""

    def test_builds_task_goal_fields(self) -> None:
        """Normalized dict maps onto TaskGoal fields."""
        params = normalize_target(
            {
                "arm_name": "arm2",
                "zone_name": "zone_b",
                "position_name": "place_low",
                "object_id": "blue_box",
                "action_type": "place",
                "approach": "side",
            },
            "place_object",
        )
        goal = build_task_goal(params)
        assert goal.arm_name == "arm2"
        assert goal.zone_name == "zone_b"
        assert goal.position_name == "place_low"
        assert goal.object_id == "blue_box"
        assert goal.action_type == "place"
        assert goal.approach == "side"

    def test_approach_defaults_to_top(self) -> None:
        """Unspecified approach defaults to 'top'.

        In the real flow extract_execution_params never emits an ``approach``
        key, so build_task_goal's ``get("approach", "top")`` resolves to "top".
        """
        params = normalize_target({"arm_name": "arm1"}, "pick_object")
        assert "approach" not in params
        goal = build_task_goal(params)
        assert goal.approach == "top"