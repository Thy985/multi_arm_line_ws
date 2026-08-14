# Robot Embodiment Migration Assessment v1.0

**Status**: FROZEN v1.0
**Date**: 2026-08-13
**Companion Document**: [robot_data_migration_assessment.md](robot_data_migration_assessment.md)
**Scope**: 评估 Phase 2 迁移（`Fixed Dual UR5e Platform` → `Embodied Robot Platform`）对**机器人物理能力**的影响

---

## 0. 与 Data Migration Assessment 的关系

| 维度 | Data Migration | Embodiment Migration |
|------|----------------|---------------------|
| **回答的问题** | 软件代码迁移成本？ | 机器人能力迁移成本？ |
| **单位** | 源代码行数 / 文件数 | 物理能力损失率 / 重新训练量 |
| **评估对象** | 字符串/接口/字典/测试 fixture | 运动学/工作空间/感知/数据分布 |
| **核心结论** | 抽象层 98% 复用 | 物理层 0% 直接复用 |
| **代价** | 6-8 周返工 | 需重新验证 + 重新采集数据 |

**两者必须结合**才能得出完整 Phase 2 迁移计划：
- Data Migration 解决"代码能不能跑"
- Embodiment Migration 解决"能力是否保留"

---

## 1. 核心结论（TL;DR）

### 1.1 一句话判断

> **物理层（运动学、工作空间、感知）几乎不能直接复用**：
> - 任务语义 100% 复用
> - 物体位置 100% 复用
> - **joint trajectory / IK solution / collision-free path 0% 复用**
> - **Episode 数据 schema 可复用，但数据本身需重新采集**
> - **Sensor 视角变化 → perception pipeline 需重新验证**

### 1.2 能力损失估算

| 能力维度 | Phase 0 性能 | Phase 2 初步估计 | 损失率 | 修复成本 |
|---------|------------|-----------------|--------|----------|
| **单臂 IK 成功率** | 100% (固定 base) | 95-98% (受 shoulder 影响) | 2-5% | 重新标定 |
| **双臂协调 IK** | 100% (对称) | 85-90% (asymmetric) | 10-15% | SRDF 重构 |
| **Workspace 覆盖** | 6.0 m³ | 5.5 m³ (head 占用) | 8% | 重新规划 |
| **Trajectory 复用率** | 100% | 0% (需重新规划) | 100% | 重新生成 |
| **Perception 精度** | 0.038m (M7.5) | 待验证 | TBD | 重新标定 |
| **PickPlace 成功率** | 100% (L1) | 78-85% (初步估计) | 15-22% | 重新调参 |

### 1.3 关键风险

| 风险 | 严重度 | 缓解 |
|------|--------|------|
| shoulder_mount 引入新 collision pair | 高 | 重新生成 collision matrix |
| 双臂 base 不对称（不同 xyz）| 高 | 重新标定双臂相对位姿 |
| 头部 camera 视角变化 | 中 | perception 重标定 |
| workspace 边界变化 | 中 | reachability map 重新生成 |
| Episode 数据分布偏移 | 中 | 增量采集，不丢弃旧数据 |
| Kinematic singularity 改变 | 中 | IK 求解器参数调整 |

---

## 2. Kinematic Migration（运动学迁移）

### 2.1 当前 Phase 0 运动学

```
base_link (固定 0,0,0)
└── arm1_pillar_link (0, 0, 0.3) [static]
    └── ur_base_link_1 (tf_prefix="arm1_")
        └── shoulder_pan_joint     (axis=z,  range=±360°)
        └── shoulder_lift_joint    (axis=y,  range=±180°)
        └── elbow_joint            (axis=y,  range=±180°)
        └── wrist_1_joint          (axis=y,  range=±360°)
        └── wrist_2_joint          (axis=z,  range=±360°)
        └── wrist_3_joint          (axis=y,  range=±360°)
        └── tool0 (arm1)           [6 DOF chain]
            └── gripper_link

双臂对称镜像：
base_link → arm2_pillar_link (1.0, 0, 0.3) → ur_base_link_2 → ... → tool0 (arm2)
```

**关键参数**（UR5e 官方）：
- Reach: 850 mm
- Payload: 5 kg
- Repeatability: ±0.03 mm
- Weight: 18.4 kg
- DOF: 6 (revolute, all joints)
- Joint velocity max: π rad/s ≈ 180°/s
- Joint range: pan=±360°, others=±180°

