"""Robot doctor — environment diagnosis and troubleshooting.

Checks all subsystems, reports health status, and suggests fixes.
"""

import os
import subprocess
import time
from typing import Any

from multi_arm_tools.paths import get_install_dir


class Doctor:
    """Robot Runtime environment diagnostic tool."""

    def __init__(self) -> None:
        self._checks: list[dict[str, Any]] = []
        self._score = 0
        self._total = 0

    def run(self) -> None:
        """Run all diagnostic checks."""
        print("\n=== Robot Runtime Diagnosis ===")
        print()

        self._check_ros2()
        self._check_gazebo()
        self._check_build()
        self._check_nodes()
        self._check_controllers()
        self._check_moveit()
        self._check_world_model()
        self._check_safety()
        self._check_runtime_api()
        self._check_experience()

        self._print_summary()
        self._print_failures()

    def _check_ros2(self) -> None:
        """Check ROS2 environment."""
        ros_distro = os.environ.get("ROS_DISTRO", "")
        if ros_distro:
            self._pass("ROS2", f"DDS communication (distro={ros_distro})")
        else:
            self._fail(
                "ROS2",
                "DDS communication",
                "ROS_DISTRO not set",
                "Run: source /opt/ros/jazzy/setup.bash",
            )

    def _check_gazebo(self) -> None:
        """Check if Gazebo is running."""
        result = subprocess.run(
            ["pgrep", "-f", "gz sim"],
            capture_output=True,
            timeout=3,
        )
        if result.returncode == 0:
            self._pass("Simulation", "Gazebo running")
        else:
            self._fail(
                "Simulation",
                "Gazebo running",
                "No Gazebo process found",
                "Run: robot sim start",
            )

    def _check_build(self) -> None:
        """Check if workspace is built."""
        ws = get_install_dir()
        if ws and os.path.isdir(ws):
            pkg_count = len(os.listdir(ws))
            self._pass("Workspace", f"{pkg_count} packages built")
        else:
            self._fail(
                "Workspace",
                "Build complete",
                "install/ directory not found",
                "Run: colcon build",
            )

    def _check_nodes(self) -> None:
        """Check ROS2 nodes."""
        nodes = self._get_nodes()
        if not nodes:
            self._fail(
                "ROS2",
                "Nodes running",
                "No nodes detected",
                "Run: robot sim start",
            )
            return

        expected = [
            "world_model_node",
            "safety_supervisor",
            "coordinator_node",
        ]
        node_names = [n.split("/")[-1] for n in nodes]
        for exp in expected:
            if exp in node_names:
                self._pass("ROS2", f"{exp} online")
            else:
                self._fail(
                    "ROS2",
                    f"{exp} online",
                    f"{exp} not found",
                    f"Run: ros2 run <package> {exp}",
                )

    def _check_controllers(self) -> None:
        """Check ros2_control controllers."""
        result = subprocess.run(
            ["ros2", "control", "list_controllers"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            self._fail(
                "Controllers",
                "Controller manager",
                "ros2 control not available",
                "Start Gazebo with controllers",
            )
            return

        lines = [
            l.strip() for l in result.stdout.strip().split("\n") if l.strip()
        ]
        for line in lines:
            parts = line.split()
            if len(parts) >= 2:
                name = parts[0]
                state = parts[1]
                if "active" in state.lower():
                    self._pass("Controllers", f"{name} ACTIVE")
                else:
                    self._fail(
                        "Controllers",
                        f"{name} active",
                        f"State: {state}",
                        f"Run: ros2 control set_controller_state {name} active",
                    )

        if not lines:
            self._fail(
                "Controllers",
                "Controllers loaded",
                "No controllers found",
                "Check controller spawner",
            )

    def _check_moveit(self) -> None:
        """Check MoveIt2 move_group."""
        nodes = self._get_nodes()
        if any("move_group" in n for n in nodes):
            services = self._get_services()
            if any("get_plan" in s for s in services):
                self._pass("MoveIt", "Planning scene available")
            else:
                self._pass("MoveIt", "move_group online")
        else:
            self._fail(
                "MoveIt",
                "move_group online",
                "move_group node not found",
                "Run: ros2 launch multi_arm_moveit_config multi_arm_moveit.launch.py",
            )

    def _check_world_model(self) -> None:
        """Check WorldModel."""
        services = self._get_services()
        if any("query_world" in s for s in services):
            self._pass("WorldModel", "Query service available")
        else:
            self._fail(
                "WorldModel",
                "Query service",
                "/world_model/query_world not found",
                "Run: ros2 run multi_arm_world_model world_model_node",
            )

    def _check_safety(self) -> None:
        """Check SafetySupervisor."""
        nodes = self._get_nodes()
        if any("safety_supervisor" in n for n in nodes):
            self._pass("Safety", "Supervisor online")
        else:
            self._fail(
                "Safety",
                "Supervisor online",
                "safety_supervisor not found",
                "Run: ros2 run multi_arm_safety safety_supervisor",
            )

    def _check_runtime_api(self) -> None:
        """Check RuntimeApiNode."""
        services = self._get_services()
        runtime_services = [s for s in services if "/runtime/" in s]
        if len(runtime_services) >= 3:
            self._pass("Runtime API", f"{len(runtime_services)} services available")
        else:
            self._fail(
                "Runtime API",
                "Services available",
                f"Only {len(runtime_services)} /runtime/* services found",
                "Run: ros2 run multi_arm_runtime_api runtime_api_node",
            )

    def _check_experience(self) -> None:
        """Check Experience infrastructure."""
        services = self._get_services()
        if any("query_experience" in s or "experience" in s for s in services):
            self._pass("Experience", "Query service available")
        else:
            self._fail(
                "Experience",
                "Query service",
                "Experience node not running",
                "Run: ros2 run multi_arm_experience experience_node",
            )

    def _pass(self, category: str, check: str, detail: str = "") -> None:
        """Record a passing check."""
        self._checks.append(
            {"category": category, "check": check, "pass": True, "detail": detail}
        )
        self._score += 1
        self._total += 1
        print(f"  [{category}] [OK] {check}")

    def _fail(
        self, category: str, check: str, detail: str, fix: str = ""
    ) -> None:
        """Record a failing check."""
        self._checks.append(
            {
                "category": category,
                "check": check,
                "pass": False,
                "detail": detail,
                "fix": fix,
            }
        )
        self._total += 1
        print(f"  [{category}] [FAIL] {check}")

    def _print_summary(self) -> None:
        """Print health score summary."""
        print()
        if self._total > 0:
            score = int(self._score / self._total * 100)
        else:
            score = 0
        print(f"  System Health: {score}/100 ({self._score}/{self._total} checks passed)")
        print()

    def _print_failures(self) -> None:
        """Print failure details and suggested fixes."""
        failures = [c for c in self._checks if not c["pass"]]
        if not failures:
            print("  All checks passed. System is healthy.")
            print()
            return

        print("  Failures:")
        for f in failures:
            print(f"    [{f['category']}] {f['check']}")
            print(f"      Problem: {f['detail']}")
            if f.get("fix"):
                print(f"      Suggested fix: {f['fix']}")
        print()

    def _get_nodes(self) -> list[str]:
        """Get ROS2 node list."""
        try:
            result = subprocess.run(
                ["ros2", "node", "list"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return [
                    line.strip()
                    for line in result.stdout.strip().split("\n")
                    if line.strip()
                ]
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        return []

    def _get_services(self) -> list[str]:
        """Get ROS2 service list."""
        try:
            result = subprocess.run(
                ["ros2", "service", "list"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return [
                    line.strip()
                    for line in result.stdout.strip().split("\n")
                    if line.strip()
                ]
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        return []