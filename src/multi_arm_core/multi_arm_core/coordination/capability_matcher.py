"""CapabilityMatcher for matching task requirements to resource capabilities."""

from typing import Any, Dict, List, Optional

from multi_arm_core.coordination.resource_manager import Resource, ResourceType


class CapabilityMatcher:
    """Matches task requirements against available resource capabilities.

    Scoring: each matching capability adds to the score; missing required
    capabilities disqualify the resource. Results are sorted by match score
    descending.
    """

    def match(
        self,
        requirements: Dict[str, Any],
        resources: List[Resource],
        resource_type: Optional[ResourceType] = None,
    ) -> List[Resource]:
        """Find resources matching the given requirements.

        Args:
            requirements: Dict of required capabilities and their constraints.
                Example: {"payload_kg": 3.0, "reachable_zones": ["zone_a"]}
            resources: List of Resource objects to search.
            resource_type: Optional filter by resource type.

        Returns:
            List of matching resources sorted by match score (best first).
        """
        candidates = resources
        if resource_type is not None:
            candidates = [r for r in resources if r.resource_type == resource_type]

        scored: List[tuple[float, Resource]] = []
        for resource in candidates:
            score = self._compute_score(requirements, resource.capabilities)
            if score >= 0:
                scored.append((score, resource))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in scored]

    LOWER_IS_BETTER_SUFFIXES = ("_mm", "_m", "_s", "_ms", "_error", "_latency")

    def _is_lower_is_better(self, key: str) -> bool:
        """Check if a capability key represents a lower-is-better metric."""
        return any(key.endswith(suffix) for suffix in self.LOWER_IS_BETTER_SUFFIXES)

    def _compute_score(
        self,
        requirements: Dict[str, Any],
        capabilities: Dict[str, Any],
    ) -> float:
        """Compute match score between requirements and capabilities.

        Returns:
            Positive score for match, -1 for disqualification.
        """
        score = 0.0
        for key, required_value in requirements.items():
            cap_value = capabilities.get(key)
            if cap_value is None:
                return -1.0

            if isinstance(required_value, (int, float)):
                if isinstance(cap_value, (int, float)):
                    if self._is_lower_is_better(key):
                        if cap_value <= required_value:
                            score += 1.0 + (required_value - cap_value) / max(required_value, 0.001)
                        else:
                            return -1.0
                    else:
                        if cap_value >= required_value:
                            score += 1.0 + (cap_value - required_value) / max(required_value, 0.001)
                        else:
                            return -1.0
                else:
                    return -1.0

            elif isinstance(required_value, str):
                if isinstance(cap_value, str):
                    if cap_value == required_value:
                        score += 1.0
                    else:
                        return -1.0
                else:
                    return -1.0

            elif isinstance(required_value, list):
                if isinstance(cap_value, list):
                    required_set = set(str(v) for v in required_value)
                    cap_set = set(str(v) for v in cap_value)
                    if required_set.issubset(cap_set):
                        score += len(required_set)
                    else:
                        missing = required_set - cap_set
                        if len(missing) == len(required_set):
                            return -1.0
                        score += len(required_set) - len(missing)
                else:
                    return -1.0

            else:
                if cap_value == required_value:
                    score += 1.0
                else:
                    return -1.0

        return score

    def find_best_robot(
        self,
        requirements: Dict[str, Any],
        resources: List[Resource],
    ) -> Optional[Resource]:
        """Find the best matching robot for the given requirements.

        Args:
            requirements: Required capabilities (e.g. payload, zones).
            resources: All available resources.

        Returns:
            Best matching robot Resource, or None if no match.
        """
        matches = self.match(requirements, resources, ResourceType.ROBOT)
        return matches[0] if matches else None