### 2.2 Phase 2 目标运动学

```
base_link (固定 or 移动底盘)
└── torso_link (0.5, 0, 0.55)  [static or yaw]
    ├── head_link (0.5, 0, 0.85)  [static or pitch]
    │   ├── head_rgb_link (0.53, 0, 0.90)
    │   ├── head_depth_link (0.55, 0, 0.90)
    │   └── head_imu_link (0.5, -0.03, 0.90)
    ├── left_shoulder_mount (0.15, 0.2, 0.55)  [static, mounting interface]
    │   └── ur_base_left
    │       └── ... 6 UR5e joints ...
    │           └── tool0_left
    │               └── left_gripper
    └── right_shoulder_mount (0.85, -0.2, 0.55)  [static, mirror]
        └── ur_base_right
            └── ... 6 UR5e joints ...
                └── tool0_right
                    └── right_gripper
```

**关键变化**：
| 维度 | Phase 0 | Phase 2 | 影响 |
|------|---------|---------|------|
| arm1_base xyz | (0, 0, 0.3) | (0.15, 0.2, 0.55) | **base frame 偏移** |
| arm2_base xyz | (1.0, 0, 0.3) | (0.85, -0.2, 0.55) | **base frame 偏移** |
| arm1→arm2 距离 | 1.0m | 0.78m | **双臂协作空间缩小** |
| 头部存在 | 无 | head_link + 3 sensor links | **新 collision pair** |
| torso 存在 | virtual frame | 实体 link (radius 0.15m, height 0.5m) | **新 collision pair** |
| shoulder_mount 存在 | 无 | 实体 link (0.15×0.15×0.08m) | **新 collision pair** |

### 2.3 IK 求解变化分析

#### 单臂 IK

**当前**（Phase 0）：
- base_frame = base_link
- target pose → KDL IK → joint solution
- IK 成功率：~100% (固定 base, 简化场景)

**Phase 2**：
- base_frame = torso_link (新)
- shoulder_mount 偏移 → target 在 arm base frame 中相对位置变化
- shoulder_mount 高度 0.55m → 目标点 z 抬高
- **预期 IK 成功率**：95-98%（少数 singularity 边界情况）

**关键代码路径**：
```python
# /multi_arm_moveit_config/launch/move_group.launch
# KDL kinematics plugin 默认 base_link
# 需改为 left_shoulder_mount / right_shoulder_mount
```

#### 双臂 IK

**当前**：
- 双臂对称，base frame 都在 (0,0,0.3) 和 (1.0,0,0.3)
- 对称镜像坐标系，collision 简单
- 双手相对位姿容易计算

**Phase 2**：
- 双臂**非对称**：left (0.15, 0.2, 0.55), right (0.85, -0.2, 0.55)
- 左右臂**不再镜像**
- 双手相对位姿需要重新标定
- **预期双手机器人任务成功率**：85-90%

### 2.4 Singularity 变化

**UR5e singularity 类型**（保持不变）：
- Wrist singularity（wrist_1=0）
- Elbow singularity（shoulder_lift=elbow=0）
- Shoulder singularity（pan=0, lift=±90°）

**变化点**：
- shoulder_mount 引入新约束：tool0 不能进入 torso 内部
- head_link 引入：tool0 不能撞头
- **新碰撞对**：shoulder_mount ↔ upperarm, head ↔ upperarm, torso ↔ forearm

**Singularity 边界示例**：
- Phase 0: arm1 伸到正前方 (x=0.85, y=0, z=0.4) 接近 singularity
- Phase 2: 同样位置相对 left_shoulder_mount 偏移，singularity 行为不同

### 2.5 验证矩阵

| 验收项 | 通过条件 | 实施成本 |
|--------|----------|----------|
| 单臂 IK 在新 base frame 求解 | 95%+ 成功率 | 1-2 天 |
| 双臂 IK 在非对称 base frame 求解 | 85%+ 成功率 | 3-5 天 |
| MoveIt 加载新 SRDF | planning group 重组成功 | 0.5 天 |
| MoveIt 规划时间不显著退化 | <2s / 规划请求 | 1 天 |
| Singularity 检测 | 0 误报 0 漏报 | 0.5 天 |
| 新 collision pair 矩阵生成 | 完整无遗漏 | 0.5 天 |

