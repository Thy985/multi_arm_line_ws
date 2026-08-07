"""Skill Runtime — executes skills with full lifecycle management.

Execution pipeline:
    1. Check lifecycle state == READY
    2. Check required_capabilities (query Capability Registry)
    3. Check preconditions (query WorldModel Relation Layer)
    4. Execute (call provided execution function)
    5. Check postconditions (query WorldModel Relation Layer)
    6. On failure → recovery strategy
    7. Monitor: update success_rate/cost → execution record
"""

from __future__ import annotations

import time as _time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable

from multi_arm_skill_runtime.skill_manifest import SkillManifest
from multi_arm_skill_runtime.skill_registry import SkillRegistry
from multi_arm_skill_runtime.skill_lifecycle import (
    SkillLifecycleState,
)


class ExecutionStatus(Enum):
    """Status of a skill execution."""

    SUCCESS = auto()
    FAILURE = auto()
    SKIPPED = auto()
    RECOVERED = auto()
    ABORTED = auto()


@dataclass
class SkillResult:
    """Result of a skill execution.

    Attributes:
        status: Execution status.
        message: Human-readable message.
        duration: Execution duration in seconds.
        postcondition_results: Results of postcondition checks.
        recovery_attempts: Number of recovery attempts made.
        failure_reason: Reason for failure if unsuccessful.

    """

    status: ExecutionStatus = ExecutionStatus.SUCCESS
    message: str = ""
    duration: float = 0.0
    postcondition_results: list[bool] = field(default_factory=list)
    recovery_attempts: int = 0
    failure_reason: str = ""


