"""Tests for M7.2 Scene Asset System — environments, objects, tasks."""

import os

import pytest
import yaml

from ament_index_python.packages import get_package_share_directory

from multi_arm_tools.scene_manager import SceneManager, SceneInfo


SIM_SHARE = get_package_share_directory("multi_arm_simulation")
SCENES_DIR = os.path.join(SIM_SHARE, "scenes")


@pytest.fixture
def mgr() -> SceneManager:
    return SceneManager(SCENES_DIR)


class TestDirectoryStructure:
    """Verify three-layer directory structure (验收#1)."""

    def test_environments_dir_exists(self):
        assert os.path.isdir(os.path.join(SCENES_DIR, "environments"))

    def test_objects_dir_exists(self):
        assert os.path.isdir(os.path.join(SCENES_DIR, "objects"))

    def test_tasks_dir_exists(self):
        assert os.path.isdir(os.path.join(SCENES_DIR, "tasks"))


class TestEnvironments:
    """Verify ≥4 environments (验收#2)."""

    EXPECTED_ENVS = ["tabletop", "home", "warehouse", "lab"]

    @pytest.mark.parametrize("env_name", EXPECTED_ENVS)
    def test_environment_yaml_exists(self, env_name: str):
        path = os.path.join(SCENES_DIR, "environments", f"{env_name}.yaml")
        assert os.path.isfile(path)

    def test_at_least_4_environments(self, mgr: SceneManager):
        envs = mgr.list_environments()
        assert len(envs) >= 4

    def test_tabletop_has_table(self, mgr: SceneManager):
        env = mgr.get_environment("tabletop")
        assert env is not None
        static_names = [m.get("name") for m in env.get("static_models", [])]
        assert "table" in static_names

    def test_each_env_has_workspace_bounds(self, mgr: SceneManager):
        for env_info in mgr.list_environments():
            env = mgr.get_environment(env_info.name)
            assert env is not None
            assert "workspace_bounds" in env

    def test_each_env_has_zones(self, mgr: SceneManager):
        for env_info in mgr.list_environments():
            assert env_info.num_zones > 0


class TestObjects:
    """Verify ≥3 objects with size/graspable (验收#3)."""

    EXPECTED_OBJECTS = ["cube", "cylinder", "box"]

    @pytest.mark.parametrize("obj_name", EXPECTED_OBJECTS)
    def test_object_yaml_exists(self, obj_name: str):
        path = os.path.join(SCENES_DIR, "objects", f"{obj_name}.yaml")
        assert os.path.isfile(path)

    def test_at_least_3_objects(self, mgr: SceneManager):
        objs = mgr.list_objects()
        assert len(objs) >= 3

    def test_objects_have_size(self, mgr: SceneManager):
        for obj in mgr.list_objects():
            assert "size" in obj, f"Object {obj.get('name')} missing size"

    def test_objects_have_graspable(self, mgr: SceneManager):
        for obj in mgr.list_objects():
            assert "graspable" in obj, f"Object {obj.get('name')} missing graspable"

    def test_objects_have_mass(self, mgr: SceneManager):
        for obj in mgr.list_objects():
            assert "mass" in obj, f"Object {obj.get('name')} missing mass"


class TestTasks:
    """Verify ≥3 tasks with precondition/postcondition (验收#4)."""

    EXPECTED_TASKS = ["pick_place", "assembly", "inspect"]

    @pytest.mark.parametrize("task_name", EXPECTED_TASKS)
    def test_task_yaml_exists(self, task_name: str):
        path = os.path.join(SCENES_DIR, "tasks", f"{task_name}.yaml")
        assert os.path.isfile(path)

    def test_at_least_3_tasks(self, mgr: SceneManager):
        tasks = mgr.list_tasks()
        assert len(tasks) >= 3

    def test_tasks_have_precondition(self, mgr: SceneManager):
        for task in mgr.list_tasks():
            assert "precondition" in task, f"Task {task.get('name')} missing precondition"

    def test_tasks_have_postcondition(self, mgr: SceneManager):
        for task in mgr.list_tasks():
            assert "postcondition" in task, f"Task {task.get('name')} missing postcondition"

    def test_tasks_have_steps(self, mgr: SceneManager):
        for task in mgr.list_tasks():
            assert "steps" in task, f"Task {task.get('name')} missing steps"
            assert len(task["steps"]) > 0


class TestTabletopMigration:
    """Verify tabletop is consistent with m6_test_world (验收#5)."""

    def test_tabletop_matches_m6_objects(self, mgr: SceneManager):
        env = mgr.get_environment("tabletop")
        assert env is not None
        dynamic_objects = [m.get("object") for m in env.get("dynamic_models", [])]
        assert "cube" in dynamic_objects
        assert "cylinder" in dynamic_objects

    def test_tabletop_has_table_at_correct_position(self, mgr: SceneManager):
        env = mgr.get_environment("tabletop")
        table = next(m for m in env["static_models"] if m["name"] == "table")
        assert table["position"] == [0.5, 0.0, 0.4]
        assert table["size"] == [0.8, 1.0, 0.02]


class TestSceneManager:
    """Test SceneManager API."""

    def test_list_environments(self, mgr: SceneManager):
        envs = mgr.list_environments()
        assert len(envs) >= 4
        names = [e.name for e in envs]
        assert "tabletop" in names
        assert "home" in names
        assert "warehouse" in names
        assert "lab" in names

    def test_get_environment(self, mgr: SceneManager):
        env = mgr.get_environment("tabletop")
        assert env is not None
        assert env["name"] == "tabletop"

    def test_get_nonexistent_environment(self, mgr: SceneManager):
        assert mgr.get_environment("nonexistent") is None

    def test_list_objects(self, mgr: SceneManager):
        objs = mgr.list_objects()
        assert len(objs) >= 3

    def test_list_tasks(self, mgr: SceneManager):
        tasks = mgr.list_tasks()
        assert len(tasks) >= 3

    def test_scene_info_dataclass(self, mgr: SceneManager):
        envs = mgr.list_environments()
        for env in envs:
            assert isinstance(env, SceneInfo)
            assert env.name
            assert isinstance(env.num_static, int)
            assert isinstance(env.num_dynamic, int)


class TestSceneDifferentiation:
    """Verify different scenes have different content (验收#8)."""

    def test_tabletop_different_from_home(self, mgr: SceneManager):
        tabletop = mgr.get_environment("tabletop")
        home = mgr.get_environment("home")
        assert tabletop["static_models"] != home["static_models"]

    def test_warehouse_different_from_lab(self, mgr: SceneManager):
        warehouse = mgr.get_environment("warehouse")
        lab = mgr.get_environment("lab")
        assert warehouse["static_models"] != lab["static_models"]

    def test_different_workspace_bounds(self, mgr: SceneManager):
        envs = mgr.list_environments()
        bounds_set = set()
        for env_info in envs:
            env = mgr.get_environment(env_info.name)
            bounds = str(env.get("workspace_bounds"))
            bounds_set.add(bounds)
        assert len(bounds_set) > 1