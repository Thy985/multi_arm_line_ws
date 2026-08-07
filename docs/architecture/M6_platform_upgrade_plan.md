# M6 Robot Platform Upgrade — 阶段规划

> 从"双臂控制系统"升级为"机器人操作系统运行时"
> M5 = 机器人OS内核 | M6 = 机器人OS运行时 | M7 = 机器人智能层
> 日期: 2026-08-07 (第四轮架构评审后调整)
> 前置: M5.7 Interface Freeze v1.0

---

## 核心理念

```
M5完成: Robot OS Kernel — 通信架构+控制抽象+协调+安全+恢复+基准 (已验证闭环)
M6目标: Robot OS Runtime — 身体描述+仿真环境+感知+世界模型+操作+技能+能力接口+数据管道
M7目标: Robot Intelligence — 自然语言+规划+推理+任务拆解+Agent
```

**M6不是"给机器人加功能"，而是"建立机器人Runtime"。**

---

## 阶段总览 (第四轮架构评审后调整)

```
M6.0 Robot Description Layer      — robot.yaml + 动态Capability Registry + Hardware Adapter
    ↓
M6.S Simulation Infrastructure    — 仿真平台 (提前, 横向贯穿M6.1-M6.6)
    ↓
M6.1 Perception + WorldModel      — 感知 + 世界模型5层 (Entity/State/Relation/History/Prediction)
    ↓
M6.2 Manipulation Layer           — Gripper + Object attachment + Force feedback
    ↓
M6.3 Skill Runtime                — Skill五要素 + Manifest + Registry + Lifecycle
    ↓
M6.5 Robot Runtime API            — 能力接口 (重命名, 非自然语言, 语言理解属M7)
    ↓
M6.6 Mobile Base                  — 移动底盘 (后置)

══ Data Layer (横向贯穿) ══       — Robot Data Pipeline (Sensor/Episode/Skill/Failure/WorldModel/Dataset)
```

### 顺序逻辑 (调整理由)

```
身体描述 (M6.0)          — 定义机器人是什么、能做什么
    ↓
仿真环境 (M6.S)          — 提前: M6.1以后所有模块都依赖仿真, Simulation是Runtime的执行环境之一
    ↓
眼睛+大脑状态 (M6.1)     — 感知+世界模型(含Relation Layer, Skill判断的关键依赖)
    ↓
手 (M6.2)               — 操作能力
    ↓
技能 (M6.3)             — Skill Lifecycle: Install→Register→Validate→Ready→Execute→Monitor→Update→Remove
    ↓
Robot Runtime API (M6.5) — 重命名: M6没有Agent, 提供能力接口给M7
    ↓
移动 (M6.6)             — 后置

Data Layer (横切)        — 类似软件Observability, M7 Agent学习靠这个
```

### 第四轮调整要点

| # | 调整 | 理由 |
|---|------|------|
| 1 | Capability Registry改为动态服务 | 能力会动态变化(gripper过热/payload减少), 不只是静态YAML |
| 2 | WorldModel新增Relation Layer | on/near/inside/attached关系是Skill判断的关键依赖 |
| 3 | Skill新增Lifecycle | Install→Register→...→Remove, 否则Skill Library变成文件仓库 |
| 4 | Simulation提前到M6.0之后 | M6.1+所有模块依赖仿真, Sim是Runtime执行环境 |
| 5 | M6.5重命名为Robot Runtime API | M6没有Agent, 名称应反映实际职责 |
| 6 | 新增Data Layer横切 | Robot Data Pipeline, M7学习的数据来源 |

---

## M6.0 Robot Description Layer

**目标**: Robot Infrastructure as Code — 不造平行系统，作为ROS模型上层管理

### 核心原则

```
❌ 错误: Robot Entity替代URDF/ros2_control/MoveIt (造平行系统)
✅ 正确: robot.yaml → 生成URDF/SRDF/controllers.yaml/moveit_config
```

### 三层架构

```
robot.yaml (结构描述)
  ↓
capability.yaml (能力描述) → 动态Capability Registry (运行时能力服务)
  ↓
Hardware Adapter (硬件适配)
  ↓
ROS模型 (URDF/ros2_control/MoveIt)
```

### 1. robot.yaml — 结构描述

```yaml
robot:
  name: dual_ur5e_platform
  version: "1.0"

components:
  arms:
    - name: arm1
      type: ur5e
      urdf: ur5e_macro.xacro
      controller: arm1_joint_trajectory_controller
    - name: arm2
      type: ur5e
      urdf: ur5e_macro.xacro
      controller: arm2_joint_trajectory_controller

  sensors:                      # M6.1填充
    - name: camera_rgb
      type: camera
      parent_link: arm1_wrist_3_link
    - name: camera_depth
      type: depth_camera
      parent_link: arm1_wrist_3_link

  end_effectors:                # M6.2填充
    - name: gripper1
      type: robotiq_2f_85
      parent: arm1
    - name: gripper2
      type: robotiq_2f_85
      parent: arm2

  body:                         # M6.6填充
    type: fixed                 # "fixed"|"differential"|"omni"
```

