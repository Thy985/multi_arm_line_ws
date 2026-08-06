# Task constraint specification.
# Used to constrain task execution with time, safety, and priority limits.

float64 max_time           # Maximum allowed execution time in seconds (0 = no limit)
uint8 safety_level         # Safety strictness: 0=normal, 1=strict, 2=critical
uint8 priority             # Task priority: 0=low, 1=normal, 2=high, 3=critical
bool allow_recovery        # Whether recovery is allowed on failure (default: true)
uint8 max_retries          # Maximum recovery retries (0 = no retry)