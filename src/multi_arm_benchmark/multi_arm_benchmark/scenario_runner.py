"""ScenarioRunner — loads scenario YAML and executes benchmark tasks.

Reads scenario definitions from YAML files and orchestrates
task execution with the BenchmarkRecorder.
"""

import os
import time as _time
from typing import Any, Dict, List, Optional

import yaml


class ScenarioRunner:
    """Loads and executes benchmark scenarios from YAML.

    Scenario YAML format:
        name: single_arm
        description: Single arm pick-and-place benchmark
        tasks:
          - task_id: task_001
            arm_name: arm1
            action_type: move
            zone_name: zone_a
            position_name: ready
            timeout: 30.0
          - task_id: task_002
            arm_name: arm1
            action_type: move
            zone_name: zone_a
            position_name: home
            timeout: 30.0
    """

    def __init__(self, scenarios_dir: str = "") -> None:
        if not scenarios_dir:
            scenarios_dir = os.path.join(os.path.dirname(__file__), "scenarios")
        self._scenarios_dir = scenarios_dir
        self._loaded_scenario: Optional[Dict[str, Any]] = None

    @property
    def scenarios_dir(self) -> str:
        return self._scenarios_dir

    def list_scenarios(self) -> List[str]:
        """List available scenario YAML files.

        Returns:
            List of scenario names (without .yaml extension).
        """
        if not os.path.exists(self._scenarios_dir):
            return []
        scenarios = []
        for f in sorted(os.listdir(self._scenarios_dir)):
            if f.endswith(".yaml") or f.endswith(".yml"):
                scenarios.append(os.path.splitext(f)[0])
        return scenarios

    def load_scenario(self, scenario_name: str) -> Dict[str, Any]:
        """Load a scenario from YAML file.

        Args:
            scenario_name: Name of the scenario (without extension).

        Returns:
            Parsed scenario dict.

        Raises:
            FileNotFoundError: If scenario YAML not found.
            ValueError: If scenario is invalid.
        """
        yaml_path = os.path.join(self._scenarios_dir, f"{scenario_name}.yaml")
        if not os.path.exists(yaml_path):
            yaml_path = os.path.join(self._scenarios_dir, f"{scenario_name}.yml")
        if not os.path.exists(yaml_path):
            raise FileNotFoundError(f"Scenario not found: {scenario_name}")

        with open(yaml_path, "r") as f:
            scenario = yaml.safe_load(f)

        self._validate_scenario(scenario)
        self._loaded_scenario = scenario
        return scenario

    def _validate_scenario(self, scenario: Dict[str, Any]) -> None:
        """Validate scenario structure.

        Args:
            scenario: Parsed scenario dict.

        Raises:
            ValueError: If required fields are missing.
        """
        if "name" not in scenario:
            raise ValueError("Scenario missing 'name' field")
        if "tasks" not in scenario:
            raise ValueError("Scenario missing 'tasks' field")
        if not isinstance(scenario["tasks"], list):
            raise ValueError("Scenario 'tasks' must be a list")

        for i, task in enumerate(scenario["tasks"]):
            if "arm_name" not in task:
                raise ValueError(f"Task {i} missing 'arm_name'")
            if "action_type" not in task:
                raise ValueError(f"Task {i} missing 'action_type'")

    @property
    def loaded_scenario(self) -> Optional[Dict[str, Any]]:
        return self._loaded_scenario

    def get_tasks(self) -> List[Dict[str, Any]]:
        """Get tasks from the loaded scenario.

        Returns:
            List of task dicts.

        Raises:
            RuntimeError: If no scenario is loaded.
        """
        if self._loaded_scenario is None:
            raise RuntimeError("No scenario loaded")
        return self._loaded_scenario["tasks"]

    def build_execute_task_goal(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Build an ExecuteTask goal dict from a task definition.

        Args:
            task: Task definition from scenario YAML.

        Returns:
            Dict with goal fields for ExecuteTask action.
        """
        arm = task.get("arm_name", "arm1")
        zone = task.get("zone_name", "zone_a")
        position = task.get("position_name", "ready")
        action_type = task.get("action_type", "move")
        task_id = task.get("task_id", f"bench_{arm}_{_time.time():.0f}")

        goal = {
            "task_id": task_id,
            "task_type": action_type,
            "description": f"{arm}:{zone}:{position}",
            "arm_name": arm,
            "zone_name": zone,
            "position_name": position,
            "action_type": action_type,
            "object_id": task.get("object_id", ""),
            "approach": task.get("approach", "top"),
            "timeout": task.get("timeout", 30.0),
        }

        return goal