### 2. 动态Capability Registry — 三层能力模型

**机器人差异主要不是结构，而是能力。且能力会动态变化。**

```
Static Capability (固有能力)     — capability.yaml声明, 启动时加载, 运行中不变
    例: manipulation.dof=6, gripper.max_opening=85mm

Dynamic Capability (当前状态能力) — 运行时计算, 随状态变化
    例: payload_remaining = max_payload - current_load
         gripper.available = not overheated
         arm.reachable = workspace_check(current_pose)

Context Capability (环境限制能力) — 结合WorldModel计算, 随环境变化
    例: arm.can_reach(zone_a) = workspace ∩ zone_a ≠ ∅
         gripper.can_grasp(object) = object.size < max_opening
         arm.path_clear = collision_check(target)
```

```yaml
# capability.yaml — Static Capability (固有能力)
capabilities:
  manipulation:
    type: joint_position         # "joint_position"|"joint_torque"|"cartesian"
    dof: 6
    payload_kg: 5.0
    available: true

  force_control:
    available: false             # UR5e仿真无力控, Franka有力控

  gripper:
    type: parallel_jaw
    max_opening_mm: 85
    available: true              # M6.2后true

  vision:
    types: ["rgb", "depth"]
    available: true              # M6.1后true

  mobile:
    available: false             # M6.6后true

  skills:                        # M6.3后填充
    - pick_object
    - place_object
    - inspect_object
```

```python
# 动态Capability Registry (运行时服务)
class CapabilityRegistry:
    """三层能力模型: Static + Dynamic + Context"""

    def __init__(self, static_caps: dict):
        self._static = static_caps        # from capability.yaml
        self._dynamic = {}                 # runtime computed
        self._context = {}                 # WorldModel-dependent

    def get_capability(self, name: str) -> Capability:
        """合并三层: static为基础, dynamic覆盖, context限制"""
        static = self._static.get(name)
        dynamic = self._dynamic.get(name)
        context = self._context.get(name)
        return merge_capabilities(static, dynamic, context)

    def update_dynamic(self, name: str, value: Any) -> None:
        """运行时更新动态能力 (gripper过热/payload变化等)"""
        self._dynamic[name] = value

    def update_context(self, name: str, world_model: WorldModel) -> None:
        """结合WorldModel更新上下文能力 (可达性/碰撞等)"""
        self._context[name] = compute_context_capability(name, world_model)
```

**用途**: Skill Runtime执行前查询能力(三层合并), Agent(M7)查询能力做任务规划。

### 3. Hardware Adapter — 硬件适配

```
换机器人 = robot.yaml + capability.yaml + hardware_adapter

UR5e:     joint_position, 6DOF, 无力控
Franka:   joint_torque, 7DOF, 力控
Humanoid: whole_body_control
```

### 4. 代码生成

```
robot.yaml + capability.yaml
  ↓
Robot Description Layer
  ├── → URDF (xacro展开)
  ├── → SRDF (MoveIt语义)
  ├── → controllers.yaml (ros2_control)
  └── → moveit_config (规划组/运动学/控制器)
```

### 新增接口

```yaml
# M6.0新增srv — 动态Capability查询
GetCapability.srv:
  request:
    capability_name: string       # "manipulation"|"gripper"|"vision"|"all"
    include_dynamic: bool         # 是否包含动态+上下文能力
    context: string               # 可选: "zone_a"|"object:red_cube" (上下文能力需要)
  response:
    capabilities: CapabilityInfo[]

# M6.0新增msg
CapabilityInfo.msg:
  name: string
  category: string                # "static"|"dynamic"|"context"
  available: bool
  value: string                   # JSON序列化能力值
  reason: string                  # 不可用原因 (如"overheated"/"out_of_workspace")

# M6.0新增topic — 能力变化通知
/capability/updates: CapabilityInfo (RELIABLE, depth=10)
```

### 验收标准

| 验收项 | 通过条件 |
|--------|----------|
| robot.yaml | 声明所有组件，参数化驱动 |
| capability.yaml | 声明Static Capability（固有能力） |
| 动态Capability Registry | 三层能力: Static+Dynamic+Context, 运行时可查询 |
| Capability变化通知 | 能力变化时发布/capability/updates |
| 代码生成 | YAML → URDF/SRDF/controllers自动生成 |
| 向后兼容 | 现有multi_arm_robot.xacro仍可用 |
| 换硬件 | robot.yaml + capability.yaml + adapter，上层接口不变 |

---

## M6.S Simulation Infrastructure (提前)

