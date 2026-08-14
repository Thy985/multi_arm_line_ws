# Robot Data Migration Assessment v1.0

**Status**: FROZEN v1.0
**Date**: 2026-08-13
**Parent Document**: [robot_body_architecture.md](robot_body_architecture.md) / [robot_urdf_evolution_plan.md](robot_urdf_evolution_plan.md)
**Scope**: 评估 Phase 2 迁移（`Fixed Dual UR5e Platform` → `Embodied Robot Platform`）对现有数据/代码资产的影响

---

## 1. 核心结论（TL;DR）

### 1.1 一句话判断

> **抽象层（Skill/Task/Episode/Capability/WorldModel 五层）几乎零返工**；
> **joint-level 边界层（URDF / controller config / joint 名字典 / Pose 物理量）需要中等规模返工**；
> **Cartesian pose 和 named position 字符串完全不需返工**。

### 1.2 返工规模量化

| 抽象层级 | 已有资产 | 返工项 | 复用率 | 关键工作 |
|---------|---------|--------|--------|---------|
| **joint 角度数据** | 30 处 | 30 处 | **0%** | 重生成字典 + SRDF + YAML + 22 个测试 fixture |
| **Cartesian pose** | 50+ 处 | 0 处 | **100%** | 无需返工 |
| **named position 字符串** | 20+ 处 | 0 处 | **100%** | 仅 PRESET 字典间接映射 |
| **Skill Manifest** | 8 skill × 3 文件 | 0 处 | **100%** | 无需返工 |
| **Task Goal Schema** | M5.7 FROZEN | 0 处破坏 | **100%** | 仅改 blackboard 默认值 6 行 |
| **Episode Data** | 4 文件 + SQLite | 0 处 | **100%** | 无需返工 |
| **Capability Registry** | YAML + Python | 0 处 | **100%** | 无需返工 |
| **WorldModel 五层** | 5 文件 | 0 处破坏 | **~95%** | 仅 Relation 层 gripper string 重命名 |
| **Runtime API** | 7 接口 | 0 处 | **100%** | 无需返工 |
| **URDF/Xacro** | 6 文件 | 6 文件 | **0%** | Phase 2 shoulder frame 重构 |
| **Controller YAML** | 8 文件 | 8 文件 | **0%** | prefix 替换 arm1→left_arm |
| **测试 fixture (joint 部分)** | 22 文件 | 22 文件 | **0%** | 改 arm 名/joint 名/数组长度 |
| **测试 fixture (Cartesian 部分)** | 18 文件 | 0 文件 | **100%** | 无需返工 |

**整体复用率**：
- 抽象层（Skill/Task/Episode/Capability/WorldModel/Runtime API）：**~98% 复用**
- 边界层（joint / controller / URDF）：**~0% 复用**
- 物理量（pose / 物体坐标）：**100% 复用**

### 1.3 关键风险

| 风险 | 严重度 | 缓解 |
|------|--------|------|
| `PRESET_POSITIONS` 字典顺序耦合 | 高 | 改为 named-dict-of-dict，重构 robot_constants |
| `coordinator_node.py` 6+ 处 controller topic 拼接 | 高 | 抽象为 helper 函数 |
| 测试 fixture arm1 字面量 22 文件 | 中 | 集中改 1-2 天工作量 |
| MotionRequest/SafetyCheck 平铺 joint 数组 | 中 | 6→7 DOF 扩展需 schema 调整 |
| dual_arm.srdf 用 left_/right_（与 arm1_/arm2_ 冲突） | 低 | 统一命名后废弃 |
| safety_config.yaml joint 名缺前缀 | 低 | 同步修正 |

---

## 2. 迁移架构

### 2.1 三层架构

```
┌─────────────────────────────────────────────────┐
│   抽象层 (98% 复用)                              │
│   Skill / Task / Episode / Capability /        │
│   WorldModel / Runtime API                     │
└─────────────────────────────────────────────────┘
                    ↓ 字符串协议 (arm_name: string)
┌─────────────────────────────────────────────────┐
│   Robot Abstraction Layer (新增)               │
│   - arm_name → controller/joint/topic 映射     │
│   - arm_name → MoveIt group 映射               │
│   - arm_name → URDF link/joint 映射            │
└─────────────────────────────────────────────────┘
                    ↓ 物理接口 (joint_names[], topics)
┌─────────────────────────────────────────────────┐
│   物理层 (0% 复用, 全部重生成)                   │
│   URDF / SRDF / Controller YAML /              │
│   Joint Name Dictionary / Preset Positions     │
└─────────────────────────────────────────────────┘
```

