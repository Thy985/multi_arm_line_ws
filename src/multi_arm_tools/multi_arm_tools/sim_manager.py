"""Simulation lifecycle manager — start/stop/status for full M6 stack.

Encapsulates ros2 launch commands, process management, and health checks.
"""

import os
import signal
import subprocess
import sys
import time
from typing import Any

from multi_arm_tools.paths import get_package_install_dir

LAUNCH_PACKAGE = "multi_arm_simulation"
LAUNCH_FILE = "m6_pick_place_sim.launch.py"
RUNTIME_API_NODE = "runtime_api_node"
RUNTIME_API_PACKAGE = "multi_arm_runtime_api"

NODE_CHECK_TIMEOUT = 45
NODE_CHECK_INTERVAL = 2

HEALTH_NODES = [
    ("world_model_node", "WorldModel"),
    ("safety_supervisor", "Safety"),
    ("coordinator_node", "Coordinator"),
    ("task_planner_node", "TaskPlanner"),
]

HEALTH_SERVICES = [
    ("/runtime/query_world", "Runtime API"),
    ("/runtime/list_skills", "Skill List"),
    ("/runtime/get_capability", "Capability"),
]


class SimManager:
    """Full-stack simulation lifecycle manager."""

    def __init__(self) -> None:
        self._launch_process: subprocess.Popen | None = None
        self._runtime_process: subprocess.Popen | None = None

    def start(self, gui: bool = False, scene: str = "tabletop") -> None:
        """Start full M6 simulation stack.

        Args:
            gui: Whether to show Gazebo GUI
            scene: Scene name (tabletop, home, warehouse, lab)
        """
        print(f"\nRobot Runtime Starting (scene: {scene})...")
        print()

        if not self._check_ros2():
            return
        print("  [OK] ROS2 Jazzy detected")

        if not self._check_build():
            return
        print("  [OK] Workspace built")

        if self._is_running():
            print("  [!] Simulation already running")
            return

        print(f"  Starting Gazebo simulation (scene={scene})...")
        self._launch_process = self._start_launch(gui, scene)
        if not self._launch_process:
            return

        print("  Waiting for nodes to be ready...")
        if not self._wait_nodes_ready():
            print("  [FAIL] Nodes did not become ready in time")
            return

        print("  Starting Runtime API node...")
        self._runtime_process = self._start_runtime_api()
        if not self._runtime_process:
            return

        time.sleep(3)
        if not self._verify_interfaces():
            print("  [WARN] Some interfaces not yet available")
        else:
            print("  [OK] All interfaces verified")

        print()
        print("  Runtime Status: READY")
        print()
        print("  Next steps:")
        print("    robot status")
        print("    robot world")
        print("    robot run pick_place red_cube zone_b")
        print()

    def stop(self) -> None:
        """Stop simulation and all related processes."""
        print("\nStopping Robot Runtime...")

        stopped_any = False

        if self._runtime_process and self._runtime_process.poll() is None:
            self._runtime_process.terminate()
            self._runtime_process.wait(timeout=5)
            print("  [OK] Runtime API stopped")
            stopped_any = True

        if self._launch_process and self._launch_process.poll() is None:
            self._launch_process.terminate()
            self._launch_process.wait(timeout=10)
            print("  [OK] Simulation stopped")
            stopped_any = True

        self._kill_orphan_processes()

        if not stopped_any:
            print("  No simulation was running.")
        print()

    def status(self) -> None:
        """Check simulation status."""
        print("\n=== Simulation Status ===")
        print()

        launch_running = self._is_launch_running()
        runtime_running = self._is_runtime_running()

        if launch_running:
            print("  Simulation:  [RUNNING]")
        else:
            print("  Simulation:  [STOPPED]")

        if runtime_running:
            print("  Runtime API:  [RUNNING]")
        else:
            print("  Runtime API:  [STOPPED]")

        print()

        nodes = self._get_ros_nodes()
        if nodes:
            print(f"  Active Nodes ({len(nodes)}):")
            for node in sorted(nodes):
                print(f"    {node}")
        else:
            print("  No ROS2 nodes detected.")
        print()

    def _check_ros2(self) -> bool:
        """Check if ROS2 is sourced."""
        ros_distro = os.environ.get("ROS_DISTRO", "")
        if ros_distro:
            return True
        try:
            result = subprocess.run(
                ["which", "ros2"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        print("  [FAIL] ROS2 not found. Run: source /opt/ros/jazzy/setup.bash")
        return False

    def _check_build(self) -> bool:
        """Check if workspace is built."""
        install_path = get_package_install_dir()
        if install_path and os.path.isdir(install_path):
            return True
        print(f"  [FAIL] Workspace not built. Run: colcon build --packages-select multi_arm_tools")
        return False

    def _is_running(self) -> bool:
        """Check if simulation is already running."""
        return self._is_launch_running()

    def _is_launch_running(self) -> bool:
        """Check if launch process is running."""
        try:
            result = subprocess.run(
                ["pgrep", "-f", LAUNCH_FILE],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def _is_runtime_running(self) -> bool:
        """Check if RuntimeApiNode is running."""
        try:
            result = subprocess.run(
                ["pgrep", "-f", RUNTIME_API_NODE],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def _start_launch(self, gui: bool, scene: str = "tabletop") -> subprocess.Popen | None:
        """Start the Gazebo simulation launch."""
        cmd = [
            "ros2", "launch", LAUNCH_PACKAGE, LAUNCH_FILE,
            f"gazebo_gui:={'true' if gui else 'false'}",
            f"scene:={scene}",
        ]
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                preexec_fn=os.setsid,
            )
            return proc
        except FileNotFoundError:
            print("  [FAIL] ros2 launch not available")
            return None

    def _start_runtime_api(self) -> subprocess.Popen | None:
        """Start RuntimeApiNode."""
        cmd = ["ros2", "run", RUNTIME_API_PACKAGE, RUNTIME_API_NODE]
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                preexec_fn=os.setsid,
            )
            return proc
        except FileNotFoundError:
            print("  [FAIL] ros2 run not available")
            return None

    def _wait_nodes_ready(self) -> bool:
        """Wait for core nodes to become ready."""
        elapsed = 0
        while elapsed < NODE_CHECK_TIMEOUT:
            nodes = self._get_ros_nodes()
            node_names = [n.split("/")[-1] for n in nodes]
            all_ready = all(
                expected in node_names
                for expected, _ in HEALTH_NODES
            )
            if all_ready:
                for expected, label in HEALTH_NODES:
                    print(f"  [OK] {label} ready")
                return True
            time.sleep(NODE_CHECK_INTERVAL)
            elapsed += NODE_CHECK_INTERVAL
            dots = "." * (elapsed // NODE_CHECK_INTERVAL)
            print(f"\r  Waiting{dots:<20}", end="", flush=True)
        print()
        return False

    def _verify_interfaces(self) -> bool:
        """Verify ROS2 services are available."""
        services = self._get_ros_services()
        all_ok = True
        for svc, label in HEALTH_SERVICES:
            if svc in services:
                print(f"  [OK] {label} available")
            else:
                print(f"  [!] {label} not available")
                all_ok = False
        return all_ok

    def _get_ros_nodes(self) -> list[str]:
        """Get list of active ROS2 nodes."""
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

    def _get_ros_services(self) -> list[str]:
        """Get list of available ROS2 services."""
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

    def _kill_orphan_processes(self) -> None:
        """Kill orphaned ROS2/Gazebo processes."""
        patterns = [
            "gz sim",
            "move_group",
            "robot_state_publisher",
            "ros_gz_bridge",
        ]
        for pattern in patterns:
            try:
                subprocess.run(
                    ["pkill", "-f", pattern],
                    capture_output=True,
                    timeout=3,
                )
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass