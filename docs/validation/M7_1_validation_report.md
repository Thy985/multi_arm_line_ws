# M7.1 Body Upgrade Validation Report

**Date**: 2026-08-12  
**Phase**: M7.1 — Body Upgrade  
**Status**: ✅ ALL PASS (10/10)

## Overview

M7.1 adds physical torso and head structures to the robot, transforming it from a dual-arm platform into a complete humanoid-upper-body robot with perception attention capability.

```
base_link → torso_link (yaw Z) → head_link (pitch Y) → head_camera (RGB-D)
                                        + torso_imu (IMU)
```

## Acceptance Criteria Results

| # | 验收项 | 通过条件 | 状态 |
|---|--------|----------|------|
| 1 | 躯干 | torso_yaw_joint (revolute Z) | ✅ |
| 2 | 头部 | neck_pitch_joint (revolute Y) | ✅ |
| 3 | 头部RGB-D | head_camera sensor type=rgbd | ✅ |
| 4 | 躯干IMU | torso_imu on torso_link (not head) | ✅ |
| 5 | 控制器拆分 | torso_controller ≠ head_controller | ✅ |
| 6 | ros2_control | 16 joints (12 arm + 2 gripper + 1 torso + 1 head) | ✅ |
| 7 | SRDF torso组 | 独立 planning group | ✅ |
| 8 | SRDF无全身组 | arm1_full 不存在 (count=0) | ✅ |
| 9 | Gazebo启动 | 无错误, joint_states含torso+head | ✅ |
| 10 | 控制器active | torso+head在list中, 状态=active | ✅ |

## Active Controllers (7 total)

```
head_controller                  joint_trajectory_controller/JointTrajectoryController  active
torso_controller                 joint_trajectory_controller/JointTrajectoryController  active
arm1_gripper_controller          position_controllers/GripperActionController           active
arm2_joint_trajectory_controller joint_trajectory_controller/JointTrajectoryController  active
arm2_gripper_controller          position_controllers/GripperActionController           active
arm1_joint_trajectory_controller joint_trajectory_controller/JointTrajectoryController  active
joint_state_broadcaster          joint_state_broadcaster/JointStateBroadcaster          active
```

## Files Modified

| File | Change |
|------|--------|
| `urdf/body/torso.xacro` | Placeholder → torso_link + torso_yaw_joint (revolute Z) |
| `urdf/body/head.xacro` | Placeholder → head_link + neck_pitch_joint (revolute Y) + head_camera (RGB-D) |
| `urdf/sensors/imu.xacro` | Placeholder → torso_imu Gazebo IMU sensor |
| `urdf/robot.xacro` | Head parent: base_link → torso_link; IMU parent: base_link → torso_link |
| `urdf/ros2_control/multi_arm_ros2_control.xacro` | 14 joints → 16 joints (+torso_yaw +neck_pitch) |
| `config/multi_arm_controllers.yaml` | +torso_controller +head_controller |
| `multi_arm_moveit_config/config/multi_arm.srdf` | +torso group +head group +collision exclusions |
| `multi_arm_moveit_config/config/moveit_controllers.yaml` | +torso_controller +head_controller |
| `launch/m6_pick_place_sim.launch.py` | +torso_spawner +head_spawner in event chain |

## Design Decisions

1. **Arms stay on base pillars** — Torso rotates independently; arms don't ride on torso. This is conservative for M7.1; future whole-body control can reparent.
2. **Head on torso_link** — neck_pitch_joint parent is torso_link, enabling head to follow torso rotation.
3. **IMU on torso, not head** — Torso attitude is the body attitude (per design spec).
4. **Controller split** — torso_controller (body control) ≠ head_controller (perception attention), per design: "不合并为一个controller"
5. **No full-body planning group** — No arm1_full or whole_body group; layered execution: torso adjust → arm execute

## Test Results

| Test Class | Tests | Duration | Status |
|------------|-------|----------|--------|
| TestM71UrdfStructure | 4 | 7.5s | ✅ |
| TestM71Controllers | 2 | 3.6s | ✅ |
| TestM71Srdf | 2 | 0.1s | ✅ |
| TestM71GazeboStartup | 2 | 61.2s | ✅ |
| **Total** | **10** | **72.4s** | **✅ ALL PASS** |