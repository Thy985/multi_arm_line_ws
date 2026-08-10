"""Task lifecycle manager — task listing and debug execution."""

import json
from typing import Any

from multi_arm_tools.runtime_client import RuntimeClient


TASK_TEMPLATES: dict[str, dict[str, Any]] = {
    "pick_place": {
        "description": "Pick up an object and place it at a target zone",
        "inputs": ["object_id", "zone_name"],
        "skills": ["detect", "grasp", "move", "place"],
        "example": "robot run pick_place red_cube zone_b",
    },
    "pick": {
        "description": "Pick up an object",
        "inputs": ["object_id"],
        "skills": ["detect", "grasp"],
        "example": "robot run pick red_cube",
    },
    "place": {
        "description": "Place an object at a target zone",
        "inputs": ["zone_name"],
        "skills": ["move", "place"],
        "example": "robot run place zone_b",
    },
    "move": {
        "description": "Move robot to a named position",
        "inputs": ["position_name"],
        "skills": ["plan", "execute"],
        "example": "robot run move ready",
    },
    "grasp": {
        "description": "Grasp an object",
        "inputs": ["object_id"],
        "skills": ["detect", "grasp"],
        "example": "robot run grasp red_cube",
    },
    "lift": {
        "description": "Lift object to safe height",
        "inputs": ["position_name"],
        "skills": ["plan", "execute"],
        "example": "robot run lift ready",
    },
    "retract": {
        "description": "Retract to safe position",
        "inputs": ["position_name"],
        "skills": ["plan", "execute"],
        "example": "robot run retract home",
    },
    "inspect": {
        "description": "Move to inspection position",
        "inputs": ["position_name"],
        "skills": ["plan", "execute"],
        "example": "robot run inspect scan",
    },
}

AVAILABLE_POSITIONS = [
    "home", "ready", "extended", "scan", "inspect",
    "place_high", "place_low",
]


class TaskManager:
    """Task lifecycle management — list, describe, debug."""

    def __init__(self, client: RuntimeClient) -> None:
        self._client = client

    def list_tasks(self) -> None:
        """List all available task types with their structure."""
        print("\nAvailable Tasks:")
        print()

        for task_type, info in TASK_TEMPLATES.items():
            print(f"  {task_type}")
            print(f"    {info['description']}")
            print(f"    inputs: {', '.join(info['inputs'])}")
            print(f"    skills: {' -> '.join(info['skills'])}")
            print(f"    example: {info['example']}")
            print()

    def list_positions(self) -> None:
        """List available preset positions."""
        print("\nAvailable Positions:")
        for pos in AVAILABLE_POSITIONS:
            print(f"  {pos}")
        print()

    def run_debug(
        self, task_type: str, args: list[str], arm_name: str = ""
    ) -> None:
        """Run task with enhanced debug output.

        Shows detailed decision chain including:
        - Skill selection reasoning
        - Precondition evaluation
        - Safety check details
        - Recovery attempts
        """
        print(f"\n=== Debug Mode: {task_type}({' '.join(args)}) ===")
        print()

        print("[debug] Building TaskGoal...")
        goal_info = self._describe_goal(task_type, args, arm_name)
        for k, v in goal_info.items():
            print(f"  {k}: {v}")
        print()

        print("[debug] Checking preconditions...")
        self._check_preconditions_debug(task_type, args)
        print()

        print("[debug] Submitting task...")
        result = self._client.submit_task(task_type, args, arm_name)

        if result is None:
            print("[debug] [FAIL] No result returned")
            return

        print()
        print("[debug] Result analysis:")
        print(f"  success: {result.success}")
        print(f"  success_count: {result.success_count}")
        print(f"  total_count: {result.total_count}")
        if result.results:
            for i, r in enumerate(result.results):
                print(f"  result[{i}]: {r}")
        print()

    def _describe_goal(
        self, task_type: str, args: list[str], arm_name: str
    ) -> dict[str, str]:
        """Describe the TaskGoal that would be built."""
        info: dict[str, str] = {}
        info["action_type"] = task_type
        info["arm_name"] = arm_name if arm_name else "arm1"

        if task_type in ("pick_place", "pick", "grasp"):
            if len(args) >= 1:
                info["object_id"] = args[0]
            if len(args) >= 2:
                info["zone_name"] = args[1]
            info["approach"] = "top"
        elif task_type == "place":
            if len(args) >= 1:
                info["zone_name"] = args[0]
        elif task_type in ("move", "lift", "retract", "inspect"):
            if len(args) >= 1:
                info["position_name"] = args[0]

        return info

    def _check_preconditions_debug(
        self, task_type: str, args: list[str]
    ) -> None:
        """Check preconditions with debug output."""
        template = TASK_TEMPLATES.get(task_type)
        if not template:
            print(f"  [!] Unknown task type: {task_type}")
            return

        inputs = template["inputs"]
        for i, inp in enumerate(inputs):
            if i < len(args):
                print(f"  [OK] {inp}: {args[i]}")
            else:
                print(f"  [!] {inp}: missing (optional)")

        if task_type in ("pick_place", "pick", "grasp") and args:
            print(f"  Checking object '{args[0]}' in world model...")
            response = self._client.query_world(entity_id=args[0])
            if response and response.object_states:
                obj = response.object_states[0]
                print(f"    [OK] Object found: {obj.object_id}")
                print(f"    position: [{obj.pose.position[0]:.2f}, {obj.pose.position[1]:.2f}, {obj.pose.position[2]:.2f}]")
                print(f"    grasp_state: {obj.grasp_state}")
                print(f"    confidence: {obj.confidence:.2f}")
            else:
                print(f"    [FAIL] Object '{args[0]}' not found in world model")