**目标**: 仿真本身是平台 — Robot Simulation OS，横向贯穿M6.1-M6.6

### 为什么提前到M6.0之后

```
M6.1 Perception:  需要Gazebo Camera + synthetic data
M6.2 Manipulation: 需要Gazebo物理附着
M6.3 Skill:        需要仿真环境执行+训练
M6.5 Runtime API:  需要仿真验证接口

Simulation是Runtime的执行环境之一, 不是事后验证工具
```

### 为什么是正式阶段而非辅助

```
Perception: 需要synthetic data
Skill:      需要百万次训练
Agent:      需要simulation environment
```

### 1. 场景生成

```
Random Scene Generator
  ├── 随机物体放置
  ├── 随机光照
  ├── 随机纹理
  └── 随机物理参数
```

### 2. Domain Randomization

```yaml
randomization:
  lighting:
    intensity: [0.5, 1.5]
    direction: random
  texture:
    pool: ["wood", "metal", "plastic"]
  object_position:
    jitter: 0.05  # ±5cm
  physics:
    friction: [0.3, 0.8]
    mass: [0.1, 2.0]
```

### 3. Dataset Pipeline

```
Gazebo (随机场景)
  ↓
sensor data (RGB+Depth+JointState)
  ↓
dataset (标注自动生成, Ground Truth)
  ↓
training (Vision/Skill Learning)
```

### 4. 仿真作为Runtime执行环境

```
Real Robot Mode:  Hardware Adapter → UR Driver → 真实UR5e
Simulation Mode:   Gazebo Plugin → 仿真UR5e
                   ↑ Domain Randomization
                   ↑ Scene Generator

两种模式共享: robot.yaml + capability.yaml + Skill Runtime + WorldModel
```

### 验收标准

| 验收项 | 通过条件 |
|--------|----------|
| 场景生成器 | 随机生成多样化场景 |
| Domain Randomization | 光照/纹理/位置/物理随机化 |
| Dataset Pipeline | Gazebo → 数据集自动采集 |
| Ground Truth | Gazebo提供精确标注 |
| 仿真/实体切换 | 共享robot.yaml, 仅Hardware Adapter不同 |

---

## M6.1 Perception + WorldModel

**目标**: 感知与世界模型绑定 — 没有WorldModel的Perception不是机器人智能

### 完整链路

```
Sensor → Perception → WorldModel → Reasoning → Action
```

### 1. Perception Node

```
Camera (RGB + Depth)
  ↓
Perception Node (multi_arm_perception)
  ├── 物体检测 (Gazebo Ground Truth / YOLOv8)
  ├── 位姿估计
  └── 语义分割
  ↓
/perception/object_poses (ObjectPose[])  # 已由WorldModel订阅
```

### 2. WorldModel升级 — 5层架构

```
WorldModel
  ├── Entity Layer     — 实体定义 (Robot/Object/Obstacle/Zone的ID+类型)
  ├── State Layer      — 实体状态 (位姿/速度/关节角/grasp_state)
  ├── Relation Layer   — 实体间关系 (on/near/inside/attached/above/below)  ← 新增
  ├── History Layer    — 状态历史 (时间序列, 趋势分析)
  └── Prediction Layer — 状态预测 (运动预测/碰撞预测/到达时间估计)
```

```python
WorldModel:
  # Entity Layer — 实体定义
  entities:
    arm1: Entity(type="robot_arm", id="arm1")
    red_cube: Entity(type="object", id="red_cube")
    table: Entity(type="surface", id="table")
    zone_a: Entity(type="zone", id="zone_a")

  # State Layer — 实体状态
  state:
    arm1:
      joint_positions: [j1, j2, j3, j4, j5, j6]
      joint_velocities: [v1, v2, v3, v4, v5, v6]
    red_cube:
      pose: [x, y, z, qx, qy, qz, qw]
      velocity: [vx, vy, vz]
      confidence: 0.93
      attached_to: "arm1_gripper"     # M6.2填充
      grasp_state: "ATTACHED"         # "FREE"|"ATTACHED"|"RELEASING"

  # Relation Layer — 实体间关系 (Skill判断的关键依赖)
  relations:
    - Relation(subject="red_cube", predicate="on", object="table", confidence=0.95)
    - Relation(subject="red_cube", predicate="attached_to", object="arm1_gripper")
    - Relation(subject="arm1", predicate="near", object="zone_a", distance=0.12)
    - Relation(subject="red_cube", predicate="inside", object="zone_a")
    - Relation(subject="arm2", predicate="above", object="table", height=0.45)

  # History Layer — 状态历史
  history:
    red_cube:
      poses: TimeSeries(pose, max_length=100)
      last_update: timestamp
    arm1:
      joint_history: TimeSeries(joint_positions, max_length=100)

  # Prediction Layer — 状态预测
  prediction:
    arm1:
      estimated_arrival: 2.3  # 秒, 到达目标的估计时间
      collision_risk: 0.05    # 当前轨迹碰撞概率
    red_cube:
      predicted_pose: [x', y', z']  # 0.5秒后预测位姿
```

