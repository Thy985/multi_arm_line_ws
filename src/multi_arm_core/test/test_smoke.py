"""Smoke test for multi_arm_core package imports."""

import pytest


def test_import_resource_manager() -> None:
    from multi_arm_core.coordination.resource_manager import (
        Resource,
        ResourceManager,
        ResourceState,
        ResourceType,
    )
    assert ResourceType.ROBOT is not None
    assert ResourceType.ZONE is not None
    assert ResourceType.TOOL is not None
    assert ResourceType.SENSOR is not None
    assert ResourceType.FIXTURE is not None


def test_import_capability_matcher() -> None:
    from multi_arm_core.coordination.capability_matcher import CapabilityMatcher
    matcher = CapabilityMatcher()
    assert matcher is not None


def test_import_time_manager() -> None:
    from multi_arm_core.coordination.time_manager import TimeManager, predict_duration
    tm = TimeManager()
    assert tm is not None
    assert predict_duration("home") > 0


def test_import_scheduler() -> None:
    from multi_arm_core.scheduler.scheduler import (
        Scheduler,
        AllocationStrategy,
        Task,
        TaskPriority,
        TaskStatus,
    )
    assert TaskPriority.CRITICAL is not None


def test_import_task_manager() -> None:
    from multi_arm_core.task.task_manager import TaskManager
    tm = TaskManager()
    assert tm is not None


def test_import_safety_interface() -> None:
    from multi_arm_core.safety.safety_interface import SafetyInterface
    assert SafetyInterface is not None


def test_five_resource_types() -> None:
    from multi_arm_core.coordination.resource_manager import ResourceType
    types = [ResourceType.ROBOT, ResourceType.ZONE, ResourceType.TOOL,
             ResourceType.SENSOR, ResourceType.FIXTURE]
    assert len(types) == 5


def test_yaml_config_exists() -> None:
    import os
    config_path = os.path.join(
        os.path.dirname(__file__), "..", "config", "robots.yaml"
    )
    config_path = os.path.abspath(config_path)
    assert os.path.exists(config_path), f"Config not found at {config_path}"