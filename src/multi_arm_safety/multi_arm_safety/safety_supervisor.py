"""SafetySupervisor - independent safety plane node.

The SafetySupervisor is an independent ROS2 node that implements the
Safety Plane as a cross-cutting concern across all layers (L1-L7).

Key properties:
- Independent: Does NOT depend on Coordinator to run
- Final authority: Can stop all arm motion via E-Stop
- Cross-cutting: Provides safety checks for Task (L6), Motion (L3), Control (L2)

M4 Enhancement: E-Stop now actively stops JTC via controller_manager/switch_controller
"""

import os
from typing import Dict, List, Optional

import rclpy
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
from sensor_msgs.msg import JointState
from lifecycle_msgs.srv import ChangeState
from lifecycle_msgs.msg import Transition

from multi_arm_safety.safety_level import SafetyLevel
from multi_arm_safety.speed_limiter import SpeedLimiter
from multi_arm_safety.workspace_limiter import WorkspaceLimiter, WorkspaceBounds
from multi_arm_safety.collision_monitor import CollisionMonitor


class SafetySupervisor(Node):
    """Independent safety supervisor node implementing the Safety Plane.

    Services:
    - /safety/safety_check (SafetyCheck.srv): Trajectory safety validation
    - /safety/emergency_stop (EmergencyStop.srv): E-Stop control

    Publishers:
    - /safety/collision_events (CollisionEvent.msg): Collision notifications
    - /safety/status (ResourceStatus.msg): Safety status updates

    Subscriptions:
    - /{arm}/joint_states: Joint state monitoring for collision detection
    """

    def __init__(self) -> None:
        super().__init__("safety_supervisor")

        cb_group = ReentrantCallbackGroup()

        self._safety_level = SafetyLevel.NORMAL
        self._speed_scale = 1.0
        self._e_stop_active = False

        self._speed_limiter = SpeedLimiter()
        self._workspace_limiter = self._load_workspace_limits()
        self._collision_monitor = CollisionMonitor(
            arm_configs=self._get_arm_configs(),
            min_clearance=0.10,
        )

        self._arm_names = self.declare_parameter("arm_names", ["arm1", "arm2"]).value
        self._joint_states: Dict[str, JointState] = {}

        self._init_services(cb_group)
        self._init_publishers(cb_group)
        self._init_subscriptions(cb_group)
        self._init_controller_clients(cb_group)

        self.create_timer(0.05, self._check_collision, callback_group=cb_group)
        self.create_timer(1.0, self._publish_status, callback_group=cb_group)

        self.get_logger().info(
            f"SafetySupervisor started (level={self._safety_level.name})"
        )
        self.get_logger().info(f"Monitoring arms: {self._arm_names}")

    def _load_workspace_limits(self) -> WorkspaceLimiter:
        """Load workspace limits from YAML config."""
        config_path = os.path.join(
            os.path.dirname(__file__), "..", "config", "safety_config.yaml"
        )
        config_path = os.path.abspath(config_path)

        if not os.path.exists(config_path):
            try:
                from ament_index_python.packages import get_package_share_directory
                pkg_dir = get_package_share_directory("multi_arm_safety")
                config_path = os.path.join(pkg_dir, "config", "safety_config.yaml")
            except Exception:
                pass

        if os.path.exists(config_path):
            import yaml
            with open(config_path, "r") as f:
                config = yaml.safe_load(f)
            return WorkspaceLimiter.from_yaml_config(config)

        limiter = WorkspaceLimiter()
        limiter.set_bounds("arm1", WorkspaceBounds(
            x_min=-1.5, x_max=1.5, y_min=-1.5, y_max=1.5, z_min=0.0, z_max=1.5
        ))
        limiter.set_bounds("arm2", WorkspaceBounds(
            x_min=-1.5, x_max=1.5, y_min=-1.5, y_max=1.5, z_min=0.0, z_max=1.5
        ))
        return limiter

    def _get_arm_configs(self) -> Dict[str, Dict]:
        """Get arm base offset configurations.

        Matches multi_arm_sim.launch.py spawn positions:
        arm1: x=0, y=0, z=0
        arm2: x=1.0, y=0, z=0
        """
        return {
            "arm1": {"base_offset": (0.0, 0.0, 0.0)},
            "arm2": {"base_offset": (1.0, 0.0, 0.0)},
        }

    def _init_services(self, cb_group: ReentrantCallbackGroup) -> None:
        """Initialize service servers."""
        try:
            from multi_arm_interfaces.srv import SafetyCheck, EmergencyStop

            self._safety_check_srv = self.create_service(
                SafetyCheck,
                "/safety/safety_check",
                self._on_safety_check,
                callback_group=cb_group,
            )
            self._e_stop_srv = self.create_service(
                EmergencyStop,
                "/safety/emergency_stop",
                self._on_e_stop,
                callback_group=cb_group,
            )
            self.get_logger().info("Safety services initialized")
        except ImportError:
            self.get_logger().warn(
                "multi_arm_interfaces not available, services not created"
            )
            self._safety_check_srv = None
            self._e_stop_srv = None

    def _init_publishers(self, cb_group: ReentrantCallbackGroup) -> None:
        """Initialize publishers."""
        try:
            from multi_arm_interfaces.msg import CollisionEvent, ResourceStatus

            self._collision_pub = self.create_publisher(
                CollisionEvent,
                "/safety/collision_events",
                QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE),
                callback_group=cb_group,
            )
            self._status_pub = self.create_publisher(
                ResourceStatus,
                "/safety/status",
                QoSProfile(depth=10, durability=DurabilityPolicy.TRANSIENT_LOCAL),
                callback_group=cb_group,
            )
        except ImportError:
            self._collision_pub = None
            self._status_pub = None

    def _init_subscriptions(self, cb_group: ReentrantCallbackGroup) -> None:
        """Initialize joint state subscriptions for each arm."""
        for arm_name in self._arm_names:
            self.create_subscription(
                JointState,
                f"/{arm_name}/joint_states",
                lambda msg, an=arm_name: self._on_joint_state(msg, an),
                10,
                callback_group=cb_group,
            )

    def _on_joint_state(self, msg: JointState, arm_name: str) -> None:
        """Process joint state updates for collision monitoring."""
        self._joint_states[arm_name] = msg
        if msg.position:
            self._collision_monitor.update_joint_positions(
                arm_name, list(msg.position)
            )

    def _on_safety_check(self, request, response) -> None:
        """Handle SafetyCheck.srv requests.

        Checks:
        1. E-Stop status (L2)
        2. Speed limits (L2)
        3. Workspace bounds (L2)
        4. Collision proximity (L3)
        """
        if self._e_stop_active:
            response.approved = False
            response.speed_scale = 0.0
            response.message = "E-Stop active, all commands rejected"
            return response

        if not self._safety_level.allows_new_commands():
            response.approved = False
            response.speed_scale = 0.0
            response.message = f"Safety level {self._safety_level.name} blocks commands"
            return response

        arm_names = list(request.arm_names)
        joint_names = list(request.trajectory_joint_names)
        positions = list(request.trajectory_positions)
        duration = request.trajectory_duration

        _, vel_scale = self._speed_limiter.check_trajectory_velocities(
            joint_names, positions, duration
        )

        workspace_ok = True
        for arm_name in arm_names:
            within, _ = self._workspace_limiter.check_joint_positions(
                arm_name, positions
            )
            if not within:
                workspace_ok = False
                break

        collision_warning = False
        for arm_name in arm_names:
            for other_arm in self._arm_names:
                if other_arm == arm_name:
                    continue
                dist, _ = self._collision_monitor.check_arm_proximity(
                    arm_name, other_arm
                )
                if dist < CollisionMonitor.MIN_CLEARANCE:
                    collision_warning = True
                    break

        speed_scale = min(vel_scale, self._speed_scale)
        if collision_warning:
            speed_scale = min(speed_scale, 0.3)

        approved = workspace_ok and speed_scale > 0.0

        messages = []
        if vel_scale < 1.0:
            messages.append(f"speed_scaled={vel_scale:.2f}")
        if not workspace_ok:
            messages.append("workspace_violation")
        if collision_warning:
            messages.append("collision_proximity_warning")

        response.approved = approved
        response.speed_scale = speed_scale
        response.message = "; ".join(messages) if messages else "approved"
        return response

    def _on_e_stop(self, request, response) -> None:
        """Handle EmergencyStop.srv requests.

        M4: E-Stop now actively stops JTC controllers via
        controller_manager/switch_controller service.
        """
        if request.emergency:
            self._e_stop_active = True
            self._safety_level = SafetyLevel.EMERGENCY_STOP
            self._speed_scale = 0.0
            self.get_logger().error("EMERGENCY STOP ACTIVATED")
            self._halt_all_controllers()
        else:
            self._e_stop_active = False
            self._safety_level = SafetyLevel.NORMAL
            self._speed_scale = 1.0
            self.get_logger().info("E-Stop released, safety level NORMAL")
            self._reactivate_controllers()

        response.success = True
        response.message = (
            f"E-Stop {'activated' if request.emergency else 'released'}"
        )
        return response

    def _init_controller_clients(self, cb_group: ReentrantCallbackGroup) -> None:
        """Initialize service clients for controller_manager interaction."""
        self._switch_ctrl_clients: Dict[str, rclpy.client.Client] = {}
        self._jtc_names: Dict[str, str] = {}
        for arm_name in self._arm_names:
            client = self.create_client(
                ChangeState,
                f"/{arm_name}/controller_manager/change_state",
                callback_group=cb_group,
            )
            self._switch_ctrl_clients[arm_name] = client
            self._jtc_names[arm_name] = "joint_trajectory_controller"

    def _halt_all_controllers(self) -> None:
        """Halt all JTC controllers by deactivating them.

        Uses controller_manager/switch_controller to stop JTC,
        which immediately halts trajectory execution.
        """
        from controller_manager_msgs.srv import SwitchController

        for arm_name in self._arm_names:
            try:
                switch_client = self.create_client(
                    SwitchController,
                    f"/{arm_name}/controller_manager/switch_controller",
                )
                if switch_client.service_is_ready():
                    req = SwitchController.Request()
                    req.deactivate_controllers = [self._jtc_names[arm_name]]
                    req.activate_controllers = []
                    req.strictness = SwitchController.Request.BEST_EFFORT
                    future = switch_client.call_async(req)
                    self.get_logger().warn(
                        f"Halted {arm_name}/{self._jtc_names[arm_name]}"
                    )
                else:
                    self.get_logger().warn(
                        f"controller_manager not ready for {arm_name}, "
                        f"E-Stop flag set but JTC not halted"
                    )
            except Exception as e:
                self.get_logger().warn(
                    f"Failed to halt {arm_name} controller: {e}"
                )

    def _reactivate_controllers(self) -> None:
        """Reactivate JTC controllers after E-Stop release."""
        from controller_manager_msgs.srv import SwitchController

        for arm_name in self._arm_names:
            try:
                switch_client = self.create_client(
                    SwitchController,
                    f"/{arm_name}/controller_manager/switch_controller",
                )
                if switch_client.service_is_ready():
                    req = SwitchController.Request()
                    req.activate_controllers = [self._jtc_names[arm_name]]
                    req.deactivate_controllers = []
                    req.strictness = SwitchController.Request.BEST_EFFORT
                    future = switch_client.call_async(req)
                    self.get_logger().info(
                        f"Reactivated {arm_name}/{self._jtc_names[arm_name]}"
                    )
            except Exception as e:
                self.get_logger().warn(
                    f"Failed to reactivate {arm_name} controller: {e}"
                )

    def _check_collision(self) -> None:
        """Periodic collision check between all arm pairs."""
        if self._e_stop_active:
            return

        results = self._collision_monitor.check_all_pairs(self._arm_names)

        for result in results:
            if result["is_collision"]:
                self.get_logger().error(
                    f"COLLISION DETECTED: {result['arm_a']} <-> {result['arm_b']} "
                    f"(distance={result['distance']:.3f}m)"
                )
                self._publish_collision_event(
                    result["arm_a"], "collision",
                    result["arm_a"], result["arm_b"],
                )
                self._safety_level = SafetyLevel.EMERGENCY_STOP
                self._e_stop_active = True
                self._speed_scale = 0.0

            elif result["is_warning"]:
                if self._safety_level < SafetyLevel.SPEED_LIMITED:
                    self._safety_level = SafetyLevel.SPEED_LIMITED
                    self._speed_scale = 0.3
                    self.get_logger().warn(
                        f"Proximity warning: {result['arm_a']} <-> {result['arm_b']} "
                        f"(distance={result['distance']:.3f}m), speed limited"
                    )
                self._publish_collision_event(
                    result["arm_a"], "proximity_warning",
                    result["arm_a"], result["arm_b"],
                )

    def _publish_collision_event(
        self,
        arm_name: str,
        collision_type: str,
        object_a: str,
        object_b: str,
    ) -> None:
        """Publish a CollisionEvent message."""
        if self._collision_pub is None:
            return

        try:
            from multi_arm_interfaces.msg import CollisionEvent

            msg = CollisionEvent()
            msg.arm_name = arm_name
            msg.collision_type = collision_type
            msg.object_a = object_a
            msg.object_b = object_b
            msg.timestamp = self.get_clock().now().nanoseconds / 1e9
            self._collision_pub.publish(msg)
        except Exception as e:
            self.get_logger().debug(f"Failed to publish collision event: {e}")

    def _publish_status(self) -> None:
        """Publish safety status periodically."""
        if self._status_pub is None:
            return

        try:
            from multi_arm_interfaces.msg import ResourceStatus

            msg = ResourceStatus()
            msg.resource_name = "safety_supervisor"
            msg.resource_type = "SAFETY"
            msg.state = self._safety_level.name
            msg.allocated_to = ""
            msg.capabilities = [
                f"level={self._safety_level.name}",
                f"speed_scale={self._speed_scale:.2f}",
                f"e_stop={'ACTIVE' if self._e_stop_active else 'INACTIVE'}",
            ]
            self._status_pub.publish(msg)
        except Exception as e:
            self.get_logger().debug(f"Failed to publish status: {e}")

    @property
    def safety_level(self) -> SafetyLevel:
        """Current safety level."""
        return self._safety_level

    @property
    def e_stop_active(self) -> bool:
        """Whether E-Stop is currently active."""
        return self._e_stop_active

    @property
    def speed_scale(self) -> float:
        """Current speed scale factor."""
        return self._speed_scale


def main(args=None) -> None:
    """Entry point for the safety supervisor node."""
    rclpy.init(args=args)

    supervisor = SafetySupervisor()

    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(supervisor)

    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        supervisor.get_logger().info("Shutting down safety supervisor")
        supervisor.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()