---

## 3. Workspace Migration（工作空间迁移）

### 3.1 Phase 0 工作空间基线

**数据来源**：
- `multi_arm_safety/config/safety_config.yaml`:
  ```yaml
  workspace_bounds: [[-1.5, 1.5], [-1.5, 1.5], [0.0, 1.5]]
  ```
- `multi_arm_safety/multi_arm_safety/safety_supervisor.py`:
  ```python
  WorkspaceBounds(x_min=-1.5, x_max=1.5, y_min=-1.5, y_max=1.5, z_min=0.0, z_max=1.5)
  ```
- UR5e reach: 850mm

**单臂可达空间**（球壳）：
- 内半径：~0.2m（自碰撞）
- 外半径：0.85m
- 体积：(4/3)π(0.85³ - 0.2³) ≈ 2.5 m³

**双臂合并可达空间**（保守估计）：
- 双臂各 2.5 m³，相加 ≈ 5 m³
- 但有重叠区域，unique ≈ 4 m³
- 加上 safety bounds [-1.5, 1.5]³ = 27 m³（实际可达 4 m³）

**关键瓶颈**：
- 桌面任务空间 0.6×0.4×0.3 = 0.072 m³（双侧 = 0.144 m³）
- 占可达空间 ~3.6%
- 实际工作空间 1.0m × 0.8m × 0.4m (双臂共同)

### 3.2 Phase 2 工作空间变化

#### 单臂可达空间变化

| 维度 | Phase 0 | Phase 2 | 变化 |
|------|---------|---------|------|
| arm base xyz | (0, 0, 0.3) | (0.15, 0.2, 0.55) | **中心抬高 0.25m** |
| arm base xyz | (1.0, 0, 0.3) | (0.85, -0.2, 0.55) | **中心抬高 0.25m** |
| 理论可达体积 | 2.5 m³ | 2.5 m³ | 不变（UR5e 自身 reach） |
| 实际可达体积 | 2.4 m³ | 2.3 m³ | **-4% (head 占用)** |
| 桌面工作区 (z<0.4) | 100% | 70% | **-30% (base 抬高)** |
| 头部工作区 (z>0.85) | 0% | 100% | **+100% (新增)** |
| torso 内部 (radius 0.15, z 0.3-0.8) | 0% | 0% (collision) | 保持 |

#### 双臂协作空间变化

**当前**（Phase 0）：
- 双臂水平距离 1.0m
- 双臂共同工作区在中央：~0.4m × 0.8m × 0.4m
- 双手协同任务（搬运箱子）需要双臂夹持区域

**Phase 2**：
- 双臂水平距离 0.78m (left-right 偏移 0.7m + 各自 ±0.2 shoulder)
- 双臂共同工作区在中央：~0.3m × 0.6m × 0.4m
- **双手协同区域缩小 25-30%**

**关键场景验证**：
- 搬运 0.4m 长物体：Phase 0 ✅, Phase 2 临界
- 装配任务（双手插入）：Phase 0 ✅, Phase 2 需调整

#### Reachability Map 对比

**Phase 0 Reachability Map v1**：
- 6.0 m³ 体积（safety bounds 内）
- 双臂各覆盖 50%
- 双手共同覆盖 30%

**Phase 2 Reachability Map v2**（估计）：
- 5.5 m³ 体积
- 双臂各覆盖 50%（不变）
- 双手共同覆盖 22% (缩小)

**Lost area vs New area**：
- Lost: torso 内部 0.04 m³, 桌面下边角 0.3 m³
- New: 头部上方 0.5 m³ (UR5e 够不到, 但视觉可达)
- Net: -0.5 m³ 总有效操作空间

### 3.3 验证矩阵

| 验收项 | 通过条件 | 实施成本 |
|--------|----------|----------|
| 桌面任务 (z<0.4) 成功率 | ≥80% | 2-3 天 |
| 双手搬运 (box 0.4m) | 成功率 ≥70% | 2-3 天 |
| 桌面双侧物体可达 | 100% 覆盖 | 0.5 天 |
| Reachability Map 重生成 | 网格采样 10cm | 1-2 天 |
| Workspace Bounds 重设 | safety_supervisor 调整 | 0.5 天 |