**Relation Layer是Skill判断的关键依赖**:
```
Skill: place_object(object, location)
  precondition: object attached_to gripper
  postcondition: object on location

  ↓ 查询Relation Layer
  Relation(object, "attached_to", gripper) == True → precondition满足
  执行后: Relation(object, "on", location) == True → postcondition满足
```

### 3. 感知-认知闭环

```
"pick red_cube"
  ↓
Perception: 检测红色物体 → 3D位姿
  ↓
WorldModel: 更新State Layer (red_cube: pose, confidence=0.93, grasp_state=FREE)
  ↓
WorldModel: 更新Relation Layer (red_cube on table, red_cube inside zone_a)
  ↓
TaskPlanner: 查询WorldModel → 获取red_cube位姿+关系
  ↓
Coordinator: 规划抓取轨迹
  ↓
Robot: 执行
  ↓
WorldModel: 更新 (red_cube: attached_to=arm1, grasp_state=ATTACHED)
  ↓
WorldModel: 更新Relation (red_cube attached_to arm1_gripper, red_cube NOT on table)
```

### 4. 新增接口

```yaml
# M6.1新增msg
SceneState.msg:
  objects: ObjectPose[]
  obstacles: ObjectPose[]
  timestamp: float64

TaskState.msg:
  task_id: string
  status: string
  progress: float32
  elapsed_time: float64

# ObjectState扩展 (不修改FROZEN的ObjectPose, 新增ObjectState.msg)
ObjectState.msg:
  object_id: string
  pose: ObjectPose
  velocity: float64[3]
  attached_to: string          # "arm1_gripper"|"" (空=未附着)
  grasp_state: string          # "FREE"|"ATTACHED"|"RELEASING"

# M6.1新增 — Relation Layer
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
QueryWorld.srv:
  request:
    query_type: string        # "robot"|"object"|"scene"|"task"|"relation"|"all"
    entity_id: string         # 可选: 查询特定实体
    relation_predicate: string # 可选: 查询特定关系 (如"on")
  response:
    object_states: ObjectState[]
    scene_state: SceneState
    task_state: TaskState
    relations: Relation[]      # Relation Layer查询结果

QueryRelation.srv:             # 专门查询关系
  request:
    subject: string            # 可选
    predicate: string          # 可选
    object: string             # 可选
  response:
    relations: Relation[]
    exists: bool

# 已预留topic (WorldModel已订阅)
/perception/object_poses: ObjectPose (RELIABLE, depth=10)
```

### 验收标准

| 验收项 | 通过条件 |
|--------|----------|
| Gazebo Camera | RGB+Depth图像正确发布 |
| 物体检测 | 检测Gazebo中物体，输出ObjectPose |
| WorldModel Entity Layer | 实体定义(Robot/Object/Obstacle/Zone) |
| WorldModel State Layer | 缓存物体位姿+grasp_state+attached_to |
| WorldModel Relation Layer | 维护on/near/inside/attached关系 |
| WorldModel History Layer | 状态时间序列历史 |
| WorldModel Prediction Layer | 运动预测/碰撞预测 |
| 感知-认知闭环 | "pick red_cube" → 检测 → WorldModel更新 → 规划 → 执行 |
| Agent查询接口 | QueryWorld.srv返回完整世界状态(含关系) |

---

## M6.2 Manipulation Layer

**目标**: 从"运动控制系统"进入"操作系统" — Gripper + Object attachment + Force feedback

### 为什么是Manipulation Layer而非仅Gripper

```
没有Gripper: MoveTo(position) = 机械臂运动控制系统
有Gripper:   MoveTo + Grasp + Attach + Force = 操作系统
```

### 1. Robotiq Gripper集成

```
UR5e + Robotiq 2F-85 Gripper
  ├── gripper_controller (position_controllers/GripperActionController)
  ├── Gazebo物理附着 (grabber plugin)
  └── 力反馈 (M6.2基础版, 力控属M6.0 Capability)
```

### 2. 完整PickPlace链路

```
Perception: 检测物体位姿
  ↓
GraspPlanner: 计算抓取姿态
  ↓
MoveTo: 移动到抓取接近位
  ↓
Grasp: 闭合Gripper
  ↓
Attach: Gazebo物理附着
  ↓
WorldModel: 更新State (object: attached_to=arm1, grasp_state=ATTACHED)
  ↓
WorldModel: 更新Relation (object attached_to arm1_gripper, object NOT on table)
  ↓
Lift: 抬起物体
  ↓
MoveTo: 移动到放置位
  ↓
Place: 张开Gripper
  ↓
Detach: Gazebo物理分离
  ↓
WorldModel: 更新State (object: attached_to="", grasp_state=FREE)
  ↓
WorldModel: 更新Relation (object on target_surface, object NOT attached_to arm1)
```