### 2.2 核心洞察：现有架构已支持抽象

**为什么抽象层 98% 复用？** 因为 M5/M6/M7 的设计**已经按"逻辑命名"和"物理命名"分离**：

| 层 | 命名 | 依赖 |
|---|------|------|
| 业务逻辑 | `arm_name: string` | 任意 string |
| Skill | `required_capabilities: List[str]` | capability 名 |
| Task | `TaskGoal.arm_name` | 字符串透传 |
| Episode | `robot_id: string` | 字符串 |
| WorldModel | `_arm_names: List[str]` 参数化 | 配置驱动 |
| Capability | `CapabilityInfo.name` | capability 名 |

**Phase 2 迁移的本质**：**改物理层 URDF 链接结构 + 改 arm_name 字符串值**，不动抽象层任何业务逻辑。

---

## 3. 必须返工的边界层（详细清单）

### 3.1 joint 名字典（核心单一事实源）

#### 文件：`multi_arm_core/robot_constants.py`

**当前结构**：
```python
ARM_JOINT_NAMES = {
    "arm1": ["arm1_shoulder_pan_joint", "arm1_shoulder_lift_joint", ...],
    "arm2": ["arm2_shoulder_pan_joint", ...],
}
PRESET_POSITIONS = {
    "home": [0, -1.57, 1.57, 0, 0, 0],
    "ready": [0, -1.57, 1.2, 0, 1.57, 0],
    ...
}
```

**Phase 2 目标**：
```python
ARM_JOINT_NAMES = {
    "left_arm": ["left_shoulder_pan_joint", "left_shoulder_lift_joint", ...],
    "right_arm": ["right_shoulder_pan_joint", ...],
}
# PRESET_POSITIONS 不变（数值不变, 顺序不变）
```

**返工类型**：**仅改 key 名**（arm1 → left_arm, arm2 → right_arm），values 可保持原值。
**关键风险**：如果 Phase 2 改了 joint 顺序（shoulder pan/lift/elbow/wrist1/2/3），values 也要重标定。
**建议**：先做命名替换，不改 joint 语义；joint 标定放 Phase 2.5。

#### 评估：**中等返工（1-2 文件，重命名 + 验证）**

---

### 3.2 controller topic 拼接

#### 文件：`multi_arm_core/coordinator_node.py`

**当前**：
```python
# L105
action_topic=f"/{arm_name}_joint_trajectory_controller/follow_joint_trajectory"
# L247
joint_names = ARM_JOINT_NAMES.get(arm_name, [])
```

**问题**：`arm_name` 直接拼到 topic，迁移后 `left_arm_joint_trajectory_controller` 是新 controller 名。
**返工类型**：随 ARM_JOINT_NAMES 字典改 key 即可（**0 代码改动，仅配置驱动**）。

#### 评估：**零返工（间接通过 robot_constants）**

---

### 3.3 WorldModel joint_states 订阅

#### 文件：`multi_arm_world_model/world_model_node.py`

**当前**：
```python
# L91-98
self._joint_state_subs[arm_name] = self.create_subscription(
    JointState, f"/{arm_name}/joint_states", ...
)
```

**Phase 2 目标**：
```python
# arm_name="left_arm" → 订阅 /left_arm/joint_states
# arm_name="right_arm" → 订阅 /right_arm/joint_states
```

**返工类型**：随 arm_name 配置改 string 值，代码逻辑不变。

#### 评估：**零返工（参数化）**

---

### 3.4 URDF xacro（Phase 2 主要工作量）

#### 文件清单
| 文件 | Phase 2 改动 |
|------|-------------|
| `ur_simulation_gz/urdf/ros2_control/multi_arm_ros2_control.xacro` | arm1/arm2 prefix → left_arm/right_arm prefix |
| `ur_simulation_gz/urdf/arms/dual_ur5e.xacro` | `tf_prefix="arm1_"` → `tf_prefix="left_arm_"` |
| `ur_simulation_gz/urdf/robot.xacro` | `prefix="arm1_"` → `prefix="left_arm_"` |
| `ur_simulation_gz/urdf/end_effectors/robotiq_2f_85.xacro` | `{prefix}` 透传 + 修改调用 |
| `ur_simulation_gz/urdf/dual_arm_robot.xacro` | 废弃（与 left_/right_ 命名重复）|
| `ur_simulation_gz/urdf/mobile_base/wheeled_base.xacro` | arm1_pillar/arm2_pillar → 重新设计为 shoulder_mount |