### 3.4 关键风险

| 风险 | 严重度 | 缓解 |
|------|--------|------|
| 桌面下边角丢失 | 中 | 调整 base 位置或加可调节柱 |
| 双手协作空间缩小 25% | 中 | 任务规划时优先单臂 |
| head 占用部分上方 | 低 | 头部工作区用作视觉/扫描 |

---

## 4. Motion Data Migration（运动数据迁移）

### 4.1 数据复用率分类

| 数据类型 | 是否复用 | 原因 |
|---------|---------|------|
| **任务语义** (PickPlace, Assemble) | ✅ 100% | 逻辑层不依赖物理 |
| **物体位置** (Cartesian) | ✅ 100% | 世界坐标系，与 arm 无关 |
| **Grasp target pose** (Cartesian) | ✅ 100% | 物体坐标系，不依赖 arm |
| **Approach vector** | ✅ 100% | 物体坐标系 |
| **Named position** ("home"/"ready") | ✅ 100% | 字符串，间接映射 |
| **Joint trajectory** | ❌ 0% | joint 值与 base frame 强耦合 |
| **IK solution** | ❌ 0% | 同上 |
| **Collision-free path** | ❌ 0% | 新 collision pair，路径失效 |
| **Cartesian trajectory** | ❌ 50% | waypoint 可用，timing 失效 |
| **Execution timing** | ❌ 0% | 加速度和 torque 变化 |
| **Demonstration data** | ⚠️ 30% | 任务层可用，运动层失效 |

### 4.2 Joint Trajectory 详细分析

**当前**（Phase 0）：
```python
# /multi_arm_core/robot_constants.py
PRESET_POSITIONS = {
    "home": [0, -1.57, 1.57, 0, 0, 0],
    "ready": [0, -1.57, 1.2, 0, 1.57, 0],
    ...
}
```

**问题**：
- joint 值**只在 Phase 0 base frame 下有意义**
- Phase 2 base frame 改变后，相同 joint 值 → 不同 tool0 pose
- 例如：Phase 0 "ready" 让 tool0 在 (0.85, 0, 0.7)
- Phase 2 同样 joint → tool0 在 (1.0, 0.2, 0.95) ← **新位置**

**结论**：所有 joint trajectory 必须**重新规划**。

### 4.3 IK Solution 失效

**当前 MoveIt 配置**：
```yaml
# /multi_arm_moveit_config/kinematics.yaml
arm1:
  kinematics_solver: kdl_kinematics_plugin/KDLKinematicsPlugin
  kinematics_solver_search_resolution: 0.005
  kinematics_solver_timeout: 0.05
```

**Phase 2 改动**：
- base_link 改为 left_shoulder_mount / right_shoulder_mount
- timeout 可能需要 0.1s (更复杂)
- search_resolution 可能需要 0.001 (更精确)

**结果**：
- 缓存的 IK solution **全部失效**
- 每次需重新求解
- **首次成功率可能降低 5-10%**（singularity 边界）

### 4.4 Collision-free Path 失效

**当前 collision pair**（已建立）：
- arm1 ↔ table
- arm2 ↔ table
- arm1 ↔ arm2 (双臂协调)

**Phase 2 新增 collision pair**：
- arm1 ↔ torso_link
- arm1 ↔ head_link
- arm1 ↔ head_camera_link
- arm1 ↔ shoulder_mount (left/right)
- arm2 ↔ torso_link
- arm2 ↔ head_link
- arm2 ↔ head_camera_link
- arm2 ↔ shoulder_mount (left/right)
- gripper ↔ torso (新)
- gripper ↔ head (新)

**影响**：
- 原有 path 缓存的 collision-free trajectory **全部失效**
- 新的"avoid torso"和"avoid head"约束加入
- 规划时间可能增加 30-50%

### 4.5 Demonstration Data 影响

**现有 episode**（M6.4 已记录）：
- 总数：~50 episodes（基于已通过测试）
- 包含：joint trajectory, world state snapshot, skill trace

**复用策略**：
- ✅ **保留 episode schema**（Episode + Snapshot + Trace）
- ✅ **保留任务语义**（哪个 skill 被调用）
- ✅ **保留世界状态**（物体位置）
- ❌ **不保留 joint trajectory**（标记为 deprecated）
- ❌ **不保留 execution timing**

