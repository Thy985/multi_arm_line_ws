"""Tests for sim manager module."""

from unittest.mock import MagicMock, patch

from multi_arm_tools.sim_manager import SimManager


def test_sim_manager_import():
    """Test SimManager can be imported."""
    assert SimManager is not None


def test_sim_manager_init():
    """Test SimManager initialization."""
    mgr = SimManager()
    assert mgr._launch_process is None
    assert mgr._runtime_process is None


def test_sim_manager_check_ros2_with_distro():
    """Test ROS2 check with ROS_DISTRO set."""
    mgr = SimManager()
    with patch.dict("os.environ", {"ROS_DISTRO": "jazzy"}):
        assert mgr._check_ros2() is True


def test_sim_manager_check_ros2_fail():
    """Test ROS2 check failure when ROS_DISTRO not set."""
    mgr = SimManager()
    with patch.dict("os.environ", {}, clear=True):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)
            assert mgr._check_ros2() is False


def test_sim_manager_is_launch_running():
    """Test launch running check."""
    mgr = SimManager()
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        assert mgr._is_launch_running() is True


def test_sim_manager_is_launch_not_running():
    """Test launch not running."""
    mgr = SimManager()
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1)
        assert mgr._is_launch_running() is False
