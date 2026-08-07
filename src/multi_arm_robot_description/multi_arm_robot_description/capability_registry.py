"""Dynamic Capability Registry — three-layer capability model."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import yaml


class CapabilityCategory(Enum):
    """Capability layer category."""

    STATIC = "static"
    DYNAMIC = "dynamic"
    CONTEXT = "context"


@dataclass
class Capability:
    """Single capability entry with three-layer information."""

    name: str
    available: bool = True
    value: Any = None
    reason: str = ""
    static_value: Any = None
    dynamic_value: Any = None
    context_value: Any = None

    def merge(self) -> None:
        """Merge three layers: static as base, dynamic overrides, context restricts."""
        merged_available = True
        merged_value = self.static_value
        merged_reason = ""

        if self.static_value is not None:
            if isinstance(self.static_value, dict):
                if not self.static_value.get("available", True):
                    merged_available = False
                    merged_reason = self.static_value.get("reason", "static unavailable")
                merged_value = {k: v for k, v in self.static_value.items() if k != "reason"}

        if self.dynamic_value is not None:
            if isinstance(self.dynamic_value, dict):
                if not self.dynamic_value.get("available", True):
                    merged_available = False
                    merged_reason = self.dynamic_value.get("reason", "dynamic unavailable")
                dyn_val = self.dynamic_value.get("value", self.dynamic_value)
                if "value" in self.dynamic_value:
                    merged_value = dyn_val
                elif isinstance(merged_value, dict):
                    merged_value.update({k: v for k, v in self.dynamic_value.items() if k != "reason"})
                else:
                    merged_value = dyn_val
            else:
                merged_value = self.dynamic_value

        if self.context_value is not None:
            if isinstance(self.context_value, dict):
                if not self.context_value.get("available", True):
                    merged_available = False
                    merged_reason = self.context_value.get("reason", "context unavailable")
                ctx_val = self.context_value.get("value", self.context_value)
                if "value" in self.context_value:
                    merged_value = ctx_val
                elif isinstance(merged_value, dict):
                    merged_value.update({k: v for k, v in self.context_value.items() if k != "reason"})
            else:
                merged_value = self.context_value

        self.available = merged_available
        self.value = merged_value
        self.reason = merged_reason

    def to_info_dict(self, category: str = "") -> dict[str, Any]:
        """Convert to CapabilityInfo-compatible dict."""
        return {
            "name": self.name,
            "category": category or CapabilityCategory.STATIC.value,
            "available": self.available,
            "value": json.dumps(self.value) if self.value is not None else "",
            "reason": self.reason,
        }


class CapabilityRegistry:
    """Three-layer capability model: Static + Dynamic + Context.

    Static Capability: declared in capability.yaml, loaded at startup, immutable.
    Dynamic Capability: computed at runtime, changes with robot state.
    Context Capability: computed with WorldModel, changes with environment.
    """

    def __init__(self, capability_yaml_path: str | Path | None = None) -> None:
        """Initialize registry, optionally loading static capabilities from YAML.

        Args:
            capability_yaml_path: Path to capability.yaml file.

        """
        self._static: dict[str, Capability] = {}
        self._dynamic: dict[str, Capability] = {}
        self._context: dict[str, Capability] = {}
        self._dynamic_configs: dict[str, dict] = {}
        self._context_configs: dict[str, dict] = {}

        if capability_yaml_path is not None:
            self.load_static_capabilities(capability_yaml_path)

    def load_static_capabilities(self, yaml_path: str | Path) -> None:
        """Load static capabilities from capability.yaml.

        Args:
            yaml_path: Path to capability.yaml file.

        Raises:
            FileNotFoundError: If YAML file does not exist.
            yaml.YAMLError: If YAML parsing fails.

        """
        path = Path(yaml_path)
        if not path.exists():
            raise FileNotFoundError(f"Capability YAML not found: {yaml_path}")

        with open(path) as f:
            data = yaml.safe_load(f)

        capabilities = data.get("capabilities", {})
        for name, value in capabilities.items():
            self._static[name] = Capability(
                name=name,
                static_value=value,
                available=value.get("available", True) if isinstance(value, dict) else True,
                reason=value.get("reason", "") if isinstance(value, dict) else "",
            )

        self._dynamic_configs = data.get("dynamic_capabilities", {})
        for name, config in self._dynamic_configs.items():
            default = config.get("default")
            self._dynamic[name] = Capability(name=name, dynamic_value=default)

        self._context_configs = data.get("context_capabilities", {})
        for name in self._context_configs:
            self._context[name] = Capability(name=name, context_value=None)

    def get_capability(self, name: str) -> Capability | None:
        """Get merged capability (static + dynamic + context).

        Args:
            name: Capability name (e.g., "manipulation", "gripper").

        Returns:
            Merged Capability or None if not found.

        """
        static = self._static.get(name)
        dynamic = self._dynamic.get(name)
        context = self._context.get(name)

        if static is None and dynamic is None and context is None:
            return None

        merged = Capability(name=name)
        if static is not None:
            merged.static_value = static.static_value
        if dynamic is not None:
            merged.dynamic_value = dynamic.dynamic_value
        if context is not None:
            merged.context_value = context.context_value
        merged.merge()
        return merged

    def get_all_capabilities(
        self, include_dynamic: bool = True
    ) -> list[dict[str, Any]]:
        """Get all capabilities as info dicts.

        Args:
            include_dynamic: Whether to include dynamic and context layers.

        Returns:
            List of capability info dicts.

        """
        all_names = set(self._static.keys())
        if include_dynamic:
            all_names.update(self._dynamic.keys())
            all_names.update(self._context.keys())

        result: list[dict[str, Any]] = []
        for name in sorted(all_names):
            cap = self.get_capability(name)
            if cap is not None:
                category = CapabilityCategory.STATIC.value
                if name in self._context and include_dynamic:
                    category = CapabilityCategory.CONTEXT.value
                elif name in self._dynamic and include_dynamic:
                    category = CapabilityCategory.DYNAMIC.value
                result.append(cap.to_info_dict(category))
        return result

    def update_dynamic(self, name: str, value: Any, available: bool = True, reason: str = "") -> bool:
        """Update a dynamic capability at runtime.

        Args:
            name: Capability name.
            value: New capability value.
            available: Whether capability is available.
            reason: Reason if unavailable.

        Returns:
            True if capability was updated, False if not registered.

        """
        if name not in self._dynamic and name not in self._static:
            self._dynamic[name] = Capability(name=name)

        cap = self._dynamic.get(name)
        if cap is None:
            cap = Capability(name=name)
            self._dynamic[name] = cap

        cap.dynamic_value = {"value": value, "available": available, "reason": reason}
        cap.available = available
        cap.value = value
        cap.reason = reason
        return True

    def update_context(
        self, name: str, value: Any, available: bool = True, reason: str = ""
    ) -> bool:
        """Update a context capability based on environment.

        Args:
            name: Capability name.
            value: Computed capability value.
            available: Whether capability is available in context.
            reason: Reason if unavailable.

        Returns:
            True if capability was updated.

        """
        if name not in self._context:
            self._context[name] = Capability(name=name)

        cap = self._context[name]
        cap.context_value = {"value": value, "available": available, "reason": reason}
        cap.available = available
        cap.value = value
        cap.reason = reason
        return True

    def check_overheated(self, temperature: float, threshold: float = 80.0) -> bool:
        """Check if gripper is overheated and update dynamic capability.

        Args:
            temperature: Current gripper temperature.
            threshold: Overheat threshold.

        Returns:
            True if overheated.

        """
        overheated = temperature >= threshold
        self.update_dynamic(
            "gripper_temperature",
            temperature,
            available=not overheated,
            reason="overheated" if overheated else "",
        )
        if overheated:
            self.update_dynamic(
                "gripper",
                {"available": False},
                available=False,
                reason="gripper overheated",
            )
        return overheated

    def check_payload(self, current_load: float, max_payload: float = 5.0) -> float:
        """Check remaining payload capacity and update dynamic capability.

        Args:
            current_load: Current load in kg.
            max_payload: Maximum payload in kg.

        Returns:
            Remaining payload capacity in kg.

        """
        remaining = max(0.0, max_payload - current_load)
        self.update_dynamic("payload_remaining", remaining)
        return remaining