**新数据采集**：
- Phase 2 重新采集 50+ episodes
- 与 Phase 0 数据**不可混用**（分布不同）
- 但 episode ID 体系延续（episode_id 是 string）

### 4.6 验证矩阵

| 验收项 | 通过条件 | 实施成本 |
|--------|----------|----------|
| MotionRequest 字段 | 重新规划 10 个 demo 任务 | 2-3 天 |
| IK 重规划 | MoveIt 重新生成 50 个 IK solution | 1 天 |
| Path 重新规划 | OMPL 重生成 20 个 collision-free path | 2-3 天 |
| 新 collision pair 矩阵 | 完整 12+ 对 | 0.5 天 |
| Execution timing 重新标定 | MoveIt execute 重新跑 30 次 | 1-2 天 |

---

## 5. Sensor Migration（传感器迁移）

### 5.1 Phase 0 感知基线

**当前相机**（M7.1 + M7.5）：
- 单 RGB-D camera (head_camera_link)
- 位置：torso 前方 0.06m
- 视角：固定俯视
- 精度（M7.5 验证）：0.038m 位姿误差

**Perception Pipeline**（M7.5/M7.6）：
- ObjectPose.msg 输出 [x, y, z, qx, qy, qz, qw]
- Belief layer 概率融合
- 6 缺陷已修复

### 5.2 Phase 2 感知变化

#### 视角变化

| 维度 | Phase 0 | Phase 2 | 影响 |
|------|---------|---------|------|
| 相机位置 | torso 前面 0.06m | head 前方 0.05m, z=0.90m | **抬高 0.55m** |
| 相机视角 | 固定俯视 ~45° | 固定俯视 ~45° (略不同) | **略变** |
| 视野范围 | 桌面 0.6×0.4m | 桌面 0.5×0.3m (受高度影响) | **-15%** |
| RGB-Depth 基线 | 单一 sensor 0 | 0.02m | **新增** |
| IMU 存在 | 无 | 头部 IMU | **新增** |

#### 遮挡变化

**Phase 0 遮挡**：
- arm1/arm2 偶尔遮挡（双臂协调任务时）
- 自遮挡（arm1 抓物体时挡住 arm2 视野）

**Phase 2 新增遮挡**：
- **head_link 自身遮挡**：当物体在 head 正下方时（少见）
- **torso 遮挡**：当物体在 torso 后面
- **双臂更靠近**：协调任务时遮挡更严重
- **新解决路径**：多视角规划（用 arm 末端 wrist camera，M6.1 预留）

#### 标定变化

**Phase 0 标定**（已通过 M7.5）：
- 相机内参：标准 pinhole model
- 外参：head_camera_link → base_link (固定)
- 精度：0.038m

**Phase 2 需重新标定**：
- 相机内参不变（同一仿真）
- 外参：head_rgb_link → base_link (新)
- 深度基线：head_rgb_optical_frame → head_depth_optical_frame
- **预期精度变化**：误差可能 0.038m → 0.05m（视角变化 + 双臂靠近）

### 5.3 Perception Pipeline 重新验证

**当前 pipeline**（M7.5 已验证）：
```
Camera → OpenCV → Pose → WorldModel → Skill precondition
```

**Phase 2 需验证**：
1. **Gazebo Camera 配置**：sensor block 改为 head_rgb + head_depth 分离
2. **TF 链路**：head_rgb_optical_frame → base_link 完整
3. **相机参数**：1280×720@30Hz, FOV 90°
4. **深度同步**：RGB + Depth 时序对齐
5. **IMU 数据流**：head_imu/data 200Hz
6. **Perception Node 适配**：订阅 `/head/camera/rgb/*` 和 `/depth/*`

**预期工作量**：
- 1-2 周（含 Gazebo sensor 重配 + 标定 + 验证）

### 5.4 验证矩阵

| 验收项 | 通过条件 | 实施成本 |
|--------|----------|----------|
| Gazebo camera spawn | head_rgb + head_depth 各自发布 | 0.5 天 |
| RGB-Depth 同步 | 时差 < 50ms | 0.5 天 |
| IMU 数据流 | 200Hz, 噪声 < 0.01 rad/s | 0.5 天 |
| TF 链路 | 完整 3 sensor frames | 0.5 天 |
| 物体检测精度 | 误差 < 0.05m | 2-3 天 |
| 视角变化测试 | 桌面任务感知 | 2-3 天 |
| 遮挡鲁棒性 | 任务成功率 ≥80% | 2-3 天 |

