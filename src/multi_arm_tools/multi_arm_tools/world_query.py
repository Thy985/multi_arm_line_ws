"""World query module — query and display WorldModel state in terminal."""

import time
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
        """Print all objects in a table with source/confidence/uncertainty."""
        objects = response.object_states
        if not objects:
            print("No objects in world model.")
            return

        print(f"\nWORLD MODEL")
        print("-" * 60)
        print()
        print(f"{'OBJECT':<15} {'POSITION':<28} {'SOURCE':<12} {'CONF':<6} {'STATUS'}")
        for obj in objects:
            pos = obj.pose.position
            source = obj.source if obj.source else "unknown"
            pos_str = f"({pos[0]:.2f}, {pos[1]:.2f}, {pos[2]:.2f})"
            state_str = obj.grasp_state if obj.grasp_state else "FREE"
            flags = []
            if obj.uncertain:
                flags.append("UNCERTAIN")
            if obj.contradiction:
                flags.append("CONFLICT")
            flag_str = f" [{' '.join(flags)}]" if flags else ""
            print(f"  {obj.object_id:<13} {pos_str:<28} {source:<12} {obj.confidence:<6.2f} {state_str}{flag_str}")
        print()

        uncertain = sum(1 for o in objects if o.uncertain)
        conflicts = sum(1 for o in objects if o.contradiction)
        stale = sum(1 for o in objects if o.ttl > 0 and o.updated_at > 0 and (time.time() - o.updated_at > o.ttl))

        print("HEALTH")
        print(f"  tracked:     {len(objects)}")
        print(f"  uncertain:   {uncertain}")
        print(f"  stale:       {stale}")
        print(f"  conflicts:   {conflicts}")
        print()

    def _print_object_detail(
        self, response: QueryWorld.Response, object_id: str
    ) -> None:
        """Print detail for a single object — WorldModel debugger."""
        for obj in response.object_states:
            if obj.object_id == object_id:
                pos = obj.pose.position
                ori = obj.pose.orientation
                print(f"\nOBJECT: {obj.object_id}")
                print()
                print("CURRENT BELIEF")
                print(f"  Position")
                print(f"    mean:       ({pos[0]:.3f}, {pos[1]:.3f}, {pos[2]:.3f})")
                if obj.position_covariance is not None and len(obj.position_covariance) > 0:
                    var_x = obj.position_covariance[0] if len(obj.position_covariance) > 0 else 0
                    var_y = obj.position_covariance[4] if len(obj.position_covariance) > 4 else 0
                    var_z = obj.position_covariance[8] if len(obj.position_covariance) > 8 else 0
                    avg_var = (var_x + var_y + var_z) / 3.0
                    print(f"    variance:   {avg_var:.6f}")
                print(f"    confidence: {obj.confidence:.2f}")
                print()
                print("SOURCE")
                src = obj.source if obj.source else "unknown"
                print(f"  {src}")
                print()
                print("STATE")
                print(f"  type:        {obj.object_type}")
                print(f"  grasp_state: {obj.grasp_state if obj.grasp_state else 'UNKNOWN'}")
                print(f"  attached_to: {obj.attached_to if obj.attached_to else '(none)'}")
                print(f"  orientation: [{ori[0]:.3f}, {ori[1]:.3f}, {ori[2]:.3f}, {ori[3]:.3f}]")
                print()
                if obj.vision_error > 0:
                    print("OBSERVATION")
                    print(f"  vision_error: {obj.vision_error:.4f}m")
                    print()
                print("HEALTH")
                stale = obj.ttl > 0 and obj.updated_at > 0 and (time.time() - obj.updated_at > obj.ttl)
                print(f"  stale:        {'YES' if stale else 'NO'}")
                print(f"  contradiction:{'YES' if obj.contradiction else 'NO'}")
                print(f"  uncertain:    {'YES' if obj.uncertain else 'NO'}")
                if obj.position_covariance is not None and len(obj.position_covariance) > 0:
                    print(f"  covariance:   [{obj.position_covariance[0]:.6f}, ...]")
                if obj.orientation_uncertainty > 0:
                    print(f"  orient_unc:   {obj.orientation_uncertainty:.4f}")
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