# Robot Sensor Layout v1.0

**Status**: FROZEN v1.0
**Date**: 2026-08-13
**Parent Document**: [robot_body_architecture.md](robot_body_architecture.md)
**Scope**: v1 传感器套件 = RGB + Depth + IMU（最小集）

---

## 1. 设计原则

### 1.1 v1 决策

```
v1 = RGB + Depth + IMU
```

**只选视觉感知闭环所需的最小集**：
- RGB → 物体识别（WorldModel Entity Layer）
- Depth → 6DoF 位姿估计（WorldModel State Layer）
- IMU → 姿态补偿、未来 SLAM 预备

**不冻结**（仅留接口）：
- 2D/3D LiDAR → M8 Navigation 用
- microphone array → 未来语音接口
- tactile sensor → M7.x+ 精细操作

### 1.2 决策原因

| 候选 | 选/不选 | 原因 |
|------|---------|------|
| RGB camera | ✅ | 物体识别基础 |
| Depth camera | ✅ | 6DoF 抓取基础 |
| IMU | ✅ | 姿态补偿 / 头部位姿稳定 |
| 2D LiDAR | ❌ v1 | Navigation 不是当前重点 |
| 3D LiDAR | ❌ v1 | 成本高，与 RGB-Depth 功能重叠 |
| microphone | ❌ v1 | 语音接口属 M7.x Agent 层 |
| tactile × 2 | ❌ v1 | 精细操作属 M7.x+ |
| force/torque（wrist） | ❌ v1 | UR5e 已内置，但不是 body 传感器 |

---

## 2. 物理布局

### 2.1 head_link 安装矩阵

```
        +Z (up)
         |
         | head_imu_link
         |  +-- head_imu_frame  (0, 0, +0.05)  from head_link
         |
         | head_link
         |  +-- head_rgb_link    (0, 0, +0.05)  from head_link, depth aligned
         |  |    +-- head_rgb_optical_frame (0, 0, 0)  ROS convention
         |  +-- head_depth_link (0, 0, +0.05)
         |       +-- head_depth_optical_frame
         |
        +X (forward)
```

### 2.2 传感器坐标系定义

| 传感器 | Optical Frame | Frame Convention |
|--------|---------------|------------------|
| RGB | head_rgb_optical_frame | +X right, +Y down, +Z forward (ROS REP-103/104) |
| Depth | head_depth_optical_frame | 同上 |
| IMU | head_imu_frame | +X forward, +Y left, +Z up (REP-145) |

### 2.3 安装位置（URDF origin）

以 `head_link` 为父：

| 子 link | xyz | rpy | 备注 |
|--------|-----|-----|------|
| head_rgb_link | 0.03 0 +0.05 | 0 0 0 | 头部前方 3cm |
| head_depth_link | 0.05 0 +0.05 | 0 0 0 | 头部前方 5cm，RGB-Depth 基线 2cm |
| head_imu_link | 0 -0.03 +0.05 | 0 0 0 | 头部后方，靠近几何中心 |

**RGB-Depth 基线**：0.02m（与 RealSense D435 一致）

---

## 3. 传感器规格

### 3.1 RGB Camera

| 参数 | 值 | 备注 |
|------|-----|------|
| 类型 | Pinhole | Gazebo sensor type=`camera` |
| 水平 FOV | 1.5708 rad (90°) | |
| 垂直 FOV | 0.7854 rad (45°) | 由 horizontal_fov + aspect 推算 |
| 分辨率 | 1280×720 | |
| 帧率 | 30 Hz | |
| 近裁剪 | 0.1 m | |
| 远裁剪 | 20.0 m | |
| 话题 | `/head/camera/rgb/image_raw` | |
| info 话题 | `/head/camera/rgb/camera_info` | |

### 3.2 Depth Camera

| 参数 | 值 | 备注 |
|------|-----|------|
| 类型 | Depth (Gazebo) | sensor type=`depth_camera` 或 `rgbd` |
| 水平 FOV | 1.5708 rad (90°) | |
| 分辨率 | 1280×720 | |
| 帧率 | 30 Hz | |
| 近裁剪 | 0.1 m | |
| 远裁剪 | 20.0 m | |
| 话题 | `/head/camera/depth/image_raw` | |
| 点云话题 | `/head/camera/depth/points` | |

**Gazebo 实现选择**：sensor type=`rgbd`（同时输出 RGB + Depth，节省 2 个 sensor block）

### 3.3 IMU

| 参数 | 值 | 备注 |
|------|-----|------|
| 类型 | IMU (3-axis accel + 3-axis gyro) | Gazebo sensor type=`imu` |
| 更新频率 | 200 Hz | 远高于控制频率，用于高频反馈 |
| 加速度量程 | ±16 g | |
| 角速度量程 | ±2000 deg/s | |
| 噪声模型 | gaussian (default) | 可后续切换为更精细模型 |
| 话题 | `/head/imu/data` | sensor_msgs/Imu |
| 坐标系 | head_imu_frame | |

---

## 4. ROS 2 Topic / TF 映射

### 4.1 发布的话题

