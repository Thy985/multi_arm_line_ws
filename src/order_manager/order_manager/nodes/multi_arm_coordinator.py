#!/usr/bin/env python3
"""
Enhanced Multi-arm coordinator node.
Coordinates multiple robot arms in a shared workspace with zone management.
"""

import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from control_msgs.action import FollowJointTrajectory
from control_msgs.action._follow_joint_trajectory import FollowJointTrajectory_Result as JTCResult  # noqa: F401
JTC_SUCCESSFUL = 0  # JTCResult.SUCCESSFUL == error_code 0
from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint
from builtin_interfaces.msg import Duration
from sensor_msgs.msg import JointState
import time
import math

from order_manager.nodes.arm_state import (
    ArmState, ArmStatus, Zone, ZoneType, DEFAULT_ZONES, ARM_JOINT_NAMES, PRESET_POSITIONS
)
from order_manager.nodes.time_manager import TimeManager, WindowStatus, predict_duration
from order_manager.nodes.task_scheduler import TaskScheduler, Task, TaskPriority, TaskStatus
from order_manager.nodes.diagnostics_publisher import DiagnosticsPublisher
from order_manager.nodes.structured_logger import StructuredLogger


class EnhancedMultiArmCoordinator(Node):
    """
    Enhanced coordinator with zone management and state machine.
    
    Architecture:
    - Each arm has its own state machine (IDLE -> REQUESTING -> WORKING -> IDLE)
    - Zone manager handles mutual exclusion for shared zones
    - Coordinator manages arm goals through the state machine
    - NOT just simultaneous sending — respects zone locks
    """

    def __init__(self):
        super().__init__('enhanced_multi_arm_coordinator')
        
        # === Configuration ===
        self.arm_names = ['arm1', 'arm2']
        self.num_arms = len(self.arm_names)
        
        # === State machine per arm ===
        self.arm_status = {
            name: ArmStatus(name=name) for name in self.arm_names
        }
        
        # === Zone management ===
        self.zones = {k: Zone(name=v.name, zone_type=v.zone_type) for k, v in DEFAULT_ZONES.items()}
        
        # === Time management ===
        self.time_manager = TimeManager()
        
        # === Task scheduling ===
        self.task_scheduler = TaskScheduler(self.time_manager, self.arm_names)
        
        # === Action clients per arm ===
        self.action_clients = {}
        self.goal_handles = {}  # track async goal handles
        
        cb_group = ReentrantCallbackGroup()
        
        for arm_name in self.arm_names:
            action_topic = f'/{arm_name}/joint_trajectory_controller/follow_joint_trajectory'
            client = ActionClient(self, FollowJointTrajectory, action_topic, callback_group=cb_group)
            self.action_clients[arm_name] = client
            self.goal_handles[arm_name] = None
        
        # === Joint state subscription per arm ===
        self.joint_states = {}
        for arm_name in self.arm_names:
            # Each arm publishes joint states on its own topic via ros_gz_bridge
            sub = self.create_subscription(
                JointState,
                f'/{arm_name}/joint_states',
                lambda msg, an=arm_name: self._on_joint_state(msg, an),
                10,
                callback_group=cb_group
            )
        
        # === Timer for state machine tick ===
        self.create_timer(0.1, self._tick, callback_group=cb_group)

        # === Structured JSON logger ===
        self.json_logger = StructuredLogger(self)
        self.json_logger.info('Enhanced Multi-arm coordinator started', component='coordinator')
        self.json_logger.info(f'Monitoring arms: {self.arm_names}', component='coordinator')
        self.json_logger.info(f'Zones: {list(self.zones.keys())}', component='coordinator')

        # === Diagnostics publisher ===
        self._diagnostics = DiagnosticsPublisher(self, self.arm_status, self.zones, self.joint_states)
        self.json_logger.info('Diagnostics publisher active on /diagnostics', component='diagnostics')
        
        self.get_logger().info('Enhanced Multi-arm coordinator started')
        self.get_logger().info(f'Monitoring arms: {self.arm_names}')
        self.get_logger().info(f'Zones: {list(self.zones.keys())}')
        
        # === Wait for action servers ===
        for arm_name, client in self.action_clients.items():
            self.get_logger().info(f'Waiting for {arm_name} action server...')
            client.wait_for_server()
            self.get_logger().info(f'{arm_name} action server ready')
        
        self.get_logger().info('All action servers available')
        
        # === Interactive mode ===
        self.get_logger().info('Coordinator ready. Use send_to_zone() to command arms.')

    # =====================================================================
    # Joint State Callbacks
    # =====================================================================
    
    def _on_joint_state(self, msg: JointState, arm_name: str):
        """Callback for joint state updates."""
        self.joint_states[arm_name] = msg

    # =====================================================================
    # Trajectory Creation
    # =====================================================================
    
    def create_trajectory(self, arm_name: str, positions, duration_sec: float = 3.0):
        """Create a joint trajectory for a specific arm (with correct prefix)."""
        trajectory = JointTrajectory()
        trajectory.joint_names = ARM_JOINT_NAMES[arm_name]
        
        point = JointTrajectoryPoint()
        point.positions = list(positions)
        point.velocities = [0.0] * 6
        point.accelerations = [0.0] * 6
        point.time_from_start = Duration(
            sec=int(duration_sec),
            nanosec=int((duration_sec % 1) * 1e9)
        )
        
        trajectory.points = [point]
        return trajectory

    # =====================================================================
    # High-Level API: Send arm to a named position
    # =====================================================================
    
    def send_to_position(self, arm_name: str, position_name: str, duration: float = 3.0):
        """
        Send arm to a preset position (e.g. 'home', 'ready', 'left', 'right').
        
        Args:
            arm_name: 'arm1' or 'arm2'
            position_name: key in PRESET_POSITIONS
            duration: seconds for trajectory
        """
        if arm_name not in self.arm_status:
            self.get_logger().error(f'Unknown arm: {arm_name}. Available: {list(self.arm_status.keys())}')
            return False
        
        if position_name not in PRESET_POSITIONS:
            self.get_logger().error(f'Unknown position: {position_name}. Available: {list(PRESET_POSITIONS.keys())}')
            return False
        
        status = self.arm_status[arm_name]
        if status.state != ArmState.IDLE:
            self.get_logger().warn(f'[{arm_name}] Cannot send position — arm is {status.state.name}')
            return False
        
        positions = PRESET_POSITIONS[position_name]
        self.get_logger().info(f'[{arm_name}] Commanding to position: {position_name} = {positions}')
        self.json_logger.info(f'Commanding to position: {position_name}', arm=arm_name, component='coordinator', data={'position': position_name, 'joints': positions})
        
        status.state = ArmState.WORKING
        status.goal_start_time = time.time()
        
        trajectory = self.create_trajectory(arm_name, positions, duration)
        return self._send_trajectory_async(arm_name, trajectory)

    # =====================================================================
    # High-Level API: Send arm to a zone
    # =====================================================================
    
    def send_to_zone(self, arm_name: str, zone_name: str, position_name: str = 'ready', duration: float = 3.0):
        """
        Send arm to a zone with zone-locking AND time-window coordination.
        
        1. Check if zone is free (zone lock)
        2. Check TimeManager for predicted time conflicts
        3. If free and no time conflict: lock zone + send trajectory
        4. If busy or time conflict: queue arm, return False
        
        Args:
            arm_name: 'arm1' or 'arm2'
            zone_name: key in self.zones (e.g. 'zone_a', 'home')
            position_name: preset position to move to
            duration: trajectory duration
        
        Returns:
            True if zone granted immediately, False if queued
        """
        if arm_name not in self.arm_status:
            self.get_logger().error(f'Unknown arm: {arm_name}. Available: {list(self.arm_status.keys())}')
            return False
        
        if zone_name not in self.zones:
            self.get_logger().error(f'Unknown zone: {zone_name}. Available: {list(self.zones.keys())}')
            return False
        
        zone = self.zones[zone_name]
        status = self.arm_status[arm_name]
        
        if status.state != ArmState.IDLE:
            self.get_logger().warn(f'[{arm_name}] Cannot request zone — arm is {status.state.name}')
            return False
        
        # Check time window conflicts via TimeManager
        predicted_duration = predict_duration(position_name, duration)
        schedule_result = self.time_manager.schedule(
            arm_name, zone_name,
            duration=predicted_duration,
            position_name=position_name,
        )
        
        if schedule_result.conflict:
            conflict = schedule_result.conflict
            self.get_logger().warn(
                f'[{arm_name}] Time conflict detected with {conflict.arm_b} '
                f'in "{zone_name}" (overlap={conflict.overlap_duration:.1f}s). '
                f'Suggested delay: {schedule_result.suggested_delay:.1f}s'
            )
            # Cancel the scheduled window since we're queuing
            self.time_manager.cancel(arm_name)
            
            # Queue this arm
            status.state = ArmState.QUEUED
            status.requested_zone = zone_name
            status.requested_position = position_name  # preserve for _trigger_queued_arm
            self.json_logger.warn(f'Time conflict, arm queued', arm=arm_name, component='coordinator', data={'zone': zone_name, 'conflict_with': conflict.arm_b, 'overlap': conflict.overlap_duration})
            return False
        
        # Try to claim the zone (zone lock)
        granted = zone.request_entry(arm_name)
        
        if granted:
            # Zone locked, schedule is confirmed
            self.get_logger().info(
                f'[{arm_name}] Zone "{zone_name}" granted, '
                f'scheduled for {predicted_duration:.1f}s'
            )
            self.json_logger.info(f'Zone granted', arm=arm_name, component='coordinator', data={'zone': zone_name, 'duration': predicted_duration})
            status.state = ArmState.WORKING
            status.current_zone = zone_name
            status.goal_start_time = time.time()
            
            self.time_manager.start_executing(arm_name)
            
            positions = PRESET_POSITIONS.get(position_name, PRESET_POSITIONS['ready'])
            trajectory = self.create_trajectory(arm_name, positions, duration)
            self._send_trajectory_async(arm_name, trajectory)
            return True
        else:
            # Zone occupied, cancel time schedule and queue
            self.time_manager.cancel(arm_name)
            self.get_logger().info(f'[{arm_name}] Zone "{zone_name}" occupied by {zone.occupied_by}, queuing')
            self.json_logger.info(f'Zone occupied, arm queued', arm=arm_name, component='coordinator', data={'zone': zone_name, 'occupied_by': zone.occupied_by})
            status.state = ArmState.QUEUED
            status.requested_zone = zone_name
            status.requested_position = position_name  # preserve for _trigger_queued_arm
            return False

    # =====================================================================
    # Internal: Send trajectory asynchronously
    # =====================================================================
    
    def _send_trajectory_async(self, arm_name: str, trajectory: JointTrajectory):
        """Send trajectory goal asynchronously."""
        client = self.action_clients[arm_name]
        goal = FollowJointTrajectory.Goal()
        goal.trajectory = trajectory
        
        self.get_logger().info(f'[{arm_name}] Sending trajectory goal')
        future = client.send_goal_async(goal)
        
        # Attach callback for when goal is accepted/rejected
        future.add_done_callback(
            lambda f, an=arm_name: self._on_goal_response(f, an)
        )
        
        # Store the future (will be replaced by GoalHandle in _on_goal_response)
        self.goal_handles[arm_name] = {'future': future, 'goal_handle': None}
        return future

    def _on_goal_response(self, future, arm_name: str):
        """Callback when goal is accepted/rejected by server."""
        try:
            goal_handle = future.result()
            if not goal_handle.accepted:
                self.get_logger().warn(f'[{arm_name}] Goal was rejected')
                self._release_arm(arm_name)
                return
            
            self.get_logger().info(f'[{arm_name}] Goal accepted, waiting for result...')
            # Store the GoalHandle for cancel_goal support
            if arm_name in self.goal_handles:
                self.goal_handles[arm_name]['goal_handle'] = goal_handle
            
            # Request result asynchronously (non-blocking)
            result_future = goal_handle.get_result_async()
            result_future.add_done_callback(
                lambda f, an=arm_name: self._on_result_complete(f, an)
            )
            
        except Exception as e:
            self.get_logger().error(f'[{arm_name}] Exception in goal response: {e}')
            self._release_arm(arm_name)

    def _on_result_complete(self, future, arm_name: str):
        """Callback when trajectory execution finishes."""
        try:
            result_response = future.result()
            result = result_response.result  # FollowJointTrajectory_Result
            status = self.arm_status[arm_name]
            
            if result.error_code == JTC_SUCCESSFUL:
                self.get_logger().info(f'[{arm_name}] Goal completed successfully')
                self.json_logger.info('Goal completed successfully', arm=arm_name, component='trajectory')
                # Mark time window as completed
                self.time_manager.complete(arm_name)
                self._release_arm(arm_name)
            else:
                self.get_logger().error(f'[{arm_name}] Goal failed with code: {result.error_code} ({result.error_string})')
                self.json_logger.error(f'Goal failed', arm=arm_name, component='trajectory', data={'error_code': result.error_code, 'error_string': result.error_string})
                status.state = ArmState.ERROR
                status.error_message = f'Goal failed: {result.error_code}'
                # Release zone lock but keep arm in ERROR state (user must call reset_arm)
                self._release_zone_only(arm_name)
            
        except Exception as e:
            self.get_logger().error(f'[{arm_name}] Exception in result callback: {e}')
            self._release_arm(arm_name)

    def _release_arm(self, arm_name: str):
        """Release zone lock and reset arm state. Also trigger queued arms."""
        status = self.arm_status[arm_name]
        
        if status.current_zone:
            zone = self.zones[status.current_zone]
            zone_name = status.current_zone
            
            # First try zone-level queue
            next_arm = zone.release(arm_name)
            
            if next_arm:
                self.get_logger().info(f'Zone "{zone.name}" transferred to [{next_arm}] (from zone queue)')
                self._trigger_queued_arm(next_arm, zone.name)
            else:
                # No one in zone queue — check for TimeManager-queued arms
                next_arm = self._find_queued_arm_for_zone(zone_name)
                if next_arm:
                    self.get_logger().info(f'Zone "{zone_name}" triggered [{next_arm}] (from time queue)')
                    self._trigger_queued_arm(next_arm, zone_name)
            
            status.current_zone = None
        
        # Reset state
        status.reset()
        self.get_logger().info(f'[{arm_name}] Released, now IDLE')
        self.json_logger.info('Arm released to IDLE', arm=arm_name, component='coordinator')

    def _release_zone_only(self, arm_name: str):
        """Release zone lock WITHOUT resetting arm state (for ERROR recovery)."""
        status = self.arm_status[arm_name]
        
        if status.current_zone:
            zone = self.zones[status.current_zone]
            zone_name = status.current_zone
            
            # Release zone and trigger queued arms
            next_arm = zone.release(arm_name)
            
            if next_arm:
                self.get_logger().info(f'Zone "{zone.name}" transferred to [{next_arm}] (from zone queue)')
                self._trigger_queued_arm(next_arm, zone.name)
            else:
                next_arm = self._find_queued_arm_for_zone(zone_name)
                if next_arm:
                    self.get_logger().info(f'Zone "{zone_name}" triggered [{next_arm}] (from time queue)')
                    self._trigger_queued_arm(next_arm, zone_name)
            
            status.current_zone = None
        
        # NOTE: Does NOT reset arm state — arm stays in ERROR until reset_arm() is called
    
    def _find_queued_arm_for_zone(self, zone_name: str) -> str:
        """Find an arm in QUEUED state that was waiting for this zone."""
        for arm_name, status in self.arm_status.items():
            if (status.state == ArmState.QUEUED and 
                status.requested_zone == zone_name):
                return arm_name
        return None

    def _trigger_queued_arm(self, arm_name: str, zone_name: str):
        """Trigger a queued arm to start its trajectory."""
        status = self.arm_status[arm_name]
        
        if status.state == ArmState.QUEUED and status.requested_zone == zone_name:
            zone = self.zones[zone_name]
            zone.occupied_by = arm_name  # re-claim (release gave it, but we're re-granting)
            
            status.state = ArmState.WORKING
            status.current_zone = zone_name
            status.requested_zone = None
            status.goal_start_time = time.time()
            
            # Use the original requested position, not hardcoded 'ready'
            position_name = getattr(status, 'requested_position', None) or 'ready'
            positions = PRESET_POSITIONS.get(position_name, PRESET_POSITIONS['ready'])
            trajectory = self.create_trajectory(arm_name, positions, 3.0)
            self._send_trajectory_async(arm_name, trajectory)
            self.get_logger().info(f'[{arm_name}] Queued trigger executed, moving to zone "{zone_name}" (position={position_name})')

    # =====================================================================
    # State Machine Tick
    # =====================================================================
    
    def _tick(self):
        """Periodic state machine check (timeouts + cleanup)."""
        for arm_name, status in self.arm_status.items():
            if status.state == ArmState.WORKING and status.goal_start_time:
                elapsed = time.time() - status.goal_start_time
                # Timeout after 2x predicted duration
                predicted = predict_duration(status.current_zone or '', 3.0)
                timeout = max(predicted * 2, 15.0)  # at least 15s
                if elapsed > timeout:
                    self.get_logger().warn(f'[{arm_name}] Goal timeout ({elapsed:.1f}s > {timeout:.1f}s), cancelling and releasing')
                    self.json_logger.warn('Goal timeout, cancelling', arm=arm_name, component='watchdog', data={'elapsed': elapsed, 'timeout': timeout})
                    self._cancel_and_release(arm_name)
        
        # Periodic cleanup of old time windows
        self.time_manager.cleanup()

    def _cancel_and_release(self, arm_name: str):
        """Cancel active goal and release arm (for timeout/error recovery)."""
        status = self.arm_status[arm_name]
        
        # Try to cancel the goal via GoalHandle
        goal_info = self.goal_handles.get(arm_name)
        if goal_info and goal_info.get('goal_handle'):
            try:
                goal_handle = goal_info['goal_handle']
                goal_handle.cancel_goal_async()
                self.get_logger().info(f'[{arm_name}] Cancel request sent')
            except Exception as e:
                self.get_logger().warn(f'[{arm_name}] Failed to cancel goal: {e}')
        
        # Release arm
        self._release_arm(arm_name)

    def reset_arm(self, arm_name: str) -> bool:
        """
        Manually reset an arm from ERROR state back to IDLE.
        
        Returns:
            True if arm was reset, False if arm was not in ERROR state
        """
        if arm_name not in self.arm_status:
            self.get_logger().error(f'Unknown arm: {arm_name}. Available: {list(self.arm_status.keys())}')
            return False
        
        status = self.arm_status[arm_name]
        if status.state != ArmState.ERROR:
            self.get_logger().warn(f'[{arm_name}] Cannot reset — arm is {status.state.name} (not ERROR)')
            return False
        
        self.get_logger().info(f'[{arm_name}] Manual reset from ERROR to IDLE')
        self.json_logger.info('Manual reset from ERROR to IDLE', arm=arm_name, component='coordinator')
        self._release_arm(arm_name)
        return True

    # =====================================================================
    # High-Level API: Task Scheduling
    # =====================================================================
    
    def submit_task(self, task: Task) -> str:
        """
        Submit a task to the scheduler.
        
        Args:
            task: Task object with zone, position, priority, etc.
        
        Returns:
            task_id for tracking
        """
        task_id = self.task_scheduler.submit(task)
        self.get_logger().info(
            f'Task submitted: {task_id} '
            f'(zone={task.zone_name}, pos={task.position_name}, '
            f'priority={task.priority.name})'
        )
        return task_id
    
    def schedule_pending_tasks(self):
        """
        Schedule all pending tasks and execute them.
        
        Returns:
            Number of tasks scheduled
        """
        plan = self.task_scheduler.schedule_all()
        
        if plan.scheduled:
            self.get_logger().info(f'Scheduled {len(plan.scheduled)} tasks')
            for t in plan.scheduled:
                self.get_logger().info(
                    f'  [{t.task_id}] arm={t.assigned_arm} '
                    f'zone={t.zone_name} delay={t.start_delay:.1f}s'
                )
        
        if plan.failed:
            self.get_logger().warn(f'Failed to schedule {len(plan.failed)} tasks')
            for t in plan.failed:
                self.get_logger().warn(f'  [{t.task_id}] {t.error_message}')
        
        # Execute scheduled tasks
        executed = self.task_scheduler.execute_plan(plan, self)
        self.get_logger().info(f'Executed {executed} tasks')
        
        return len(plan.scheduled)
    
    def cancel_task(self, task_id: str) -> bool:
        """Cancel a pending or scheduled task."""
        result = self.task_scheduler.cancel(task_id)
        if result:
            self.get_logger().info(f'Task cancelled: {task_id}')
        return result
    
    # =====================================================================
    # Debug / Status
    # =====================================================================
    
    def print_status(self):
        """Print current system status including time windows and tasks."""
        self.get_logger().info('====== Coordinator Status ======')
        for arm_name, status in self.arm_status.items():
            self.get_logger().info(
                f'  {arm_name}: {status.state.name}'
                f' | zone={status.current_zone or "-"}'
                f' | requested={status.requested_zone or "-"}'
            )
        for zone_name, zone in self.zones.items():
            self.get_logger().info(
                f'  zone:{zone_name}: occupied_by={zone.occupied_by or "FREE"}'
                f' | queue={zone.waiting_queue}'
            )
        # Time manager schedule
        schedule_str = self.time_manager.print_schedule()
        if schedule_str:
            self.get_logger().info('  --- Time Windows ---')
            for line in schedule_str.split('\n'):
                self.get_logger().info(line)
        # Task scheduler status
        pending = self.task_scheduler.get_pending_tasks()
        if pending:
            self.get_logger().info(f'  --- Pending Tasks: {len(pending)} ---')
            for t in pending[:3]:
                self.get_logger().info(
                    f'    [{t.task_id}] {t.priority.name} '
                    f'zone={t.zone_name} pos={t.position_name}'
                )
        self.get_logger().info('==============================')


def main(args=None):
    rclpy.init(args=args)
    
    coordinator = EnhancedMultiArmCoordinator()
    
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(coordinator)
    
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        coordinator.get_logger().info('Shutting down coordinator')
        coordinator.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()