### 3. 新增接口

```yaml
# M6.2新增srv
ControlGripper.srv:
  request:
    arm_name: string
    command: string        # "open"|"close"|"attach"|"detach"
    object_id: string
    force: float64
  response:
    success: bool
    message: string

# M6.2新增action
GraspObject.action:
  goal:
    arm_name: string
    object_id: string
    approach: string       # "top"|"side"|"front"
  result:
    success: bool
    message: string
    attached: bool
  feedback:
    status: string
    progress: float32
```

### 验收标准

| 验收项 | 通过条件 |
|--------|----------|
| Robotiq URDF | Gazebo加载UR5e+Gripper模型 |
| Gripper Controller | open/close控制成功 |
| 物理附着 | Gazebo中物体附着到Gripper |
| Manipulation State | WorldModel更新object attached_to/grasp_state |
| Relation更新 | WorldModel更新attached_to/on关系 |
| 完整PickPlace | 检测→抓取→搬运→放置 全链路成功 |

---

## M6.3 Skill Runtime

**目标**: Skill = Manifest + Capability + Preconditions + Execution + Postcondition + Recovery + **Lifecycle**

### Skill ≠ BT包装

```
❌ 退化: Skill = 漂亮的任务脚本 (BT XML包装)
✅ 正确: Skill = 软件包 (类似pip install, 机器人获得能力) + 生命周期管理
```

### 1. Skill Manifest — 类似package.json

```yaml
# skills/pick_object/skill.yaml (Skill Manifest)
skill:
  name: pick_object
  version: "1.0.0"
  description: "Pick up an object from a specified location"

  # 依赖的机器人能力
  required_capabilities:
    manipulation: true
    gripper: true
    vision: true

  # 输入参数
  input:
    object_id: string
    arm_name: string
    approach: string         # "top"|"side"|"front"

  # 输出
  output:
    object_state: ObjectState   # 抓取后的物体状态

  # 成本估计 (Agent选择Skill依据)
  cost:
    time: 5.0                # 预估执行时间(秒)
    risk: 0.1                # 风险等级(0-1)
    success_rate: 0.95       # 历史成功率

  # 前置条件 (查询WorldModel Relation Layer)
  preconditions:
    - "object exists in WorldModel"
    - "arm is idle"
    - "gripper is open"
    - "zone is accessible"
    - "NOT (object attached_to any_gripper)"  # Relation查询

  # 执行步骤
  execute:
    - perceive_object(object_id)
    - plan_grasp(object_id, approach)
    - move_to_grasp_approach()
    - grasp_object(object_id)
    - lift_object()

  # 后置条件 (查询WorldModel Relation Layer)
  postconditions:
    - "object attached_to gripper"            # Relation查询
    - "object above table"                    # Relation查询

  # 恢复策略
  recovery:
    grasp_failed: retry(3) → change_approach → abort
    planning_failed: relax_constraints → replan → abort
    object_lost: re_perceive → re_plan → abort
```

### 2. Skill Lifecycle — 类似K8s Pod生命周期

```
Install → Register → Validate → Ready → Execute → Monitor → Update → Remove

Install:   Skill包安装到skills/目录
Register:  Skill Registry注册 (解析Manifest)
Validate:  检查required_capabilities + preconditions可行性
Ready:     Skill可用, 等待执行请求
Execute:   运行Skill (检查pre → 执行 → 检查post → recovery)
Monitor:   收集执行数据 (success_rate/cost更新) → Data Layer
Update:    Skill版本升级 (热更新, 不中断当前执行)
Remove:    Skill卸载 (等待当前执行完成)
```

```python
class SkillLifecycleState(Enum):
    INSTALLED = "installed"      # 包已安装
    REGISTERED = "registered"    # Registry已注册
    VALIDATED = "validated"      # 能力+前置条件检查通过
    READY = "ready"              # 可执行
    EXECUTING = "executing"      # 正在执行
    MONITORING = "monitoring"    # 执行后监控
    UPDATING = "updating"        # 版本更新中
    REMOVING = "removing"        # 卸载中
    REMOVED = "removed"          # 已卸载
    INVALID = "invalid"          # 验证失败

class SkillLifecycle:
    """Skill生命周期管理, 类似K8s Pod"""

    def install(self, skill_package: str) -> SkillId:
        """安装Skill包到skills/目录"""
        ...

    def register(self, skill_id: SkillId) -> None:
        """解析Manifest, 注册到Skill Registry"""
        ...

    def validate(self, skill_id: SkillId) -> bool:
        """检查required_capabilities (查询Capability Registry三层)
        检查preconditions可行性 (查询WorldModel)
        """
        ...

    def execute(self, skill_id: SkillId, params: dict) -> SkillResult:
        """Ready → Execute: 检查pre → 执行 → 检查post → recovery"""
        ...

    def monitor(self, skill_id: SkillId, result: SkillResult) -> None:
        """收集执行数据 → 更新success_rate/cost → Data Layer"""
        ...

    def update(self, skill_id: SkillId, new_version: str) -> None:
        """热更新Skill版本, 不中断当前执行"""
        ...

    def remove(self, skill_id: SkillId) -> None:
        """等待当前执行完成 → 卸载Skill"""
        ...
```

