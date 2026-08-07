"""Tests for HardwareAdapter."""

from pathlib import Path

import pytest
import yaml

from multi_arm_simulation.hardware_adapter import (
    HardwareAdapter,
    HardwareConfig,
    HardwareMode,
)


class TestHardwareAdapter:
    """Tests for HardwareAdapter."""

    def test_default_simulation_mode(self) -> None:
        adapter = HardwareAdapter()
        assert adapter.is_simulation is True
        assert adapter.mode == HardwareMode.SIMULATION

    def test_real_mode(self) -> None:
        config = HardwareConfig(mode=HardwareMode.REAL)
        adapter = HardwareAdapter(config)
        assert adapter.is_simulation is False

    def test_get_hardware_config_simulation(self) -> None:
        adapter = HardwareAdapter()
        config = adapter.get_hardware_config()
        assert "GazeboSimSystem" in config["hardware_interface"]

    def test_get_hardware_config_real(self) -> None:
        config = HardwareConfig(mode=HardwareMode.REAL)
        adapter = HardwareAdapter(config)
        hw_config = adapter.get_hardware_config()
        assert "ur_robot_driver" in hw_config["hardware_interface"]

    def test_get_ros2_control_config(self) -> None:
        adapter = HardwareAdapter()
        config = adapter.get_ros2_control_config()
        assert config["ros__parameters"]["update_rate"] == 500

    def test_get_ros2_control_config_real(self) -> None:
        config = HardwareConfig(mode=HardwareMode.REAL)
        adapter = HardwareAdapter(config)
        rc_config = adapter.get_ros2_control_config()
        assert rc_config["ros__parameters"]["update_rate"] == 125

    def test_switch_mode(self) -> None:
        adapter = HardwareAdapter()
        assert adapter.is_simulation is True
        adapter.switch_mode(HardwareMode.REAL)
        assert adapter.is_simulation is False

    def test_to_dict(self) -> None:
        adapter = HardwareAdapter()
        d = adapter.to_dict()
        assert d["mode"] == "simulation"
        assert "hardware_interface" in d

    def test_from_yaml(self, tmp_path: Path) -> None:
        data = {
            "active": "simulation",
            "adapters": {
                "simulation": {
                    "adapter": "gazebo",
                    "hardware_interface": "gz_ros2_control/GazeboSimSystem",
                    "controllers_file": "test.yaml",
                },
                "real": {
                    "adapter": "ur_driver",
                    "hardware_interface": "ur_robot_driver/URPositionHardwareInterface",
                    "controllers_file": "test_real.yaml",
                },
            },
        }
        path = tmp_path / "hw.yaml"
        with open(path, "w") as f:
            yaml.dump(data, f)

        adapter = HardwareAdapter.from_yaml(path)
        assert adapter.is_simulation is True

    def test_controllers_path(self) -> None:
        adapter = HardwareAdapter()
        path = adapter.get_controllers_path()
        assert "multi_arm_controllers.yaml" in path

    def test_controllers_path_real(self) -> None:
        config = HardwareConfig(mode=HardwareMode.REAL)
        adapter = HardwareAdapter(config)
        path = adapter.get_controllers_path()
        assert "real" in path