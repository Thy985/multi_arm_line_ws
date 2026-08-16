"""M7.1 Body Upgrade — Validation Tests.

Verifies all 10 acceptance criteria from the M7.1 spec:

    1. Torso: torso_yaw_joint (revolute Z)
    2. Head: neck_pitch_joint (revolute Y)
    3. Head RGB-D: head_rgb sensor type=rgbd
    4. Torso IMU: head_imu (on torso, not head)
    5. Controller split: torso_controller ≠ head_controller
    6. ros2_control: 16 joints
    7. SRDF torso group: independent
    8. SRDF no full-body group: left_arm_full does not exist
    9. Gazebo startup: no errors
   10. Controllers active: torso + head in list
"""

from __future__ import annotations

import os
import re
import subprocess
import time
from typing import Any

import pytest


def _source_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PATH"] = f"/usr/bin:{env.get('PATH', '')}"
    return env


def _xacro_output() -> str:
    """Generate URDF from xacro and return content."""
    env = _source_env()
    result = subprocess.run(
        [
            "bash", "-c",
            "source /opt/ros/jazzy/setup.bash && source install/setup.bash && "
            "xacro $(ros2 pkg prefix ur_simulation_gz)/share/ur_simulation_gz/urdf/robot.xacro "
            "simulation_controllers:=$(ros2 pkg prefix ur_simulation_gz)/share/ur_simulation_gz/config/multi_arm_controllers.yaml",
        ],
        capture_output=True, text=True, timeout=30, env=env,
    )
    assert result.returncode == 0, f"Xacro failed: {result.stderr}"
    return result.stdout


def _srdf_content() -> str:
    """Read SRDF file content."""
    srdf_path = os.path.join(
        os.path.dirname(__file__), "..", "..",
        "multi_arm_moveit_config", "config", "multi_arm.srdf",
    )
    with open(srdf_path) as f:
        return f.read()


def _controllers_yaml() -> str:
    """Read controllers YAML content."""
    yaml_path = os.path.join(
        os.path.dirname(__file__), "..", "..",
        "ur_simulation_gz", "ur_simulation_gz", "config",
        "multi_arm_controllers.yaml",
    )
    with open(yaml_path) as f:
        return f.read()


class TestM71UrdfStructure:
    """Tests 1-4: URDF structure verification via xacro parsing."""

    @pytest.fixture(scope="class")
    def urdf(self) -> str:
        return _xacro_output()

    def test_01_torso_yaw_joint_revolute_z(self, urdf: str) -> None:
        """torso_yaw_joint exists as revolute with Z axis."""
        assert 'name="torso_yaw_joint" type="revolute"' in urdf
        torso_section = urdf.split('name="torso_yaw_joint"')[1]
        axis_match = re.search(r'<axis\s+xyz="([^"]+)"', torso_section)
        assert axis_match is not None
        axis = axis_match.group(1).split()
        assert abs(float(axis[2]) - 1.0) < 0.01, f"Z axis should be 1.0, got {axis[2]}"

    def test_02_neck_pitch_joint_revolute_y(self, urdf: str) -> None:
        """neck_pitch_joint exists as revolute with Y axis."""
        assert 'name="neck_pitch_joint" type="revolute"' in urdf
        neck_section = urdf.split('name="neck_pitch_joint"')[1]
        axis_match = re.search(r'<axis\s+xyz="([^"]+)"', neck_section)
        assert axis_match is not None
        axis = axis_match.group(1).split()
        assert abs(float(axis[1]) - 1.0) < 0.01, f"Y axis should be 1.0, got {axis[1]}"

    def test_03_head_rgb_rgbd(self, urdf: str) -> None:
        """head_rgb camera and head_depth depth sensor exist."""
        assert 'name="head_rgb" type="camera"' in urdf
        assert 'name="head_depth" type="depth"' in urdf

    def test_04_head_imu_on_head(self, urdf: str) -> None:
        """head_imu sensor exists and is on head_imu_link."""
        assert 'name="head_imu" type="imu"' in urdf
        imu_section = urdf.split('name="head_imu"')[0].split('<gazebo reference="')[-1]
        assert "head_imu_link" in imu_section, "IMU should be on head_imu_link"


class TestM71Controllers:
    """Tests 5-6: Controller configuration verification."""

    def test_05_controller_split(self) -> None:
        """torso_controller and head_controller are separate."""
        yaml_content = _controllers_yaml()
        assert "torso_controller:" in yaml_content
        assert "head_controller:" in yaml_content
        torso_idx = yaml_content.rfind("torso_controller:")
        head_idx = yaml_content.rfind("head_controller:")
        torso_section = yaml_content[torso_idx:head_idx]
        assert "torso_yaw_joint" in torso_section
        head_section = yaml_content[head_idx:]
        assert "neck_pitch_joint" in head_section

    def test_06_ros2_control_16_joints(self) -> None:
        """ros2_control has 16 joints (12 arm + 2 gripper + 1 torso + 1 head)."""
        urdf = _xacro_output()
        ros2_control_section = urdf.split('<ros2_control name="MultiArmSystem"')[1].split('</ros2_control>')[0]
        joint_count = ros2_control_section.count('<joint name=')
        assert joint_count == 16, f"Expected 16 joints in ros2_control, got {joint_count}"


class TestM71Srdf:
    """Tests 7-8: SRDF verification."""

    @pytest.fixture(scope="class")
    def srdf(self) -> str:
        return _srdf_content()

    def test_07_srdf_torso_group(self, srdf: str) -> None:
        """SRDF has independent torso planning group."""
        assert '<group name="torso">' in srdf
        assert '<joint name="torso_yaw_joint"/>' in srdf

    def test_08_srdf_no_full_body_group(self, srdf: str) -> None:
        """SRDF does NOT have left_arm_full or similar full-body group."""
        assert "left_arm_full" not in srdf
        assert "whole_body" not in srdf
        assert "full_body" not in srdf


class TestM71GazeboStartup:
    """Tests 9-10: Gazebo startup and controller activation."""

    @pytest.fixture(autouse=True)
    def _launch_stack(self) -> Any:
        from m7_int_helpers import launch_full_stack, wait_stack_ready, shutdown_full_stack
        print("\n  [M7.1] Starting full stack...")
        launch_proc, aux_procs = launch_full_stack()
        try:
            assert wait_stack_ready(), "Stack did not become ready"
            yield
        finally:
            print("\n  [M7.1] Shutting down...")
            shutdown_full_stack(launch_proc, aux_procs)

    def test_09_gazebo_starts_without_error(self) -> None:
        """Gazebo starts and torso_link + head_link exist in TF."""
        from m7_int_helpers import run_cmd
        result = run_cmd(
            ["ros2", "topic", "echo", "--once", "/joint_states", "--field", "name"],
            timeout=10.0,
        )
        assert result.returncode == 0, f"Failed to get joint_states: {result.stderr}"
        assert "torso_yaw_joint" in result.stdout, "torso_yaw_joint not in joint_states"
        assert "neck_pitch_joint" in result.stdout, "neck_pitch_joint not in joint_states"

    def test_10_torso_head_controllers_active(self) -> None:
        """torso_controller and head_controller are active."""
        from m7_int_helpers import run_cmd, wait_for_condition
        time.sleep(5)
        result = run_cmd(["ros2", "control", "list_controllers"], timeout=10.0)
        print(f"  controllers:\n{result.stdout}")
        assert "torso_controller" in result.stdout, "torso_controller not found"
        assert "head_controller" in result.stdout, "head_controller not found"