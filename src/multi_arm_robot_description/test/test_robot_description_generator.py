"""Tests for RobotDescriptionGenerator."""

from pathlib import Path

import pytest
import yaml

from multi_arm_robot_description.robot_description_generator import (
    GeneratedFile,
    RobotDescriptionGenerator,
)


@pytest.fixture
def robot_yaml(tmp_path: Path) -> Path:
    """Create a test robot.yaml file."""
    data = {
        "robot": {"name": "dual_ur5e_test", "version": "1.0"},
        "components": {
            "arms": [
                {
                    "name": "left_arm",
                    "type": "ur5e",
                    "prefix": "left_arm_",
                    "controller": "left_arm_joint_trajectory_controller",
                    "joint_state_broadcaster": "left_arm_joint_state_broadcaster",
                },
                {
                    "name": "right_arm",
                    "type": "ur5e",
                    "prefix": "right_arm_",
                    "controller": "right_arm_joint_trajectory_controller",
                    "joint_state_broadcaster": "right_arm_joint_state_broadcaster",
                    "origin": [1.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                },
            ],
            "sensors": [],
            "end_effectors": [],
            "body": {"type": "fixed"},
        },
        "generation": {"output_dir": "generated"},
        "hardware": {"adapter": "simulation", "mode": "gazebo"},
    }
    path = tmp_path / "robot.yaml"
    with open(path, "w") as f:
        yaml.dump(data, f)
    return path


class TestRobotDescriptionGenerator:
    """Tests for RobotDescriptionGenerator."""

    def test_load_yaml(self, robot_yaml: Path) -> None:
        gen = RobotDescriptionGenerator(robot_yaml)
        assert gen.robot_name == "dual_ur5e_test"
        assert len(gen.arms) == 2

    def test_file_not_found(self) -> None:
        with pytest.raises(FileNotFoundError):
            RobotDescriptionGenerator("/nonexistent/robot.yaml")

    def test_generate_urdf(self, robot_yaml: Path) -> None:
        gen = RobotDescriptionGenerator(robot_yaml)
        result = gen.generate_urdf()
        assert "dual_ur5e_test" in result.content
        assert "left_arm_" in result.content
        assert "right_arm_" in result.content
        assert "ur_macro.xacro" in result.content

    def test_generate_controllers(self, robot_yaml: Path) -> None:
        gen = RobotDescriptionGenerator(robot_yaml)
        result = gen.generate_controllers()
        config = yaml.safe_load(result.content)
        cm = config["controller_manager"]["ros__parameters"]
        assert "left_arm_joint_trajectory_controller" in cm
        assert "right_arm_joint_trajectory_controller" in cm
        assert cm["update_rate"] == 500

    def test_generate_controllers_joint_names(self, robot_yaml: Path) -> None:
        gen = RobotDescriptionGenerator(robot_yaml)
        result = gen.generate_controllers()
        config = yaml.safe_load(result.content)
        jtc = config["left_arm_joint_trajectory_controller"]["ros__parameters"]
        assert "left_arm_shoulder_pan_joint" in jtc["joints"]
        assert len(jtc["joints"]) == 6

    def test_generate_kinematics(self, robot_yaml: Path) -> None:
        gen = RobotDescriptionGenerator(robot_yaml)
        result = gen.generate_kinematics()
        config = yaml.safe_load(result.content)
        assert "left_arm" in config
        assert "right_arm" in config
        assert "dual_arm" in config

    def test_generate_all(self, robot_yaml: Path, tmp_path: Path) -> None:
        gen = RobotDescriptionGenerator(robot_yaml)
        output_dir = tmp_path / "generated"
        files = gen.generate_all(output_dir)
        assert len(files) == 3
        for f in files:
            assert (output_dir / f.path.name).exists()

    def test_single_arm(self, tmp_path: Path) -> None:
        data = {
            "robot": {"name": "single_arm_test"},
            "components": {
                "arms": [
                    {
                        "name": "left_arm",
                        "type": "ur5e",
                        "prefix": "left_arm_",
                        "controller": "left_arm_jtc",
                        "joint_state_broadcaster": "left_arm_jsb",
                    }
                ],
            },
        }
        path = tmp_path / "robot.yaml"
        with open(path, "w") as f:
            yaml.dump(data, f)

        gen = RobotDescriptionGenerator(path)
        assert len(gen.arms) == 1

        kinematics = gen.generate_kinematics()
        config = yaml.safe_load(kinematics.content)
        assert "left_arm" in config
        assert "dual_arm" not in config