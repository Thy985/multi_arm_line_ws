# API Contracts — 接口契约与数据模型冻结

> M5.7 Interface & Architecture Audit
> 版本: v1.0 (Interface Freeze)
> 日期: 2026-08-07

---

## 1. 核心数据模型 (FROZEN v1.0)

### 1.1 TaskGoal — 任务目标领域模型

```
TaskGoal.msg (FROZEN v1.0)
├── action_type: string     # "move"|"pick_place"|"grasp"|"place"|"lift"|"retract"|"inspect"
├── arm_name: string        # "arm1"|"arm2"
├── zone_name: string       # "zone_a"|"zone_b"|"zone_c"
├── position_name: string   # "home"|"ready"|"scan"|"inspect"|"place_high"|"place_low"|...
├── object_id: string       # "red_cube"|"blue_cylinder"|...
├── approach: string        # "top"|"side"|"front"
└── constraints: TaskConstraint
```

**冻结理由**: TaskGoal是M5.3从字符串协议升级的结构化领域模型，是M6 Agent接入的核心依赖。M6 Agent将通过TaskGoal指定任务目标，字段不可变。

**扩展规则**: M6可新增可选字段（如`scene_context`, `skill_id`），只能追加到末尾且有默认值。

### 1.2 TaskConstraint — 任务约束

```
TaskConstraint.msg (FROZEN v1.0)
├── max_time: float64       # 最大执行时间 (0=无限)
├── safety_level: uint8     # 0=normal, 1=strict, 2=critical
├── priority: uint8         # 0=low, 1=normal, 2=high, 3=critical
├── allow_recovery: bool    # 是否允许恢复
└── max_retries: uint8      # 最大重试次数
```

### 1.3 ExecuteTask — 任务执行Action

```
ExecuteTask.action (FROZEN v1.0)
Goal:
├── task_id: string         # 唯一标识
├── task_type: string       # 任务类型
├── description: string     # Legacy字符串 (向后兼容)
└── goal: TaskGoal          # 结构化目标 (preferred)

Result:
├── success: bool
└── message: string

Feedback:
├── status: string
├── progress: float32
└── error_message: string
```

**契约**:
- Producer发送Goal后，Consumer必须在5s内accept/reject
- 执行超时由constraints.max_time控制，默认30s
- success=false时，message必须包含失败原因
- progress范围[0.0, 1.0]

### 1.4 SafetyCheck — 安全审批Service

```
SafetyCheck.srv (FROZEN v1.0)
Request:
├── arm_names: string[]
├── trajectory_joint_names: string[]
├── trajectory_positions: float64[]
└── trajectory_duration: float64

Response:
├── approved: bool
├── speed_scale: float32    # 0.0-1.0
└── message: string
```

**契约**:
- approved=false时，message必须包含拒绝原因
- speed_scale范围[0.0, 1.0]，1.0=全速
- 服务不可用时，Coordinator默认**拒绝**（安全优先）
- 服务不可用时，BT插件AsyncCheckSafetyNode默认**FAILURE**（安全优先）

### 1.5 QueryResources — 资源查询Service

```
QueryResources.srv (FROZEN v1.0)
Request:
└── resource_types: string[]

Response:
├── resource_names: string[]
├── resource_types: string[]
├── states: string[]
└── allocated_to: string[]
```

**契约**:
- 返回的4个数组长度必须一致
- 服务不可用时，BT插件AsyncQueryWorldNode默认**SUCCESS**（fallback空结果）

---

## 2. 消息类型契约 (FROZEN v1.0)

### 2.1 CollisionEvent

```
CollisionEvent.msg (FROZEN v1.0)
├── arm_name: string
├── collision_type: string
├── object_a: string
├── object_b: string
└── timestamp: float64
```

### 2.2 ObjectPose

```
ObjectPose.msg (FROZEN v1.0)
├── object_id: string
├── object_type: string
├── position: float64[3]     # x, y, z
├── orientation: float64[4]  # qx, qy, qz, qw
└── confidence: float32
```

**M6用途**: Perception Server发布检测到的物体位姿，WorldModel订阅。

### 2.3 ResourceStatus

