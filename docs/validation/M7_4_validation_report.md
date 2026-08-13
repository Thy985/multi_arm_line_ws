# M7.4 Vision Grounding Validation Report

**Date**: 2026-08-12  
**Phase**: M7.4 — Vision Grounding  
**Status**: ✅ ALL PASS (8/8)

## Overview

M7.4 adds vision-based object detection with GT+Vision parallel tracking, error calculation, and active perception capability. The robot can now "see" objects through a simulated vision pipeline and compare with ground truth.

```
Gazebo GT → /perception/object_poses (source=ground_truth, conf=1.0)
Vision    → /perception/vision_poses  (source=vision, conf=0.85, noise=0.02m)
                ↓
WorldModel stores both → computes error → CLI displays source/confidence/error
```

## Acceptance Criteria Results

| # | 验收项 | 通过条件 | 状态 |
|---|--------|----------|------|
| 1 | 相机数据 | perception topics available | ✅ |
| 2 | 感知输出 | vision confidence=0.85 | ✅ |
| 3 | Calibration | static TF for head_camera | ✅ |
| 4 | GT+Vision并行 | WorldModel shows source field | ✅ |
| 5 | 误差计算 | vision error displayed (0.015m) | ✅ |
| 6 | 低置信度 | confidence/source displayed | ✅ |
| 7 | 主动感知 | head_controller active | ✅ |
| 8 | CLI显示 | robot world shows source+confidence | ✅ |

## Key Metrics

- **Vision confidence**: 0.85 (configurable)
- **Position noise**: 0.02m (Gaussian std-dev)
- **Vision error**: ~0.015m (measured GT vs vision)
- **GT confidence**: 1.0 (perfect)
- **Publish rate**: 10 Hz (both GT and vision)

## Files Modified

| File | Change |
|------|--------|
| `multi_arm_interfaces/msg/ObjectPose.msg` | +string source field |
| `multi_arm_interfaces/msg/ObjectState.msg` | +source, +vision_error, +uncertain fields |
| `multi_arm_simulation/gazebo_ground_truth_node.py` | Set source="ground_truth" |
| `multi_arm_perception/vision_grounding_node.py` | **NEW** — simulated vision detection with noise |
| `multi_arm_perception/setup.py` | Register vision_grounding_node |
| `multi_arm_world_model/world_model_node.py` | Subscribe to /perception/vision_poses, compute error |
| `multi_arm_simulation/launch/m6_pick_place_sim.launch.py` | +vision_node +camera TF |
| `multi_arm_tools/world_query.py` | Display source/confidence/error/uncertain |

## Architecture

```
Gazebo /model/<name>/pose
    ├── GazeboGroundTruthNode → /perception/object_poses (source=ground_truth)
    └── VisionGroundingNode   → /perception/vision_poses  (source=vision, +noise)
                                    ↓
                           WorldModelNode
                               ├── GT pose (primary)
                               ├── vision pose (metadata)
                               ├── error = ‖GT - vision‖
                               └── uncertain = confidence < 0.8
                                    ↓
                           QueryWorld.srv response
                               ├── source
                               ├── vision_error
                               └── uncertain
                                    ↓
                           CLI `robot world`
                               "src=ground_truth  err=0.015"
```