| Topic | Type | Rate | 发布者 |
|-------|------|------|--------|
| `/head/camera/rgb/image_raw` | sensor_msgs/Image | 30 Hz | Gazebo camera plugin |
| `/head/camera/rgb/camera_info` | sensor_msgs/CameraInfo | 30 Hz | Gazebo |
| `/head/camera/depth/image_raw` | sensor_msgs/Image | 30 Hz | Gazebo |
| `/head/camera/depth/points` | sensor_msgs/PointCloud2 | 30 Hz | Gazebo depth |
| `/head/imu/data` | sensor_msgs/Imu | 200 Hz | Gazebo imu |

### 4.2 TF 发布

- `head_rgb_optical_frame` → 由 `robot_state_publisher` 自动发布（URDF joint）
- `head_depth_optical_frame` → 同上
- `head_imu_frame` → 同上
- 静态 TF 关系：head_rgb_optical_frame → head_depth_optical_frame (translation 0.02m X)
- 静态 TF 关系：head_imu_frame → head_link (translation -0.03m Y)

### 4.3 命名空间冻结

```
/head/camera/rgb/*         — RGB image + info
/head/camera/depth/*       — Depth image + points
/head/imu/*                — IMU data
```

**重要**：不混入 `/left_arm/` 或 `/right_arm/`——头/臂解耦清晰。

---

## 5. 与 WorldModel / Skill 的关系

### 5.1 WorldModel Entity Layer

```
Entity head:
  type: sensor_module
  modules: [rgb, depth, imu]
  state: { rgb_overheated: false, depth_active: true, imu_bias: [...] }
  capabilities:
    - can_see(object_pose)
    - can_observe_scene()
    - can_self_localize (with IMU)
```

### 5.2 Skill precondition 查询

```
Skill pick_object precondition:
  head.can_see(target_object) == True
  → 查询 head_rgb 是否在视野内
  → 依赖 RGB image + WorldModel Entity Layer
```

### 5.3 Capability Registry（M6.0）

```
/head capability:
  Static:
    rgb_max_resolution: "1280x720"
    depth_range: [0.1, 20.0]
    imu_rate: 200
  Dynamic:
    rgb_active: true
    depth_active: true
    imu_calibrated: true
  Context:
    can_observe(target_in_fov)
    can_localize(target_with_visual_features)
```

---

## 6. 与 M7.1 现有结构的关系

### 6.1 M7.1 已建立（不破坏）

```
head_link
  + head_camera_link (含 RGB-D sensor)
```

### 6.2 v1.0 升级（Phase 2 实施）

```
head_link
  + head_rgb_link        (新增)
  |   + head_rgb_optical_frame
  + head_depth_link      (新增)
  |   + head_depth_optical_frame
  + head_imu_link        (新增)
      + head_imu_frame
```

**M7.1 head_camera_link** 在 Phase 2 标记为 deprecated，迁移到 head_rgb_link + head_depth_link。**M7.1 验证报告保留**作为历史。

---

## 7. 不在 v1 范围但预留接口

### 7.1 物理安装位（URDF 留 link，无 sensor）

| Link 名 | 位置 | 用途 |
|---------|------|------|
| lidar_2d_mount | torso_link +Y 0.3 | 2D LiDAR 备用位（M8） |
| lidar_3d_mount | head_link 顶部 | 3D LiDAR 备用位 |
| mic_array_mount | head_link 周围 | microphone array 备用位 |
| left_wrist_ft_link | tool0_left | 力矩传感器（M7.x） |
| right_wrist_ft_link | tool0_right | 力矩传感器（M7.x） |

**实施原则**：v1 不加这些 link，仅在 body_architecture v1.x 升级时考虑加。

### 7.2 Service 接口（M5.7 冻结，无破坏）

所有 v1 传感器数据通过 `sensor_msgs` 标准消息发布，**不增加 ROS 接口**：
- ✅ 复用 `sensor_msgs/Image`
- ✅ 复用 `sensor_msgs/Imu`
- ✅ 复用 `sensor_msgs/PointCloud2`
- ✅ 复用 `sensor_msgs/CameraInfo`

**WorldModel 已有订阅**（M6.1）：
- `/perception/object_poses` topic（publisher 由 v1 实现）

---

## 8. 验证矩阵

| 验收项 | 通过条件 |
|--------|----------|
| head_rgb_link | URDF 存在，TF 链路正确 |
| head_depth_link | URDF 存在，TF 链路正确 |
| head_imu_link | URDF 存在，TF 链路正确 |
| RGB topic | `/head/camera/rgb/image_raw` 30Hz 发布 |
| Depth topic | `/head/camera/depth/image_raw` 30Hz 发布 |
| IMU topic | `/head/imu/data` 200Hz 发布 |
| TF 一致性 | `ros2 run tf2_tools view_frames` 显示完整 head→optical 链 |
| M7.1 向后兼容 | M7.1 验证报告仍可重跑 |

---

## 9. 冻结声明

本文档 v1.0 冻结以下内容：
- ✅ v1 传感器 = RGB + Depth + IMU
- ✅ 物理位置：head_link
- ✅ Topic 命名：`/head/camera/*` + `/head/imu/*`
- ✅ 坐标系：head_rgb_optical_frame / head_depth_optical_frame / head_imu_frame
- ✅ 规格：1280×720@30Hz / 200Hz IMU
- ✅ 与 WorldModel/Skill/Capability 的绑定关系

**禁止破坏性修改**。如需新增传感器，进入 v1.1 评审。

---

**End of Robot Sensor Layout v1.0**