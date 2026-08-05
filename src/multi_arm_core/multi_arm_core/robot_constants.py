"""Shared constants for multi-arm robot configuration.

Extracted from coordinator_node.py to avoid circular imports.
"""

ARM_JOINT_NAMES = {
    "arm1": [
        "arm1_shoulder_pan_joint",
        "arm1_shoulder_lift_joint",
        "arm1_elbow_joint",
        "arm1_wrist_1_joint",
        "arm1_wrist_2_joint",
        "arm1_wrist_3_joint",
    ],
    "arm2": [
        "arm2_shoulder_pan_joint",
        "arm2_shoulder_lift_joint",
        "arm2_elbow_joint",
        "arm2_wrist_1_joint",
        "arm2_wrist_2_joint",
        "arm2_wrist_3_joint",
    ],
}

PRESET_POSITIONS = {
    "home": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    "ready": [0.0, -1.57, 1.57, 0.0, 0.0, 0.0],
    "extended": [0.0, -0.5, 2.5, 0.5, 0.5, 0.0],
    "left": [-1.57, -1.0, 1.5, 0.0, 0.5, 0.0],
    "right": [1.57, -1.0, 1.5, 0.0, 0.5, 0.0],
}