**新增 URDF 文件**：
| 文件 | 用途 |
|------|------|
| `ur_simulation_gz/urdf/head/head.xacro` | 升级 head_link + head_rgb + head_depth + head_imu |
| `ur_simulation_gz/urdf/torso/torso.xacro` | 升级 torso_link（已存在，重构） |
| `ur_simulation_gz/urdf/shoulder/left_shoulder.xacro` | 新增 left_shoulder_mount |
| `ur_simulation_gz/urdf/shoulder/right_shoulder.xacro` | 新增 right_shoulder_mount |

**返工类型**：**结构性重构**（不只是重命名，要加 shoulder frame、head sensor suite、torso 实体化）。

#### 评估：**高工作量（2-3 周），但不破坏已积累能力**

---

### 3.5 SRDF predefined group_state

#### 文件：`multi_arm_moveit_config/config/multi_arm.srdf`

**当前 12 个 group_state**：
```xml
<group_state name="home" group="arm1">
  <joint name="arm1_shoulder_pan_joint" value="0"/>
  <joint name="arm1_shoulder_lift_joint" value="-1.57"/>
  ...
</group_state>
```

**Phase 2 目标**：
```xml
<group_state name="home" group="left_arm">
  <joint name="left_shoulder_pan_joint" value="0"/>
  ...
</group_state>
```

**返工类型**：**仅改 group 名 + joint 名**，values 复用（如果不改 joint 顺序）。

**遗留文件清理**：
- `single_arm.srdf`（用 arm1）→ 废弃
- `dual_arm.srdf`（用 left_/right_）→ 合并到 multi_arm.srdf

#### 评估：**中等返工（1 文件 12 处重命名 + 2 文件废弃）**

---

### 3.6 Controller YAML

#### 文件清单（8 个）
| 文件 | Phase 2 改动 |
|------|-------------|
| `multi_arm_moveit_config/config/initial_positions.yaml` | 启动 joint 字典 key 改 |
| `multi_arm_moveit_config/config/joint_limits.yaml` | 14 joint 名前缀改 |
| `multi_arm_moveit_config/config/moveit_controllers.yaml` | 6 controller 名改 |
| `ur_simulation_gz/config/multi_arm_controllers.yaml` | ros2_control joints + controllers |
| `ur_simulation_gz/config/arm1_controllers.yaml` | 改 left_arm_controllers.yaml |
| `ur_simulation_gz/config/arm2_controllers.yaml` | 改 right_arm_controllers.yaml |
| `ur_simulation_gz/config/joint_limits_custom.yaml` | 上游 UR5e 固定，**无需改** |
| `multi_arm_safety/config/safety_config.yaml` | arm1/arm2 + joint 名修正（缺前缀 bug 一起修）|

**返工类型**：**机械重命名**（arm1 → left_arm, arm2 → right_arm）。

#### 评估：**高工作量（8 文件 × 5-20 处/文件 = 100+ 行）**

---

### 3.7 测试 fixture（joint 部分）

#### 文件清单（22 个）
- `multi_arm_core/test/test_e2e_integration.py` (2 处)
- `multi_arm_core/test/test_task_goal.py` (1 处)
- `multi_arm_safety/test/test_collision_monitor.py` (5 处)
- `multi_arm_safety/test/test_workspace_limiter.py` (1 处)
- `multi_arm_simulation/test/test_dataset_pipeline.py` (1 处)
- `multi_arm_moveit_config/scripts/m4_*_test.py` (5 文件 × 5 处)
- `multi_arm_simulation/scripts/m6_*_e2e.py` (4 文件 × 3-5 处)
- `multi_arm_robot_description/test/test_robot_description_generator.py` (1 处)
- `order_manager/test/*.py` (2 文件，遗留包)

**返工类型**：**机械替换**（arm1 → left_arm, joint 名替换）。

**特殊风险**：
- `m6_pick_place_sim_e2e.py` 等 Gazebo 脚本有 `arm_name="arm1"` 字面量
- `test_collision_monitor.py` 有 mock joint 数据

