"""Unit tests for multi_arm_recovery package."""

import pytest
import time

from multi_arm_recovery.failure_classifier import (
    FailureClassifier,
    FailureEvent,
    FailureType,
)
from multi_arm_recovery.recovery_manager import (
    RecoveryManager,
    RecoveryRecord,
    RecoveryStatus,
)
from multi_arm_recovery.handlers.planning_failure import PlanningFailureHandler
from multi_arm_recovery.handlers.collision_handler import CollisionHandler
from multi_arm_recovery.handlers.resource_timeout import ResourceTimeoutHandler
from multi_arm_recovery.handlers.controller_failure import ControllerFailureHandler
from multi_arm_recovery.handlers.grasp_retry import GraspRetryHandler


class TestFailureClassifier:
    """Tests for FailureClassifier."""

    def setup_method(self):
        self.classifier = FailureClassifier()

    def test_classify_planning_failure_moveit_error(self):
        event = self.classifier.classify("moveit_error_-1", arm_name="arm1")
        assert event.failure_type == FailureType.PLANNING_FAILURE
        assert event.recoverable is True

    def test_classify_planning_failure_goal_send_timeout(self):
        event = self.classifier.classify("goal_send_timeout", arm_name="arm1")
        assert event.failure_type == FailureType.PLANNING_FAILURE

    def test_classify_planning_failure_goal_rejected(self):
        event = self.classifier.classify("goal_rejected", arm_name="arm1")
        assert event.failure_type == FailureType.PLANNING_FAILURE

    def test_classify_collision(self):
        event = self.classifier.classify("collision detected", arm_name="arm1")
        assert event.failure_type == FailureType.COLLISION_DETECTED
        assert event.recoverable is True

    def test_classify_collision_from_context(self):
        event = self.classifier.classify(
            "motion failed", arm_name="arm1", context={"collision_detected": True}
        )
        assert event.failure_type == FailureType.COLLISION_DETECTED

    def test_classify_safety_rejection(self):
        event = self.classifier.classify("Safety check rejected", arm_name="arm1")
        assert event.failure_type == FailureType.SAFETY_REJECTION
        assert event.recoverable is False

    def test_classify_e_stop(self):
        event = self.classifier.classify("E-Stop active", arm_name="arm1")
        assert event.failure_type == FailureType.SAFETY_REJECTION
        assert event.recoverable is False

    def test_classify_zone_occupied(self):
        event = self.classifier.classify("Zone zone_a occupied", arm_name="arm1")
        assert event.failure_type == FailureType.RESOURCE_TIMEOUT

    def test_classify_jtc_failed(self):
        event = self.classifier.classify("jtc_failed", arm_name="arm1")
        assert event.failure_type == FailureType.CONTROLLER_FAILURE

    def test_classify_execution_timeout(self):
        event = self.classifier.classify("execution_timeout", arm_name="arm1")
        assert event.failure_type == FailureType.EXECUTION_TIMEOUT

    def test_classify_grasp_failure(self):
        event = self.classifier.classify("grasp failed", arm_name="arm1")
        assert event.failure_type == FailureType.GRASP_FAILURE

    def test_classify_grasp_from_context(self):
        event = self.classifier.classify(
            "action failed", arm_name="arm1", context={"grasp_failed": True}
        )
        assert event.failure_type == FailureType.GRASP_FAILURE

    def test_classify_resource_timeout_from_context(self):
        event = self.classifier.classify(
            "wait failed", arm_name="arm1", context={"resource_timeout": True}
        )
        assert event.failure_type == FailureType.RESOURCE_TIMEOUT

    def test_classify_unknown(self):
        event = self.classifier.classify("something weird happened", arm_name="arm1")
        assert event.failure_type == FailureType.UNKNOWN
        assert event.recoverable is True

    def test_classify_preserves_arm_name(self):
        event = self.classifier.classify("jtc_failed", arm_name="arm2")
        assert event.arm_name == "arm2"

    def test_classify_preserves_task_id(self):
        event = self.classifier.classify("jtc_failed", arm_name="arm1", task_id="t123")
        assert event.task_id == "t123"

    def test_classify_preserves_context(self):
        ctx = {"zone": "zone_a", "error_code": -1}
        event = self.classifier.classify("jtc_failed", arm_name="arm1", context=ctx)
        assert event.context == ctx


