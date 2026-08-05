"""SafetyInterface for communicating with the Safety Plane via SafetyCheck service."""

from typing import List, Optional

from rclpy.node import Node
from rclpy.callback_groups import ReentrantCallbackGroup


class SafetyInterface:
    """Client interface to the Safety Plane.

    In Phase 1-2, safety checks are performed via SafetyCheck.srv service calls
    before sending trajectory commands. This is non-hard-realtime but provides
    a software safety check layer.

    The SafetySupervisor (in multi_arm_safety package) is the service server.
    This class is the client side used by the Coordinator.
    """

    def __init__(self, node: Node, cb_group: Optional[ReentrantCallbackGroup] = None) -> None:
        """Initialize the safety interface.

        Args:
            node: The ROS2 node that owns this interface.
            cb_group: Optional callback group for async service calls.
        """
        self._node = node
        self._cb_group = cb_group or ReentrantCallbackGroup()
        self._safety_check_client = None
        self._e_stop_client = None
        self._e_stop_active = False
        self._speed_scale = 1.0

        self._init_clients()

    def _init_clients(self) -> None:
        """Initialize service clients."""
        try:
            from multi_arm_interfaces.srv import SafetyCheck, EmergencyStop

            self._safety_check_client = self._node.create_client(
                SafetyCheck,
                "/safety/safety_check",
                callback_group=self._cb_group,
            )
            self._e_stop_client = self._node.create_client(
                EmergencyStop,
                "/safety/emergency_stop",
                callback_group=self._cb_group,
            )
        except ImportError:
            self._node.get_logger().warn(
                "multi_arm_interfaces not available, safety checks will be skipped"
            )

    def check_safety_sync(
        self,
        arm_names: List[str],
        joint_names: List[str],
        positions: List[float],
        duration: float,
    ) -> tuple[bool, float]:
        """Synchronous safety check (blocking).

        Args:
            arm_names: List of arm names involved.
            joint_names: Joint names for the trajectory.
            positions: Target joint positions.
            duration: Trajectory duration in seconds.

        Returns:
            Tuple of (approved, speed_scale).
        """
        if self._safety_check_client is None:
            return True, 1.0

        if self._e_stop_active:
            return False, 0.0

        if not self._safety_check_client.service_is_ready():
            self._node.get_logger().warn(
                "SafetyCheck service not ready, approving by default"
            )
            return True, self._speed_scale

        from multi_arm_interfaces.srv import SafetyCheck

        request = SafetyCheck.Request()
        request.arm_names = arm_names
        request.trajectory_joint_names = joint_names
        request.trajectory_positions = [float(p) for p in positions]
        request.trajectory_duration = duration

        future = self._safety_check_client.call_async(request)
        self._node.get_logger().debug("Safety check request sent")

        try:
            from rclpy.task import Future
            import time
            timeout = 2.0
            start = time.time()
            while not future.done() and (time.time() - start) < timeout:
                time.sleep(0.01)

            if future.done():
                result = future.result()
                if result.approved:
                    self._speed_scale = result.speed_scale
                return result.approved, result.speed_scale
            else:
                self._node.get_logger().warn("Safety check timed out, rejecting")
                return False, 0.0
        except Exception as e:
            self._node.get_logger().error(f"Safety check failed: {e}")
            return False, 0.0

    def trigger_e_stop(self, emergency: bool = True) -> bool:
        """Trigger emergency stop.

        Args:
            emergency: True to activate E-Stop, False to release.

        Returns:
            True if E-Stop was successfully triggered/released.
        """
        if self._e_stop_client is None:
            self._e_stop_active = emergency
            return True

        from multi_arm_interfaces.srv import EmergencyStop

        request = EmergencyStop.Request()
        request.emergency = emergency

        if self._e_stop_client.service_is_ready():
            future = self._e_stop_client.call_async(request)
            import time
            timeout = 2.0
            start = time.time()
            while not future.done() and (time.time() - start) < timeout:
                time.sleep(0.01)

            if future.done():
                result = future.result()
                self._e_stop_active = emergency
                return result.success

        self._e_stop_active = emergency
        return True

    @property
    def e_stop_active(self) -> bool:
        """Whether E-Stop is currently active."""
        return self._e_stop_active

    @property
    def speed_scale(self) -> float:
        """Current speed scale from safety checks."""
        return self._speed_scale