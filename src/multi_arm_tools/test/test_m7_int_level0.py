"""M7.INT Level 0 — Platform Startup Test.

Verifies that all M7 platform assets are loadable and CLI commands work
correctly WITHOUT requiring Gazebo or a running ROS2 stack.

Test scope:
    1. Scene assets (4 environments, 3 objects, 3 tasks)
    2. Task benchmark sets (3 task_sets)
    3. Capability graph (YAML + graph queries)
    4. Base interface contract (YAML)
    5. WorldModel schema (msg field existence)
    6. CLI command parsing (all subcommands)
    7. CLI subprocess execution (scene list/show)

This is the foundation gate: if Level 0 fails, Levels 1-4 cannot run.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


def _robot_cmd(args: list[str], timeout: float = 10.0) -> subprocess.CompletedProcess:
    """Run robot CLI command via subprocess."""
    env = os.environ.copy()
    env["PATH"] = f"/usr/bin:{env.get('PATH', '')}"
    env["ROS_HOME"] = "/tmp/ros_home"
    env["HOME"] = "/tmp"
    try:
        return subprocess.run(
            [sys.executable, "-m", "multi_arm_tools.cli"] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
    except subprocess.TimeoutExpired as e:
        return subprocess.CompletedProcess(
            args=args,
            returncode=-1,
            stdout=e.stdout or "",
            stderr=e.stderr or "",
        )


class TestSceneAssets:
    """Verify all scene assets are loadable."""

    def test_scene_manager_imports(self) -> None:
        """SceneManager module imports successfully."""
        from multi_arm_tools.scene_manager import SceneManager
        mgr = SceneManager()
        assert mgr is not None

    def test_all_environments_loadable(self) -> None:
        """All 4 environment YAMLs load successfully."""
        from multi_arm_tools.scene_manager import SceneManager
        mgr = SceneManager()
        scenes = mgr.list_environments()
        assert len(scenes) >= 4, f"Expected >=4 scenes, got {len(scenes)}"
        names = {s.name for s in scenes}
        expected = {"tabletop", "home", "warehouse", "lab"}
        assert expected.issubset(names), f"Missing scenes: {expected - names}"

    def test_tabletop_scene_structure(self) -> None:
        """Tabletop scene has required fields."""
        from multi_arm_tools.scene_manager import SceneManager
        mgr = SceneManager()
        scene = mgr.get_environment("tabletop")
        assert scene is not None, "tabletop scene not found"
        assert scene["name"] == "tabletop"
        assert "description" in scene

    def test_all_object_assets_loadable(self) -> None:
        """All 3 object YAMLs load successfully."""
        sim_share = Path(__file__).parent.parent.parent
        obj_dir = sim_share / "src" / "multi_arm_simulation" / "scenes" / "objects"
        if not obj_dir.exists():
            obj_dir = Path("/home/lenovo/multi_arm_line_ws/src/multi_arm_simulation/scenes/objects")
        yaml_files = list(obj_dir.glob("*.yaml"))
        assert len(yaml_files) >= 3, f"Expected >=3 object YAMLs, got {len(yaml_files)}"
        names = {f.stem for f in yaml_files}
        expected = {"cube", "cylinder", "box"}
        assert expected.issubset(names), f"Missing objects: {expected - names}"

    def test_all_task_assets_loadable(self) -> None:
        """All 3 task YAMLs load successfully."""
        task_dir = Path("/home/lenovo/multi_arm_line_ws/src/multi_arm_simulation/scenes/tasks")
        yaml_files = list(task_dir.glob("*.yaml"))
        assert len(yaml_files) >= 3, f"Expected >=3 task YAMLs, got {len(yaml_files)}"
        names = {f.stem for f in yaml_files}
        expected = {"pick_place", "assembly", "inspect"}
        assert expected.issubset(names), f"Missing tasks: {expected - names}"


class TestTaskBenchmarkSets:
    """Verify task benchmark sets are loadable."""

    def test_all_task_sets_loadable(self) -> None:
        """All 3 task_set YAMLs load successfully."""
        ts_dir = Path("/home/lenovo/multi_arm_line_ws/src/multi_arm_simulation/scenes/task_sets")
        yaml_files = list(ts_dir.glob("*.yaml"))
        assert len(yaml_files) >= 3, f"Expected >=3 task_sets, got {len(yaml_files)}"
        names = {f.stem for f in yaml_files}
        expected = {"basic", "dual_arm", "stress"}
        assert expected.issubset(names), f"Missing task_sets: {expected - names}"

    def test_basic_task_set_structure(self) -> None:
        """Basic task_set has required fields."""
        import yaml
        ts_path = Path("/home/lenovo/multi_arm_line_ws/src/multi_arm_simulation/scenes/task_sets/basic.yaml")
        with open(ts_path) as f:
            ts = yaml.safe_load(f)
        assert "name" in ts
        assert "tasks" in ts or "episodes" in ts
        assert "scene" in ts or "environment" in ts


class TestCapabilityGraph:
    """Verify capability graph is loadable and queryable."""

    def test_capability_yaml_loadable(self) -> None:
        """Capability YAML loads and has graph fields."""
        import yaml
        cap_path = Path("/home/lenovo/multi_arm_line_ws/src/multi_arm_robot_description/config/capability.yaml")
        with open(cap_path) as f:
            caps = yaml.safe_load(f)
        assert "capabilities" in caps
        assert len(caps["capabilities"]) > 0

    def test_capability_graph_queries(self) -> None:
        """Capability graph queries work."""
        from pathlib import Path
        from multi_arm_robot_description.capability_registry import CapabilityRegistry
        reg = CapabilityRegistry()
        yaml_path = Path("/home/lenovo/multi_arm_line_ws/src/multi_arm_robot_description/config/capability.yaml")
        reg.load_static_capabilities(str(yaml_path))
        deps = reg.get_dependencies("manipulation")
        assert deps is not None
        conflicts = reg.get_conflicts("force_control")
        assert conflicts is not None

    def test_capability_msg_has_graph_fields(self) -> None:
        """CapabilityInfo.msg has graph fields."""
        from multi_arm_interfaces.msg import CapabilityInfo
        msg = CapabilityInfo()
        assert hasattr(msg, "requires")
        assert hasattr(msg, "conflicts_with")
        assert hasattr(msg, "composed_of")


class TestBaseInterface:
    """Verify base interface contract is loadable."""

    def test_base_interface_yaml_loadable(self) -> None:
        """Base interface YAML loads successfully."""
        import yaml
        bi_path = Path("/home/lenovo/multi_arm_line_ws/src/multi_arm_robot_description/config/base_interface.yaml")
        assert bi_path.exists(), "base_interface.yaml not found"
        with open(bi_path) as f:
            bi = yaml.safe_load(f)
        assert "base" in bi or "steering_mode" in str(bi)

    def test_base_state_msg_exists(self) -> None:
        """BaseState.msg is importable with required fields."""
        from multi_arm_interfaces.msg import BaseState
        msg = BaseState()
        assert hasattr(msg, "is_moving")
        assert hasattr(msg, "steering_mode")
        assert hasattr(msg, "linear_velocity")
        assert hasattr(msg, "angular_velocity")


class TestWorldModelSchema:
    """Verify extended WorldModel schema (M7.0.2)."""

    def test_object_state_temporal_fields(self) -> None:
        """ObjectState.msg has temporal + uncertainty fields."""
        from multi_arm_interfaces.msg import ObjectState
        msg = ObjectState()
        assert hasattr(msg, "observed_at")
        assert hasattr(msg, "updated_at")
        assert hasattr(msg, "ttl")
        assert hasattr(msg, "position_covariance")
        assert hasattr(msg, "orientation_uncertainty")

    def test_relation_ttl_field(self) -> None:
        """Relation.msg has ttl field."""
        from multi_arm_interfaces.msg import Relation
        msg = Relation()
        assert hasattr(msg, "ttl")

    def test_query_world_at_time_field(self) -> None:
        """QueryWorld.srv has at_time field."""
        from multi_arm_interfaces.srv import QueryWorld
        req = QueryWorld.Request()
        assert hasattr(req, "at_time")


class TestCLIParsing:
    """Verify all CLI commands parse correctly."""

    @pytest.mark.parametrize("cmd", [
        ["sim", "start"],
        ["sim", "start", "--gui"],
        ["sim", "start", "--scene", "warehouse"],
        ["sim", "stop"],
        ["sim", "status"],
        ["scene", "list"],
        ["scene", "show", "tabletop"],
        ["doctor"],
        ["status"],
        ["world"],
        ["world", "red_cube"],
        ["world", "--relations"],
        ["skills"],
        ["capability"],
        ["task", "list"],
        ["task", "positions"],
        ["run", "pick_place", "red_cube", "zone_b"],
        ["run", "move", "ready", "--arm", "left_arm"],
        ["run", "pick_place", "red_cube", "--debug"],
        ["episodes"],
        ["episodes", "--failures-only"],
        ["episode", "ep_001"],
        ["analyze", "ep_001"],
        ["traces"],
        ["trace", "tr_001"],
        ["benchmark", "pick_place"],
        ["benchmark", "pick_place", "--count", "50"],
        ["watch", "--duration", "5"],
        ["evaluate"],
        ["evaluate", "--db", "/tmp/test.db"],
    ])
    def test_command_parses(self, cmd: list[str]) -> None:
        """CLI command parses without argparse error."""
        from multi_arm_tools.cli import main
        with patch.object(sys, "argv", ["robot"] + cmd):
            with patch("multi_arm_tools.cli._dispatch"):
                main()


class TestCLISubprocess:
    """Verify CLI commands execute via subprocess (no ROS2 needed)."""

    def test_scene_list_subprocess(self) -> None:
        """`robot scene list` runs and lists scenes."""
        result = _robot_cmd(["scene", "list"])
        assert result.returncode == 0, f"Failed: {result.stderr}"
        output = result.stdout.lower()
        assert "tabletop" in output, f"tabletop not in output: {result.stdout}"

    def test_scene_show_tabletop_subprocess(self) -> None:
        """`robot scene show tabletop` runs and shows details."""
        result = _robot_cmd(["scene", "show", "tabletop"])
        assert result.returncode == 0, f"Failed: {result.stderr}"
        assert "tabletop" in result.stdout.lower()

    def test_scene_show_home_subprocess(self) -> None:
        """`robot scene show home` runs successfully."""
        result = _robot_cmd(["scene", "show", "home"])
        assert result.returncode == 0, f"Failed: {result.stderr}"

    def test_scene_show_warehouse_subprocess(self) -> None:
        """`robot scene show warehouse` runs successfully."""
        result = _robot_cmd(["scene", "show", "warehouse"])
        assert result.returncode == 0, f"Failed: {result.stderr}"

    def test_scene_show_lab_subprocess(self) -> None:
        """`robot scene show lab` runs successfully."""
        result = _robot_cmd(["scene", "show", "lab"])
        assert result.returncode == 0, f"Failed: {result.stderr}"

    def test_scene_show_invalid_fails_gracefully(self) -> None:
        """`robot scene show invalid` handles missing scene gracefully."""
        result = _robot_cmd(["scene", "show", "nonexistent_scene"])
        assert result.returncode == 0, f"Should not crash: {result.stderr}"


# Import patch at module level for parametrize
from unittest.mock import patch