#### 评估：**高工作量（22 文件 × 3-5 处 = 80+ 行），但模式统一**

---

## 4. 无需返工的资产（详细清单）

### 4.1 Cartesian Pose 数据（100% 复用）

**为什么无需返工？** 所有 Cartesian pose 都是基于**世界坐标系**或**物体坐标系**，不依赖 arm 名或 link 名。

#### 已盘点文件（约 50+ 处）
- `multi_arm_manipulation/grasp_planner.py` 的 `GraspPose` dataclass
- `multi_arm_manipulation/test/test_grasp_planner.py` 的 mock
- `multi_arm_skill_runtime/test/test_m6_full_chain_e2e.py` 的 grasp_pose
- 所有场景 YAML（warehouse/lab/tabletop/home）的物体 position
- 所有 `multi_arm_experience/test/*.py` 的 mock position
- 所有 `multi_arm_world_model/test/*.py` 的 mock position
- 所有 `multi_arm_perception/test/*.py` 的 pose mock
- 所有 `multi_arm_tools/test/*.py` 的 episode position

#### 关键示例
```python
# 迁移前
grasp_pose = [0.5, 0, 0.05]
plan_grasp(target_position=[0.5, 0, 0.05])

# 迁移后（完全不变）
grasp_pose = [0.5, 0, 0.05]
plan_grasp(target_position=[0.5, 0, 0.05])
```

**理由**：物体在世界中，grasp 是物体坐标系下的操作，arm 改变不改变这个。

---

### 4.2 Named Position 字符串（100% 复用）

**所有 named position 都是字符串**：`"home"` / `"ready"` / `"scan"` / `"place_high"` / `"inspect"` / `"place_low"`

**间接映射通过**：
- `multi_arm_core/robot_constants.py` 的 `PRESET_POSITIONS` 字典
- `multi_arm_moveit_config/config/multi_arm.srdf` 的 `<group_state name=...>`

**Phase 2 迁移后**：
- named string 不变
- 字典和 SRDF 内部 key 改（arm1→left_arm），但 named 字符串透传层不变

---

### 4.3 Skill Manifest / Lifecycle / Registry（100% 复用）

#### 文件清单
- `multi_arm_skill_runtime/skill_manifest.py`
- `multi_arm_skill_runtime/skill_registry.py`
- `multi_arm_skill_runtime/skill_lifecycle.py`
- `multi_arm_skill_runtime/skill_runtime.py`
- `multi_arm_skill_runtime/config/skills/*.yaml`

**为什么无需返工？**
- Skill manifest 用 `required_capabilities: List[str]`（capability 名，不是 joint 名）
- precondition/postcondition 表达式查询 WorldModel Relation
- Lifecycle 状态机是 callable 注入

**唯一硬编码**（1 行）：
```python
# multi_arm_skill_runtime/skill_motion_bridge.py L134
out["arm_name"] = "arm1"  # 改为 out["arm_name"] = "left_arm"
```

---

### 4.4 Task Goal Schema（100% 复用，M5.7 FROZEN）

#### 文件清单
- `multi_arm_interfaces/msg/TaskGoal.msg` — 字段 `arm_name: string`
- `multi_arm_interfaces/msg/TaskConstraint.msg`
- `multi_arm_interfaces/msg/CapabilityInfo.msg`
- `multi_arm_interfaces/action/ExecuteTask.action`
- `multi_arm_task_planner/bt_xml/pick_place*.xml`
- `multi_arm_task_planner/bt_plugins/async_ros2_plugins.py`

**为什么无需返工？**
- `arm_name` 是 string 字段，Phase 2 改 string 值即可
- M5.7 FROZEN v1.0 接口**不破坏**
- BT XML 不含 arm_name，通过 blackboard 注入

**需改的硬编码默认值**（6 行）：
```python
# multi_arm_task_planner/task_planner_node.py L203-208
arm_name="arm1"     →  arm_name="left_arm"
zone="zone_a"       →  zone="zone_a"  # 不变
object_id="red_cube" → 不变
```

```python
# multi_arm_core/coordinator_node.py _parse_task fallback L486-487
arm_name="arm1"     →  arm_name="left_arm"
zone_name="zone_a"  →  zone_name="zone_a"  # 不变
```

---

### 4.5 Episode Data（100% 复用）