```
ResourceStatus.msg (FROZEN v1.0)
├── resource_name: string
├── resource_type: string
├── state: string
├── allocated_to: string
└── capabilities: string[]
```

### 2.4 RecoveryAction

```
RecoveryAction.msg (FROZEN v1.0)
├── failure_type: string
├── task_id: string
├── strategy_used: string
├── success: bool
└── message: string
```

### 2.5 SystemHealth

```
SystemHealth.msg (FROZEN v1.0)
├── component: string
├── status: string
├── uptime_s: float64
└── error_messages: string[]
```

### 2.6 MotionRequest

```
MotionRequest.msg (FROZEN v1.0)
├── arm_name: string
├── target_position: string
├── joint_positions: float64[6]
├── use_named_target: bool
├── speed_scale: float64
├── collision_check: bool
└── max_velocity: float64
```

---

## 3. 预设位置契约 (FROZEN v1.0)

```python
PRESET_POSITIONS = {
    "home":       [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    "ready":      [0.0, -1.57, 1.57, 0.0, 0.0, 0.0],
    "extended":   [0.0, -0.5, 2.5, 0.5, 0.5, 0.0],
    "left":       [-1.57, -1.0, 1.5, 0.0, 0.5, 0.0],
    "right":      [1.57, -1.0, 1.5, 0.0, 0.5, 0.0],
    "scan":       [0.0, -1.2, 1.8, -0.5, 0.0, 0.0],
    "inspect":    [0.0, -1.0, 1.5, -0.3, 0.3, 0.0],
    "place_high": [0.0, -1.5, 1.5, -0.3, 0.0, 0.0],
    "place_low":  [0.0, -0.8, 1.0, -0.5, 0.0, 0.0],
}
```

**契约**: 所有预设位置必须通过SafetyCheck审批。新增位置需验证安全限制。

---

## 4. M6/M7 预留接口

> 详细规划见 `docs/architecture/M6_platform_upgrade_plan.md` (第四轮架构评审后调整)

### 4.0 Robot Description Layer (M6.0)

**原则**: 不造平行系统，作为ROS模型上层管理 + 动态Capability Registry三层

```yaml
# robot.yaml结构 (非ROS接口，配置文件)
robot:
  components:
    arms: [{name, type, urdf, controller}]
    sensors: [{name, type, parent_link}]      # M6.1填充
    end_effectors: [{name, type, parent}]      # M6.2填充
    body: {type: "fixed"|"differential"}       # M6.6填充
  generation:
    - urdf, srdf, controllers.yaml, moveit_config

# M6.0新增msg — 动态能力信息(三层)
CapabilityInfo.msg:
  name: string
  category: string                # "static"|"dynamic"|"context"
  available: bool
  value: string                   # JSON序列化能力值
  reason: string                  # 不可用原因 (如"overheated"/"out_of_workspace")

# M6.0新增srv — 动态Capability查询 (三层: Static+Dynamic+Context)
GetCapability.srv:
  request:
    capability_name: string       # "manipulation"|"gripper"|"vision"|"all"
    include_dynamic: bool         # 是否包含动态+上下文能力
    context: string               # 可选: "zone_a"|"object:red_cube" (上下文能力需要)
  response:
    capabilities: CapabilityInfo[]

# M6.0新增topic — 能力变化通知
/capability/updates: CapabilityInfo (RELIABLE, depth=10)
```

**动态Capability Registry三层**: Static(固有能力, capability.yaml) + Dynamic(当前状态, payload_remaining/gripper_overheated) + Context(环境限制, can_reach/can_grasp/path_clear)

**接入方式**: M6.0实现Robot Description Layer包 + CapabilityRegistry节点。YAML驱动生成ROS模型文件，不替代URDF/ros2_control/MoveIt。能力变化时发布/capability/updates。

### 4.S Simulation Infrastructure (M6.S, 提前)

**仿真本身是平台 — Robot Simulation OS，横向贯穿M6.1-M6.6**

```yaml
# M6.S不新增msg/srv，提供:
# - 场景生成器 (随机物体/光照/纹理/物理参数)
# - Domain Randomization (光照/纹理/位置/物理随机化)
# - Dataset Pipeline (Gazebo → 数据集自动采集)
# - Ground Truth (Gazebo精确标注)
# - 仿真/实体切换 (共享robot.yaml, 仅Hardware Adapter不同)
```

