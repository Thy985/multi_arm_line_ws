"""Skill Registry — manages skill manifests and lifecycle entries.

Agent queries Skill Registry to find available skills (READY state only),
filtered by required capabilities, sorted by cost/risk/success_rate.
"""

from __future__ import annotations

from typing import Any

from multi_arm_skill_runtime.skill_manifest import SkillManifest
from multi_arm_skill_runtime.skill_lifecycle import (
    SkillLifecycle,
    SkillLifecycleEntry,
    SkillLifecycleState,
)


class SkillRegistry:
    """Skill Registry — central catalog of all skills.

    Manages the mapping between skill manifests and lifecycle entries.
    Agent queries this to find skills by capability, cost, or state.
    """

    def __init__(self) -> None:
        """Initialize skill registry."""
        self._manifests: dict[str, SkillManifest] = {}
        self._lifecycle = SkillLifecycle()

    @property
    def lifecycle(self) -> SkillLifecycle:
        """Get the lifecycle manager."""
        return self._lifecycle

    def install_skill(self, manifest: SkillManifest) -> str:
        """Install a skill from its manifest.

        Args:
            manifest: Skill manifest to install.

        Returns:
            Skill ID.

        """
        skill_id = self._lifecycle.install(manifest.name, manifest.version)
        self._manifests[skill_id] = manifest
        return skill_id

    def register_skill(self, skill_id: str) -> bool:
        """Register an installed skill.

        Args:
            skill_id: Skill ID.

        Returns:
            True if registration succeeded.

        """
        return self._lifecycle.register(skill_id)

    def validate_skill(
        self,
        skill_id: str,
        capability_checker: Any = None,
    ) -> bool:
        """Validate a registered skill.

        Checks:
        1. Manifest completeness
        2. Required capabilities available (if checker provided)

        Args:
            skill_id: Skill ID.
            capability_checker: Callable(cap_name) -> bool for capability check.

        Returns:
            True if validation passed.

        """
        manifest = self._manifests.get(skill_id)
        if manifest is None:
            return self._lifecycle.validate(skill_id, ["Manifest not found"])

        errors = manifest.validate()

        if capability_checker is not None:
            for cap in manifest.required_capabilities:
                if not capability_checker(cap):
                    errors.append(f"Missing required capability: {cap}")

        if errors:
            return self._lifecycle.validate(skill_id, errors)

        success = self._lifecycle.validate(skill_id)
        if success:
            self._lifecycle.make_ready(skill_id)
        return success

    def get_manifest(self, skill_id: str) -> SkillManifest | None:
        """Get skill manifest by ID.

        Args:
            skill_id: Skill ID.

        Returns:
            Manifest or None.

        """
        return self._manifests.get(skill_id)

    def find_by_name(self, name: str) -> str | None:
        """Find skill ID by name (returns first READY match).

        Args:
            name: Skill name.

        Returns:
            Skill ID or None.

        """
        for sid, manifest in self._manifests.items():
            if manifest.name == name:
                state = self._lifecycle.get_state(sid)
                if state == SkillLifecycleState.READY:
                    return sid
        return None

    def list_skills(
        self,
        required_capabilities: list[str] | None = None,
        lifecycle_state: str = "",
    ) -> list[tuple[str, SkillManifest]]:
        """List skills matching criteria.

        Args:
            required_capabilities: Filter by required capabilities (skill must have all).
            lifecycle_state: Filter by lifecycle state (empty = any).

        Returns:
            List of (skill_id, manifest) tuples.

        """
        results: list[tuple[str, SkillManifest]] = []

        target_state: SkillLifecycleState | None = None
        if lifecycle_state:
            for s in SkillLifecycleState:
                if s.value == lifecycle_state:
                    target_state = s
                    break

        for sid, manifest in self._manifests.items():
            state = self._lifecycle.get_state(sid)
            if state is None:
                continue

            if target_state is not None and state != target_state:
                continue

            if required_capabilities:
                has_all = all(
                    cap in manifest.required_capabilities
                    for cap in required_capabilities
                )
                if not has_all:
                    continue

            results.append((sid, manifest))

        return results

    def list_ready_skills(
        self,
        required_capabilities: list[str] | None = None,
    ) -> list[tuple[str, SkillManifest]]:
        """List skills in READY state.

        Args:
            required_capabilities: Filter by required capabilities.

        Returns:
            List of (skill_id, manifest) tuples, sorted by cost.

        """
        skills = self.list_skills(
            required_capabilities=required_capabilities,
            lifecycle_state=SkillLifecycleState.READY.value,
        )
        return sorted(
            skills,
            key=lambda x: (x[1].cost.time, -x[1].cost.success_rate),
        )

    def get_status(self, skill_id: str) -> dict[str, Any] | None:
        """Get skill status for ROS msg conversion.

        Args:
            skill_id: Skill ID.

        Returns:
            Status dict or None.

        """
        entry = self._lifecycle.get_entry(skill_id)
        if entry is None:
            return None
        return {
            "skill_id": entry.skill_id,
            "name": entry.name,
            "version": entry.version,
            "lifecycle_state": entry.state.value,
            "last_executed": entry.last_executed,
            "total_executions": entry.total_executions,
            "success_count": entry.success_count,
        }

    def remove_skill(self, skill_id: str) -> bool:
        """Remove a skill from the registry.

        Args:
            skill_id: Skill ID.

        Returns:
            True if removal succeeded.

        """
        if skill_id not in self._manifests:
            return False

        self._lifecycle.start_removal(skill_id)
        if self._lifecycle.finish_removal(skill_id):
            del self._manifests[skill_id]
            return True
        return False

    def get_all_skills(self) -> dict[str, SkillManifest]:
        """Get all registered skill manifests."""
        return dict(self._manifests)