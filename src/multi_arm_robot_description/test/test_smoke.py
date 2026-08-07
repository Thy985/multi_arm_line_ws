"""Smoke test for multi_arm_robot_description package."""

from pathlib import Path

from ament_index_python.packages import get_package_share_directory


def test_package_exists() -> None:
    """Test that the package is installed and findable."""
    share_dir = get_package_share_directory("multi_arm_robot_description")
    assert Path(share_dir).exists()


def test_config_files_exist() -> None:
    """Test that config files are installed."""
    share_dir = get_package_share_directory("multi_arm_robot_description")
    assert (Path(share_dir) / "config" / "robot.yaml").exists()
    assert (Path(share_dir) / "config" / "capability.yaml").exists()


def test_robot_yaml_loadable() -> None:
    """Test that robot.yaml can be loaded."""
    import yaml

    share_dir = get_package_share_directory("multi_arm_robot_description")
    robot_yaml = Path(share_dir) / "config" / "robot.yaml"
    with open(robot_yaml) as f:
        data = yaml.safe_load(f)
    assert data["robot"]["name"] == "dual_ur5e_platform"
    assert len(data["components"]["arms"]) == 2


def test_capability_yaml_loadable() -> None:
    """Test that capability.yaml can be loaded."""
    import yaml

    share_dir = get_package_share_directory("multi_arm_robot_description")
    cap_yaml = Path(share_dir) / "config" / "capability.yaml"
    with open(cap_yaml) as f:
        data = yaml.safe_load(f)
    assert "manipulation" in data["capabilities"]
    assert "dynamic_capabilities" in data
    assert "context_capabilities" in data