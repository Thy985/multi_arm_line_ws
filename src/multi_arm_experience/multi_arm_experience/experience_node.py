"""Experience Node — ROS2 interface for Robot Experience Infrastructure.

Services:
    - /experience/record (RecordEpisode.srv) — record a completed episode
    - /experience/query (QueryExperience.srv) — query experience data

Topics:
    - /data/episode (EpisodeData.msg) — published when an episode is recorded
"""

from __future__ import annotations

import json
import sys
from typing import Any

import rclpy
from rclpy.callback_group import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node

from multi_arm_interfaces.msg import EpisodeData
from multi_arm_interfaces.srv import QueryExperience, RecordEpisode

from multi_arm_experience.episode import Episode, WorldStateSnapshot
from multi_arm_experience.experience_recorder import ExperienceRecorder
from multi_arm_experience.dataset_exporter import DatasetExporter


class ExperienceNode(Node):
    """ROS2 node for Robot Experience Infrastructure.

    Records episodes, exports to dataset, and exposes query interface.
    """

    def __init__(self) -> None:
        """Initialize experience node."""
        super().__init__("experience_node")

        self._callback_group = ReentrantCallbackGroup()

        self.declare_parameter("db_path", "experience.db")
        self.declare_parameter("json_dir", "")

        db_path = self.get_parameter("db_path").value
        json_dir = self.get_parameter("json_dir").value

        self._recorder = ExperienceRecorder()
        self._exporter = DatasetExporter(
            db_path=db_path,
            json_dir=json_dir if json_dir else None,
        )

        self._record_srv = self.create_service(
            RecordEpisode,
            "/experience/record",
            self._handle_record,
            callback_group=self._callback_group,
        )

        self._query_srv = self.create_service(
            QueryExperience,
            "/experience/query",
            self._handle_query,
            callback_group=self._callback_group,
        )

        self._episode_pub = self.create_publisher(
            EpisodeData,
            "/data/episode",
            10,
        )

        self.get_logger().info("Experience Node started")

    def _handle_record(
        self,
        request: RecordEpisode.Request,
        response: RecordEpisode.Response,
    ) -> RecordEpisode.Response:
        """Handle RecordEpisode service call.

        Args:
            request: RecordEpisode request.
            response: RecordEpisode response.

        Returns:
            RecordEpisode response.

        """
        episode = self._recorder.start_episode(
            task_type=request.task_type,
            skill_name=request.skill_name,
            robot_id="dual_ur5e",
        )

        try:
            steps = json.loads(request.steps_json) if request.steps_json else []
        except json.JSONDecodeError:
            steps = []

        for step in steps:
            self._recorder.record_step(
                episode,
                step_name=step.get("name", ""),
                success=step.get("success", True),
                duration=step.get("duration", 0.0),
            )

        self._recorder.finish_episode(
            episode,
            result=request.result,
            duration=request.duration,
        )

        self._exporter.export_episode(episode)

        self._publish_episode(episode)

        response.success = True
        response.episode_id = episode.episode_id

        self.get_logger().info(
            f"Recorded episode {episode.episode_id}: "
            f"{request.task_type}/{request.skill_name} -> {request.result}"
        )

        return response

    def _handle_query(
        self,
        request: QueryExperience.Request,
        response: QueryExperience.Response,
    ) -> QueryExperience.Response:
        """Handle QueryExperience service call.

        Args:
            request: QueryExperience request.
            response: QueryExperience response.

        Returns:
            QueryExperience response.

        """
        data_type = request.data_type or "episode"

        try:
            filter_spec = json.loads(request.filter_json) if request.filter_json else {}
        except json.JSONDecodeError:
            filter_spec = {}

        results = self._recorder.query(data_type=data_type)

        if filter_spec:
            results = self._apply_filter(results, filter_spec)

        records_json = []
        for r in results:
            if isinstance(r, Episode):
                records_json.append(r.to_json())
            elif isinstance(r, dict):
                records_json.append(json.dumps(r))
            else:
                records_json.append(json.dumps(str(r)))

        response.records_json = records_json
        response.count = len(records_json)

        return response

    def _apply_filter(
        self,
        results: list[Any],
        filter_spec: dict[str, Any],
    ) -> list[Any]:
        """Apply filter specification to results.

        Args:
            results: List of results.
            filter_spec: Filter specification dict.

        Returns:
            Filtered list.

        """
        filtered = []
        for r in results:
            if isinstance(r, Episode):
                match = True
                if "task_type" in filter_spec:
                    match = match and r.task_type == filter_spec["task_type"]
                if "skill_name" in filter_spec:
                    match = match and r.skill_name == filter_spec["skill_name"]
                if "result" in filter_spec:
                    match = match and r.result == filter_spec["result"]
                if match:
                    filtered.append(r)
            else:
                filtered.append(r)
        return filtered

    def _publish_episode(self, episode: Episode) -> None:
        """Publish episode data on /data/episode topic.

        Args:
            episode: Episode to publish.

        """
        msg = EpisodeData()
        msg.episode_id = episode.episode_id
        msg.task_type = episode.task_type
        msg.skill_name = episode.skill_name
        msg.robot_id = episode.robot_id
        msg.initial_world_json = episode.initial_world.to_json()
        msg.execution_steps_json = json.dumps(
            [
                {
                    "name": s.step_name,
                    "success": s.success,
                    "duration": s.duration,
                }
                for s in episode.execution_steps
            ]
        )
        msg.result = episode.result
        msg.duration = episode.duration
        msg.recovery_count = episode.recovery_count
        msg.timestamp = episode.timestamp

        self._episode_pub.publish(msg)


def main(args: list[str] | None = None) -> None:
    """Entry point for experience node.

    Args:
        args: Command line arguments.

    """
    rclpy.init(args=args)
    node = ExperienceNode()
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
    main(sys.argv)