class TestPlanningFailureHandler:
    """Tests for PlanningFailureHandler."""

    def setup_method(self):
        self.handler = PlanningFailureHandler()

    def test_can_handle_planning_failure(self):
        event = FailureEvent(failure_type=FailureType.PLANNING_FAILURE, arm_name="arm1")
        assert self.handler.can_handle(event) is True

    def test_cannot_handle_other_failure(self):
        event = FailureEvent(failure_type=FailureType.COLLISION_DETECTED, arm_name="arm1")
        assert self.handler.can_handle(event) is False

    def test_first_strategy_relax_constraints(self):
        event = FailureEvent(failure_type=FailureType.PLANNING_FAILURE, arm_name="arm1")
        name, params = self.handler.get_recovery_strategy(event)
        assert name == "relax_constraints"
        assert params["tolerance_multiplier"] == 2.0
        assert params["velocity_scaling"] == 0.1

    def test_second_strategy_change_grasp(self):
        event = FailureEvent(failure_type=FailureType.PLANNING_FAILURE, arm_name="arm1")
        self.handler.get_recovery_strategy(event)
        name, params = self.handler.get_recovery_strategy(event)
        assert name == "change_grasp_pose"

    def test_third_strategy_release_and_abort(self):
        event = FailureEvent(failure_type=FailureType.PLANNING_FAILURE, arm_name="arm1")
        self.handler.get_recovery_strategy(event)
        self.handler.get_recovery_strategy(event)
        name, params = self.handler.get_recovery_strategy(event)
        assert name == "release_and_abort"

    def test_exhausted_after_three_attempts(self):
        event = FailureEvent(failure_type=FailureType.PLANNING_FAILURE, arm_name="arm1")
        for _ in range(3):
            self.handler.get_recovery_strategy(event)
        assert self.handler.exhausted is True

    def test_reset_clears_attempts(self):
        event = FailureEvent(failure_type=FailureType.PLANNING_FAILURE, arm_name="arm1")
        self.handler.get_recovery_strategy(event)
        self.handler.reset()
        assert self.handler.attempts == 0
        assert self.handler.exhausted is False


class TestCollisionHandler:
    """Tests for CollisionHandler."""

    def setup_method(self):
        self.handler = CollisionHandler()

    def test_first_strategy_retreat(self):
        event = FailureEvent(failure_type=FailureType.COLLISION_DETECTED, arm_name="arm1")
        name, params = self.handler.get_recovery_strategy(event)
        assert name == "retreat_to_safe"
        assert params["safe_position"] == "home"

    def test_second_strategy_replan(self):
        event = FailureEvent(failure_type=FailureType.COLLISION_DETECTED, arm_name="arm1")
        self.handler.get_recovery_strategy(event)
        name, params = self.handler.get_recovery_strategy(event)
        assert name == "replan_with_avoidance"

    def test_exhausted_after_three(self):
        event = FailureEvent(failure_type=FailureType.COLLISION_DETECTED, arm_name="arm1")
        for _ in range(3):
            self.handler.get_recovery_strategy(event)
        assert self.handler.exhausted is True


class TestResourceTimeoutHandler:
    """Tests for ResourceTimeoutHandler."""

    def setup_method(self):
        self.handler = ResourceTimeoutHandler()

    def test_first_strategy_release_and_requeue(self):
        event = FailureEvent(failure_type=FailureType.RESOURCE_TIMEOUT, arm_name="arm1")
        name, params = self.handler.get_recovery_strategy(event)
        assert name == "release_and_requeue"
        assert params["wait_before_retry"] == 5.0

    def test_second_strategy_release_and_abort(self):
        event = FailureEvent(failure_type=FailureType.RESOURCE_TIMEOUT, arm_name="arm1")
        self.handler.get_recovery_strategy(event)
        name, _ = self.handler.get_recovery_strategy(event)
        assert name == "release_and_abort"


