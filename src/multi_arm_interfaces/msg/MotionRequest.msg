# Motion request for trajectory planning.
# Sent from Coordinator to MoveIt2 for motion planning and execution.

string arm_name            # Arm to move: "arm1", "arm2"
string target_position     # Named target: "home", "ready", or custom
float64[6] joint_positions # Joint positions (alternative to named target)
bool use_named_target      # True = use target_position, False = use joint_positions
float64 speed_scale       # Speed scaling factor (0.0-1.0, default 0.5)
bool collision_check      # Whether to check for collisions (default: true)
float64 max_velocity      # Maximum joint velocity (rad/s, 0 = use default)