**没有Lifecycle的后果**: Skill Library变成文件仓库, 无法管理版本/依赖/状态。

### 3. Skill Registry — Agent选择Skill依据

```
Agent: "把杯子放到桌子"
  ↓
Skill Registry: 搜索可用Skill (仅READY状态)
  ├── pick_object (cost: 5s, risk: 0.1, success: 0.95)
  ├── move_object (cost: 3s, risk: 0.05, success: 0.98)
  └── place_object (cost: 4s, risk: 0.08, success: 0.96)
  ↓
根据 capability/cost/risk/success_rate 选择
  ↓
组合: pick_object → move_object → place_object
```

### 4. Skill Runtime执行

```
Agent → ExecuteSkill(skill_name, parameters)
  ↓
Skill Runtime:
  1. 检查Lifecycle状态 == READY
  2. 检查required_capabilities (查询动态Capability Registry三层)
  3. 检查preconditions (查询WorldModel Relation Layer)
  4. 执行execute (调用Perception/Coordinator/Gripper)
  5. 检查postconditions (查询WorldModel Relation Layer)
  6. 失败 → recovery
  7. Monitor: 更新success_rate/cost → Data Layer
```

### 5. 新增接口

```yaml
# M6.3新增msg
SkillDescription.msg:
  name: string
  version: string
  required_capabilities: string[]
  preconditions: string[]
  postconditions: string[]
  parameters: string[]
  cost_time: float64
  cost_risk: float64
  success_rate: float64

SkillStatus.msg:
  skill_id: string
  name: string
  version: string
  lifecycle_state: string     # "installed"|"ready"|"executing"|...
  last_executed: float64
  total_executions: int32
  success_count: int32

# M6.3新增srv
ListSkills.srv:
  request:
    required_capabilities: string[]
    lifecycle_state: string    # 可选: 仅返回指定状态的Skill
  response:
    skills: SkillDescription[]

ManageSkill.srv:               # Skill Lifecycle管理
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
```

### 验收标准

| 验收项 | 通过条件 |
|--------|----------|
| Skill Manifest | 包含required_capabilities/input/output/cost/pre/post/recovery |
| Skill Lifecycle | Install→Register→Validate→Ready→Execute→Monitor→Update→Remove |
| Skill Registry | ListSkills返回READY状态Skill列表 |
| Skill Runtime | ExecuteSkill.action执行成功 |
| Capability检查 | Skill执行前查询动态Capability Registry三层 |
| precondition | 前置条件检查正确（查询WorldModel Relation Layer） |
| postcondition | 后置条件验证正确（查询WorldModel Relation Layer） |
| recovery | Skill失败→恢复策略执行 |
| 执行监控 | Monitor更新success_rate/cost → Data Layer |
| BT兼容 | 现有BT XML可包装为Skill |
| Skill组合 | 多Skill可串联（pick→move→place） |
| 热更新 | Skill版本升级不中断当前执行 |

---

## M6.5 Robot Runtime API (重命名)

**目标**: M6只提供能力接口，不包含自然语言理解（语言理解属M7）

### 重命名理由

```
❌ 旧名: Agent Capability Interface — M6没有Agent, 名称误导
✅ 新名: Robot Runtime API — 准确反映M6提供的是Runtime能力接口
```

### 边界划分

```
M6提供: ExecuteSkill, QueryWorld, GetCapability, ListSkills, ManageSkill, SubmitTaskGoals
M7负责: 自然语言理解, 规划, 推理, 任务拆解, Agent决策
```

```
Agent (M7)
  ↓ 自然语言→TaskGoal[]
Robot Runtime API (M6.5)
  ↓ ExecuteSkill/QueryWorld/GetCapability/ListSkills/ManageSkill
Skill Runtime (M6.3)
  ↓
WorldModel (M6.1) → Coordinator → Robot
```

### 接口

