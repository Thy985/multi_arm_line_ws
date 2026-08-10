"""Workspace path resolution — robust against HOME override (WSL2 HOME=/tmp)."""

import os
import subprocess


def _find_ws_from_file() -> str | None:
    """Derive workspace root from this module's installed location."""
    here = os.path.abspath(__file__)
    parts = here.split(os.sep)
    for i in range(len(parts) - 1, 0, -1):
        if parts[i] == "install" and i + 1 < len(parts) and parts[i + 1] == "multi_arm_tools":
            return os.sep.join(parts[:i])
        if parts[i] == "src" and i + 1 < len(parts) and parts[i + 1] == "multi_arm_tools":
            return os.sep.join(parts[:i])
    return None


def _find_ws_from_ros2() -> str | None:
    """Use ros2 pkg prefix to find install path."""
    try:
        result = subprocess.run(
            ["ros2", "pkg", "prefix", "multi_arm_tools"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            pkg_prefix = result.stdout.strip()
            install_dir = os.path.dirname(pkg_prefix)
            ws_root = os.path.dirname(install_dir)
            if os.path.isdir(install_dir):
                return ws_root
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def _find_ws_from_home() -> str | None:
    """Fallback: try expanduser (works when HOME is correct)."""
    candidate = os.path.expanduser("~/multi_arm_line_ws")
    if os.path.isdir(os.path.join(candidate, "install")):
        return candidate
    return None


def get_workspace_root() -> str | None:
    """Find workspace root, trying multiple strategies.

    Returns:
        Workspace root path, or None if not found.
    """
    return _find_ws_from_file() or _find_ws_from_ros2() or _find_ws_from_home()


def get_install_dir() -> str | None:
    """Get install/ directory path.

    Returns:
        install/ path, or None if not found.
    """
    ws = get_workspace_root()
    if ws:
        install = os.path.join(ws, "install")
        if os.path.isdir(install):
            return install
    return None


def get_package_install_dir(package_name: str = "multi_arm_tools") -> str | None:
    """Get install/<package>/ directory path.

    Args:
        package_name: ROS2 package name.

    Returns:
        install/<package>/ path, or None if not found.
    """
    install = get_install_dir()
    if install:
        pkg_dir = os.path.join(install, package_name)
        if os.path.isdir(pkg_dir):
            return pkg_dir
    return None