class TestControllerFailureHandler:
    """Tests for ControllerFailureHandler."""

    def setup_method(self):
        self.handler = ControllerFailureHandler()

    def test_first_strategy_wait_and_retry(self):
        event = FailureEvent(failure_type=FailureType.CONTROLLER_FAILURE, arm_name="arm1")
        name, params = self.handler.get_recovery_strategy(event)
        assert name == "wait_and_retry"
        assert params["wait_seconds"] == 2.0

    def test_second_strategy_switch_controller(self):
        event = FailureEvent(failure_type=FailureType.CONTROLLER_FAILURE, arm_name="arm1")
        self.handler.get_recovery_strategy(event)
        name, params = self.handler.get_recovery_strategy(event)
        assert name == "switch_controller"


class TestGraspRetryHandler:
    """Tests for GraspRetryHandler."""

    def setup_method(self):
        self.handler = GraspRetryHandler()

    def test_first_retry(self):
        event = FailureEvent(failure_type=FailureType.GRASP_FAILURE, arm_name="arm1")
        name, params = self.handler.get_recovery_strategy(event)
        assert name == "retry_grasp"
        assert params["attempt"] == 1

    def test_max_retries(self):
        event = FailureEvent(failure_type=FailureType.GRASP_FAILURE, arm_name="arm1")
        for _ in range(3):
            name, _ = self.handler.get_recovery_strategy(event)
            assert name == "retry_grasp"
        name, _ = self.handler.get_recovery_strategy(event)
        assert name == "release_and_abort"

    def test_exhausted_after_max_retries_plus_one(self):
        event = FailureEvent(failure_type=FailureType.GRASP_FAILURE, arm_name="arm1")
        for _ in range(4):
            self.handler.get_recovery_strategy(event)
        assert self.handler.exhausted is True


