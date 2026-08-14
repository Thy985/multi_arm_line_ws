# Dual Arm Embodied Robot — Body Architecture v1.0

**Status**: FROZEN v1.0
**Date**: 2026-08-13
**Author**: Architecture Review
**Supersedes**: 阶段1 mesh 工作（torso_shell/head_shell 占位 mesh 已回退保留，但不再代表身体架构）
**Informs**: URDF evolution (Phase 0 → 3), 传感器布局, 软件 namespace, 视觉语言

---

## 1. 设计哲学（Design Philosophy）

### 1.1 机器人身份

```
工业级双臂移动操作机器人
Industrial Dual-Arm Mobile Manipulator
```

**类比参考**（非完全对齐）：
- **Franka Research Robot** — 共享 torso 基座 + 独立 shoulder mount
- **ABB YuMi** — 工业级双臂协调，简化外观
- **KUKA LWR4+ 双臂研究平台** — 模块化、研究友好

**明确否定方向**：
- ❌ **Humanoid upper body** — 不引入 neck、肩部 2DOF（避免 DOF 爆炸和 IK/标定复杂度）
- ❌ **仿人外观 / 脸 / 皮肤** — 不做
- ❌ **预冻结移动底盘** — base_link 以下由后续 M8 决定

### 1.2 三大原则

#### 原则 1：软件优先（Software-First）
机械结构必须服务：
```
Skill Runtime
WorldModel
Runtime API
```
而**不是**反过来。
→ 任何 URDF/机械结构决策都需先问"软件需要这个 link/joint 吗？"

#### 原则 2：模块化（Module-First）
身体拆成 5 个 ROS namespace：
```
/head
/torso
/left_arm
/right_arm
/base
```
每个模块：
- 独立 xacro 文件
- 独立 namespace
- 独立 capability 集合

#### 原则 3：演进可逆（Phase-Safe）
URDF 演进路径**不破坏**已有 M5.7 FROZEN v1.0 接口、Skill Manifest、WorldModel Schema。
→ Phase 0-3 之间保持向后兼容。

---

## 2. 形态假设（Morphological Assumption）

### 2.1 整体结构

```
                 head_link
                     |
              [ RGB + Depth + IMU ]
                     |
               torso_link          ← 共享基座 / 协调中枢
                     |
        ┌────────────┴────────────┐
        |                         |
  left_shoulder_mount    right_shoulder_mount
        |                         |
   [joint_fixed]            [joint_fixed]
        |                         |
   ur5e_left                 ur5e_right
   (6 DOF)                   (6 DOF)
        |                         |
   left_gripper              right_gripper
                     |
              base_link              ← base_link 以下是 M8 决策
```

### 2.2 关键决策

| 决策 | 结论 | 原因 |
|------|------|------|
| 双臂共享 torso 基座 | ✅ | 双手协作/相对姿态/碰撞规划需要共享参考 |
| 独立 shoulder_mount | ✅ | 装配误差隔离、便于单独标定和替换 |
| 引入肩部 2DOF | ❌ | UR5e 6DOF 已够；引入后 = 9DOF/臂，IK 复杂 |
| 引入 neck 关节 | ❌ | head 固定到 torso，简化视觉系统 |
| 头颈独立基座 | ❌ | 多余自由度，研究阶段不必要 |

### 2.3 DOF 总览

| 部位 | DOF | 备注 |
|------|-----|------|
| base_link | 0 (M8) | 底盘类型 M8 决定 |
| torso | 0 | 静态结构 |
| head | 0 | 固定到 torso |
| left_arm | 6 (UR5e) | + 0 shoulder DOF |
| right_arm | 6 (UR5e) | + 0 shoulder DOF |
| left_gripper | 1 | open/close |
| right_gripper | 1 | open/close |
| **总计** | **14 DOF** | 双手 + 双夹爪 |

