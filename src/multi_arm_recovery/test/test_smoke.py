"""Smoke tests for multi_arm_recovery package imports."""

import pytest


def test_import_failure_classifier():
    from multi_arm_recovery.failure_classifier import FailureClassifier
    assert FailureClassifier is not None


def test_import_failure_type():
    from multi_arm_recovery.failure_classifier import FailureType
    assert FailureType.PLANNING_FAILURE is not None


def test_import_failure_event():
    from multi_arm_recovery.failure_classifier import FailureEvent
    assert FailureEvent is not None


def test_import_recovery_manager():
    from multi_arm_recovery.recovery_manager import RecoveryManager
    assert RecoveryManager is not None


def test_import_recovery_status():
    from multi_arm_recovery.recovery_manager import RecoveryStatus
    assert RecoveryStatus.RECOVERED is not None


def test_import_planning_handler():
    from multi_arm_recovery.handlers.planning_failure import PlanningFailureHandler
    assert PlanningFailureHandler is not None


def test_import_collision_handler():
    from multi_arm_recovery.handlers.collision_handler import CollisionHandler
    assert CollisionHandler is not None


def test_import_resource_timeout_handler():
    from multi_arm_recovery.handlers.resource_timeout import ResourceTimeoutHandler
    assert ResourceTimeoutHandler is not None


def test_import_controller_failure_handler():
    from multi_arm_recovery.handlers.controller_failure import ControllerFailureHandler
    assert ControllerFailureHandler is not None


def test_import_grasp_retry_handler():
    from multi_arm_recovery.handlers.grasp_retry import GraspRetryHandler
    assert GraspRetryHandler is not None


def test_five_failure_types():
    from multi_arm_recovery.failure_classifier import FailureType
    expected = [
        FailureType.PLANNING_FAILURE,
        FailureType.COLLISION_DETECTED,
        FailureType.RESOURCE_TIMEOUT,
        FailureType.CONTROLLER_FAILURE,
        FailureType.GRASP_FAILURE,
    ]
    assert len(expected) == 5


def test_five_handlers_registered():
    from multi_arm_recovery.recovery_manager import RecoveryManager
    from multi_arm_recovery.failure_classifier import FailureType
    mgr = RecoveryManager()
    expected_types = [
        FailureType.PLANNING_FAILURE,
        FailureType.COLLISION_DETECTED,
        FailureType.RESOURCE_TIMEOUT,
        FailureType.CONTROLLER_FAILURE,
        FailureType.GRASP_FAILURE,
    ]
    for ft in expected_types:
        assert mgr.get_handler(ft) is not None