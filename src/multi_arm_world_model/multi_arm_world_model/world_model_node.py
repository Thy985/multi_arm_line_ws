"""WorldModelNode - ROS2 node implementing the World Model (L5).

The WorldModel is the world cognition truth source.
- OWNS: Objects, Environment, TaskContext
- CACHES (non-owning): RobotState at 1-10Hz
- DOES NOT OWN: Real-time control state (ros2_control, 100-500Hz)
"""

import os
from typing import Dict, List, Optional, Tuple

import rclpy
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import QoSProfile, DurabilityPolicy, ReliabilityPolicy
from sensor_msgs.msg import JointState

from multi_arm_world_model.state_database import (
    StateDatabase,
    TrackedObject,
    CachedRobotState,
    TaskContext,
)
from multi_arm_world_model.object_tracker import ObjectTracker


class WorldModelNode(Node):
    """World Model node - the world cognition truth source (L5).

    Subscriptions:
    - /perception/object_poses: Object detection updates
    - /{arm}/joint_states: Joint states (cached at 1-10Hz, NOT 500Hz)

    Publishers:
    - /world_model/state: Full world state (1Hz)
    - /world_model/changes: Change events (event-driven)

    Services:
    - /world_model/query_objects: Query tracked objects
    - /world_model/query_robot_pose: Query cached robot state
    """

    CACHE_RATE_HZ = 5.0

    def __init__(self) -> None:
        super().__init__("world_model_node")

        cb_group = ReentrantCallbackGroup()
        self._db = StateDatabase()
        self._tracker = ObjectTracker()

        self._arm_names = self.declare_parameter(
            "arm_names", ["arm1", "arm2"]
        ).value

        self._joint_states_raw: Dict[str, JointState] = {}
        self._cache_counter = 0

        self._init_subscriptions(cb_group)
        self._init_publishers(cb_group)
        self._init_services(cb_group)

        self.create_timer(1.0 / self.CACHE_RATE_HZ, self._cache_joint_states, callback_group=cb_group)
        self.create_timer(1.0, self._publish_state, callback_group=cb_group)
        self.create_timer(10.0, self._cleanup, callback_group=cb_group)

        self._init_default_environment()

        self.get_logger().info("WorldModel node started")
        self.get_logger().info(f"Caching robot state at {self.CACHE_RATE_HZ}Hz (NOT 500Hz)")

    def _init_subscriptions(self, cb_group: ReentrantCallbackGroup) -> None:
        """Initialize subscriptions."""
        for arm_name in self._arm_names:
            self.create_subscription(
                JointState,
                f"/{arm_name}/joint_states",
                lambda msg, an=arm_name: self._on_joint_state(msg, an),
                10,
                callback_group=cb_group,
            )

        try:
            from multi_arm_interfaces.msg import ObjectPose

            self.create_subscription(
                ObjectPose,
                "/perception/object_poses",
                self._on_object_pose,
                10,
                callback_group=cb_group,
            )
        except ImportError:
            self.get_logger().warn("multi_arm_interfaces not available, object tracking disabled")

    def _init_publishers(self, cb_group: ReentrantCallbackGroup) -> None:
        """Initialize publishers."""
        try:
            from multi_arm_interfaces.msg import ObjectPose

            self._state_pub = self.create_publisher(
                ObjectPose,
                "/world_model/state",
                QoSProfile(depth=10, durability=DurabilityPolicy.TRANSIENT_LOCAL),
                callback_group=cb_group,
            )
        except ImportError:
            self._state_pub = None

    def _init_services(self, cb_group: ReentrantCallbackGroup) -> None:
        """Initialize service servers."""
        try:
            from multi_arm_interfaces.srv import QueryResources

            self._query_objects_srv = self.create_service(
                QueryResources,
                "/world_model/query_objects",
                self._on_query_objects,
                callback_group=cb_group,
            )
        except ImportError:
            self.get_logger().warn("multi_arm_interfaces not available, query services disabled")
            self._query_objects_srv = None

    def _init_default_environment(self) -> None:
        """Initialize default environment from config."""
        config_path = os.path.join(
            os.path.dirname(__file__), "..", "config", "world_model_config.yaml"
        )
        config_path = os.path.abspath(config_path)

        if not os.path.exists(config_path):
            try:
                from ament_index_python.packages import get_package_share_directory
                pkg_dir = get_package_share_directory("multi_arm_world_model")
                config_path = os.path.join(pkg_dir, "config", "world_model_config.yaml")
            except Exception:
                pass

        if os.path.exists(config_path):
            import yaml
            with open(config_path, "r") as f:
                config = yaml.safe_load(f)
            for zone_name, zone_info in config.get("zones", {}).items():
                self._db.add_zone(zone_name, zone_info)
            for obstacle in config.get("obstacles", []):
                self._db.add_obstacle(obstacle)
        else:
            for zone in ["zone_a", "zone_b", "zone_c", "home"]:
                self._db.add_zone(zone, {"type": "shared"})

    def _on_joint_state(self, msg: JointState, arm_name: str) -> None:
        """Store raw joint states (will be cached at lower rate)."""
        self._joint_states_raw[arm_name] = msg

    def _cache_joint_states(self) -> None:
        """Cache joint states at 1-10Hz (NOT 500Hz).

        This is the key ownership boundary: 500Hz joint_states from
        ros2_control do NOT enter WorldModel. Only downsampled cache.
        """
        for arm_name, msg in self._joint_states_raw.items():
            if msg.position:
                self._db.update_robot_state(
                    arm_name,
                    joint_positions=list(msg.position),
                    joint_velocities=list(msg.velocity) if msg.velocity else None,
                )

    def _on_object_pose(self, msg) -> None:
        """Handle object pose updates from perception."""
        detection = {
            "id": msg.object_id,
            "object_type": msg.object_type,
            "position": tuple(msg.position),
            "orientation": tuple(msg.orientation),
            "confidence": msg.confidence,
        }
        self._tracker.update(self._db, [detection])

    def _on_query_objects(self, request, response) -> None:
        """Handle query objects service."""
        objects = self._db.get_all_objects()
        response.resource_names = [o.object_id for o in objects]
        response.resource_types = [o.object_type for o in objects]
        response.states = ["active" if not o.is_stale() else "stale" for o in objects]
        response.allocated_to = [f"{o.confidence:.2f}" for o in objects]
        return response

    def _publish_state(self) -> None:
        """Publish world model state at 1Hz."""
        if self._state_pub is None:
            return
        try:
            from multi_arm_interfaces.msg import ObjectPose

            for obj in self._db.get_all_objects():
                msg = ObjectPose()
                msg.object_id = obj.object_id
                msg.object_type = obj.object_type
                msg.position = list(obj.position)
                msg.orientation = list(obj.orientation)
                msg.confidence = obj.confidence
                self._state_pub.publish(msg)
        except Exception:
            pass

    def _cleanup(self) -> None:
        """Periodic cleanup of stale data."""
        self._db.cleanup_stale(object_max_age=30.0)

    @property
    def database(self) -> StateDatabase:
        """Access the state database (for testing)."""
        return self._db


def main(args=None) -> None:
    """Entry point for the world model node."""
    rclpy.init(args=args)
    node = WorldModelNode()
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()