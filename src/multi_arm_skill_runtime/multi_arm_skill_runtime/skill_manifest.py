"""Skill Manifest — declarative skill definition (similar to package.json).

A Skill Manifest declares:
  - required_capabilities (robot abilities needed)
  - input/output parameters
  - cost estimate (time, risk, success_rate)
  - preconditions (WorldModel Relation queries)
  - execute steps
  - postconditions (WorldModel Relation queries)
  - recovery strategies
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class SkillCost:
    """Cost estimate for a skill — used by Agent for skill selection."""

    time: float = 5.0
    risk: float = 0.1
    success_rate: float = 0.95

    def to_dict(self) -> dict[str, float]:
        """Serialize to dict."""
        return {"time": self.time, "risk": self.risk, "success_rate": self.success_rate}


@dataclass
class SkillManifest:
    """Declarative skill definition parsed from skill.yaml.

    Attributes:
        name: Skill name (unique identifier).
        version: Semantic version string.
        description: Human-readable description.
        required_capabilities: List of capability names needed.
        input_params: Input parameter definitions.
        output_params: Output parameter definitions.
        cost: Cost estimate (time, risk, success_rate).
        preconditions: List of precondition expressions.
        execute_steps: Ordered list of execution step names.
        postconditions: List of postcondition expressions.
        recovery: Recovery strategy mapping (failure_type -> strategy).
        raw: Raw YAML dict for extensibility.

    """

    name: str = ""
    version: str = "1.0.0"
    description: str = ""
    required_capabilities: list[str] = field(default_factory=list)
    input_params: dict[str, str] = field(default_factory=dict)
    output_params: dict[str, str] = field(default_factory=dict)
    cost: SkillCost = field(default_factory=SkillCost)
    preconditions: list[str] = field(default_factory=list)
    execute_steps: list[str] = field(default_factory=list)
    postconditions: list[str] = field(default_factory=list)
    recovery: dict[str, str] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_yaml(cls, yaml_path: str | Path) -> SkillManifest:
        """Parse a skill.yaml file into a SkillManifest.

        Args:
            yaml_path: Path to the skill.yaml file.

        Returns:
            Parsed SkillManifest instance.

        Raises:
            FileNotFoundError: If file does not exist.
            ValueError: If YAML structure is invalid.

        """
        path = Path(yaml_path)
        if not path.exists():
            raise FileNotFoundError(f"Skill manifest not found: {yaml_path}")

        with open(path) as f:
            data = yaml.safe_load(f)

        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SkillManifest:
        """Parse a dict into a SkillManifest.

        Args:
            data: Dict with skill manifest data.

        Returns:
            Parsed SkillManifest instance.

        Raises:
            ValueError: If required fields are missing.

        """
        skill_data = data.get("skill", data)

        name = skill_data.get("name", "")
        if not name:
            raise ValueError("Skill manifest must have a 'name' field")

        cost_data = skill_data.get("cost", {})
        cost = SkillCost(
            time=cost_data.get("time", 5.0),
            risk=cost_data.get("risk", 0.1),
            success_rate=cost_data.get("success_rate", 0.95),
        )

        return cls(
            name=name,
            version=skill_data.get("version", "1.0.0"),
            description=skill_data.get("description", ""),
            required_capabilities=list(
                skill_data.get("required_capabilities", {}).keys()
            ) if isinstance(skill_data.get("required_capabilities"), dict)
            else list(skill_data.get("required_capabilities", [])),
            input_params=skill_data.get("input", {}),
            output_params=skill_data.get("output", {}),
            cost=cost,
            preconditions=skill_data.get("preconditions", []),
            execute_steps=skill_data.get("execute", []),
            postconditions=skill_data.get("postconditions", []),
            recovery=skill_data.get("recovery", {}),
            raw=skill_data,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for ROS msg conversion."""
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "required_capabilities": self.required_capabilities,
            "preconditions": self.preconditions,
            "postconditions": self.postconditions,
            "parameters": list(self.input_params.keys()),
            "cost_time": self.cost.time,
            "cost_risk": self.cost.risk,
            "success_rate": self.cost.success_rate,
        }

    def validate(self) -> list[str]:
        """Validate manifest completeness.

        Returns:
            List of validation error messages (empty if valid).

        """
        errors: list[str] = []
        if not self.name:
            errors.append("Missing required field: name")
        if not self.version:
            errors.append("Missing required field: version")
        if not self.execute_steps:
            errors.append("Missing required field: execute steps")
        return errors