**提前理由**: M6.1+所有模块依赖仿真, Simulation是Runtime执行环境之一

**接入方式**: M6.S扩展ur_simulation_gz包，新增场景生成+Domain Randomization脚本。Data Layer的Dataset Pipeline依赖此模块。

### 4.1 Perception + WorldModel Interface (M6.1)

**感知与世界模型绑定**: camera → perception → WorldModel(5层) → reasoning → action

**WorldModel 5层**: Entity Layer + State Layer + Relation Layer + History Layer + Prediction Layer

```yaml
# M6.1新增msg
SceneUpdate.msg:
  objects: ObjectPose[]
  timestamp: float64
  source: string          # "camera"|"gazebo_ground_truth"

SceneState.msg:
  objects: ObjectPose[]
  obstacles: ObjectPose[]
  timestamp: float64

TaskState.msg:
  task_id: string
  status: string
  progress: float32
  elapsed_time: float64
  error_message: string

# M6.1新增msg — Relation Layer (Skill判断的关键依赖)
Relation.msg:
  subject: string              # 主体实体ID
  predicate: string            # "on"|"near"|"inside"|"attached_to"|"above"|"below"
  object: string               # 客体实体ID
  confidence: float32
  distance: float32            # 可选: 距离值 (near/inside关系)

RelationGraph.msg:
  relations: Relation[]
  timestamp: float64

# M6.1新增srv
GetObjectState.srv:
  request:
    object_id: string
  response:
    object_state: ObjectState     # 含attached_to/grasp_state
    found: bool

# M6.1新增srv (扩展查询, 不修改FROZEN的QueryResources)
QueryWorld.srv:
  request:
    query_type: string        # "robot"|"object"|"scene"|"task"|"relation"|"all"
    entity_id: string         # 可选, 查询特定实体
    relation_predicate: string # 可选, 查询特定关系 (如"on")
  response:
    object_states: ObjectState[]   # 含manipulation state
    scene_state: SceneState
    task_state: TaskState
    relations: Relation[]          # Relation Layer查询结果

# M6.1新增srv — 专门查询实体间关系
QueryRelation.srv:
  request:
    subject: string            # 可选
    predicate: string          # 可选
    object: string             # 可选
  response:
    relations: Relation[]
    exists: bool

# 预留topic (已存在, WorldModel已订阅)
/perception/object_poses: ObjectPose (RELIABLE, depth=10)
/perception/scene_update: SceneUpdate (M6.1新增)
```

**Relation Layer是Skill判断的关键依赖**: Skill的precondition/postcondition查询Relation判断是否满足 (如"object attached_to gripper"、"object on table")

**接入方式**: M6.1实现Perception Server + WorldModel升级为5层。WorldModel同时提供QueryResources(冻结)和QueryWorld/QueryRelation(新增)。

### 4.2 Manipulation Interface (M6.2)

```yaml
# M6.2新增srv
ControlGripper.srv:
  request:
    arm_name: string
    command: string          # "open"|"close"|"attach"|"detach"
    object_id: string        # attach/detach的目标物体
    force: float64           # 抓取力 (N)
  response:
    success: bool
    message: string

# M6.2新增action
GraspObject.action:
  goal:
    arm_name: string
    object_id: string
    approach: string         # "top"|"side"|"front"
  result:
    success: bool
    message: string
    attached: bool
  feedback:
    status: string
    progress: float32
```

**接入方式**: M6.2实现Gripper Controller + GraspPlanner，BT插件新增GraspNode/PlaceNode。抓取/放置后更新WorldModel State Layer和Relation Layer。

### 4.3 Skill Interface (M6.3) — FROZEN v1.0

**Skill = Manifest + Capability + Preconditions + Execution + Postcondition + Recovery + Lifecycle**

**Skill Lifecycle**: Install→Register→Validate→Ready→Execute→Monitor→Update→Remove (类似K8s Pod生命周期)

> **⚠️ FROZEN v1.0 (M6 Gate 2 Baseline, 2026-08-07)**
> 完整SPEC见 `docs/architecture/M6_3_SPEC.md`
> 决策记录见 `docs/architecture/ADR-M6.3-Freeze.md`
> 90 tests ALL PASS (63 unit + 25 E2E + 2 smoke)

