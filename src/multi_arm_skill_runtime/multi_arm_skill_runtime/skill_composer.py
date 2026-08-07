"""Skill Composer — chain multiple skills into composite operations.

Example: pick_object → move_object → place_object = transport_object
"""

from __future__ import annotations

import time as _time
from dataclasses import dataclass, field
from typing import Any

from multi_arm_skill_runtime.skill_manifest import SkillManifest, SkillCost
from multi_arm_skill_runtime.skill_runtime import SkillRuntime, SkillResult, ExecutionStatus


@dataclass
class CompositeResult:
    """Result of a composite skill execution.

    Attributes:
        success: Whether all steps succeeded.
        step_results: Results of each step.
        total_duration: Total execution duration.
        completed_steps: Number of successfully completed steps.

    """

    success: bool = False
    step_results: list[SkillResult] = field(default_factory=list)
    total_duration: float = 0.0
    completed_steps: int = 0


class SkillComposer:
    """Compose multiple skills into a chain.

    Skills execute in order. If a step fails, the chain stops
    (unless the step is marked as optional).
    """

    def __init__(self, runtime: SkillRuntime) -> None:
        """Initialize skill composer.

        Args:
            runtime: SkillRuntime instance for executing individual skills.

        """
        self._runtime = runtime

    def compose(
        self,
        name: str,
        version: str = "1.0.0",
        description: str = "",
    ) -> CompositeSkillBuilder:
        """Start building a composite skill.

        Args:
            name: Composite skill name.
            version: Composite skill version.
            description: Human-readable description.

        Returns:
            CompositeSkillBuilder for fluent chaining.

        """
        return CompositeSkillBuilder(
            composer=self,
            name=name,
            version=version,
            description=description,
        )

    def execute_chain(
        self,
        steps: list[dict[str, Any]],
        context: dict[str, Any] | None = None,
    ) -> CompositeResult:
        """Execute a chain of skill steps.

        Args:
            steps: List of step dicts with keys:
                - skill_id: Skill ID to execute
                - parameters: Execution parameters
                - optional: If True, failure doesn't stop chain
            context: Shared execution context.

        Returns:
            CompositeResult with overall outcome.

        """
        context = context or {}
        start = _time.time()
        results: list[SkillResult] = []
        completed = 0

        for step in steps:
            skill_id = step["skill_id"]
            parameters = step.get("parameters", {})
            optional = step.get("optional", False)

            result = self._runtime.execute(skill_id, parameters, context)
            results.append(result)

            if result.status in (ExecutionStatus.SUCCESS, ExecutionStatus.RECOVERED):
                completed += 1
                context.setdefault("_step_outputs", {})[skill_id] = result
            elif not optional:
                break

        return CompositeResult(
            success=completed == len(steps),
            step_results=results,
            total_duration=_time.time() - start,
            completed_steps=completed,
        )


class CompositeSkillBuilder:
    """Fluent builder for composite skills."""

    def __init__(
        self,
        composer: SkillComposer,
        name: str,
        version: str = "1.0.0",
        description: str = "",
    ) -> None:
        """Initialize composite skill builder.

        Args:
            composer: SkillComposer instance.
            name: Composite skill name.
            version: Version string.
            description: Description.

        """
        self._composer = composer
        self._name = name
        self._version = version
        self._description = description
        self._steps: list[dict[str, Any]] = []
        self._required_capabilities: list[str] = []

    def add_step(
        self,
        skill_id: str,
        parameters: dict[str, Any] | None = None,
        optional: bool = False,
    ) -> CompositeSkillBuilder:
        """Add a step to the composite skill.

        Args:
            skill_id: Skill ID to execute.
            parameters: Execution parameters for this step.
            optional: If True, failure doesn't stop the chain.

        Returns:
            Self for fluent chaining.

        """
        self._steps.append({
            "skill_id": skill_id,
            "parameters": parameters or {},
            "optional": optional,
        })
        return self

    def require_capability(self, cap: str) -> CompositeSkillBuilder:
        """Add a required capability.

        Args:
            cap: Capability name.

        Returns:
            Self for fluent chaining.

        """
        self._required_capabilities.append(cap)
        return self

    def build_manifest(self) -> SkillManifest:
        """Build a composite SkillManifest.

        Returns:
            SkillManifest representing the composite skill.

        """
        total_time = sum(
            s.get("parameters", {}).get("estimated_time", 5.0)
            for s in self._steps
        )
        return SkillManifest(
            name=self._name,
            version=self._version,
            description=self._description,
            required_capabilities=self._required_capabilities,
            execute_steps=[s["skill_id"] for s in self._steps],
            cost=SkillCost(time=total_time),
        )

    def execute(self, context: dict[str, Any] | None = None) -> CompositeResult:
        """Execute the composite skill chain.

        Args:
            context: Shared execution context.

        Returns:
            CompositeResult.

        """
        return self._composer.execute_chain(self._steps, context)