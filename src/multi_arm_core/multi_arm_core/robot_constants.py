"""Shared constants for multi-arm robot configuration.

Extracted from coordinator_node.py to avoid circular imports.
"""

ARM_JOINT_NAMES = {
    "left_arm": [
        "left_arm_shoulder_pan_joint",
        "left_arm_shoulder_lift_joint",
        "left_arm_elbow_joint",
        "left_arm_wrist_1_joint",
        "left_arm_wrist_2_joint",
        "left_arm_wrist_3_joint",
    ],
    "right_arm": [
        "right_arm_shoulder_pan_joint",
        "right_arm_shoulder_lift_joint",
        "right_arm_elbow_joint",
        "right_arm_wrist_1_joint",
        "right_arm_wrist_2_joint",
        "right_arm_wrist_3_joint",
    ],
}

PRESET_POSITIONS = {
    "home": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    "ready": [0.0, -1.57, 1.57, 0.0, 0.0, 0.0],
    "extended": [0.0, -0.5, 2.5, 0.5, 0.5, 0.0],
    "left": [-1.57, -1.0, 1.5, 0.0, 0.5, 0.0],
    "right": [1.57, -1.0, 1.5, 0.0, 0.5, 0.0],
    "scan": [0.0, -1.2, 1.8, -0.5, 0.0, 0.0],
    "inspect": [0.0, -1.0, 1.5, -0.3, 0.3, 0.0],
    "place_high": [0.0, -1.5, 1.5, -0.3, 0.0, 0.0],
    "place_low": [0.0, -0.8, 1.0, -0.5, 0.0, 0.0],
}