class SkillRuntime:
    """Skill execution runtime — orchestrates the full execution pipeline.

    Args:
        registry: SkillRegistry instance.
        capability_checker: Callable(cap_name) -> bool for capability checks.
        precondition_checker: Callable(expr) -> bool for precondition checks.
        postcondition_checker: Callable(expr) -> bool for postcondition checks.
        execution_functions: Dict mapping skill_name -> callable(params) -> bool.
        recovery_handler: Callable(skill_name, failure) -> bool for recovery.

    """

    def __init__(
        self,
        registry: SkillRegistry,
        capability_checker: Callable[[str], bool] | None = None,
        precondition_checker: Callable[[str, dict], bool] | None = None,
        postcondition_checker: Callable[[str, dict], bool] | None = None,
        execution_functions: dict[str, Callable[..., bool]] | None = None,
        recovery_handler: Callable[[str, str], bool] | None = None,
    ) -> None:
        """Initialize skill runtime.

        Args:
            registry: SkillRegistry instance.
            capability_checker: Callable(cap_name) -> bool.
            precondition_checker: Callable(expr, context) -> bool.
            postcondition_checker: Callable(expr, context) -> bool.
            execution_functions: Dict skill_name -> callable.
            recovery_handler: Callable(skill_name, failure) -> bool.

        """
        self._registry = registry
        self._capability_checker = capability_checker
        self._precondition_checker = precondition_checker
        self._postcondition_checker = postcondition_checker
        self._execution_functions = execution_functions or {}
        self._recovery_handler = recovery_handler

    def register_execution_function(
        self,
        skill_name: str,
        func: Callable[..., bool],
    ) -> None:
        """Register an execution function for a skill.

        Args:
            skill_name: Skill name.
            func: Callable that executes the skill.

        """
        self._execution_functions[skill_name] = func

    def execute(
        self,
        skill_id: str,
        parameters: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> SkillResult:
        """Execute a skill through the full pipeline.

        Args:
            skill_id: Skill ID to execute.
            parameters: Execution parameters.
            context: Execution context (WorldModel state, etc).

        Returns:
            SkillResult with execution outcome.

        """
        parameters = parameters or {}
        context = context or {}
        start_time = _time.time()

        manifest = self._registry.get_manifest(skill_id)
        if manifest is None:
            return SkillResult(
                status=ExecutionStatus.FAILURE,
                message=f"Skill not found: {skill_id}",
                failure_reason="manifest_not_found",
            )

        state = self._registry.lifecycle.get_state(skill_id)
        if state != SkillLifecycleState.READY:
            return SkillResult(
                status=ExecutionStatus.FAILURE,
                message=f"Skill not READY (current: {state.value if state else 'None'})",
                failure_reason="not_ready",
            )

        cap_errors = self._check_capabilities(manifest)
        if cap_errors:
            return SkillResult(
                status=ExecutionStatus.FAILURE,
                message=f"Capability check failed: {cap_errors}",
                failure_reason="missing_capabilities",
                duration=_time.time() - start_time,
            )

        pre_errors = self._check_preconditions(manifest, context)
        if pre_errors:
            return SkillResult(
                status=ExecutionStatus.FAILURE,
                message=f"Precondition check failed: {pre_errors}",
                failure_reason="precondition_failed",
                duration=_time.time() - start_time,
            )

        if not self._registry.lifecycle.start_execution(skill_id):
            return SkillResult(
                status=ExecutionStatus.FAILURE,
                message="Failed to transition to EXECUTING",
                failure_reason="lifecycle_error",
            )

        exec_success = self._run_execution(manifest, parameters)

        post_results = self._check_postconditions(manifest, context)

        duration = _time.time() - start_time
        all_post_ok = all(post_results) if post_results else True

        if exec_success and all_post_ok:
            self._registry.lifecycle.finish_execution(
                skill_id, success=True, duration=duration,
            )
            self._registry.lifecycle.complete_monitoring(skill_id)
            return SkillResult(
                status=ExecutionStatus.SUCCESS,
                message="Skill executed successfully",
                duration=duration,
                postcondition_results=post_results,
            )

        failure_reason = "execution_failed" if not exec_success else "postcondition_failed"
        recovery_attempts = 0
        recovered = False

        if self._recovery_handler is not None:
            matching: list[tuple[str, str]] = []
            fallback: list[tuple[str, str]] = []
            for failure_type, strategy in manifest.recovery.items():
                if failure_type in failure_reason or failure_type == "default":
                    matching.append((failure_type, strategy))
                else:
                    fallback.append((failure_type, strategy))

            for failure_type, strategy in matching + fallback:
                recovery_attempts += 1
                try:
                    recovered = self._recovery_handler(
                        manifest.name,
                        failure_reason,
                    )
                except Exception:
                    recovered = False
                if recovered:
                    break

        self._registry.lifecycle.finish_execution(
            skill_id,
            success=recovered,
            duration=duration,
            failure_reason=failure_reason if not recovered else "",
        )
        self._registry.lifecycle.complete_monitoring(skill_id)

        if recovered:
            return SkillResult(
                status=ExecutionStatus.RECOVERED,
                message="Skill recovered after failure",
                duration=duration,
                postcondition_results=post_results,
                recovery_attempts=recovery_attempts,
                failure_reason=failure_reason,
            )

        return SkillResult(
            status=ExecutionStatus.FAILURE,
            message=f"Skill failed: {failure_reason}",
            duration=duration,
            postcondition_results=post_results,
            recovery_attempts=recovery_attempts,
            failure_reason=failure_reason,
        )

    def _check_capabilities(self, manifest: SkillManifest) -> list[str]:
        """Check required capabilities.

        Args:
            manifest: Skill manifest.

        Returns:
            List of missing capability names (empty if all present).

        """
        if self._capability_checker is None:
            return []

        missing: list[str] = []
        for cap in manifest.required_capabilities:
            if not self._capability_checker(cap):
                missing.append(cap)
        return missing

    def _check_preconditions(
        self,
        manifest: SkillManifest,
        context: dict[str, Any],
    ) -> list[str]:
        """Check preconditions against WorldModel.

        Args:
            manifest: Skill manifest.
            context: Execution context.

        Returns:
            List of failed precondition expressions (empty if all pass).

        """
        if self._precondition_checker is None:
            return []

        failed: list[str] = []
        for expr in manifest.preconditions:
            if not self._precondition_checker(expr, context):
                failed.append(expr)
        return failed

    def _check_postconditions(
        self,
        manifest: SkillManifest,
        context: dict[str, Any],
    ) -> list[bool]:
        """Check postconditions against WorldModel.

        Args:
            manifest: Skill manifest.
            context: Execution context.

        Returns:
            List of postcondition check results.

        """
        if self._postcondition_checker is None:
            return []

        return [
            self._postcondition_checker(expr, context)
            for expr in manifest.postconditions
        ]

    def _run_execution(
        self,
        manifest: SkillManifest,
        parameters: dict[str, Any],
    ) -> bool:
        """Run the skill's execution function.

        Args:
            manifest: Skill manifest.
            parameters: Execution parameters.

        Returns:
            True if execution succeeded.

        """
        func = self._execution_functions.get(manifest.name)
        if func is None:
            return True

        try:
            return bool(func(**parameters))
        except Exception:
            return False