**对比 humanoid upper body**：每手 9 DOF × 2 = 18+ DOF
**当前决策节省**：4+ DOF，IK/规划/标定复杂度显著降低

---

## 3. TF Tree v1.0（权威标准）

```
base_link
└── torso_link
    ├── head_link
    │   ├── head_rgb_optical_frame
    │   ├── head_depth_optical_frame
    │   └── head_imu_frame
    ├── left_shoulder_mount
    │   └── ur_base_left        (UR5e base, 复用 UR5e 标准命名)
    │       └── ... 6 joints ...
    │           └── tool0_left  (UR5e 末端)
    │               └── left_gripper_link
    └── right_shoulder_mount
        └── ur_base_right
            └── ... 6 joints ...
                └── tool0_right
                    └── right_gripper_link
```

### 3.1 TF 命名规则

| 层级 | 命名规范 | 示例 |
|------|----------|------|
| 根 | `base_link` | `base_link` |
| 模块 | `<module>_link` | `torso_link`, `head_link` |
| 肩部 mount | `<side>_shoulder_mount` | `left_shoulder_mount` |
| UR5e 子树 | 复用 UR 官方 | `shoulder_pan_left`, `ur_base_left` |
| 工具 | `<module>_tool0` / `<side>_gripper_link` | `tool0_left` |
| 传感器光学 | `<module>_<sensor>_optical_frame` | `head_rgb_optical_frame` |
| 传感器惯性 | `<module>_<sensor>_frame` | `head_imu_frame` |

**侧别命名**：使用 `left_` / `right_`（不是 `arm1_` / `arm2_`）
→ **Phase 2 迁移时统一替换**

---

## 4. ROS 2 Namespace 映射

| 模块 | Namespace | 主要话题/服务 |
|------|-----------|---------------|
| base | `/base` | `/base/cmd_vel`, `/base/odom` (M8) |
| torso | `/torso` | （目前无动态节点，未来诊断/状态） |
| head | `/head` | `/head/camera/rgb/image_raw`, `/head/camera/depth/...`, `/head/imu/data` |
| left_arm | `/left_arm` | 复用现有 `/arm1/*` 接口（**Phase 2 命名替换**） |
| right_arm | `/right_arm` | 复用现有 `/arm2/*` 接口（**Phase 2 命名替换**） |

**关键冻结**：M5.7 FROZEN v1.0 接口（ExecuteTask/SafetyCheck 等）**不依赖**模块名，迁移到新 namespace 时接口不变。

---

## 5. 传感器套件 v1（最小集）

### 5.1 决策：v1 仅 RGB + Depth + IMU

| 传感器 | 位置 | 原因 |
|--------|------|------|
| RGB camera | head_link | 物体识别、WorldModel Entity Layer 基础（M6.1/M7.5） |
| Depth camera | head_link | 6DoF 位姿估计、抓取点云 |
| IMU | head_link | 姿态补偿、视觉 SLAM 前置（M8/Navigation 用） |

**明确不冻结**（留接口）：
- 2D/3D LiDAR → 未来 Navigation
- microphone array → 未来语音接口
- tactile sensor → 未来精细操作（M7.x 后）

### 5.2 head_link 内部结构

```
head_link
├── head_rgb_link          (固定 joint)
│   └── head_rgb_optical_frame  (camera optical frame convention)
├── head_depth_link        (固定 joint, 与 rgb 刚性连接)
│   └── head_depth_optical_frame
└── head_imu_link          (固定 joint)
    └── head_imu_frame
```

**RGB-Depth 基线**：camera optical frame 之间偏移 0.05m（实际相机硬件决定）

### 5.3 与现有 M7.1 关系

- M7.1 Body Upgrade 已建立 head_camera_link
- v1.0 升级为 `head_rgb_link` + `head_depth_link` + `head_imu_link`
- M7.1 验证报告保留（向后兼容），**Phase 2 命名替换**

---

