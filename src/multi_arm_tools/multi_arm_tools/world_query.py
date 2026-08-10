"""World query module — query and display WorldModel state in terminal."""

from typing import Any

from multi_arm_interfaces.srv import QueryWorld


class WorldQuery:
    """Terminal viewer for world model state."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def print_world(self, object_id: str | None = None, show_relations: bool = False) -> None:
        """Print world state.

        Args:
            object_id: If given, print detail for this object only
            show_relations: If True, print relations graph
        """
        entity_id = object_id if object_id else ""
        response = self._client.query_world(entity_id=entity_id)
        if response is None:
            return

        if object_id:
            self._print_object_detail(response, object_id)
        else:
            self._print_objects_list(response)

        if show_relations or object_id is None:
            if show_relations:
                self._print_relations(response.relations)

    def _print_objects_list(self, response: QueryWorld.Response) -> None:
        """Print all objects in a table."""
        objects = response.object_states
        if not objects:
            print("No objects in world model.")
            return

        print(f"\nObjects ({len(objects)}):")
        for obj in objects:
            pos = obj.pose.position
            state_str = obj.grasp_state if obj.grasp_state else "UNKNOWN"
            attached = f"  -> {obj.attached_to}" if obj.attached_to else ""
            print(
                f"  {obj.object_id:<15} "
                f"[{pos[0]:6.2f}, {pos[1]:6.2f}, {pos[2]:6.2f}]  "
                f"{state_str:<10}  conf={obj.confidence:.2f}{attached}"
            )
        print()

    def _print_object_detail(
        self, response: QueryWorld.Response, object_id: str
    ) -> None:
        """Print detail for a single object."""
        for obj in response.object_states:
            if obj.object_id == object_id:
                pos = obj.pose.position
                ori = obj.pose.orientation
                print(f"\nObject: {obj.object_id}")
                print(f"  type:        {obj.object_type}")
                print(f"  position:    [{pos[0]:.3f}, {pos[1]:.3f}, {pos[2]:.3f}]")
                print(f"  orientation: [{ori[0]:.3f}, {ori[1]:.3f}, {ori[2]:.3f}, {ori[3]:.3f}]")
                print(f"  grasp_state: {obj.grasp_state if obj.grasp_state else 'UNKNOWN'}")
                print(f"  attached_to: {obj.attached_to if obj.attached_to else '(none)'}")
                print(f"  confidence:  {obj.confidence:.2f}")
                print()
                return
        print(f"Object '{object_id}' not found in world model.")

    def _print_relations(self, relations: list) -> None:
        """Print relations list."""
        if not relations:
            print("No relations found.")
            return

        print(f"\nRelations ({len(relations)}):")
        for rel in relations:
            dist_str = f"  (dist={rel.distance:.3f}m)" if rel.distance > 0 else ""
            conf_str = f"  conf={rel.confidence:.2f}"
            print(
                f"  {rel.subject:<15} {rel.predicate:<15} {rel.object:<15}"
                f"{conf_str}{dist_str}"
            )
        print()