```yaml
# M6.5提供的Robot Runtime API (M7 Agent调用)
# 已在M6.0定义: GetCapability.srv (动态能力查询)
# 已在M6.1定义: QueryWorld.srv, QueryRelation.srv (世界状态+关系查询)
# 已在M6.3定义: ExecuteSkill.action, ListSkills.srv, ManageSkill.srv (Skill管理+执行)

# M6.5新增: 任务提交接口 (结构化, 非自然语言)
SubmitTaskGoals.srv:
  request:
    task_goals: TaskGoal[]     # 引用已冻结的TaskGoal
    strategy: string           # "sequential"|"parallel"|"best_effort"
  response:
    task_ids: string[]
    accepted: bool
    message: string

# M7负责: 自然语言→TaskGoal[] (不属于M6)
# SubmitNaturalLanguage.srv → M7实现, 调用M6.5的SubmitTaskGoals
```

### 验收标准

| 验收项 | 通过条件 |
|--------|----------|
| Robot Runtime API | ExecuteSkill/QueryWorld/GetCapability/ListSkills/ManageSkill/SubmitTaskGoals |
| TaskGoal引用 | 接口引用M5.7冻结的TaskGoal |
| 边界清晰 | M6不含自然语言理解，M7负责 |
| Skill调用 | SubmitTaskGoals → ExecuteSkill → Coordinator链路 |
| 能力查询 | GetCapability返回三层能力(Static+Dynamic+Context) |

---

## M6.6 Mobile Base (后置)

**目标**: 从固定机械臂升级为移动操作机器人

### 后置理由

```
正确路线: 固定操作机器人 → 移动操作机器人
  先保证运动控制 → 再操作 → 再自主任务
Navigation2+SLAM复杂度高，后置
```

### 新增接口

```yaml
BodyState.msg:
  base_position: float64[3]    # x, y, theta
  base_velocity: float64[3]
  localized: bool

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

### 验收标准

| 验收项 | 通过条件 |
|--------|----------|
| Mobile Base URDF | Gazebo加载移动底盘 |
| Navigation2 | 自主导航到目标位 |
| SLAM | 建图成功 |
| 移动+操作 | 导航到桌边→抓取→导航到放置位 |

---

## Data Layer (横向贯穿)

**目标**: Robot Data Pipeline — 类似软件的Observability, M7 Agent学习的数据来源

### 为什么需要Data Layer

```
软件系统: Observability = Metrics + Logs + Traces
机器人系统: Data Pipeline = Sensor Data + Episode Data + Skill Log + Failure Data + WorldModel Snapshot + Training Dataset

没有Data Layer:
  - Skill success_rate无法更新 (Monitor无数据)
  - M7 Agent无法学习 (无训练数据)
  - 调试困难 (无执行回放)
  - 性能退化无法检测 (无历史对比)
```

### 六类数据

```
1. Sensor Data        — 原始传感器流 (RGB/Depth/JointState), 高频, 短期存储
2. Episode Data       — 任务执行episode (从开始到结束的完整记录), 中频, 中期存储
3. Skill Execution Log — Skill执行日志 (参数/结果/耗时/recovery), 低频, 长期存储
4. Failure Data       — 失败案例 (失败原因/上下文/recovery结果), 低频, 长期存储
5. WorldModel Snapshot — 世界模型快照 (定期/事件触发), 中频, 中期存储
6. Training Dataset   — 训练数据集 (从上述数据生成), 离线, 永久存储
```

### 数据流

```
Robot Runtime (M6.0-M6.6)
  ↓ 采集
Data Pipeline
  ├── Sensor Data → 短期存储 (ring buffer, 1小时)
  ├── Episode Data → 中期存储 (SQLite, 7天)
  ├── Skill Log → 长期存储 (SQLite, 永久)
  ├── Failure Data → 长期存储 (SQLite, 永久)
  ├── WorldModel Snapshot → 中期存储 (SQLite, 7天)
  └── Training Dataset → 永久存储 (文件系统/对象存储)
  ↓
M7 Agent: 从Training Dataset学习, 从Skill Log更新策略
```

### 与M5.4 Benchmark的关系

```
M5.4 Benchmark: 采集执行指标 (planning_time/execution_time/success_rate) → SQLite
M6 Data Layer:  扩展为完整数据管道 (含Sensor/Episode/Skill/Failure/WorldModel/Dataset)

M5.4的benchmark.db是Data Layer的一部分 (Skill Execution Log的子集)
```

### 新增接口

```yaml
# Data Layer新增srv
QueryData.srv:
  request:
    data_type: string          # "sensor"|"episode"|"skill_log"|"failure"|"worldmodel"|"dataset"
    time_range: TimeRange      # 开始/结束时间
    filter: string             # 可选: 过滤条件 (JSON)
  response:
    records: string[]          # JSON序列化数据记录
    count: int32

RecordEpisode.srv:             # 记录任务执行episode
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

### 验收标准