## 6. 外观设计语言（Visual Identity）

### 6.1 风格定位

```
Industrial Research Robot
```

**关键词**：
- 简洁（clean lines）
- 模块化（可见模块边界）
- 可信（industrial-grade 质感）
- 非仿人（no human resemblance）

### 6.2 视觉参考

| 参考 | 借鉴点 |
|------|--------|
| Franka Emika Panda | 白色外壳 + 暴露机械结构 + 模块化 |
| Universal Robots | 工业工具感 + 圆角 |
| ABB IRB 系列 | 工程感 + 显式功能分区 |

### 6.3 色彩与材质 v1

| 模块 | 主色 | 辅助色 | 材质 |
|------|------|--------|------|
| base | 哑光黑 | — | metal_dark |
| torso | 白色 | 灰色接缝 | metal_light |
| shoulder_mount | 灰色 | — | metal_dark |
| head | 白色 | 黑色传感器窗口 | metal_light + glass |
| gripper | 黑色 + 黄色安全标识 | — | rubber + metal |

**禁止**：
- ❌ 皮肤色
- ❌ 卡通色彩
- ❌ 发光装饰（除状态指示 LED）

### 6.4 状态表达（LED + Display）

> 这是与软件最重要的视觉绑定。

| Runtime State | LED Ring (head) | LED Strip (torso) | Head Display |
|---------------|----------------|-------------------|--------------|
| READY | 绿（常亮） | 绿（慢闪） | "READY" |
| RUNNING | 蓝（常亮） | 蓝（流光） | Task ID + 进度 |
| FAILED | 红（常亮） | 红（快闪） | 失败原因（缩写） |
| SAFETY_STOP | 红（闪烁） | 红（闪烁） | "ESTOP" |
| OFFLINE | 灭 | 灭 | "OFFLINE" |

**实施位置**：状态灯 v1.0 已预留 link 结构，**Phase 2 LED** 实施时绑定 RuntimeManager topic。

---

## 7. URDF 演进路径（Phase 0 → 3）

### Phase 0（当前 — M4.6 + M6.x 已完成）

```
base_link (临时)
└── arm1_pillar_link
│   └── ur_base_1
│       └── ... UR5e ...
│           └── tool0_1
└── arm2_pillar_link
    └── ur_base_2
        └── ... UR5e ...
            └── tool0_2
```

- 双臂独立 namespace
- torso 是 virtual frame
- head 是 virtual frame
- 验证：Skill, Runtime, WorldModel

### Phase 1（视觉层 — 立即执行）

```
不变 control
不变 collision
替换 visual mesh
```

- ✅ **已完成**（9 个 STL 占位 visual）
- mesh 命名为 `<module>_shell.stl` 占位
- **Phase 2 shoulder frame 确定后统一替换为正式 visual**

### Phase 2（shoulder + torso 真实化 — 近期）

```
base_link
└── torso_link              (新增实体 link)
    ├── head_link           (新增实体 link + 传感器)
    ├── left_shoulder_mount (新增 link)
    │   └── ur_base_left    (原 arm1_pillar_link 改造)
    └── right_shoulder_mount
        └── ur_base_right
```

**迁移任务**：
- MoveIt SRDF 更新（planning group 重组为 left_arm/right_arm/dual_arm）
- `arm1_*` → `left_*` namespace 替换
- `arm2_*` → `right_*` namespace 替换
- Collision matrix 重新生成
- WorldModel static TF 缓存更新
- 现有 158 tests 重跑验证

### Phase 3（完整机器人 — M8+）

```
base_link                  ← M8 决策
└── ... 底盘 ...
    └── torso_link
        └── (同 Phase 2)
```

- 加 mobile base（具体形态 M8 决定）
- 加电源管理 link（电池）
- 完整外观 mesh

---

## 8. 文档体系（本文档是根）

