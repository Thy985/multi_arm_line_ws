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
from multi_arm_world_model.relation_layer import RelationLayer
from multi_arm_world_model.history_layer import HistoryLayer
from multi_arm_world_model.prediction_layer import PredictionLayer
from multi_arm_world_model.belief_layer import BeliefUpdater, GaussianBelief


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
        self._relations = RelationLayer()
        self._history = HistoryLayer(max_length=100)
        self._prediction = PredictionLayer(history=self._history)
        self._belief_updater = BeliefUpdater(base_variance=0.05, gt_variance=0.001)

        self._arm_names = self.declare_parameter(
            "arm_names", ["left_arm", "right_arm"]
        ).value

        self._min_confidence = self.declare_parameter(
            "min_confidence", 0.3
        ).value

        self._contradiction_threshold = self.declare_parameter(
            "contradiction_threshold", 0.5
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
            self.create_subscription(
                ObjectPose,
                "/perception/vision_poses",
                self._on_vision_pose,
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

        try:
            from multi_arm_interfaces.srv import QueryWorld, QueryRelation

            self._query_world_srv = self.create_service(
                QueryWorld,
                "/world_model/query_world",
                self._on_query_world,
                callback_group=cb_group,
            )
            self._query_relation_srv = self.create_service(
                QueryRelation,
                "/world_model/query_relation",
                self._on_query_relation,
                callback_group=cb_group,
            )
        except ImportError:
            self.get_logger().warn("QueryWorld/QueryRelation services not available")
            self._query_world_srv = None
            self._query_relation_srv = None

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

        obj = self._db.get_object(msg.object_id)
        if obj is not None:
            source = msg.source if msg.source else "ground_truth"
            obj.metadata["source"] = source

            belief = self._belief_updater.update(
                msg.object_id,
                tuple(msg.position),
                msg.confidence,
                source,
            )
            obj.position_covariance = belief.to_covariance_flat()
            obj.metadata["belief_uncertainty"] = belief.uncertainty

        self._history.record(
            msg.object_id,
            {
                "position": list(msg.position),
                "orientation": list(msg.orientation),
                "confidence": msg.confidence,
                "velocity": list(obj.velocity) if obj else [0.0, 0.0, 0.0],
                "source": msg.source if msg.source else "ground_truth",
            },
        )

    def _on_vision_pose(self, msg) -> None:
        """Handle vision pose updates.

        - Reject detections below min_confidence (hallucination defense)
        - When GT absent, use vision as primary position (vision-only mode)
        - When GT present, compute error and flag/clear contradictions
        - Update belief state with vision observation
        - Record to history layer (M7.6: vision now writes history)
        """
        if msg.confidence < self._min_confidence:
            return

        obj = self._db.get_object(msg.object_id)
        gt_claimed = obj is not None and obj.metadata.get("source") == "ground_truth"

        if obj is None:
            detection = {
                "id": msg.object_id,
                "object_type": msg.object_type,
                "position": tuple(msg.position),
                "orientation": tuple(msg.orientation),
                "confidence": msg.confidence,
            }
            self._tracker.update(self._db, [detection])
            obj = self._db.get_object(msg.object_id)

        if obj is None:
            return

        obj.metadata["vision_position"] = list(msg.position)
        obj.metadata["vision_confidence"] = msg.confidence

        belief = self._belief_updater.update(
            msg.object_id,
            tuple(msg.position),
            msg.confidence,
            "vision",
        )
        obj.metadata["belief_uncertainty"] = belief.uncertainty

        if not gt_claimed:
            obj.metadata["source"] = "vision"
            obj.position = tuple(msg.position)
            obj.orientation = tuple(msg.orientation)
            obj.confidence = msg.confidence
            obj.position_covariance = belief.to_covariance_flat()

        gt_pos = obj.position
        vis_pos = tuple(msg.position)
        error = (
            (gt_pos[0] - vis_pos[0]) ** 2
            + (gt_pos[1] - vis_pos[1]) ** 2
            + (gt_pos[2] - vis_pos[2]) ** 2
        ) ** 0.5
        obj.metadata["vision_error"] = error
        obj.metadata["uncertain"] = msg.confidence < 0.8

        if gt_claimed and error > self._contradiction_threshold:
            obj.metadata["contradiction"] = True
        elif gt_claimed and error <= self._contradiction_threshold:
            obj.metadata["contradiction"] = False

        self._history.record(
            msg.object_id,
            {
                "position": list(msg.position),
                "orientation": list(msg.orientation),
                "confidence": msg.confidence,
                "velocity": list(obj.velocity),
                "source": "vision",
                "vision_error": error,
            },
        )

    def _on_query_objects(self, request, response) -> None:
        """Handle query objects service."""
        objects = self._db.get_all_objects()
        response.resource_names = [o.object_id for o in objects]
        response.resource_types = [o.object_type for o in objects]
        response.states = ["active" if not o.is_stale() else "stale" for o in objects]
        response.allocated_to = [f"{o.confidence:.2f}" for o in objects]
        return response

    def _on_query_world(self, request, response) -> None:
        """Handle QueryWorld service — return complete world state.

        M7.6: Supports at_time temporal query (0.0 = now, nonzero = state at time T).
        """
        try:
            from multi_arm_interfaces.msg import (
                ObjectState, SceneState, TaskState, Relation as RelationMsg,
                ObjectPose,
            )

            query_type = request.query_type
            at_time = getattr(request, "at_time", 0.0)

            if query_type in ("object", "all", ""):
                for obj in self._db.get_all_objects():
                    pose = ObjectPose()
                    pose.object_id = obj.object_id
                    pose.object_type = obj.object_type

                    if at_time > 0.0:
                        hist_entry = self._history.get_latest(obj.object_id)
                        if hist_entry and hist_entry.timestamp <= at_time:
                            hist_pos = hist_entry.data.get("position", list(obj.position))
                            pose.position = hist_pos
                            pose.confidence = hist_entry.data.get("confidence", obj.confidence)
                        else:
                            pose.position = list(obj.position)
                            pose.confidence = obj.confidence
                    else:
                        pose.position = list(obj.position)
                        pose.confidence = obj.confidence

                    pose.orientation = list(obj.orientation) if obj.orientation else [0, 0, 0, 1]

                    state = ObjectState()
                    state.object_id = obj.object_id
                    state.object_type = obj.object_type
                    state.pose = pose
                    state.velocity = list(obj.velocity) if obj.velocity else [0.0, 0.0, 0.0]
                    state.confidence = obj.confidence
                    state.attached_to = ""
                    state.grasp_state = "FREE"
                    state.observed_at = obj.observed_at if obj.observed_at > 0.0 else obj.last_seen
                    state.updated_at = obj.updated_at
                    state.ttl = obj.ttl
                    state.position_covariance = list(obj.position_covariance)
                    state.orientation_uncertainty = obj.orientation_uncertainty
                    state.source = obj.metadata.get("source", "unknown")
                    state.vision_error = obj.metadata.get("vision_error", 0.0)
                    state.uncertain = obj.metadata.get("uncertain", False)
                    state.contradiction = obj.metadata.get("contradiction", False)

                    belief = self._belief_updater.get_belief(obj.object_id)
                    if belief is not None:
                        obj.metadata["belief_uncertainty"] = belief.uncertainty

                    attached_rels = self._relations.query(
                        subject=obj.object_id, predicate="attached_to"
                    )
                    if attached_rels:
                        state.attached_to = attached_rels[0].object
                        state.grasp_state = "ATTACHED"

                    response.object_states.append(state)

            if query_type in ("relation", "all", ""):
                for rel in self._relations.get_all_relations():
                    msg = RelationMsg()
                    msg.subject = rel.subject
                    msg.predicate = rel.predicate
                    msg.object = rel.object
                    msg.confidence = rel.confidence
                    msg.distance = rel.distance
                    msg.ttl = rel.ttl
                    response.relations.append(msg)

            if query_type in ("scene", "all", ""):
                env = self._db.environment
                scene = SceneState()
                scene.timestamp = float(self.get_clock().now().nanoseconds / 1e9)
                response.scene_state = scene

        except Exception as e:
            self.get_logger().warn(f"QueryWorld error: {e}")

        return response

    def _on_query_relation(self, request, response) -> None:
        """Handle QueryRelation service — query entity relations."""
        try:
            from multi_arm_interfaces.msg import Relation as RelationMsg

            rels = self._relations.query(
                subject=request.subject,
                predicate=request.predicate,
                object=request.object,
            )

            for rel in rels:
                msg = RelationMsg()
                msg.subject = rel.subject
                msg.predicate = rel.predicate
                msg.object = rel.object
                msg.confidence = rel.confidence
                msg.distance = rel.distance
                msg.ttl = rel.ttl
                response.relations.append(msg)

            response.exists = len(rels) > 0

        except Exception as e:
            self.get_logger().warn(f"QueryRelation error: {e}")

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