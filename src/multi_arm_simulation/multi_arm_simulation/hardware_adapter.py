"""Hardware Adapter — simulation/real robot switching."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import yaml


class HardwareMode(Enum):
    """Hardware operation mode."""

    SIMULATION = "simulation"
    REAL = "real"


@dataclass
class HardwareConfig:
    """Hardware adapter configuration."""

    mode: HardwareMode = HardwareMode.SIMULATION
    adapter: str = "gazebo"
    controllers_file: str = ""
    urdf_file: str = ""
    hardware_interface: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HardwareConfig":
        """Create from= from dictionary.

        Args:
            data: Configuration dict.

        Returns:
            HardwareConfig instance.

        """
        mode_str = data.get("mode", "simulation")
        mode = HardwareMode(mode_str)
        return cls(
            mode=mode,
            adapter=data.get("adapter", "gazebo" if mode == HardwareMode.SIMULATION else "ur_driver"),
            controllers_file=data.get("controllers_file", ""),
            urdf_file=data.get("urdf_file", ""),
            hardware_interface=data.get("hardware_interface", ""),
        )


class HardwareAdapter:
    """Adapter for switching between simulation and real robot.

    Both modes share robot.yaml + capability.yaml.
    Only the hardware_interface differs:

    Simulation: GazeboSimSystem plugin
    Real:       ur_robot_driver hardware_interface
    """

    SIMULATION_CONFIG = {
        "hardware_interface": "gz_ros2_control/GazeboSimSystem",
        "controllers_file": "multi_arm_controllers.yaml",
        "urdf_plugin": "gz_ros2_control",
    }

    REAL_CONFIG = {
        "hardware_interface": "ur_robot_driver/URPositionHardwareInterface",
        "controllers_file": "multi_arm_controllers_real.yaml",
        "urdf_plugin": "ros2_control",
    }

    def __init__(self, config: HardwareConfig | None = None) -> None:
        """Initialize hardware adapter.

        Args:
            config: Hardware configuration.

        """
        self._config = config or HardwareConfig()

    @property
    def mode(self) -> HardwareMode:
        """Get current hardware mode."""
        return self._config.mode

    @property
    def is_simulation(self) -> bool:
        """Check if in simulation mode."""
        return self._config.mode == HardwareMode.SIMULATION

    def get_hardware_config(self) -> dict[str, Any]:
        """Get hardware-specific configuration.

        Returns:
            Hardware config dict.

        """
        if self.is_simulation:
            return self.SIMULATION_CONFIG.copy()
        return self.REAL_CONFIG.copy()

    def get_ros2_control_config(self) -> dict[str, Any]:
        """Generate ros2_control configuration for current mode.

        Returns:
            ros2_control parameters dict.

        """
        hw_config = self.get_hardware_config()
        return {
            "ros__parameters": {
                "update_rate": 500 if self.is_simulation else 125,
                "hardware": {
                    "plugin": hw_config["hardware_interface"],
                },
            },
        }

    def get_controllers_path(self) -> str:
        """Get controllers file path for current mode.

        Returns:
            Controllers file path.

        """
        hw_config = self.get_hardware_config()
        return hw_config["controllers_file"]

    def switch_mode(self, new_mode: HardwareMode) -> None:
        """Switch hardware mode.

        Args:
            new_mode: Target hardware mode.

        """
        self._config.mode = new_mode
        self._config.adapter = "gazebo" if new_mode == HardwareMode.SIMULATION else "ur_driver"

    @classmethod
    def from_yaml(cls, yaml_path: str | Path) -> "HardwareAdapter":
        """Create adapter from YAML configuration.

        Args:
            yaml_path: Path to hardware_adapters.yaml.

        Returns:
            HardwareAdapter instance.

        """
        with open(yaml_path) as f:
            data = yaml.safe_load(f)

        active = data.get("active", "simulation")
        config_data = data.get("adapters", {}).get(active, {})
        config_data["mode"] = active
        config = HardwareConfig.from_dict(config_data)
        return cls(config)

    def to_dict(self) -> dict[str, Any]:
        """Export adapter configuration.

        Returns:
            Configuration dict.

        """
        return {
            "mode": self._config.mode.value,
            "adapter": self._config.adapter,
            "hardware_interface": self.get_hardware_config()["hardware_interface"],
            "controllers_file": self.get_controllers_path(),
            "update_rate": 500 if self.is_simulation else 125,
        }