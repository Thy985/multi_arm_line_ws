"""Tests for M7.0.1 modular URDF (robot.xacro).

Verifies that:
1. robot.xacro (new modular) parses correctly
2. multi_arm_robot.xacro (backward-compat wrapper) parses correctly
3. Both produce equivalent URDF (same links/joints)
4. All expected components are present (base, arms, grippers, camera, ros2_control)
5. Module files exist and are includeable
"""

import os
import subprocess
import tempfile

import pytest

from ament_index_python.packages import get_package_share_directory


PKG_SHARE = get_package_share_directory("ur_simulation_gz")
URDF_DIR = os.path.join(PKG_SHARE, "urdf")


def _parse_xacro(xacro_path: str) -> tuple[int, str]:
    """Parse xacro and return (returncode, output)."""
    ctrl_file = os.path.join(PKG_SHARE, "config", "multi_arm_controllers.yaml")
    with tempfile.NamedTemporaryFile(suffix=".urdf", delete=False) as f:
        out_path = f.name
    try:
        result = subprocess.run(
            ["xacro", xacro_path, f"simulation_controllers:={ctrl_file}"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            with open(out_path, "w") as f:
                f.write(result.stdout)
        return result.returncode, result.stdout if result.returncode == 0 else result.stderr
    finally:
        if os.path.exists(out_path):
            os.unlink(out_path)


def _count_tags(urdf: str, tag: str) -> int:
    """Count XML tags in URDF string."""
    return urdf.count(f"<{tag} ")


@pytest.fixture
def modular_urdf() -> str:
    """Parse robot.xacro and return URDF string."""
    rc, output = _parse_xacro(os.path.join(URDF_DIR, "robot.xacro"))
    assert rc == 0, f"robot.xacro parse failed: {output}"
    return output


@pytest.fixture
def wrapper_urdf() -> str:
    """Parse multi_arm_robot.xacro (wrapper) and return URDF string."""
    rc, output = _parse_xacro(os.path.join(URDF_DIR, "multi_arm_robot.xacro"))
    assert rc == 0, f"multi_arm_robot.xacro parse failed: {output}"
    return output


class TestModuleFilesExist:
    """Verify all modular xacro files exist."""

    EXPECTED_MODULES = [
        "materials.xacro",
        "robot.xacro",
        "multi_arm_robot.xacro",
        "mobile_base/wheeled_base.xacro",
        "arms/dual_ur5e.xacro",
        "end_effectors/robotiq_2f_85.xacro",
        "sensors/camera.xacro",
        "sensors/imu.xacro",
        "body/torso.xacro",
        "body/head.xacro",
        "ros2_control/multi_arm_ros2_control.xacro",
    ]

    @pytest.mark.parametrize("module", EXPECTED_MODULES)
    def test_module_file_exists(self, module: str):
        path = os.path.join(URDF_DIR, module)
        assert os.path.isfile(path), f"Module file missing: {module}"


class TestXacroParsing:
    """Verify xacro files parse correctly."""

    def test_robot_xacro_parses(self, modular_urdf: str):
        assert "<robot" in modular_urdf
        assert "</robot>" in modular_urdf

    def test_wrapper_xacro_parses(self, wrapper_urdf: str):
        assert "<robot" in wrapper_urdf
        assert "</robot>" in wrapper_urdf

    def test_both_produce_same_link_count(self, modular_urdf: str, wrapper_urdf: str):
        assert _count_tags(modular_urdf, "link") == _count_tags(wrapper_urdf, "link")

    def test_both_produce_same_joint_count(self, modular_urdf: str, wrapper_urdf: str):
        assert _count_tags(modular_urdf, "joint") == _count_tags(wrapper_urdf, "joint")


class TestComponentsPresent:
    """Verify all robot components are present in the URDF."""

    def test_mobile_base_present(self, modular_urdf: str):
        assert '"base_link"' in modular_urdf
        assert "front_panel" in modular_urdf
        assert "status_led" in modular_urdf
        assert "arm1_pillar" in modular_urdf
        assert "arm2_pillar" in modular_urdf

    def test_wheels_present(self, modular_urdf: str):
        for wheel in ["wheel_fl", "wheel_fr", "wheel_bl", "wheel_br"]:
            assert wheel in modular_urdf, f"Missing wheel: {wheel}"

    def test_dual_arms_present(self, modular_urdf: str):
        for arm in ["arm1", "arm2"]:
            for joint in ["shoulder_pan_joint", "shoulder_lift_joint",
                          "elbow_joint", "wrist_1_joint", "wrist_2_joint",
                          "wrist_3_joint"]:
                assert f"{arm}_{joint}" in modular_urdf, f"Missing {arm}_{joint}"
            assert f"{arm}_tool0" in modular_urdf

    def test_grippers_present(self, modular_urdf: str):
        for arm in ["arm1", "arm2"]:
            assert f"{arm}_robotiq_base_link" in modular_urdf
            assert f"{arm}_robotiq_left_knuckle_joint" in modular_urdf
            assert f"{arm}_robotiq_left_finger_link" in modular_urdf
            assert f"{arm}_robotiq_right_knuckle_link" in modular_urdf

    def test_camera_sensor_present(self, modular_urdf: str):
        assert "arm1_wrist_camera" in modular_urdf
        assert "arm1_wrist_3_link" in modular_urdf

    def test_ros2_control_present(self, modular_urdf: str):
        assert "MultiArmSystem" in modular_urdf
        assert "GazeboSimSystem" in modular_urdf

    def test_mimic_joints_present(self, modular_urdf: str):
        mimic_count = modular_urdf.count("<mimic")
        assert mimic_count == 6, f"Expected 6 mimic joints, got {mimic_count}"

    def test_revolute_joint_count(self, modular_urdf: str):
        revolute_count = modular_urdf.count('type="revolute"')
        assert revolute_count == 20, f"Expected 20 revolute joints, got {revolute_count}"


class TestBackwardCompatibility:
    """Verify backward compatibility with existing references."""

    def test_multi_arm_robot_xacro_exists(self):
        assert os.path.isfile(os.path.join(URDF_DIR, "multi_arm_robot.xacro"))

    def test_robotiq_wrapper_exists(self):
        assert os.path.isfile(os.path.join(URDF_DIR, "robotiq_2f_85.xacro"))

    def test_wrapper_includes_robot_xacro(self):
        wrapper = os.path.join(URDF_DIR, "multi_arm_robot.xacro")
        with open(wrapper) as f:
            content = f.read()
        assert "robot.xacro" in content

    def test_robotiq_wrapper_includes_end_effectors(self):
        wrapper = os.path.join(URDF_DIR, "robotiq_2f_85.xacro")
        with open(wrapper) as f:
            content = f.read()
        assert "end_effectors/robotiq_2f_85.xacro" in content