| 验收项 | 通过条件 |
|--------|----------|
| Sensor Data采集 | 原始传感器流ring buffer存储 |
| Episode Data记录 | 任务执行完整episode记录到SQLite |
| Skill Log记录 | Skill执行日志(参数/结果/耗时/recovery) |
| Failure Data记录 | 失败案例(原因/上下文/recovery结果) |
| WorldModel Snapshot | 定期+事件触发快照 |
| Training Dataset | 从上述数据生成训练数据集 |
| Skill Monitor集成 | Skill执行后Monitor更新success_rate (读Skill Log) |
| M7数据接口 | QueryData.srv供M7查询训练数据 |
| M5.4兼容 | benchmark.db作为Skill Log子集 |

---

## M6接口变更汇总

### 新增msg

| msg | 阶段 | 用途 |
|-----|------|------|
| CapabilityInfo.msg | M6.0 | 动态能力信息(三层) |
| ObjectState.msg | M6.1 | 物体状态(含attached_to/grasp_state) |
| SceneState.msg | M6.1 | 环境布局 |
| TaskState.msg | M6.1 | 任务状态 |
| Relation.msg | M6.1 | 实体间关系(on/near/inside/attached) |
| RelationGraph.msg | M6.1 | 关系图(关系集合) |
| SkillDescription.msg | M6.3 | Skill Manifest |
| SkillStatus.msg | M6.3 | Skill Lifecycle状态 |
| BodyState.msg | M6.6 | 移动底盘状态 |

### 新增srv

| srv | 阶段 | 用途 |
|-----|------|------|
| GetCapability.srv | M6.0 | 查询三层能力(Static+Dynamic+Context) |
| QueryWorld.srv | M6.1 | 查询完整世界(含关系) |
| QueryRelation.srv | M6.1 | 专门查询实体间关系 |
| ControlGripper.srv | M6.2 | Gripper控制 |
| ListSkills.srv | M6.3 | 列出可用Skill(按Lifecycle状态) |
| ManageSkill.srv | M6.3 | Skill Lifecycle管理(install/update/remove) |
| SubmitTaskGoals.srv | M6.5 | 提交结构化任务 |
| QueryData.srv | Data | 查询数据管道数据 |
| RecordEpisode.srv | Data | 记录任务执行episode |

### 新增action

| action | 阶段 | 用途 |
|--------|------|------|
| GraspObject.action | M6.2 | 抓取物体 |
| ExecuteSkill.action | M6.3 | 执行Skill |
| NavigateTo.action | M6.6 | 导航 |

### 新增topic

| topic | 阶段 | 用途 |
|-------|------|------|
| /perception/object_poses | M6.1 | 感知结果 (已预留) |
| /perception/scene_update | M6.1 | 场景更新 |
| /capability/updates | M6.0 | 能力变化通知 |
| /data/episode | Data | Episode数据流 |
| /data/failure | Data | 失败数据流 |
| /data/skill_log | Data | Skill执行日志流 |

---

## M6与Interface Freeze v1.0的关系

```
M5.7冻结: ExecuteTask, TaskGoal, SafetyCheck, QueryResources, ... (v1.0)

M6规则:
  ✅ 新增msg/srv/action (不修改FROZEN接口)
  ✅ 末尾追加字段 (有默认值)
  ❌ 修改FROZEN字段

M6.1扩展查询:
  QueryResources保持不变 (FROZEN)
  新增QueryWorld.srv (扩展查询能力, 含Relation Layer)
  WorldModel同时提供两个Service
```

---

## M6完成后系统定位

```
M5完成: Robot OS Kernel — 能完成任务且鲁棒的执行机器人
M6完成: Robot OS Runtime — 具备身体、仿真、感知、世界模型、操作、技能、数据管道的机器人操作系统运行时

  Agent (M7): 自然语言→TaskGoal[]
    ↓
  Robot Runtime API (M6.5): ExecuteSkill/QueryWorld/GetCapability/ManageSkill
    ↓
  Skill Runtime (M6.3): Skill五要素 + Manifest + Registry + Lifecycle
    ↓
  World Model (M6.1): 5层 (Entity/State/Relation/History/Prediction) ← Perception
    ↓
  Task Planner → Coordinator → Safety
    ↓
  Robot Description Layer (M6.0): robot.yaml + 动态Capability Registry
    ├── Manipulation (arm1 + arm2)
    ├── End Effector (Gripper, M6.2)
    ├── Mobile Base (M6.6)
    └── Sensors (Camera, M6.1)

  Simulation Infrastructure (M6.S) — 贯穿M6.0-M7
  Data Layer — 横切, 供M7学习
```

---

## M6/M7边界

```
M6 (Runtime): 能力接口、世界模型、技能执行+生命周期、仿真、数据管道
M7 (Intelligence): 自然语言理解、任务规划、推理、Agent决策、学习

M6提供: ExecuteSkill, QueryWorld, GetCapability, ListSkills, ManageSkill, SubmitTaskGoals, QueryData
M7负责: SubmitNaturalLanguage, 任务拆解, Skill选择, 执行监控, 从Data Layer学习
```