```
docs/design/
├── robot_body_architecture.md        ← 本文档 v1.0 FROZEN
├── robot_mechanical_concept.md        ← 机械结构详细（Phase 2+）
├── robot_urdf_evolution_plan.md        ← URDF 迁移详细步骤
├── robot_sensor_layout.md              ← 传感器规格和安装
└── robot_visual_identity.md            ← 视觉语言详细规格
```

**冻结顺序**：
1. ✅ `robot_body_architecture.md` (本文档，v1.0 FROZEN)
2. ⏳ `robot_sensor_layout.md` (v1.0 RGB+Depth+IMU 已定)
3. ⏳ `robot_visual_identity.md` (风格和色彩已定，详细待补)
4. ⏳ `robot_urdf_evolution_plan.md` (Phase 1 mesh 回滚，Phase 2 迁移路径)
5. 🔒 `robot_mechanical_concept.md` (Phase 2 启动时写)

---

## 9. 已知偏差与开放问题

### 9.1 已知偏差

1. **当前 `arm1/arm2` 命名** 与 v1.0 `left/right` 不一致
   → **Phase 2 统一替换**，期间文档并行维护
2. **当前 `multi_arm_robot.xacro`** 仍是 Phase 0 结构
   → **Phase 2 重构**为 `dual_arm_robot.xacro` + `left_arm.xacro` + `right_arm.xacro` + `torso.xacro` + `head.xacro` + `base.xacro`
3. **Phase 1 mesh**（已生成的 9 个 STL）是占位 visual
   → Phase 2 重新设计 visual 时可能替换

### 9.2 开放问题（M8 后决定）

- 移动底盘：差速 / 全向 / 腿式？
- 电源管理：电池 + UPS？
- 通信：网线 / WiFi / 5G？
- 安全认证：协作机器人标准 ISO/TS 15066？

---

## 10. 与软件架构的绑定

### 10.1 Capability Registry 三层（重述 M6.0）

| 模块 | Static | Dynamic | Context |
|------|--------|---------|---------|
| /base | wheel_type, payload_max | battery_remaining | path_clear |
| /torso | module_type | temperature | — |
| /head | rgb_max_res, depth_range | camera_overheated, imu_bias | light_level |
| /left_arm | ur5e_dof=6, payload_max=5kg | joint_temp, payload_remaining | can_reach(target) |
| /right_arm | ur5e_dof=6, payload_max=5kg | joint_temp, payload_remaining | can_reach(target) |

### 10.2 Skill 与身体模块的语义对应

| Skill | 涉及的模块 | Capability 依赖 |
|-------|------------|----------------|
| pick_object | left_arm/right_arm + head | can_reach, can_see(object) |
| place_object | left_arm/right_arm + torso | can_reach, zone_available |
| dual_arm_lift | left_arm + right_arm | sync_available, payload_combined |
| navigate | base (M8) | path_clear, battery_remaining |

### 10.3 WorldModel Entity Layer 对应

- **Entity**: robot, base, torso, head, left_arm, right_arm, left_gripper, right_gripper
- **State**: joint_state (UR5e), sensor_state (camera/imu), module_state (temperature, battery)
- **Relation**: `head_rgb mounted_on head`, `tool0_left attached_to left_gripper`

---

## 11. 冻结声明

本文档（v1.0）冻结以下内容：
- ✅ 工业级双臂站台式形态
- ✅ 共享 torso + 独立 shoulder mount
- ✅ 14 DOF（双臂 + 双夹爪）
- ✅ TF tree 命名规范
- ✅ 5 个模块 namespace
- ✅ 传感器 v1 = RGB + Depth + IMU
- ✅ 视觉风格 = Industrial Research Robot
- ✅ LED/Display 与 Runtime State 绑定规范
- ✅ URDF 演进 Phase 0→3 路径

**禁止破坏性修改**。如需变更，需进入 v1.1 评审流程。

---

**End of Robot Body Architecture v1.0**