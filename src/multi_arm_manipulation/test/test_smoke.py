"""Smoke test for multi_arm_manipulation package."""

from pathlib import Path

from ament_index_python.packages import get_package_share_directory


def test_package_exists() -> None:
    """Test that the package is installed."""
    share_dir = get_package_share_directory("multi_arm_manipulation")
    assert Path(share_dir).exists()


def test_config_exists() -> None:
    """Test that config file is installed."""
    share_dir = get_package_share_directory("multi_arm_manipulation")
    assert (Path(share_dir) / "config" / "gripper_config.yaml").exists()