```yaml
# M6.3新增msg — Skill Manifest (类似package.json)
SkillDescription.msg:
  name: string
  version: string
  required_capabilities: string[]    # 依赖的机器人能力
  preconditions: string[]
  postconditions: string[]
  parameters: string[]
  cost_time: float64                 # 预估执行时间(秒) — Agent选择依据
  cost_risk: float64                 # 风险等级(0-1)
  success_rate: float64              # 历史成功率

# M6.3新增msg — Skill Lifecycle状态
SkillStatus.msg:
  skill_id: string
  name: string
  version: string
  lifecycle_state: string     # "installed"|"registered"|"validated"|"ready"|"executing"|"monitoring"|"updating"|"removing"|"removed"|"invalid"
  last_executed: float64
  total_executions: int32
  success_count: int32

# M6.3新增srv — Skill列表 (按Lifecycle状态过滤)
ListSkills.srv:
  request:
    required_capabilities: string[]
    lifecycle_state: string    # 可选: 仅返回指定状态的Skill (如"ready")
  response:
    skills: SkillDescription[]

# M6.3新增srv — Skill Lifecycle管理
ManageSkill.srv:
  request:
    action: string             # "install"|"register"|"validate"|"update"|"remove"
    skill_package: string      # install: 包路径
    skill_id: string           # 其他: Skill ID
    version: string            # update: 目标版本
  response:
    success: bool
    skill_status: SkillStatus
    message: string

# M6.3新增action
ExecuteSkill.action:
  goal:
    skill_name: string
    parameters: string[]
    task_goal: TaskGoal      # 引用已冻结的TaskGoal
  result:
    success: bool
    message: string
    postcondition_results: bool[]
  feedback:
    status: string
    progress: float32

# Skill七要素契约
Skill:
  manifest: SkillDescription          # 元数据(能力/成本/风险)
  lifecycle: SkillLifecycle           # 生命周期管理 (Install→...→Remove)
  precondition: () -> bool           # 什么时候可以做 (查询WorldModel Relation Layer)
  execute: (TaskGoal) -> Result       # 怎么做 (BT + Motion Planner + 可选LLM)
  postcondition: () -> bool           # 完成了吗 (查询WorldModel Relation Layer)
  recover: (Failure) -> Result        # 失败怎么办
  monitor: (Result) -> None           # 执行后监控 → Data Layer
```

**接入方式**: M6.3实现SkillRuntime节点。Skill Manifest包含cost/risk/success_rate供Agent选择。Skill Registry提供ListSkills查询(仅READY状态)。ManageSkill管理Skill Lifecycle。precondition/postcondition查询WorldModel Relation Layer。

### 4.5 Robot Runtime API (M6.5, 重命名)

**M6只提供能力接口，不包含自然语言理解（语言理解属M7）**

**重命名理由**: 旧名"Agent Capability Interface"误导(M6没有Agent), 新名"Robot Runtime API"准确反映M6提供的是Runtime能力接口

```yaml
# M6.5新增srv — 结构化任务提交 (非自然语言)
SubmitTaskGoals.srv:
  request:
    task_goals: TaskGoal[]           # 引用已冻结的TaskGoal
    strategy: string                 # "sequential"|"parallel"|"best_effort"
  response:
    task_ids: string[]
    accepted: bool
    message: string

# M6.5提供的Robot Runtime API (M7 Agent调用):
#   ExecuteSkill.action (M6.3)
#   QueryWorld.srv (M6.1)
#   QueryRelation.srv (M6.1)
#   GetCapability.srv (M6.0)
#   ListSkills.srv (M6.3)
#   ManageSkill.srv (M6.3)
#   SubmitTaskGoals.srv (M6.5)
#   QueryData.srv (Data Layer)
```

**接入方式**: M7实现自然语言→TaskGoal[]，调用M6.5的SubmitTaskGoals。M6不含SubmitNaturalLanguage。

### 4.6 Mobile Base Interface (M6.6, 后置)