---

## 6. Data Distribution Shift（数据分布偏移）

### 6.1 Episode 数据复用

**Episode schema**（M6.4 已建立）：
- episode_id, robot_id, start_time, end_time
- initial_world_json (objects, relations)
- execution_steps_json (skill_traces, recovery_records)
- final_world_json
- success, failure_reason

**字段复用**：
- ✅ schema 100% 复用
- ✅ initial_world_json 可复用（物体位置不依赖 arm）
- ✅ execution_steps_json skill 名可复用
- ⚠️ joint trajectory 字段标记为 deprecated
- ❌ execution timing 重新记录

**策略**：
- Phase 0 episodes 标记 `robot_id="dual_ur5e"` 保留作为历史
- Phase 2 episodes 标记 `robot_id="embodied_robot"` 重新采集
- **不删除 Phase 0 数据**，作为对照

### 6.2 数据分布差异

**Phase 0 分布**：
- 工作空间：x∈[0, 1.0], y∈[-0.4, 0.4], z∈[0, 0.4]
- 物体：5-10 个
- 任务：PickPlace (90%), Inspect (10%)
- 成功率：100% (L1 stress test)

**Phase 2 分布**（预期）：
- 工作空间：x∈[0, 1.0], y∈[-0.4, 0.4], z∈[0, 0.4]（不变）
- **视野范围**变化（受 head 影响）
- **关节空间**变化（base 抬高）
- **碰撞模式**变化（torso/head 障碍）

**Distribution Shift 量化**：
- 工作空间分布：偏移 5% (可接受)
- 关节空间分布：偏移 30% (显著)
- 碰撞模式分布：偏移 100% (新维度)

### 6.3 增量采集策略

**不建议**：完全丢弃 Phase 0 数据
**不建议**：仅用 Phase 0 数据训练 Phase 2 模型
**推荐**：双轨数据

```
Phase 0 episodes (历史)
    |
    └── 用于：分析基线性能 / 不变量验证
    |
    └── 标记 robot_id="dual_ur5e"

Phase 2 episodes (新采集)
    |
    └── 用于：训练 / 回归测试
    |
    └── 标记 robot_id="embodied_robot"
```

**采集目标**（Phase 2 启动后）：
- 100+ episodes 覆盖桌面任务
- 50+ episodes 双手协调
- 30+ episodes 失败案例（恢复）
- 20+ episodes 边界情况（singularity / occlusion）

---

## 7. Benchmark Migration（基准测试迁移）

### 7.1 当前 Benchmark 体系（M5.4）

**已建立**：
- benchmark.db (SQLite, M5.4 验证 34 tests)
- 4 scenarios: single_arm / dual_arm / conflict / recovery
- 指标：success_rate, planning_time, execution_time, recovery_count, collision_count, safety_rejections

**Phase 0 性能基线**（M5.6 验证）：
- L1 Random Task 100 次: 100% success
- L1 Gazebo E2E 20 次: 100% success
- L4 多任务: 3 任务全成功
- Planning time: <0.1s
- Execution time: 2-5s

### 7.2 需新增的指标：Embodiment Transfer Score

**问题**：现有 benchmark 指标（success_rate / planning_time）不能完整衡量"具身迁移"质量。

**新增指标**：

#### EmbodiedTransferScore (ETS)

```python
ETS = (
    alpha * (new_success_rate / old_success_rate) * 0.4  # 任务成功率保持
  + beta  * (new_workspace_coverage / old_workspace_coverage) * 0.2  # 工作空间保持
  + gamma * (new_ik_success / old_ik_success) * 0.2  # IK 成功率保持
  + delta * (1 - new_collision_violations / 100) * 0.1  # 碰撞避免
  + epsilon * (new_perception_accuracy / old_perception_accuracy) * 0.1  # 感知精度
)
```

**目标 ETS ≥ 0.85**（即 85% 能力保留）

#### 单项指标

