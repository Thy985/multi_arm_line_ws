"""BT Skill Wrapper — wrap existing BehaviorTree XML as a Skill.

This enables backward compatibility: BT XML tasks can be registered
as Skills without rewriting them.
"""

from __future__ import annotations

from typing import Any

from multi_arm_skill_runtime.skill_manifest import SkillManifest, SkillCost


def bt_xml_to_skill_manifest(
    bt_xml_path: str,
    skill_name: str = "",
    version: str = "1.0.0",
    description: str = "",
    required_capabilities: list[str] | None = None,
) -> SkillManifest:
    """Convert a BT XML file to a SkillManifest.

    Args:
        bt_xml_path: Path to the BT XML file.
        skill_name: Override skill name (empty = use filename).
        version: Skill version.
        description: Skill description.
        required_capabilities: Required capabilities (empty = ["manipulation"]).

    Returns:
        SkillManifest representing the BT as a skill.

    """
    from pathlib import Path

    path = Path(bt_xml_path)
    if not skill_name:
        skill_name = path.stem

    return SkillManifest(
        name=skill_name,
        version=version,
        description=description or f"BT-wrapped skill from {path.name}",
        required_capabilities=required_capabilities or ["manipulation"],
        execute_steps=[f"bt_execute({path.name})"],
        cost=SkillCost(time=10.0, risk=0.15, success_rate=0.90),
        preconditions=[],
        postconditions=[],
        recovery={"default": "retry(1) → abort"},
        raw={"bt_xml_path": str(path)},
    )


class BTSkillWrapper:
    """Wrapper that adapts BT execution to Skill execution interface.

    This allows the SkillRuntime to execute BT-based skills
    using the same execute() interface as native skills.
    """

    def __init__(self, bt_xml_path: str) -> None:
        """Initialize BT skill wrapper.

        Args:
            bt_xml_path: Path to BT XML file.

        """
        self._bt_xml_path = bt_xml_path
        self._manifest = bt_xml_to_skill_manifest(bt_xml_path)

    @property
    def manifest(self) -> SkillManifest:
        """Get the skill manifest for this BT wrapper."""
        return self._manifest

    def execute(self, **kwargs: Any) -> bool:
        """Execute the BT as a skill.

        In production, this would:
        1. Load the BT XML
        2. Set blackboard variables from kwargs
        3. Tick the BT until SUCCESS/FAILURE
        4. Return the result

        For now, returns True (placeholder for BT execution).

        Args:
            **kwargs: Execution parameters.

        Returns:
            True if BT execution succeeded.

        """
        return True