#### 文件清单
- `multi_arm_experience/episode.py` (Episode, WorldStateSnapshot, SkillTraceStep, RecoveryRecord)
- `multi_arm_experience/experience_recorder.py`
- `multi_arm_experience/dataset_exporter.py`
- `multi_arm_interfaces/msg/EpisodeData.msg`

**为什么无需返工？**
- `Episode.robot_id: string` 默认 `"dual_ur5e"` → 改为 `"embodied_robot"` 即可
- `WorldStateSnapshot` 只含 `objects: dict` + `relations: list`（无 joint）
- `SkillTraceStep.step_name: string`（如"perceive/grasp"），无 joint
- `RecoveryRecord.failure_type: string` 抽象枚举（PLANNING/COLLISION/GRASP）
- SQLite schema 无 joint 列
- `EpisodeData.msg` 全 JSON blob

**唯一改动**（1 行）：
```python
# multi_arm_experience/experience_recorder.py L48
robot_id="dual_ur5e"  →  robot_id="embodied_robot"
```

---

### 4.6 Capability Registry（100% 复用）

#### 文件清单
- `multi_arm_robot_description/capability_registry.py`
- `multi_arm_robot_description/config/capability.yaml`
- `multi_arm_interfaces/msg/CapabilityInfo.msg`

**为什么无需返工？**
- `CapabilityInfo.name` 按 capability 名索引（如 `arm_can_reach`）
- 三层模型（Static/Dynamic/Context）不绑 arm
- WorldModel 内部 `_arm_names` 是参数化配置

**唯一改动**：`robot.yaml` 的 arms 列表：
```yaml
# 当前
arms:
  - name: arm1
    prefix: arm1_
  - name: arm2
    prefix: arm2_

# 目标
arms:
  - name: left_arm
    prefix: left_arm_
  - name: right_arm
    prefix: right_arm_
```

---

### 4.7 WorldModel 五层（~95% 复用）

#### 文件清单
- `multi_arm_world_model/entity_layer.py` (Entity)
- `multi_arm_world_model/state_layer.py` (CachedRobotState)
- `multi_arm_world_model/relation_layer.py` (Relation)
- `multi_arm_world_model/history_layer.py` (History)
- `multi_arm_world_model/prediction_layer.py` (Prediction)

**为什么几乎全复用？**
- 五层 schema 都是 `string` 字段，参数化
- `_arm_names: List[str]` 是参数
- `CachedRobotState.joint_positions: List[float]` 默认 `[0]*6` → Phase 2 改 `[0]*6`（**不需返工**）

**唯一改动**：
```python
# relation_layer.py 测试 (L51-58)
"arm1_gripper"  →  "left_arm_gripper"  # 仅测试 fixture
"arm2_gripper"  →  "right_arm_gripper"
```

**生产代码影响**：WorldModel 推理会写入 gripper 字符串，需搜索替换 `arm1_gripper` → `left_arm_gripper`（约 3-5 处）。

---

### 4.8 Runtime API（100% 复用）

#### 文件清单
- `multi_arm_runtime_api/runtime_api_node.py`
- 7 个 API：SubmitTaskGoals / QueryWorld / GetCapability / ListSkills / ManageSkill / QueryExperience / ExecuteSkill

**为什么无需返工？**
- 7 个 API 都基于 string 参数（arm_name / skill_name / robot_id）
- 不接触 joint
- action_type → skill_name 映射（pick_place→pick_object）是逻辑映射

**action_type 映射**（M6.5 已冻结）保留，arm 名改动不影响。

---

### 4.9 Recovery Manager（100% 复用）

#### 文件清单
- `multi_arm_recovery/recovery_manager.py`
- `multi_arm_recovery/failure_classifier.py`
- `multi_arm_recovery/handlers/*.py`

**为什么无需返工？**
- `FailureType` 枚举（PLANNING/COLLISION/GRASP/SAFETY/CONTROLLER）是抽象分类
- 恢复策略基于 FailureType，不绑 arm
- RecoveryManager 接收 `RecoveryAction` msg，arm_name string 透传

---

### 4.10 Benchmark System（95% 复用）

#### 文件清单
- `multi_arm_benchmark/benchmark_node.py`
- `multi_arm_benchmark/benchmark_recorder.py`
- `multi_arm_benchmark/scenario_runner.py`
- `multi_arm_benchmark/regression_detector.py`
- `multi_arm_benchmark/scenarios/{single_arm,dual_arm,conflict,recovery}.yaml`