| 指标 | Phase 0 基线 | Phase 2 目标 | ETS 权重 |
|------|-------------|-------------|----------|
| **Task Success Rate** | 100% (L1) | ≥85% | 0.4 |
| **Workspace Coverage** | 100% (基线) | ≥92% | 0.2 |
| **IK Success Rate** | 100% | ≥95% | 0.2 |
| **Collision-free Rate** | 100% | ≥98% | 0.1 |
| **Perception Accuracy** | 0.038m | ≤0.05m | 0.1 |

### 7.3 Phase 2 Benchmark 重新运行

**实施步骤**：
1. **新场景录制**：M5.4 benchmark_recorder 配置改为新 robot_id
2. **基线对比**：跑 100 个 episode，收集所有指标
3. **ETS 计算**：对比 Phase 0 基线
4. **退化分析**：分解各指标损失原因

**关键退化源**：
- IK 失败 → Kinematic 问题
- 碰撞违反 → Collision model 问题
- 感知失败 → Sensor / viewpoint 问题
- 工作空间不足 → Reachability 问题

### 7.4 验证矩阵

| 验收项 | 通过条件 | 实施成本 |
|--------|----------|----------|
| ETS 指标定义 | ETS 计算函数 + 5 子指标 | 1 天 |
| 新场景录制 | robot_id="embodied_robot" | 0.5 天 |
| 100 episodes 采集 | success_rate, planning_time | 1-2 天 |
| 基线对比 | Phase 0 vs Phase 2 | 0.5 天 |
| 退化分析 | 分解到子指标 | 0.5 天 |
| 报告输出 | docs/benchmark/embodiment_transfer_report.md | 0.5 天 |

---

## 8. 完整 Phase 2 迁移工作量

### 8.1 综合 Data + Embodiment 评估

| 类别 | Data Migration | Embodiment Migration | 合计 |
|------|----------------|---------------------|------|
| **URDF 重构** | - | 2-3 周 | 2-3 周 |
| **SRDF + Controller YAML** | 1 周 | - | 1 周 |
| **MoveIt 重新配置** | - | 3-5 天 | 3-5 天 |
| **Collision matrix** | - | 2-3 天 | 2-3 天 |
| **IK 重新标定** | - | 1-2 天 | 1-2 天 |
| **Path 重新规划** | - | 2-3 天 | 2-3 天 |
| **代码返工** | 1 周 | - | 1 周 |
| **测试 fixture** | 3-5 天 | - | 3-5 天 |
| **Gazebo 脚本** | 1-2 天 | - | 1-2 天 |
| **Sensor 重配置** | - | 1-2 周 | 1-2 周 |
| **Perception 重新标定** | - | 2-3 天 | 2-3 天 |
| **Episode 重新采集** | - | 1-2 周 | 1-2 周 |
| **Benchmark 重跑** | - | 1 周 | 1 周 |
| **集成验证 E2E** | - | 1-2 周 | 1-2 周 |
| **合计** | **6-8 周** | **+8-12 周** | **14-20 周** |

### 8.2 关键里程碑

```
M-Phase2-1: URDF 重构（shoulder + head sensor）
   └─ xacro 编译通过 + 52→60+ links + MoveIt 加载

M-Phase2-2: 代码迁移（Data Migration 6-8 周）
   └─ 158+ tests pass + Scenario 100% pass

M-Phase2-3: 运动学重新验证（Embodiment 2-3 周）
   └─ 单臂 IK 95% + 双臂 IK 85% + Workspace 92%

M-Phase2-4: 感知重新验证（Embodiment 1-2 周）
   └─ RGB + Depth + IMU 全部就绪 + 精度 ≤0.05m

M-Phase2-5: Episode 重新采集（Embodiment 1-2 周）
   └─ 200+ episodes + Distribution Shift 接受

M-Phase2-6: Benchmark ETS 验证（Embodiment 1 周）
   └─ ETS ≥ 0.85 + 退化分析报告

M-Phase2-7: 集成验证 E2E（1-2 周）
   └─ L1-L4 stress test + L1 Random 100 次
```

**总周期**：14-20 周（3-5 个月）

### 8.3 阶段性目标

