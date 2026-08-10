"""Coordinator node - thin orchestration engine for multi-arm system.

The Coordinator is an orchestration engine only. All business logic
is delegated to sub-modules:
- ResourceManager: resource allocation and tracking
- CapabilityMatcher: task-resource matching
- TimeManager: time-window scheduling
- Scheduler: task scheduling and arm assignment
- TaskManager: task lifecycle management
- SafetyInterface: safety plane communication
- MoveItInterface: MoveIt2 planning and execution
"""

import os

import time as _time
from typing import Any, Dict, List, Optional, Tuple

import rclpy
from rclpy.action import ActionClient, ActionServer
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
from multi_arm_core.moveit_interface import MoveItInterface
from multi_arm_core.robot_constants import ARM_JOINT_NAMES, PRESET_POSITIONS
from multi_arm_recovery.recovery_manager import RecoveryManager
from multi_arm_recovery.failure_classifier import FailureEvent, FailureType



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

        self._moveit_interface = MoveItInterface(self, cb_group)
        self._recovery_manager = RecoveryManager()

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

            action_topic = f"/{arm_name}_joint_trajectory_controller/follow_joint_trajectory"
            client = ActionClient(
                self, FollowJointTrajectory, action_topic, callback_group=cb_group
            )
            self._action_clients[arm_name] = client
            self._goal_handles[arm_name] = None

        self.create_subscription(
            JointState,
            "/joint_states",
            self._on_joint_state_all,
            10,
            callback_group=cb_group,
        )

        self._init_action_server(cb_group)

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

    def _init_action_server(self, cb_group: ReentrantCallbackGroup) -> None:
        """Initialize ExecuteTask action server."""
        try:
            from multi_arm_interfaces.action import ExecuteTask

            self._execute_task_server = ActionServer(
                self,
                ExecuteTask,
                "/coordinator/execute_task",
                self._on_execute_task,
                callback_group=cb_group,
            )
            self.get_logger().info("ExecuteTask action server started at /coordinator/execute_task")
        except ImportError:
            self.get_logger().warn(
                "multi_arm_interfaces not available, ExecuteTask action server disabled"
            )
            self._execute_task_server = None

    async def _on_execute_task(self, goal_handle) -> object:
        """Handle ExecuteTask action goal.

        Executes a task by:
        1. Parsing task_type to determine arm + zone + position
        2. Allocating zone via ResourceManager
        3. Safety check via SafetyInterface
        4. MoveIt2 planning and execution
        5. Releasing zone on completion

        Args:
            goal_handle: The action goal handle.

        Returns:
            ExecuteTask.Result with success and message.
        """
        from multi_arm_interfaces.action import ExecuteTask

        goal = goal_handle.request
        task_id = goal.task_id
        task_type = goal.task_type
        description = goal.description

        task_goal = getattr(goal, 'goal', None)

        self.get_logger().info(
            f"ExecuteTask received: id={task_id} type={task_type} desc={description}"
        )

        if task_goal is not None and task_goal.arm_name:
            arm_name, zone_name, position_name = self._parse_task_goal(task_goal)
            self.get_logger().info(
                f"Parsed from TaskGoal: arm={arm_name} zone={zone_name} pos={position_name}"
            )
        else:
            arm_name, zone_name, position_name = self._parse_task(task_type, description)

        if arm_name is None:
            goal_handle.abort()
            result = ExecuteTask.Result()
            result.success = False
            result.message = f"Cannot parse task: {task_type}/{description}"
            return result

        if arm_name not in self._arm_status:
            goal_handle.abort()
            result = ExecuteTask.Result()
            result.success = False
            result.message = f"Unknown arm: {arm_name}"
            return result

        status = self._arm_status[arm_name]
        if status["state"] != ArmState.IDLE:
            goal_handle.abort()
            result = ExecuteTask.Result()
            result.success = False
            result.message = f"Arm {arm_name} is {status['state']}, not IDLE"
            return result

        if self._safety_interface.e_stop_active:
            goal_handle.abort()
            result = ExecuteTask.Result()
            result.success = False
            result.message = "E-Stop active, rejecting task"
            return result

        task_internal_id = f"task_{arm_name}_{_time.time():.0f}"
        if zone_name:
            granted = self._resource_manager.allocate(zone_name, task_internal_id)
            self.get_logger().info(
                f"[ZONE] allocate({zone_name}, {task_internal_id}) = {granted}"
            )
            if not granted:
                zone = self._resource_manager.get(zone_name)
                if zone and task_internal_id in zone.waiting_queue:
                    zone.waiting_queue.remove(task_internal_id)
                    self.get_logger().info(
                        f"[ZONE] removed {task_internal_id} from {zone_name} waiting_queue"
                    )
                goal_handle.abort()
                result = ExecuteTask.Result()
                result.success = False
                result.message = f"Zone {zone_name} occupied"
                return result
            status["current_zone"] = zone_name

        status["state"] = ArmState.WORKING
        status["goal_start_time"] = _time.time()

        positions = PRESET_POSITIONS.get(position_name, PRESET_POSITIONS["ready"])
        joint_names = ARM_JOINT_NAMES.get(arm_name, [])

        approved, speed_scale = self._safety_interface.check_safety_sync(
            [arm_name], joint_names, positions, 3.0,
        )

        if not approved:
            self.get_logger().warn(f"[{arm_name}] Safety check rejected for task {task_id}")
            if zone_name:
                self._resource_manager.release(zone_name, task_internal_id)
                status["current_zone"] = None
            status["state"] = ArmState.IDLE
            goal_handle.abort()
            result = ExecuteTask.Result()
            result.success = False
            result.message = "Safety check rejected"
            return result

        use_moveit = self._moveit_interface.is_available()

        if use_moveit:
            self.get_logger().info(
                f"[{arm_name}] Using MoveIt2 for task {task_id} -> {position_name}"
            )
            success, msg = self._moveit_interface.move_to_preset(
                arm_name, position_name, timeout=60.0,
            )
            if not success:
                self.get_logger().warn(
                    f"[{arm_name}] MoveIt2 failed ({msg}), falling back to JTC direct"
                )
                duration = 3.0
                if speed_scale < 1.0:
                    duration = duration / speed_scale
                trajectory = self.create_trajectory(arm_name, positions, duration)
                success = self._send_trajectory_sync(arm_name, trajectory, timeout=15.0)
                msg = "jtc_fallback_success" if success else "jtc_fallback_failed"
        else:
            self.get_logger().info(
                f"[{arm_name}] MoveIt2 unavailable, using JTC direct for task {task_id}"
            )
            duration = 3.0
            if speed_scale < 1.0:
                duration = duration / speed_scale
            trajectory = self.create_trajectory(arm_name, positions, duration)
            success = self._send_trajectory_sync(arm_name, trajectory, timeout=15.0)
            msg = "jtc_success" if success else "jtc_failed"

        if not success:
            self.get_logger().warn(
                f"[{arm_name}] Execution failed for task {task_id}: {msg}"
            )
            success, msg = self._attempt_recovery(
                task_id, arm_name, msg, zone_name, position_name, task_internal_id
            )

        if zone_name:
            release_result = self._resource_manager.release(zone_name, task_internal_id)
            self.get_logger().info(
                f"[ZONE] release({zone_name}, {task_internal_id}) = {release_result}"
            )
            status["current_zone"] = None

        status["state"] = ArmState.IDLE
        status["goal_start_time"] = None

        if success:
            goal_handle.succeed()
        else:
            goal_handle.abort()

        result = ExecuteTask.Result()
        result.success = success
        result.message = msg
        return result

    def _attempt_recovery(
        self,
        task_id: str,
        arm_name: str,
        error_msg: str,
        zone_name: Optional[str],
        position_name: str,
        task_internal_id: str,
    ) -> Tuple[bool, str]:
        """Attempt recovery after a motion execution failure.

        Uses RecoveryManager to classify the failure and execute
        progressive recovery strategies.

        Args:
            task_id: External task ID.
            arm_name: Name of the arm that failed.
            error_msg: Error message from the failed execution.
            zone_name: Zone that was allocated (if any).
            position_name: Target position name.
            task_internal_id: Internal task ID for resource management.

        Returns:
            Tuple of (success, message).
        """
        from multi_arm_recovery.recovery_manager import RecoveryStatus

        event = self._recovery_manager.classify_failure(
            message=error_msg,
            arm_name=arm_name,
            context={"zone": zone_name, "position": position_name},
            task_id=task_id,
        )

        self.get_logger().info(
            f"[RECOVERY] Classified failure: type={event.failure_type.name} "
            f"recoverable={event.recoverable} arm={arm_name}"
        )

        if not event.recoverable:
            self.get_logger().warn(
                f"[RECOVERY] Non-recoverable failure: {event.failure_type.name}"
            )
            return False, f"non_recoverable:{event.failure_type.name}"

        record = self._recovery_manager.handle_failure(
            event, executor=self._execute_recovery_strategy
        )

        if record.status == RecoveryStatus.RECOVERED:
            self.get_logger().info(
                f"[RECOVERY] Recovered task {task_id} via "
                f"strategy={record.current_strategy} "
                f"attempts={record.recovery_count}"
            )
            return True, f"recovered:{record.current_strategy}"

        self.get_logger().warn(
            f"[RECOVERY] Failed to recover task {task_id} after "
            f"{record.recovery_count} attempts, "
            f"strategies={record.strategies_tried}"
        )
        return False, f"recovery_failed:{record.strategies_tried}"

    def _execute_recovery_strategy(
        self,
        strategy_name: str,
        strategy_params: Dict,
        event: FailureEvent,
    ) -> bool:
        """Execute a recovery strategy determined by RecoveryManager.

        Args:
            strategy_name: Name of the recovery strategy.
            strategy_params: Parameters for the strategy.
            event: The failure event being recovered.

        Returns:
            True if the strategy succeeded.
        """
        arm_name = event.arm_name
        self.get_logger().info(
            f"[RECOVERY] Executing strategy: {strategy_name} "
            f"for arm={arm_name} params={strategy_params}"
        )

        if strategy_name == "relax_constraints":
            position_name = event.context.get("position", "ready")
            success, msg = self._moveit_interface.move_to_preset(
                arm_name,
                position_name,
                timeout=strategy_params.get("planning_time", 60.0),
            )
            return success

        if strategy_name == "change_grasp_pose":
            position_name = event.context.get("position", "ready")
            success, msg = self._moveit_interface.move_to_preset(
                arm_name, position_name, timeout=60.0,
            )
            return success

        if strategy_name == "retreat_to_safe":
            success, msg = self._moveit_interface.move_to_preset(
                arm_name, "home", timeout=30.0,
            )
            return success

        if strategy_name == "replan_with_avoidance":
            position_name = event.context.get("position", "ready")
            success, msg = self._moveit_interface.move_to_preset(
                arm_name, position_name, timeout=60.0,
            )
            return success

        if strategy_name == "wait_and_retry":
            _time.sleep(strategy_params.get("wait_seconds", 2.0))
            position_name = event.context.get("position", "ready")
            positions = PRESET_POSITIONS.get(position_name, PRESET_POSITIONS["ready"])
            trajectory = self.create_trajectory(arm_name, positions, 3.0)
            return self._send_trajectory_sync(arm_name, trajectory, timeout=15.0)

        if strategy_name == "retry_grasp":
            position_name = event.context.get("position", "ready")
            success, msg = self._moveit_interface.move_to_preset(
                arm_name, position_name, timeout=30.0,
            )
            return success

        if strategy_name in ("release_and_abort", "safe_abort"):
            return False

        if strategy_name == "release_and_requeue":
            return False

        if strategy_name == "switch_controller":
            return False

        self.get_logger().warn(
            f"[RECOVERY] Unknown strategy: {strategy_name}"
        )
        return False

    def _parse_task(
        self, task_type: str, description: str
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Parse task_type and description into arm, zone, position.

        Args:
            task_type: Task type string (e.g. 'pick_place', 'move').
            description: Description string (e.g. 'arm1:zone_a:ready').

        Returns:
            Tuple of (arm_name, zone_name, position_name).
        """
        if description and ":" in description:
            parts = description.split(":")
            arm_name = parts[0] if len(parts) > 0 else None
            zone_name = parts[1] if len(parts) > 1 else None
            position_name = parts[2] if len(parts) > 2 else "ready"
            return arm_name, zone_name, position_name

        arm_name = "arm1"
        zone_name = "zone_a"
        position_name = "ready"

        if task_type == "pick_place":
            position_name = "ready"
        elif task_type == "move":
            position_name = "ready"

        return arm_name, zone_name, position_name

    def _parse_task_goal(
        self, task_goal: object
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Parse structured TaskGoal into arm, zone, position.

        Args:
            task_goal: TaskGoal message with structured fields.

        Returns:
            Tuple of (arm_name, zone_name, position_name).
        """
        arm_name = task_goal.arm_name or None
        zone_name = task_goal.zone_name or None
        position_name = task_goal.position_name or "ready"

        if not arm_name:
            return None, None, None

        return arm_name, zone_name, position_name

    def _send_trajectory_sync(
        self, arm_name: str, trajectory: JointTrajectory, timeout: float = 15.0
    ) -> bool:
        """Send trajectory and wait for completion synchronously.

        Args:
            arm_name: Name of the arm.
            trajectory: Joint trajectory to send.
            timeout: Maximum wait time in seconds.

        Returns:
            True if execution succeeded.
        """
        client = self._action_clients.get(arm_name)
        if client is None or not client.wait_for_server(timeout_sec=3.0):
            self.get_logger().error(f"[{arm_name}] JTC action server not available")
            return False

        goal = FollowJointTrajectory.Goal()
        goal.trajectory = trajectory

        self.get_logger().info(f"[{arm_name}] Sending JTC trajectory (sync)")
        future = client.send_goal_async(goal)

        deadline = _time.time() + timeout
        while not future.done() and _time.time() < deadline:
            _time.sleep(0.05)

        if not future.done() or future.result() is None:
            self.get_logger().error(f"[{arm_name}] JTC goal send failed")
            return False

        goal_handle = future.result()
        if not goal_handle.accepted:
            self.get_logger().warn(f"[{arm_name}] JTC goal rejected")
            return False

        result_future = goal_handle.get_result_async()
        while not result_future.done() and _time.time() < deadline:
            _time.sleep(0.05)

        if not result_future.done():
            self.get_logger().warn(f"[{arm_name}] JTC execution timeout")
            return False

        result = result_future.result().result
        if result.error_code == 0:
            self.get_logger().info(f"[{arm_name}] JTC execution succeeded")
            return True

        self.get_logger().error(
            f"[{arm_name}] JTC execution failed: error_code={result.error_code}"
        )
        return False


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

    def _on_joint_state_all(self, msg: JointState) -> None:
        """Callback for joint state updates from /joint_states (merged URDF)."""
        js_dict = {}
        for i, name in enumerate(msg.name):
            js_dict[name] = msg.position[i]
        self._moveit_interface.update_joint_states(js_dict)
        for arm_name in self._arm_status:
            self._joint_states[arm_name] = msg

    def _on_joint_state(self, msg: JointState, arm_name: str) -> None:
        """Callback for joint state updates (per-arm namespace)."""
        self._joint_states[arm_name] = msg
        js_dict = {}
        for i, name in enumerate(msg.name):
            js_dict[name] = msg.position[i]
        self._moveit_interface.update_joint_states(js_dict)

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