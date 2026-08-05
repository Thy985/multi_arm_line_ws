"""Smoke tests for multi_arm_safety package."""

import pytest


def test_import_safety_level() -> None:
    from multi_arm_safety.safety_level import SafetyLevel
    assert SafetyLevel.NORMAL == 0
    assert SafetyLevel.EMERGENCY_STOP == 3


def test_import_speed_limiter() -> None:
    from multi_arm_safety.speed_limiter import SpeedLimiter
    limiter = SpeedLimiter()
    assert limiter is not None


def test_import_workspace_limiter() -> None:
    from multi_arm_safety.workspace_limiter import WorkspaceLimiter, WorkspaceBounds
    limiter = WorkspaceLimiter()
    assert limiter is not None


def test_import_collision_monitor() -> None:
    from multi_arm_safety.collision_monitor import CollisionMonitor
    monitor = CollisionMonitor()
    assert monitor is not None


def test_import_safety_supervisor() -> None:
    from multi_arm_safety.safety_supervisor import SafetySupervisor
    assert SafetySupervisor is not None


def test_safety_config_exists() -> None:
    import os
    config_path = os.path.join(
        os.path.dirname(__file__), "..", "config", "safety_config.yaml"
    )
    config_path = os.path.abspath(config_path)
    assert os.path.exists(config_path), f"Config not found at {config_path}"


def test_safety_level_allows_motion() -> None:
    from multi_arm_safety.safety_level import SafetyLevel
    assert SafetyLevel.NORMAL.allows_motion()
    assert not SafetyLevel.EMERGENCY_STOP.allows_motion()


def test_safety_level_rejects_commands_on_estop() -> None:
    from multi_arm_safety.safety_level import SafetyLevel
    assert not SafetyLevel.EMERGENCY_STOP.allows_new_commands()