| 阶段 | 时间 | 关键交付 | 验收 |
|------|------|---------|------|
| **Phase 2.1** | 4-6 周 | URDF + 代码迁移 + 158 tests pass | 基础可运行 |
| **Phase 2.2** | 2-3 周 | 运动学重验证 | 单臂/双臂 IK 达标 |
| **Phase 2.3** | 2-3 周 | 感知重验证 | RGB + Depth + IMU |
| **Phase 2.4** | 2-3 周 | Episode 采集 + Benchmark ETS | ETS ≥ 0.85 |
| **Phase 2.5** | 2 周 | E2E + 压力测试 | L1-L4 全通过 |

---

## 9. Phase 2 不需要做的事（基于 Embodiment 分析）

### 9.1 不需要重写

- ❌ Skill Runtime（不依赖物理层）
- ❌ TaskPlanner（接口冻结）
- ❌ WorldModel 五层（参数化）
- ❌ Runtime API（不依赖物理层）
- ❌ Capability Registry（按 capability 名）
- ❌ Recovery Manager（按 failure type 抽象）
- ❌ ResourceManager（按 capability 匹配）

### 9.2 不需要重新设计

- ❌ ObjectPose.msg（坐标系与 arm 无关）
- ❌ TaskGoal.msg（arm_name 是 string）
- ❌ Skill manifest（required_capabilities 是抽象名）
- ❌ Episode schema（robot_id 是 string）
- ❌ Capability 三层（按 capability 名）

### 9.3 不需要返工

- ❌ Cartesian pose 数据（世界坐标系）
- ❌ Named position 字符串（间接映射）
- ❌ Grasp approach vector（物体坐标系）
- ❌ Task 语义（不依赖物理）

### 9.4 不需要重采集（但保留为历史）

- ⚠️ Phase 0 episodes（标记 robot_id="dual_ur5e"，作为基线）
- ⚠️ 旧 SRDF group_state（仅改 key，不改 values）
- ⚠️ 旧 controller YAML（仅改前缀）

---

## 10. 决策建议

### 10.1 立即可做（Phase 1.5）

**Data Migration 已确认的 6 项微改动**（半天搞定）：
1. `robot_id` 默认值改 1 行
2. scenario YAML 改 3-4 行
3. blackboard 默认值改 6 行
4. `skill_motion_bridge.py` 默认值改 1 行
5. WorldModel relation 测试改 3-5 行
6. `robot_constants.py` 字典 key 改 30 处

### 10.2 Phase 2 启动前必做（数据基线采集）

**建议在 Phase 0 完成时立即做**：
1. **录制约 50 个 Phase 0 episodes**（M6.4 已部分完成）
2. **跑 M5.4 Benchmark 100 次**（L1 stress test 已完成）
3. **建立 Phase 0 ETS 基线**（成功/IK/工作空间/感知）
4. **生成 Phase 0 Reachability Map v1**

**原因**：这些是 Phase 2 验证 ETS ≥ 0.85 的对照基准。**没有基线，无法证明能力保留**。

### 10.3 Phase 2 启动建议

**不立即做** Embodiment 重验证的原因：
- 缺乏基线对比
- URDF 重构未完成，验证目标不明确
- 工作量大（8-12 周），需要准备好

**建议启动时机**：
- Phase 1.5 微改动完成（建立惯例）
- Phase 0 ETS 基线建立
- URDF Phase 2 重构启动

### 10.4 长期路线（Phase 2 → Phase 3）

```
Phase 0 (Fixed Dual UR5e)
    ↓ ETS 基线建立
Phase 1.5 (微改动, 1 周)
    ↓ 重命名惯例
Phase 2 (Embodied Robot, 14-20 周)
    ↓ ETS ≥ 0.85 验证
Phase 3 (Mobile Base, M8+)
    ↓ 加移动底盘
Phase 4 (Humanoid, 远期)
```

---

## 11. 冻结声明

本文档 v1.0 冻结以下评估结论：
- ✅ 物理层 0% 直接复用
- ✅ 能力损失估算（IK 2-5%, 双臂 10-15%, Workspace 8%）
- ✅ 5 维度评估（Kinematic/Workspace/Motion/Sensor/Distribution）
- ✅ 新增 ETS 指标
- ✅ Phase 2 完整工作量 14-20 周
- ✅ 不需重做的能力清单
- ✅ 阶段性目标

**与 Data Migration Assessment 合并使用**，共同构成完整 Phase 2 迁移计划。

**禁止破坏性修改**。如需新增评估维度，进入 v1.1 评审。

---

**End of Robot Embodiment Migration Assessment v1.0**