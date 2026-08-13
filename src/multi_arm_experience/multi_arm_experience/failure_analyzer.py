"""Failure Analyzer — examines failed episodes and suggests parameter adjustments.

This is the first step toward Experience-driven Skill Evolution (M7.5).
Not machine learning — rule-based analysis with structured suggestions.

Usage:
    analyzer = FailureAnalyzer()
    suggestion = analyzer.analyze(failed_episode)
    if suggestion:
        adjusted_params = analyzer.apply(original_params, suggestion)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from multi_arm_experience.episode import Episode


@dataclass
class FailureSuggestion:
    """Suggested adjustment based on failure analysis.

    Attributes:
        failure_type: Type of failure identified.
        adjustment_key: Parameter key to adjust.
        adjustment_value: New parameter value.
        reason: Human-readable explanation.
        confidence: Confidence in the suggestion (0.0-1.0).
    """

    failure_type: str = ""
    adjustment_key: str = ""
    adjustment_value: Any = None
    reason: str = ""
    confidence: float = 0.8


class FailureAnalyzer:
    """Analyzes failed episodes and suggests parameter adjustments.

    Rule-based analysis — each failure type maps to a known adjustment.
    """

    VALID_POSITIONS = {
        "ready", "home", "extended", "pick_ready", "place_ready",
        "safe", "observe",
    }

    def analyze(self, episode: Episode) -> FailureSuggestion | None:
        """Analyze a failed episode and suggest an adjustment.

        Args:
            episode: A failed Episode.

        Returns:
            FailureSuggestion if analysis finds a fix, None otherwise.
        """
        if episode.success:
            return None

        failure_reason = episode.metadata.get("failure_reason", "")
        task_type = episode.task_type

        if "invalid" in failure_reason and "position" in failure_reason:
            return FailureSuggestion(
                failure_type="invalid_position",
                adjustment_key="position",
                adjustment_value="ready",
                reason="Target position was invalid; fallback to known valid 'ready' position",
                confidence=0.9,
            )

        if "unreachable" in failure_reason or "planning" in failure_reason:
            return FailureSuggestion(
                failure_type="unreachable_target",
                adjustment_key="position",
                adjustment_value="home",
                reason="Target unreachable; fallback to 'home' for safe retry",
                confidence=0.85,
            )

        if "grasp" in failure_reason or "gripper" in failure_reason:
            return FailureSuggestion(
                failure_type="grasp_failure",
                adjustment_key="approach_offset_z",
                adjustment_value=0.02,
                reason="Grasp failed; increase approach height by 2cm",
                confidence=0.7,
            )

        if "timeout" in failure_reason:
            return FailureSuggestion(
                failure_type="timeout",
                adjustment_key="timeout_sec",
                adjustment_value=120.0,
                reason="Execution timed out; increase timeout to 120s",
                confidence=0.6,
            )

        if "collision" in failure_reason:
            return FailureSuggestion(
                failure_type="collision",
                adjustment_key="approach_offset_z",
                adjustment_value=0.05,
                reason="Collision detected; retract 5cm and retry",
                confidence=0.75,
            )

        return FailureSuggestion(
            failure_type="unknown",
            adjustment_key="retry",
            adjustment_value=True,
            reason=f"Unknown failure: {failure_reason}; suggest retry",
            confidence=0.3,
        )

    def apply(
        self,
        original_params: dict[str, Any],
        suggestion: FailureSuggestion,
    ) -> dict[str, Any]:
        """Apply suggestion to parameters.

        Args:
            original_params: Original task parameters.
            suggestion: Failure suggestion.

        Returns:
            Adjusted parameters.
        """
        adjusted = original_params.copy()
        adjusted[suggestion.adjustment_key] = suggestion.adjustment_value
        adjusted["_adjusted_from_failure"] = suggestion.failure_type
        return adjusted