# Structured task goal — replaces the old "arm1:zone_a:ready" string protocol.
# This is the domain model for task specification.

string action_type         # Action type: "move", "pick_place", "grasp", "place", "lift", "retract", "inspect"
string arm_name            # Target arm: "arm1", "arm2"
string zone_name           # Target zone: "zone_a", "zone_b"
string position_name       # Target position: "home", "ready", "scan"
string object_id           # Target object for pick/place: "red_cube", "blue_box"
string approach            # Grasp approach: "top", "side", "front"
multi_arm_interfaces/TaskConstraint constraints