**为什么几乎全复用？**
- `BenchmarkRecorder` 记录的指标是 `success/planning_time/execution_time`，不绑 arm
- `RegressionDetector` 比较历史运行，不绑 arm
- `ScenarioRunner` 读取 scenario YAML，arm 列表是配置

**唯一改动**：scenario YAML 的 `arms: [arm1]` 列表
```yaml
# 当前
arms: ["arm1"]

# 目标
arms: ["left_arm"]
```

约 3-4 行。

---

## 5. 接口冻结影响（M5.7 FROZEN v1.0）

### 5.1 接口不变（强保证）

| 接口 | 字段 | Phase 2 是否变 |
|------|------|----------------|
| `ExecuteTask.action` | description, TaskGoal | ❌ 不变（arm_name 是 string） |
| `TaskGoal.msg` | arm_name, zone_name, position_name, object_id, approach, constraints | ❌ 不变 |
| `TaskConstraint.msg` | max_time, safety_level, priority, allow_recovery, max_retries | ❌ 不变 |
| `SafetyCheck.srv` | arm_names[], trajectory_joint_names[], trajectory_positions[] | ⚠️ 数组长度需扩展 |
| `QueryWorld.srv` | query_type, robot_id | ❌ 不变 |
| `EpisodeData.msg` | episode_id, robot_id, ... | ❌ 不变（robot_id 是 string） |
| `CapabilityInfo.msg` | name, category, available, value | ❌ 不变（按 capability 名）|

### 5.2 `SafetyCheck.srv` 唯一风险

**当前 schema**（M5.7 冻结）：
```
trajectory_joint_names[]   (平铺)
trajectory_positions[]     (平铺)
```

**Phase 2 风险**：如果双臂从 6 DOF 增加到 7 DOF（加 shoulder），joint 数组长度变。

**缓解**：
- 当前已冻结为 6 DOF/臂（UR5e），Phase 2 决定不加 shoulder DOF（body_architecture v1.0 冻结）
- 未来如果加 DOF，schema 进入 v1.1 评审

### 5.3 MotionRequest.msg 风险

**当前 schema**：
```
float64[6] joint_positions  # 隐式 6 长度
```

**Phase 2**：如果换机械臂（UR5e → 7 DOF Franka），需改。
**当前决策**：保持 UR5e（body_architecture v1.0 冻结），不需改 schema。

---

## 6. 迁移工作量评估

### 6.1 工作量分类

| 类别 | 文件数 | 估算工时 | 风险 |
|------|--------|----------|------|
| **URDF 重构** | 6+4 新增 | 2-3 周 | 高 |
| **SRDF 重命名** | 3 (含 2 废弃) | 3 天 | 中 |
| **Controller YAML 重命名** | 7 | 3 天 | 中 |
| **robot_constants.py 字典重命名** | 1 | 1 天 | 高 |
| **测试 fixture 重命名** | 22 | 3-5 天 | 中 |
| **Scenario YAML 重命名** | 4 | 0.5 天 | 低 |
| **硬编码默认值修正** | 3 文件 8 行 | 0.5 天 | 低 |
| **WorldModel relation 重命名** | 1 文件 3-5 行 | 0.5 天 | 低 |
| **Episode robot_id 改默认值** | 1 文件 1 行 | 0.1 天 | 低 |
| **Gazebo 脚本改 arm 名** | 4 脚本 | 1-2 天 | 中 |
| **集成验证** | - | 1 周 | 中 |
| **总计** | - | **6-8 周** | - |

### 6.2 关键里程碑

```
M-Phase2-1: URDF 重构完成（shoulder frame + head sensor）
  └─ milestone: xacro 编译通过 + MoveIt 启动 + 28→52 links 一致

M-Phase2-2: SRDF + Controller YAML 重命名完成
  └─ milestone: 12 group_state 重命名 + 7 YAML 重命名

M-Phase2-3: robot_constants 字典重命名 + 硬编码修正
  └─ milestone: arm1→left_arm 全部替换

M-Phase2-4: 测试 fixture 全部更新 + 158+ tests 通过
  └─ milestone: 100% 测试通过率

M-Phase2-5: Gazebo 集成 + E2E 验证
  └─ milestone: PickPlace E2E 100% 成功
```

### 6.3 风险与回滚

