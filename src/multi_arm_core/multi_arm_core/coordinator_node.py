"""Coordinator node - thin orchestration engine for multi-arm system.

The Coordinator is an orchestration engine only. All business logic
is delegated to sub-modules:
- ResourceManager: resource allocation and tracking
- CapabilityMatcher: task-resource matching
- TimeManager: time-window scheduling
- Scheduler: task scheduling and arm assignment
- TaskManager: task lifecycle management
- SafetyInterface: safety plane communication
"""

import os
import time as _time
from typing import Dict, List, Optional

import rclpy
from rclpy.action import ActionClient
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from control_msgs.action import FollowJointTrajectory
from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint
from builtin_interfaces.msg import Duration
from sensor_msgs.msg import JointState

from multi_arm_core.coordination.resource_manager import (
    Resource,
    ResourceManager,
    ResourceState,
    ResourceType,
)
from multi_arm_core.coordination.capability_matcher import CapabilityMatcher
from multi_arm_core.coordination.time_manager import (
    TimeManager,
    predict_duration,
    SAFETY_MARGIN,
)
from multi_arm_core.scheduler.scheduler import (
    AllocationStrategy,
    Scheduler,
    Task,
    TaskPriority,
    TaskStatus,
)
from multi_arm_core.task.task_manager import TaskManager
from multi_arm_core.safety.safety_interface import SafetyInterface


ARM_JOINT_NAMES = {
    "arm1": [
        "arm1_shoulder_pan_joint",
        "arm1_shoulder_lift_joint",
        "arm1_elbow_joint",
        "arm1_wrist_1_joint",
        "arm1_wrist_2_joint",
        "arm1_wrist_3_joint",
    ],
    "arm2": [
        "arm2_shoulder_pan_joint",
        "arm2_shoulder_lift_joint",
        "arm2_elbow_joint",
        "arm2_wrist_1_joint",
        "arm2_wrist_2_joint",
        "arm2_wrist_3_joint",
    ],
}

PRESET_POSITIONS = {
    "home": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    "ready": [0.0, -1.57, 1.57, 0.0, 0.0, 0.0],
    "extended": [0.0, -0.5, 2.5, 0.5, 0.5, 0.0],
    "left": [-1.57, -1.0, 1.5, 0.0, 0.5, 0.0],
    "right": [1.57, -1.0, 1.5, 0.0, 0.5, 0.0],
}


class ArmState:
    """State machine for each arm."""
    IDLE = "IDLE"
    QUEUED = "QUEUED"
    WORKING = "WORKING"
    ERROR = "ERROR"


