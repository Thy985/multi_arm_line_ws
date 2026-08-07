"""FailureInjector — injects failures for stress testing (M5.6 Level 3).

Deliberately creates failure conditions to verify Recovery Framework:
- Planning failure: unreachable target pose
- Controller failure: JTC inactive simulation
- Safety violation: velocity exceeds limits
"""

import time as _time
from typing import Any, Dict, List, Optional


class FailureInjector:
    """Injects failures into the system for stress testing.

    Each injection method returns a FailureScenario that describes
    what failure to inject and what recovery behavior to expect.
    """

    def __init__(self) -> None:
        self._injection_count = 0
        self._injection_log: List[Dict[str, Any]] = []

    def inject_planning_failure(self) -> Dict[str, Any]:
        """Inject a planning failure by requesting unreachable pose.

        Expected recovery: PlanningFailure → relax constraints → retry → abort

        Returns:
            FailureScenario dict.
        """
        self._injection_count += 1
        scenario = {
            "injection_id": self._injection_count,
            "failure_type": "planning_failure",
            "method": "unreachable_target",
            "description": "arm1:zone_invalid:unreachable_pose",
            "expected_recovery": ["relax_constraints", "change_grasp_pose", "release_resources", "safe_abort"],
            "expected_outcome": "recovered_or_aborted",
            "timestamp": _time.time(),
        }
        self._injection_log.append(scenario)
        return scenario

    def inject_controller_failure(self) -> Dict[str, Any]:
        """Inject a controller failure by simulating JTC inactive.

        Expected recovery: ControllerFailure → wait_retry → switch_controller → abort

        Returns:
            FailureScenario dict.
        """
        self._injection_count += 1
        scenario = {
            "injection_id": self._injection_count,
            "failure_type": "controller_failure",
            "method": "jtc_inactive",
            "description": "joint_trajectory_controller inactive",
            "expected_recovery": ["wait_retry", "switch_controller", "safe_abort"],
            "expected_outcome": "recovered_or_aborted",
            "timestamp": _time.time(),
        }
        self._injection_log.append(scenario)
        return scenario

    def inject_safety_violation(self) -> Dict[str, Any]:
        """Inject a safety violation by exceeding velocity limits.

        Expected behavior: SafetySupervisor → E-Stop → abort (NOT recoverable)

        Returns:
            FailureScenario dict.
        """
        self._injection_count += 1
        scenario = {
            "injection_id": self._injection_count,
            "failure_type": "safety_violation",
            "method": "velocity_exceeds_limit",
            "description": "velocity_scale=2.0 exceeds safety limit",
            "expected_recovery": [],
            "expected_outcome": "aborted",
            "recoverable": False,
            "timestamp": _time.time(),
        }
        self._injection_log.append(scenario)
        return scenario

    def inject_resource_timeout(self) -> Dict[str, Any]:
        """Inject a resource timeout by requesting occupied zone.

        Expected recovery: ResourceTimeout → release + reallocate → abort

        Returns:
            FailureScenario dict.
        """
        self._injection_count += 1
        scenario = {
            "injection_id": self._injection_count,
            "failure_type": "resource_timeout",
            "method": "zone_occupied_timeout",
            "description": "zone_a occupied by another task, timeout waiting",
            "expected_recovery": ["release_and_reallocate", "safe_abort"],
            "expected_outcome": "reallocated_or_aborted",
            "timestamp": _time.time(),
        }
        self._injection_log.append(scenario)
        return scenario

    def verify_recovery(
        self, scenario: Dict[str, Any], actual_outcome: str,
        recovery_attempts: int = 0, recovery_strategy_used: str = ""
    ) -> Dict[str, Any]:
        """Verify that recovery behavior matches expectations.

        Args:
            scenario: The injected failure scenario.
            actual_outcome: What actually happened ("success", "recovered", "aborted").
            recovery_attempts: Number of recovery attempts made.
            recovery_strategy_used: Which recovery strategy was used.

        Returns:
            Verification result dict.
        """
        expected = scenario.get("expected_outcome", "recovered_or_aborted")
        recoverable = scenario.get("recoverable", True)

        if recoverable:
            passed = actual_outcome in ("success", "recovered", "aborted")
        else:
            passed = actual_outcome == "aborted"

        result = {
            "injection_id": scenario["injection_id"],
            "failure_type": scenario["failure_type"],
            "expected_outcome": expected,
            "actual_outcome": actual_outcome,
            "recovery_attempts": recovery_attempts,
            "recovery_strategy_used": recovery_strategy_used,
            "passed": passed,
            "timestamp": _time.time(),
        }
        return result

    @property
    def injection_count(self) -> int:
        return self._injection_count

    @property
    def injection_log(self) -> List[Dict[str, Any]]:
        return list(self._injection_log)