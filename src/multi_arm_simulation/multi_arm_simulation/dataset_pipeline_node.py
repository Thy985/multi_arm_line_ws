"""ROS2 node for dataset pipeline data collection."""

from __future__ import annotations

import sys

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import JointState, Image
from pathlib import Path

from .dataset_pipeline import DatasetPipeline, GroundTruth


class DatasetPipelineNode(Node):
    """ROS2 node for collecting simulation data.

    Subscribes to sensor topics and records data samples
    with ground truth annotations.
    """

    def __init__(self) -> None:
        """Initialize dataset pipeline node."""
        super().__init__("dataset_pipeline_node")

        self.declare_parameter("output_dir", "/tmp/simulation_dataset")
        self.declare_parameter("scene_name", "default")
        self.declare_parameter("record_rate", 10.0)

        output_dir = self.get_parameter("output_dir").value
        self._pipeline = DatasetPipeline(output_dir)
        self._scene_name = self.get_parameter("scene_name").value

        self._episode_id = self._pipeline.start_episode(self._scene_name)

        self._joint_states: dict[str, list[float]] = {}

        self.create_subscription(
            JointState, "/joint_states", self._joint_state_callback, 10
        )

        rate = self.get_parameter("record_rate").value
        self._timer = self.create_timer(1.0 / rate, self._record_sample)

        self.get_logger().info(
            f"DatasetPipelineNode started, recording to {output_dir}"
        )

    def _joint_state_callback(self, msg: JointState) -> None:
        """Store latest joint states.

        Args:
            msg: JointState message.

        """
        self._joint_states[msg.name[0] if msg.name else "default"] = list(msg.position)

    def _record_sample(self) -> None:
        """Record a data sample with current sensor data."""
        gt = GroundTruth(
            timestamp=self.get_clock().now().nanoseconds / 1e9,
            joint_states=self._joint_states.copy(),
        )

        self._pipeline.record_sample(
            joint_states=self._joint_states.copy(),
            ground_truth=gt,
            scene_name=self._scene_name,
        )

    def destroy_node(self) -> bool:
        """Clean up on shutdown."""
        self._pipeline.end_episode(self._episode_id)
        count = self._pipeline.get_sample_count()
        self.get_logger().info(f"Recorded {count} samples total")
        return super().destroy_node()


def main(args: list[str] | None = None) -> None:
    """Entry point for dataset pipeline node.

    Args:
        args: Command line arguments.

    """
    rclpy.init(args=args)
    node = DatasetPipelineNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main(sys.argv)