class CoordinatorNode(Node):
    """Thin orchestration engine for the multi-arm system.

    The Coordinator only orchestrates - it delegates all logic to sub-modules.
    """

    def __init__(self) -> None:
        super().__init__("coordinator_node")

        cb_group = ReentrantCallbackGroup()

        self._resource_manager = self._load_resources()
        self._capability_matcher = CapabilityMatcher()
        self._time_manager = TimeManager()
        self._allocation_strategy = AllocationStrategy(self._capability_matcher)
        self._scheduler = Scheduler(
            self._time_manager, self._resource_manager, self._allocation_strategy
        )
        self._task_manager = TaskManager()
        self._safety_interface = SafetyInterface(self, cb_group)

        self._arm_status: Dict[str, Dict] = {}
        self._action_clients: Dict[str, ActionClient] = {}
        self._goal_handles: Dict[str, Dict] = {}
        self._joint_states: Dict[str, JointState] = {}

        for robot in self._resource_manager.get_robots():
            arm_name = robot.name
            self._arm_status[arm_name] = {
                "state": ArmState.IDLE,
                "current_zone": None,
                "requested_zone": None,
                "requested_position": None,
                "goal_start_time": None,
                "error_message": None,
            }

            action_topic = f"/{arm_name}/joint_trajectory_controller/follow_joint_trajectory"
            client = ActionClient(
                self, FollowJointTrajectory, action_topic, callback_group=cb_group
            )
            self._action_clients[arm_name] = client
            self._goal_handles[arm_name] = None

            self.create_subscription(
                JointState,
                f"/{arm_name}/joint_states",
                lambda msg, an=arm_name: self._on_joint_state(msg, an),
                10,
                callback_group=cb_group,
            )

        self.create_timer(0.1, self._tick, callback_group=cb_group)

        self.get_logger().info("Coordinator node started")
        self.get_logger().info(
            f"Managing arms: {[r.name for r in self._resource_manager.get_robots()]}"
        )
        self.get_logger().info(
            f"Zones: {[z.name for z in self._resource_manager.get_zones()]}"
        )

        for arm_name, client in self._action_clients.items():
            self.get_logger().info(f"Waiting for {arm_name} action server...")
            client.wait_for_server()
            self.get_logger().info(f"{arm_name} action server ready")

        self.get_logger().info("All action servers available")

    def _load_resources(self) -> ResourceManager:
        """Load resources from YAML configuration."""
        config_path = os.path.join(
            os.path.dirname(__file__), "..", "config", "robots.yaml"
        )
        config_path = os.path.abspath(config_path)

        if os.path.exists(config_path):
            self.get_logger().info(f"Loading resources from {config_path}")
            return ResourceManager.from_yaml(config_path)

        self.get_logger().warn(
            f"Config not found at {config_path}, using default resources"
        )
        manager = ResourceManager()
        for name in ["arm1", "arm2"]:
            manager.register(
                Resource(
                    name=name,
                    resource_type=ResourceType.ROBOT,
                    capabilities={
                        "payload_kg": 5.0,
                        "gripper": "robotiq_2f85",
                        "precision_mm": 0.1,
                        "reachable_zones": ["zone_a", "zone_b", "home"],
                        "namespace": f"/{name}",
                    },
                )
            )
        for zone in ["zone_a", "zone_b", "zone_c", "home"]:
            manager.register(
                Resource(
                    name=zone,
                    resource_type=ResourceType.ZONE,
                    capabilities={"zone_type": "shared"},
                )
            )
        return manager

    def _on_joint_state(self, msg: JointState, arm_name: str) -> None:
        """Callback for joint state updates."""
        self._joint_states[arm_name] = msg

    def create_trajectory(
        self, arm_name: str, positions: List[float], duration_sec: float = 3.0
    ) -> JointTrajectory:
        """Create a joint trajectory for a specific arm."""
        trajectory = JointTrajectory()
        trajectory.joint_names = ARM_JOINT_NAMES.get(
            arm_name, [f"{arm_name}_shoulder_pan_joint"]
        )

        point = JointTrajectoryPoint()
        point.positions = list(positions)
        point.velocities = [0.0] * 6
        point.accelerations = [0.0] * 6
        point.time_from_start = Duration(
            sec=int(duration_sec), nanosec=int((duration_sec % 1) * 1e9)
        )

        trajectory.points = [point]
        return trajectory

    def send_to_zone(
        self,
        arm_name: str,
        zone_name: str,
        position_name: str = "ready",
        duration: float = 3.0,
    ) -> bool:
        """Send arm to a zone with zone-locking and time-window coordination.

        Args:
            arm_name: Name of the arm.
            zone_name: Target zone name.
            position_name: Preset position to move to.
            duration: Trajectory duration.

        Returns:
            True if zone granted immediately, False if queued.
        """
        if arm_name not in self._arm_status:
            self.get_logger().error(f"Unknown arm: {arm_name}")
            return False

        zone_resource = self._resource_manager.get(zone_name)
        if zone_resource is None:
            self.get_logger().error(f"Unknown zone: {zone_name}")
            return False

        status = self._arm_status[arm_name]
        if status["state"] != ArmState.IDLE:
            self.get_logger().warn(
                f"[{arm_name}] Cannot request zone — arm is {status['state']}"
            )
            return False

        if self._safety_interface.e_stop_active:
            self.get_logger().warn(f"[{arm_name}] E-Stop active, rejecting command")
            return False

        predicted_duration = predict_duration(position_name, duration)
        schedule_result = self._time_manager.schedule(
            arm_name,
            zone_name,
            duration=predicted_duration,
            position_name=position_name,
        )

        if schedule_result.conflict:
            conflict = schedule_result.conflict
            self.get_logger().warn(
                f"[{arm_name}] Time conflict with {conflict.arm_b} "
                f'in "{zone_name}" (overlap={conflict.overlap_duration:.1f}s)'
            )
            self._time_manager.cancel(arm_name)
            status["state"] = ArmState.QUEUED
            status["requested_zone"] = zone_name
            status["requested_position"] = position_name
            return False

        task_id = f"cmd_{arm_name}_{_time.time():.0f}"
        granted = self._resource_manager.allocate(zone_name, task_id)

        if granted:
            self.get_logger().info(
                f'[{arm_name}] Zone "{zone_name}" granted, '
                f"scheduled for {predicted_duration:.1f}s"
            )
            status["state"] = ArmState.WORKING
            status["current_zone"] = zone_name
            status["goal_start_time"] = _time.time()

            self._time_manager.start_executing(arm_name)

            positions = PRESET_POSITIONS.get(position_name, PRESET_POSITIONS["ready"])
            trajectory = self.create_trajectory(arm_name, positions, duration)

            approved, speed_scale = self._safety_interface.check_safety_sync(
                [arm_name],
                trajectory.joint_names,
                positions,
                duration,
            )

            if not approved:
                self.get_logger().warn(
                    f"[{arm_name}] Safety check rejected, releasing zone"
                )
                self._resource_manager.release(zone_name, task_id)
                self._time_manager.cancel(arm_name)
                status["state"] = ArmState.IDLE
                status["current_zone"] = None
                return False

            if speed_scale < 1.0:
                duration = duration / speed_scale
                trajectory = self.create_trajectory(arm_name, positions, duration)

            self._send_trajectory_async(arm_name, trajectory)
            return True
        else:
            self._time_manager.cancel(arm_name)
            self.get_logger().info(
                f'[{arm_name}] Zone "{zone_name}" occupied, queuing'
            )
            status["state"] = ArmState.QUEUED
            status["requested_zone"] = zone_name
            status["requested_position"] = position_name
            return False

    def submit_task(
        self,
        zone_name: str,
        position_name: str = "ready",
        priority: TaskPriority = TaskPriority.NORMAL,
        preferred_arm: Optional[str] = None,
        required_capabilities: Optional[Dict] = None,
    ) -> str:
        """Submit a task to the scheduler.

        Args:
            zone_name: Target zone.
            position_name: Target position.
            priority: Task priority.
            preferred_arm: Optional preferred arm.
            required_capabilities: Optional capability requirements.

        Returns:
            task_id for tracking.
        """
        task = self._task_manager.create_task(
            zone_name=zone_name,
            position_name=position_name,
            priority=priority,
            preferred_arm=preferred_arm,
            required_capabilities=required_capabilities,
        )
        self._scheduler.submit(task)
        self.get_logger().info(
            f"Task submitted: {task.task_id} "
            f"(zone={zone_name}, pos={position_name}, priority={priority.name})"
        )
        return task.task_id

    def schedule_pending_tasks(self) -> int:
        """Schedule all pending tasks and execute them.

        Returns:
            Number of tasks scheduled.
        """
        plan = self._scheduler.schedule_all()

        if plan.scheduled:
            self.get_logger().info(f"Scheduled {len(plan.scheduled)} tasks")

        if plan.failed:
            self.get_logger().warn(f"Failed to schedule {len(plan.failed)} tasks")

        for task in plan.scheduled:
            if task.status == TaskStatus.SCHEDULED and task.assigned_arm:
                success = self.send_to_zone(
                    arm_name=task.assigned_arm,
                    zone_name=task.zone_name,
                    position_name=task.position_name,
                    duration=task.predicted_duration - SAFETY_MARGIN,
                )
                if success:
                    self._task_manager.update_status(task.task_id, TaskStatus.EXECUTING)
                else:
                    self._task_manager.update_status(task.task_id, TaskStatus.QUEUED)

        return len(plan.scheduled)

    def _send_trajectory_async(self, arm_name: str, trajectory: JointTrajectory) -> None:
        """Send trajectory goal asynchronously."""
        client = self._action_clients[arm_name]
        goal = FollowJointTrajectory.Goal()
        goal.trajectory = trajectory

        self.get_logger().info(f"[{arm_name}] Sending trajectory goal")
        future = client.send_goal_async(goal)
        future.add_done_callback(
            lambda f, an=arm_name: self._on_goal_response(f, an)
        )
        self._goal_handles[arm_name] = {"future": future, "goal_handle": None}

    def _on_goal_response(self, future, arm_name: str) -> None:
        """Callback when goal is accepted/rejected by server."""
        try:
            goal_handle = future.result()
            if not goal_handle.accepted:
                self.get_logger().warn(f"[{arm_name}] Goal was rejected")
                self._release_arm(arm_name)
                return

            self.get_logger().info(f"[{arm_name}] Goal accepted, waiting for result...")
            if arm_name in self._goal_handles:
                self._goal_handles[arm_name]["goal_handle"] = goal_handle

            result_future = goal_handle.get_result_async()
            result_future.add_done_callback(
                lambda f, an=arm_name: self._on_result_complete(f, an)
            )
        except Exception as e:
            self.get_logger().error(f"[{arm_name}] Exception in goal response: {e}")
            self._release_arm(arm_name)

    def _on_result_complete(self, future, arm_name: str) -> None:
        """Callback when trajectory execution finishes."""
        try:
            result_response = future.result()
            result = result_response.result
            status = self._arm_status[arm_name]

            if result.error_code == 0:
                self.get_logger().info(f"[{arm_name}] Goal completed successfully")
                self._time_manager.complete(arm_name)
                self._release_arm(arm_name)
            else:
                self.get_logger().error(
                    f"[{arm_name}] Goal failed with code: {result.error_code}"
                )
                status["state"] = ArmState.ERROR
                status["error_message"] = f"Goal failed: {result.error_code}"
                self._release_zone_only(arm_name)
        except Exception as e:
            self.get_logger().error(f"[{arm_name}] Exception in result callback: {e}")
            self._release_arm(arm_name)

    def _release_arm(self, arm_name: str) -> None:
        """Release zone lock and reset arm state."""
        status = self._arm_status[arm_name]

        if status["current_zone"]:
            zone_name = status["current_zone"]
            zone = self._resource_manager.get(zone_name)

            if zone:
                next_task = self._resource_manager.release(zone_name, zone.allocated_to or "")
                if next_task:
                    next_arm = self._find_arm_for_task(next_task)
                    if next_arm:
                        self._trigger_queued_arm(next_arm, zone_name)

            if not next_task if zone else True:
                queued_arm = self._find_queued_arm_for_zone(zone_name)
                if queued_arm:
                    self._trigger_queued_arm(queued_arm, zone_name)

            status["current_zone"] = None

        status["state"] = ArmState.IDLE
        status["requested_zone"] = None
        status["requested_position"] = None
        status["goal_start_time"] = None
        status["error_message"] = None
        self.get_logger().info(f"[{arm_name}] Released, now IDLE")

    def _release_zone_only(self, arm_name: str) -> None:
        """Release zone lock WITHOUT resetting arm state (for ERROR recovery)."""
        status = self._arm_status[arm_name]

        if status["current_zone"]:
            zone_name = status["current_zone"]
            zone = self._resource_manager.get(zone_name)

            if zone:
                next_task = self._resource_manager.release(zone_name, zone.allocated_to or "")
                if next_task:
                    next_arm = self._find_arm_for_task(next_task)
                    if next_arm:
                        self._trigger_queued_arm(next_arm, zone_name)

            status["current_zone"] = None

    def _find_queued_arm_for_zone(self, zone_name: str) -> Optional[str]:
        """Find an arm in QUEUED state that was waiting for this zone."""
        for arm_name, status in self._arm_status.items():
            if status["state"] == ArmState.QUEUED and status["requested_zone"] == zone_name:
                return arm_name
        return None

    def _find_arm_for_task(self, task_id: str) -> Optional[str]:
        """Find which arm is associated with a task_id."""
        for arm_name, status in self._arm_status.items():
            if status["state"] == ArmState.QUEUED:
                return arm_name
        return None

    def _trigger_queued_arm(self, arm_name: str, zone_name: str) -> None:
        """Trigger a queued arm to start its trajectory."""
        status = self._arm_status[arm_name]

        if status["state"] == ArmState.QUEUED and status["requested_zone"] == zone_name:
            zone = self._resource_manager.get(zone_name)
            if zone:
                task_id = f"cmd_{arm_name}_{_time.time():.0f}"
                self._resource_manager.allocate(zone_name, task_id)

            status["state"] = ArmState.WORKING
            status["current_zone"] = zone_name
            status["requested_zone"] = None
            status["goal_start_time"] = _time.time()

            position_name = status.get("requested_position") or "ready"
            positions = PRESET_POSITIONS.get(position_name, PRESET_POSITIONS["ready"])
            trajectory = self.create_trajectory(arm_name, positions, 3.0)
            self._send_trajectory_async(arm_name, trajectory)
            self.get_logger().info(
                f'[{arm_name}] Queued trigger executed, moving to zone "{zone_name}"'
            )

    def _tick(self) -> None:
        """Periodic state machine check (timeouts + cleanup)."""
        for arm_name, status in self._arm_status.items():
            if status["state"] == ArmState.WORKING and status["goal_start_time"]:
                elapsed = _time.time() - status["goal_start_time"]
                predicted = predict_duration(status.get("current_zone") or "", 3.0)
                timeout = max(predicted * 2, 15.0)
                if elapsed > timeout:
                    self.get_logger().warn(
                        f"[{arm_name}] Goal timeout ({elapsed:.1f}s > {timeout:.1f}s)"
                    )
                    self._cancel_and_release(arm_name)

        self._time_manager.cleanup()

    def _cancel_and_release(self, arm_name: str) -> None:
        """Cancel active goal and release arm."""
        goal_info = self._goal_handles.get(arm_name)
        if goal_info and goal_info.get("goal_handle"):
            try:
                goal_handle = goal_info["goal_handle"]
                goal_handle.cancel_goal_async()
            except Exception as e:
                self.get_logger().warn(f"[{arm_name}] Failed to cancel goal: {e}")

        self._release_arm(arm_name)

    def reset_arm(self, arm_name: str) -> bool:
        """Manually reset an arm from ERROR state back to IDLE.

        Args:
            arm_name: Name of the arm to reset.

        Returns:
            True if arm was reset, False if arm was not in ERROR state.
        """
        if arm_name not in self._arm_status:
            self.get_logger().error(f"Unknown arm: {arm_name}")
            return False

        status = self._arm_status[arm_name]
        if status["state"] != ArmState.ERROR:
            self.get_logger().warn(
                f"[{arm_name}] Cannot reset — arm is {status['state']} (not ERROR)"
            )
            return False

        self.get_logger().info(f"[{arm_name}] Manual reset from ERROR to IDLE")
        self._release_arm(arm_name)
        return True


def main(args=None) -> None:
    """Entry point for the coordinator node."""
    rclpy.init(args=args)

    coordinator = CoordinatorNode()

    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(coordinator)

    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        coordinator.get_logger().info("Shutting down coordinator")
        coordinator.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()