```yaml
# M6.6新增msg
BodyState.msg:
  base_position: float64[3]    # x, y, theta
  base_velocity: float64[3]
  localized: bool

# M6.6新增action
NavigateTo.action:
  goal:
    target_pose: PoseStamped
    behavior: string          # "navigate"|"approach"|"retreat"
  result:
    success: bool
    message: string
  feedback:
    status: string
    distance_remaining: float64
```

**接入方式**: M6.6集成Navigation2，后置实现。

### 4.D Data Layer Interface (横切)

**Robot Data Pipeline — 类似软件的Observability, M7 Agent学习的数据来源**

**六类数据**: Sensor Data(短期) + Episode Data(中期) + Skill Execution Log(长期) + Failure Data(长期) + WorldModel Snapshot(中期) + Training Dataset(永久)

```yaml
# Data Layer新增srv — 数据查询 (M7使用)
QueryData.srv:
  request:
    data_type: string          # "sensor"|"episode"|"skill_log"|"failure"|"worldmodel"|"dataset"
    time_range: TimeRange      # 开始/结束时间
    filter: string             # 可选: 过滤条件 (JSON)
  response:
    records: string[]          # JSON序列化数据记录
    count: int32

# Data Layer新增srv — 记录任务执行episode
RecordEpisode.srv:
  request:
    task_id: string
    task_goal: TaskGoal
    steps: string[]            # 执行步骤JSON
    result: string             # "success"|"failure"
    duration: float64
  response:
    success: bool
    episode_id: string

# Data Layer新增topic — 数据流发布
/data/episode: EpisodeData (RELIABLE, depth=100)
/data/failure: FailureData (RELIABLE, depth=100)
/data/skill_log: SkillLog (RELIABLE, depth=100)
```

**与M5.4 Benchmark的关系**: M5.4的benchmark.db是Data Layer的一部分 (Skill Execution Log的子集)

**接入方式**: Data Layer横切M6.0-M6.6。Skill Monitor执行后更新success_rate (读Skill Log)。M7 Agent从Training Dataset学习。

### 4.7 Agent Natural Language Interface (M7, 非M6)

```yaml
# M7新增srv (不属于M6)
SubmitNaturalLanguage.srv:
  request:
    instruction: string
    context: string
  response:
    task_ids: string[]
    accepted: bool
    message: string

# 预留action (M7新增)
ExecuteAgentGoal.action:
  goal:
    instruction: string
    task_goals: TaskGoal[]    # 引用已冻结的TaskGoal
  result:
    success: bool
    message: string
    completed_tasks: string[]
  feedback:
    status: string
    current_task: string
    progress: float32
```

**接入方式**: M7实现Agent节点，将自然语言指令转换为TaskGoal[]，通过ExecuteTask.action提交给TaskPlanner/Coordinator。

### 4.8 Robot Hardware Interface (M6 Sim2Real)

```yaml
# 硬件抽象层 (已由ros2_control提供)
# 仿真配置: ur_simulation_gz/config/multi_arm_controllers.yaml
# 实体配置: (M6新增) ur_robot_driver/config/multi_arm_controllers_real.yaml

# 冻结的硬件接口:
FollowJointTrajectory.action (control_msgs)  # JTC
/joint_states (sensor_msgs)                   # 关节状态
controller_manager services                   # 控制器管理

# Sim2Real切换: 仅hardware_interface不同，上层接口不变
```

---

## 5. 接口版本治理

### 5.1 版本号规则

```
multi_arm_interfaces vMAJOR.MINOR

MAJOR: 破坏性变更 (删除字段/修改类型) — M5.7后禁止
MINOR: 兼容性新增 (新增msg/新增字段) — M6+允许
```

当前版本: **v1.0** (M5.7 Interface Freeze)

### 5.2 变更审批流程

```
M6+ 接口变更流程:

1. 提出变更 (PR描述)
2. 检查是否破坏FROZEN接口
   ├── 破坏 → 拒绝，需Architecture Review Board
   └── 兼容 → 继续
3. 更新 interface_catalog.md
4. 更新 api_contracts.md
5. 更新 dependency_graph.md
6. 更新 data_flow.md
7. 通过CI interface-compat检查
8. 合并
```

### 5.3 CI保障

```
CI Layer: interface-compat
  ├── 检查multi_arm_interfaces是否与catalog一致
  ├── 检查FROZEN接口字段是否被修改
  └── 检查新增接口是否已更新catalog
```