**风险**：
- URDF 重构可能引入 collision 矩阵错误
- 158 tests 可能因 TF 变化失败
- MoveIt SRDF 重组可能破坏 dual_arm planning

**回滚策略**：
- Phase 2 启用独立分支 `feat/phase2-shoulder`
- 每个 commit 必须保持测试 100% 通过
- 失败立即 revert，不累积技术债
- 关键节点（每个 milestone）打 tag 便于回退

---

## 7. 与 Phase 2 详细计划对照

### 7.1 哪些工作提前在 Phase 1.5 完成？

| 任务 | 建议 Phase |
|------|-----------|
| robot_constants.py 重命名 | Phase 1.5（独立小 PR） |
| Scenario YAML 重命名 | Phase 1.5（独立小 PR） |
| 默认值修正（8 行） | Phase 1.5（独立小 PR） |
| robot_id 默认值改 | Phase 1.5 |
| Controller YAML 重命名 | Phase 2（与 URDF 同步） |
| SRDF 重命名 | Phase 2（与 URDF 同步） |
| URDF 重构 | Phase 2 |
| 测试 fixture 重命名 | Phase 2（与 SRDF 同步） |
| Gazebo 脚本 | Phase 2 |

**好处**：Phase 1.5 提前做 5 个低风险改动，建立"arm1→left_arm"重命名惯例，Phase 2 专注于 URDF 重构。

### 7.2 Phase 2 不破坏的能力

经过盘点确认 Phase 2 迁移**不破坏**以下能力：
- ✅ Skill Runtime 全部（8 skill × 3 文件）
- ✅ TaskPlanner 全部（4 BT XML + 8 async plugin + TaskPlannerNode）
- ✅ Experience 全部（Episode + Snapshot + Trace + Failure + Dataset）
- ✅ WorldModel 五层（Entity/State/Relation/History/Prediction + Belief）
- ✅ Capability Registry（三层模型）
- ✅ Runtime API 7 接口
- ✅ ResourceManager / Scheduler / AllocationStrategy
- ✅ Recovery Manager + FailureClassifier
- ✅ Benchmark System
- ✅ 所有 Cartesian pose 数据
- ✅ 所有 named position 字符串

**Phase 2 迁移后** Robot 立即拥有：
- 158+ tests passing（同 Phase 0 数量）
- 102 Skill Runtime tests passing
- 48 Experience tests passing
- 32 Runtime API tests passing
- 全部 M5.7 FROZEN v1.0 接口

---

## 8. 决策建议

### 8.1 立即可做的（Phase 1.5）

按工作量从小到大排序：
1. **改 robot_id 默认值**（1 行，1 分钟）— 立即做
2. **改 scenario YAML arm 列表**（3-4 行，1 小时）— 立即做
3. **改 blackboard 默认值**（6 行，1 小时）— 立即做
4. **改 skill_motion_bridge 默认值**（1 行，5 分钟）— 立即做
5. **改 WorldModel relation 测试**（3-5 行，30 分钟）— 立即做
6. **改 robot_constants 字典 key**（30 处，1-2 天）— 单独 PR

### 8.2 需与 URDF 同步（Phase 2）

- URDF 重构（2-3 周）
- SRDF 重命名（3 天）
- Controller YAML 重命名（3 天）
- 测试 fixture 重命名（3-5 天）
- Gazebo 脚本（1-2 天）
- 集成验证（1 周）

### 8.3 不需要做的事

- ❌ 重写 Skill（抽象已正确）
- ❌ 重写 TaskPlanner（接口冻结）
- ❌ 重写 Experience（schema 抽象）
- ❌ 重写 WorldModel 五层（参数化）
- ❌ 重写 Runtime API（不依赖物理层）
- ❌ 重写 Capability Registry（按 capability 名）
- ❌ 重写 Benchmark（仅 scenario YAML 改）

---

## 9. 冻结声明

本文档 v1.0 冻结以下评估结论：
- ✅ 抽象层 98% 复用
- ✅ 边界层返工清单（30 项 joint-level）
- ✅ 物理量 100% 复用
- ✅ M5.7 FROZEN v1.0 接口不变
- ✅ Phase 1.5 可提前做的工作
- ✅ Phase 2 工作量 6-8 周
- ✅ 风险与回滚策略

**禁止破坏性修改**。如需新增返工项，进入 v1.1 评审。

---

**End of Robot Data Migration Assessment v1.0**