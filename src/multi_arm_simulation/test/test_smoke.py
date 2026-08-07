"""Smoke test for multi_arm_simulation package."""

from pathlib import Path

from ament_index_python.packages import get_package_share_directory


def test_package_exists() -> None:
    """Test that the package is installed."""
    share_dir = get_package_share_directory("multi_arm_simulation")
    assert Path(share_dir).exists()


def test_config_files_exist() -> None:
    """Test that config files are installed."""
    share_dir = get_package_share_directory("multi_arm_simulation")
    assert (Path(share_dir) / "config" / "domain_randomization.yaml").exists()
    assert (Path(share_dir) / "config" / "hardware_adapters.yaml").exists()


def test_scenario_files_exist() -> None:
    """Test that scenario files are installed."""
    share_dir = get_package_share_directory("multi_arm_simulation")
    assert (Path(share_dir) / "scenarios" / "single_arm.yaml").exists()
    assert (Path(share_dir) / "scenarios" / "dual_arm.yaml").exists()
    assert (Path(share_dir) / "scenarios" / "conflict.yaml").exists()