---

## 6. 已知偏差 (Accepted Deviations)

### 6.1 BT插件越层调用

```
偏差: TaskPlanner BT插件直接调用SafetyCheck.srv和QueryResources.srv
位置: async_ros2_plugins.py:267, 306
原因: M5.2避免Coordinator瓶颈
影响: 只读查询，不影响安全审批链路
状态: 接受为已知偏差
复查: M6重构时评估
```

### 6.2 RecoveryManager非ROS2节点

```
偏差: RecoveryManager是纯Python模块，非ROS2节点
原因: M5.1设计时Recovery为内部逻辑
影响: Recovery不能跨节点调用
状态: 接受，RecoverFromFailure.srv预留为M6分布式接口
复查: M6如需分布式Recovery，激活此Service
```

### 6.3 SafetyCheck不可用时默认批准

```
偏差: Coordinator在SafetyCheck服务不可用时默认批准运动
位置: safety_interface.py
影响: 安全风险——SafetySupervisor崩溃时运动不被拦截
状态: 已知风险，M6需改为默认拒绝
复查: M6.1 Safety强化
```

---

## 7. Interface Freeze总结

### 冻结的接口 (v1.0)

#### M5.7 Freeze (v1.0) — 18项

| 接口 | 类型 | 冻结内容 |
|------|------|----------|
| ExecuteTask.action | Action | Goal/Result/Feedback字段 |
| TaskGoal.msg | Message | 所有字段 |
| TaskConstraint.msg | Message | 所有字段 |
| MotionRequest.msg | Message | 所有字段 |
| SafetyCheck.srv | Service | Request/Response字段 |
| EmergencyStop.srv | Service | Request/Response字段 |
| QueryResources.srv | Service | Request/Response字段 |
| RecoverFromFailure.srv | Service | Request/Response字段 |
| CollisionEvent.msg | Message | 所有字段 |
| ObjectPose.msg | Message | 所有字段 |
| ResourceStatus.msg | Message | 所有字段 |
| RecoveryAction.msg | Message | 所有字段 |
| SystemHealth.msg | Message | 所有字段 |
| PRESET_POSITIONS | Constant | 9个预设位置 |
| /safety/collision_events | Topic | 类型+QoS |
| /safety/status | Topic | 类型+QoS |
| /world_model/state | Topic | 类型+QoS |
| /perception/object_poses | Topic | 类型+QoS (M6实现Publisher) |

#### M6.3 Freeze (v1.0, Gate 2) — 12项

| 接口 | 类型 | 冻结内容 |
|------|------|----------|
| ExecuteSkill.action | Action | Goal/Result/Feedback字段 |
| ListSkills.srv | Service | Request/Response字段 |
| ManageSkill.srv | Service | Request/Response字段 |
| SkillDescription.msg | Message | 所有字段 |
| SkillStatus.msg | Message | 所有字段 |
| SkillManifest Schema | Data Model | 14A14个字段 |
| SkillLifecycleState | Enum | 10个状态 |
| VALID_TRANSITIONS | State Machine | 状态转换矩阵 |
| ExecutionStatus | Enum | 5个值 |
| Recovery Policy | Contract | 触发条件+匹配顺序 |
| Skill Composition | Contract | 链式执行+optional规则 |
| BT Compatibility | Contract | BT→Skill包装规则 |

**SPEC**: `docs/architecture/M6_3_SPEC.md`
**ADR**: `docs/architecture/ADR-M6.3-Freeze.md`
**Tests**: 90 ALL PASS (63 unit + 25 E2E + 2 smoke)

### 未冻结的接口

| 接口 | 状态 | 计划 |
|------|------|------|
| PickPlace.action | EXPERIMENTAL | M7可能重构为Skill |
| SubmitTask.srv | EXPERIMENTAL | M7 Agent层同步接口 |

### M6+新增接口规则

- ✅ 允许新增msg/srv/action文件
- ✅ 允许在现有msg末尾新增字段（有默认值）
- ❌ 禁止修改/删除FROZEN字段
- ❌ 禁止重命名FROZEN接口
- ❌ 禁止修改FROZEN topic的QoS