class TestRecoveryManager:
    """Tests for RecoveryManager."""

    def setup_method(self):
        self.manager = RecoveryManager()

    def test_classify_failure(self):
        event = self.manager.classify_failure("moveit_error_-1", arm_name="arm1")
        assert event.failure_type == FailureType.PLANNING_FAILURE

    def test_handle_non_recoverable_failure(self):
        event = FailureEvent(
            failure_type=FailureType.SAFETY_REJECTION,
            arm_name="arm1",
            message="E-Stop active",
            recoverable=False,
            task_id="t1",
        )
        record = self.manager.handle_failure(event)
        assert record.status == RecoveryStatus.ABORTED
        assert record.recovery_count == 0

    def test_handle_recoverable_with_executor_success(self):
        event = FailureEvent(
            failure_type=FailureType.PLANNING_FAILURE,
            arm_name="arm1",
            message="moveit_error_-1",
            recoverable=True,
            task_id="t2",
        )

        def mock_executor(strategy_name, params, ev):
            return strategy_name == "relax_constraints"

        record = self.manager.handle_failure(event, executor=mock_executor)
        assert record.status == RecoveryStatus.RECOVERED
        assert record.current_strategy == "relax_constraints"
        assert record.recovery_count == 1

    def test_handle_recoverable_with_executor_second_strategy(self):
        event = FailureEvent(
            failure_type=FailureType.PLANNING_FAILURE,
            arm_name="arm1",
            message="moveit_error_-1",
            recoverable=True,
            task_id="t3",
        )

        call_count = {"n": 0}

        def mock_executor(strategy_name, params, ev):
            call_count["n"] += 1
            return call_count["n"] >= 2

        record = self.manager.handle_failure(event, executor=mock_executor)
        assert record.status == RecoveryStatus.RECOVERED
        assert record.recovery_count == 2
        assert "relax_constraints" in record.strategies_tried
        assert "change_grasp_pose" in record.strategies_tried

    def test_handle_all_strategies_fail(self):
        event = FailureEvent(
            failure_type=FailureType.PLANNING_FAILURE,
            arm_name="arm1",
            message="moveit_error_-1",
            recoverable=True,
            task_id="t4",
        )

        record = self.manager.handle_failure(
            event, executor=lambda s, p, e: False
        )
        assert record.status == RecoveryStatus.FAILED
        assert record.recovery_count == 3
        assert len(record.strategies_tried) == 3

    def test_handle_without_executor_always_fails(self):
        event = FailureEvent(
            failure_type=FailureType.PLANNING_FAILURE,
            arm_name="arm1",
            message="moveit_error_-1",
            recoverable=True,
            task_id="t5",
        )
        record = self.manager.handle_failure(event)
        assert record.status == RecoveryStatus.FAILED

    def test_handle_unknown_failure_type(self):
        event = FailureEvent(
            failure_type=FailureType.UNKNOWN,
            arm_name="arm1",
            message="weird error",
            recoverable=True,
            task_id="t6",
        )
        record = self.manager.handle_failure(event)
        assert record.status == RecoveryStatus.ABORTED

    def test_history_tracking(self):
        event = FailureEvent(
            failure_type=FailureType.PLANNING_FAILURE,
            arm_name="arm1",
            message="moveit_error_-1",
            recoverable=True,
            task_id="t7",
        )
        self.manager.handle_failure(
            event, executor=lambda s, p, e: True
        )
        assert len(self.manager.get_history()) == 1
        assert self.manager.total_recoveries == 1
        assert self.manager.successful_recoveries == 1

    def test_recovery_success_rate(self):
        for i in range(4):
            event = FailureEvent(
                failure_type=FailureType.PLANNING_FAILURE,
                arm_name="arm1",
                message="moveit_error_-1",
                recoverable=True,
                task_id=f"t_rate_{i}",
            )
            self.manager.handle_failure(
                event, executor=lambda s, p, e: e.task_id.endswith("0")
            )
        rate = self.manager.recovery_success_rate
        assert rate == 0.25

    def test_get_history_by_task_id(self):
        event = FailureEvent(
            failure_type=FailureType.PLANNING_FAILURE,
            arm_name="arm1",
            message="moveit_error_-1",
            recoverable=True,
            task_id="t_specific",
        )
        self.manager.handle_failure(
            event, executor=lambda s, p, e: True
        )
        history = self.manager.get_history("t_specific")
        assert len(history) == 1
        assert history[0].task_id == "t_specific"

    def test_collision_recovery_chain(self):
        event = FailureEvent(
            failure_type=FailureType.COLLISION_DETECTED,
            arm_name="arm1",
            message="collision detected",
            recoverable=True,
            task_id="t_collision",
        )
        call_count = {"n": 0}

        def mock_executor(strategy_name, params, ev):
            call_count["n"] += 1
            return strategy_name == "replan_with_avoidance"

        record = self.manager.handle_failure(event, executor=mock_executor)
        assert record.status == RecoveryStatus.RECOVERED
        assert "retreat_to_safe" in record.strategies_tried
        assert "replan_with_avoidance" in record.strategies_tried

    def test_grasp_retry_three_times(self):
        event = FailureEvent(
            failure_type=FailureType.GRASP_FAILURE,
            arm_name="arm1",
            message="grasp failed",
            recoverable=True,
            task_id="t_grasp",
        )
        call_count = {"n": 0}

        def mock_executor(strategy_name, params, ev):
            call_count["n"] += 1
            return call_count["n"] >= 3

        record = self.manager.handle_failure(event, executor=mock_executor)
        assert record.status == RecoveryStatus.RECOVERED
        assert record.recovery_count == 3

    def test_register_custom_handler(self):
        from multi_arm_recovery.handlers.planning_failure import PlanningFailureHandler

        custom_handler = PlanningFailureHandler()
        self.manager.register_handler(FailureType.PLANNING_FAILURE, custom_handler)
        assert self.manager.get_handler(FailureType.PLANNING_FAILURE) is custom_handler

    def test_record_has_timestamps(self):
        event = FailureEvent(
            failure_type=FailureType.PLANNING_FAILURE,
            arm_name="arm1",
            message="moveit_error_-1",
            recoverable=True,
            task_id="t_time",
        )
        before = time.time()
        record = self.manager.handle_failure(
            event, executor=lambda s, p, e: True
        )
        after = time.time()
        assert record.start_time >= before - 0.1
        assert record.end_time <= after + 0.1
        assert record.end_time >= record.start_time