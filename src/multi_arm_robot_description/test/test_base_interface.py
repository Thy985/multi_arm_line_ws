"""Tests for M7.0.4 Base Interface — contract definition and BaseState message."""

import os

import pytest
import yaml

from ament_index_python.packages import get_package_share_directory


@pytest.fixture
def base_config() -> dict:
    """Load base_interface.yaml."""
    path = os.path.join(
        get_package_share_directory("multi_arm_robot_description"),
        "config", "base_interface.yaml",
    )
    with open(path) as f:
        return yaml.safe_load(f)


class TestBaseStateMessage:
    """Test BaseState message definition."""

    def test_base_state_exists(self):
        from multi_arm_interfaces.msg import BaseState
        msg = BaseState()
        assert msg is not None

    def test_base_state_fields(self):
        from multi_arm_interfaces.msg import BaseState
        msg = BaseState()
        assert hasattr(msg, "position")
        assert hasattr(msg, "orientation")
        assert hasattr(msg, "linear_velocity")
        assert hasattr(msg, "angular_velocity")
        assert hasattr(msg, "is_moving")
        assert hasattr(msg, "steering_mode")
        assert len(msg.position) == 3
        assert len(msg.orientation) == 4
        assert len(msg.linear_velocity) == 3
        assert len(msg.angular_velocity) == 3

    def test_base_state_defaults(self):
        from multi_arm_interfaces.msg import BaseState
        msg = BaseState()
        assert msg.is_moving is False
        assert msg.steering_mode == ""


class TestBaseInterfaceContract:
    """Test base_interface.yaml contract."""

    def test_config_loads(self, base_config: dict):
        assert "base" in base_config

    def test_steering_mode_is_fixed_in_m70(self, base_config: dict):
        assert base_config["base"]["steering_mode"] == "fixed"

    def test_not_movable_in_m70(self, base_config: dict):
        assert base_config["base"]["is_movable"] is False

    def test_tf_frames_defined(self, base_config: dict):
        assert base_config["base"]["odom_frame"] == "odom"
        assert base_config["base"]["base_frame"] == "base_link"

    def test_topics_defined(self, base_config: dict):
        assert base_config["base"]["cmd_vel_topic"] == "/cmd_vel"
        assert base_config["base"]["odom_topic"] == "/odom"
        assert base_config["base"]["base_state_topic"] == "/base/state"

    def test_wheels_fixed_in_m70(self, base_config: dict):
        wheels = base_config["base"]["wheels"]
        assert wheels["count"] == 4
        assert wheels["joint_type"] == "fixed"
        assert len(wheels["names"]) == 4

    def test_differential_params_for_m76(self, base_config: dict):
        diff = base_config["base"]["differential"]
        assert diff["wheel_separation_m"] > 0
        assert diff["max_linear_speed_ms"] > 0
        assert diff["max_angular_speed_rads"] > 0

    def test_safety_defined(self, base_config: dict):
        safety = base_config["base"]["safety"]
        assert safety["max_speed_ms"] > 0
        assert safety["estop_enabled"] is True


class TestContractConsistency:
    """Test that base_interface.yaml is consistent with URDF and capability.yaml."""

    def test_wheel_names_match_urdf(self, base_config: dict):
        from ament_index_python.packages import get_package_share_directory
        urdf_path = os.path.join(
            get_package_share_directory("ur_simulation_gz"),
            "urdf", "mobile_base", "wheeled_base.xacro",
        )
        with open(urdf_path) as f:
            xacro_content = f.read()
        for wheel_name in base_config["base"]["wheels"]["names"]:
            assert wheel_name in xacro_content, f"Wheel {wheel_name} not found in URDF"

    def test_base_frame_matches_urdf(self, base_config: dict):
        from ament_index_python.packages import get_package_share_directory
        urdf_path = os.path.join(
            get_package_share_directory("ur_simulation_gz"),
            "urdf", "mobile_base", "wheeled_base.xacro",
        )
        with open(urdf_path) as f:
            xacro_content = f.read()
        assert base_config["base"]["base_frame"] in xacro_content

    def test_mobile_capability_matches_config(self, base_config: dict):
        from ament_index_python.packages import get_package_share_directory
        cap_path = os.path.join(
            get_package_share_directory("multi_arm_robot_description"),
            "config", "capability.yaml",
        )
        with open(cap_path) as f:
            cap_data = yaml.safe_load(f)
        mobile_cap = cap_data["capabilities"]["mobile"]
        assert mobile_cap["available"] is False
        assert base_config["base"]["is_movable"] is False