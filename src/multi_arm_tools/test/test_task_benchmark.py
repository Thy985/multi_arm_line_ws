"""Tests for M7.3 Task Benchmark — task_sets and Episode model."""

import os

import pytest
import yaml

from ament_index_python.packages import get_package_share_directory

SIM_SHARE = get_package_share_directory("multi_arm_simulation")
SCENES_DIR = os.path.join(SIM_SHARE, "scenes")
TASK_SETS_DIR = os.path.join(SCENES_DIR, "task_sets")


class TestTaskSets:
    """Verify 3 task_set YAMLs with scene+tasks+repetitions (验收#1)."""

    EXPECTED_SETS = ["basic", "dual_arm", "stress"]

    @pytest.mark.parametrize("set_name", EXPECTED_SETS)
    def test_task_set_exists(self, set_name: str):
        path = os.path.join(TASK_SETS_DIR, f"{set_name}.yaml")
        assert os.path.isfile(path)

    def test_at_least_3_task_sets(self):
        yamls = list(yaml.safe_load(open(os.path.join(TASK_SETS_DIR, f)))
                     for f in os.listdir(TASK_SETS_DIR) if f.endswith(".yaml"))
        assert len(yamls) >= 3

    @pytest.mark.parametrize("set_name", EXPECTED_SETS)
    def test_has_scene(self, set_name: str):
        with open(os.path.join(TASK_SETS_DIR, f"{set_name}.yaml")) as f:
            data = yaml.safe_load(f)
        assert "scene" in data, f"{set_name} missing scene"

    @pytest.mark.parametrize("set_name", EXPECTED_SETS)
    def test_has_tasks(self, set_name: str):
        with open(os.path.join(TASK_SETS_DIR, f"{set_name}.yaml")) as f:
            data = yaml.safe_load(f)
        assert "tasks" in data, f"{set_name} missing tasks"
        assert len(data["tasks"]) > 0

    @pytest.mark.parametrize("set_name", EXPECTED_SETS)
    def test_has_repetitions(self, set_name: str):
        with open(os.path.join(TASK_SETS_DIR, f"{set_name}.yaml")) as f:
            data = yaml.safe_load(f)
        assert "repetitions" in data, f"{set_name} missing repetitions"
        assert data["repetitions"] > 0


class TestTaskSetScenesValid:
    """Verify task_set scenes reference valid M7.2 environments."""

    VALID_SCENES = ["tabletop", "home", "warehouse", "lab"]

    @pytest.mark.parametrize("set_name", ["basic", "dual_arm", "stress"])
    def test_scene_is_valid(self, set_name: str):
        with open(os.path.join(TASK_SETS_DIR, f"{set_name}.yaml")) as f:
            data = yaml.safe_load(f)
        assert data["scene"] in self.VALID_SCENES, f"{set_name} has invalid scene: {data['scene']}"


class TestEpisodeModel:
    """Verify Episode model has required fields (验收#2)."""

    def test_episode_data_msg_exists(self):
        from multi_arm_interfaces.msg import EpisodeData
        msg = EpisodeData()
        assert msg is not None

    def test_episode_has_task_type(self):
        from multi_arm_interfaces.msg import EpisodeData
        msg = EpisodeData()
        assert hasattr(msg, "task_type")

    def test_episode_has_steps(self):
        from multi_arm_interfaces.msg import EpisodeData
        msg = EpisodeData()
        assert hasattr(msg, "execution_steps_json")

    def test_episode_has_result(self):
        from multi_arm_interfaces.msg import EpisodeData
        msg = EpisodeData()
        assert hasattr(msg, "result")

    def test_episode_has_duration(self):
        from multi_arm_interfaces.msg import EpisodeData
        msg = EpisodeData()
        assert hasattr(msg, "duration")

    def test_episode_has_recovery_count(self):
        from multi_arm_interfaces.msg import EpisodeData
        msg = EpisodeData()
        assert hasattr(msg, "recovery_count")

    def test_episode_has_initial_world(self):
        from multi_arm_interfaces.msg import EpisodeData
        msg = EpisodeData()
        assert hasattr(msg, "initial_world_json")


class TestBenchmarkRunner:
    """Verify BenchmarkRunner exists and can load task_sets (验收#3)."""

    def test_benchmark_runner_importable(self):
        from multi_arm_tools.benchmark_runner import BenchmarkRunner
        assert BenchmarkRunner is not None

    def test_task_set_basic_loadable(self):
        path = os.path.join(TASK_SETS_DIR, "basic.yaml")
        with open(path) as f:
            data = yaml.safe_load(f)
        assert data["name"] == "basic"
        assert data["scene"] == "tabletop"
        assert data["repetitions"] == 5
        assert len(data["tasks"]) == 3

    def test_task_set_stress_has_more_repetitions(self):
        with open(os.path.join(TASK_SETS_DIR, "basic.yaml")) as f:
            basic = yaml.safe_load(f)
        with open(os.path.join(TASK_SETS_DIR, "stress.yaml")) as f:
            stress = yaml.safe_load(f)
        assert stress["repetitions"] > basic["repetitions"]


class TestSuccessStatistics:
    """Verify success rate statistics structure (验收#4)."""

    def test_benchmark_runner_has_run_method(self):
        from multi_arm_tools.benchmark_runner import BenchmarkRunner
        assert hasattr(BenchmarkRunner, "run")


class TestEpisodeRecording:
    """Verify Episode recording infrastructure (验收#5)."""

    def test_experience_recorder_importable(self):
        from multi_arm_experience.experience_recorder import ExperienceRecorder
        assert ExperienceRecorder is not None

    def test_dataset_exporter_importable(self):
        from multi_arm_experience.dataset_exporter import DatasetExporter
        assert DatasetExporter is not None


class TestFailureAnalysis:
    """Verify failure analysis infrastructure (验收#6)."""

    def test_episode_analyzer_importable(self):
        from multi_arm_tools.analyzer import EpisodeAnalyzer
        assert EpisodeAnalyzer is not None

    def test_analyzer_has_analyze_method(self):
        from multi_arm_tools.analyzer import EpisodeAnalyzer
        assert hasattr(EpisodeAnalyzer, "analyze")