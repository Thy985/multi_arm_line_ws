# 架构设计文档 - 双UR5e多机械臂ROS2仿真与协调控制系统

| 字段 | 内容 |
|------|------|
| 版本 | v2.1 |
| 作者 | Thy985 |
| 日期 | 2026-08-05 |
| 状态 | Draft |
| 变更说明 | v2.0→v2.1：Safety重构为横切平面、WorldModel所有权边界限定、BehaviorTree采用BT.CPP、新增Recovery层、Task接口拆分、Benchmark场景化 |

---

## 1. 文档信息

本文档描述双UR5e多机械臂系统的目标架构设计。v2.1基于工程实现反馈，重点解决：Safety从单层重构为横切平面、WorldModel数据所有权边界、BehaviorTree工程选型、故障恢复层缺失、接口消息膨胀等问题。

---

## 2. 系统全景

### 2.1 设计原则

| 原则 | 描述 |
|------|------|
| 分层解耦 | 7层功能层 + Safety横切平面，各层通过接口包通信 |
| Safety横切 | Safety不是流水线中的一层，而是贯穿所有功能层的横切平面 |
| 接口先行 | 所有跨节点/跨包通信必须通过multi_arm_interfaces定义 |
| 编排不实现 | Coordinator是编排引擎，不包含业务逻辑 |
| 真相源分离 | WorldModel拥有世界认知，ros2_control拥有实时控制状态，Safety拥有安全状态 |
| 可度量 | Benchmark模块记录所有执行数据，场景化驱动 |
| 可恢复 | Recovery层独立于Safety，负责故障诊断与策略恢复 |

---

## 3. 系统分层架构（7层 + Safety Plane）

```
┌─────────────────────────────────────────────────────────────────┐
│  L7  应用层 Application                                         │
│       PickPlace / Assembly / Inspection / VisualServo           │
├─────────────────────────────────────────────────────────────────┤
│  L6  任务规划层 Task Planning                                    │
│       TaskManager + BehaviorTree.CPP + Task Decomposition       │
├─────────────────────────────────────────────────────────────────┤
│  L5  环境模型层 World Model                                      │
│       Objects / Environment / Task Context (缓存Robot State)     │
├─────────────────────────────────────────────────────────────────┤
│  L4  协调层 Coordination                                         │
│       ResourceManager + Scheduler + MultiRobotCoordinator       │
├─────────────────────────────────────────────────────────────────┤
│  L3  运动规划层 Motion Planning                                  │
│       MoveIt2 + IK + Collision + Trajectory Optimization        │
├─────────────────────────────────────────────────────────────────┤
│  L2  控制层 Control                                              │
│       ros2_control + JTC + GripperController                    │
├─────────────────────────────────────────────────────────────────┤
│  L1  硬件层 Hardware                                             │
│       Gazebo / UR Driver / Sensors / Fixtures                   │
└─────────────────────────────────────────────────────────────────┘

╔═════════════════════════════════════════════════════════════════╗
║  Safety Plane (横切平面，贯穿L1-L7)                              ║
║  SafetySupervisor + SpeedLimiter + WorkspaceLimiter + E-Stop    ║
║  ─ 对L6: 任务安全约束    对L3: 碰撞约束   对L2: 速度限制 ─      ║
╚═════════════════════════════════════════════════════════════════╝

╔═════════════════════════════════════════════════════════════════╗
║  System Services (横向基础设施)                                  ║
║  Diagnostics + StructuredLogger + Benchmark + Recovery          ║
╚═════════════════════════════════════════════════════════════════╝
```

### 3.1 Safety Plane详解

Safety不是流水线中的一层，而是横切所有功能层的平面：

```
              Safety Plane
                   │
    ┌──────────────┼──────────────┐
    │              │              │
    ▼              ▼              ▼
 L6 Task       L3 Motion       L2 Control
 安全约束:      碰撞约束:        速度限制:
 - 任务可行性   - 自碰撞检测     - 关节速度限制
 - 资源安全     - 双臂间碰撞     - 工作空间边界
 - 人机协作区   - 环境碰撞       - E-Stop拦截
```

**Safety Plane实现策略（分阶段）**：

| 阶段 | 方案 | 说明 |
|------|------|------|
| Phase 1-2 | 软件Safety Check | Coordinator发送前调用Safety服务检查，非硬实时 |
| Phase 3+ | Safety Proxy Controller | SafetySupervisor作为Action代理拦截轨迹命令 |
| 实体部署 | Hardware Safety Interface | 安全在ros2_control硬件接口层，硬实时保证 |

**Phase 1-2软件安全方案**：
```
Coordinator → SafetyCheck Service → 批准/拒绝 → JTC Action Client → JTC Action Server
```

**Phase 3+ Safety Proxy方案**：
```
Coordinator → /coordinator/trajectory_commands
                    │
                    ▼
          SafetySupervisor (Action Proxy)
                    │
          ┌─────────┼─────────┐
          │         │         │
     速度检查   边界检查   E-Stop检查
          │         │         │
          └─────────┼─────────┘
                    │ approved
                    ▼
          /safety/approved_trajectory → JTC Action Server
```

**实体部署方案**：
```
ros2_control Hardware Interface
        │
        ▼
  Safety Layer (硬实时)
        │
        ▼
  Robot Driver (TCP/IP → UR5e)
```

### 3.2 三个真相源

| 真相源 | 拥有者 | 数据 | 频率 |
|--------|--------|------|------|
| 实时控制状态 | ros2_control (L2) | joint_states, controller_state | 100-500Hz |
| 世界认知状态 | WorldModel (L5) | objects, environment, task_context | 1-10Hz |
| 安全状态 | SafetySupervisor (Safety Plane) | safety_level, limits, e-stop | 事件驱动 |

**WorldModel数据所有权边界**：

```
WorldModel 拥有:
  ├── Objects (物体位姿、类型、置信度)
  ├── Environment (工作空间布局、障碍物)
  └── Task Context (当前任务关联的环境快照)

WorldModel 缓存 (非拥有):
  └── Robot State (从/joint_states缓存，供上层查询)

WorldModel 不拥有:
  ├── Real-time control state (→ ros2_control)
  └── Safety state (→ SafetySupervisor)
```

**关键规则**：500Hz的joint_state不进入WorldModel，WorldModel仅以1-10Hz缓存机器人位姿供任务层查询。实时控制回路直接使用ros2_control的joint_states。

---

## 4. 包拓扑架构

### 4.1 目标包结构

```
src/
├── multi_arm_interfaces/            # 接口定义包 (ament_cmake)
│   ├── msg/
│   │   ├── TaskDescription.msg      # 任务描述（纯语义）
│   │   ├── TaskStatus.msg           # 任务运行状态
│   │   ├── TaskRequirement.msg      # 任务资源需求
│   │   ├── ObjectPose.msg
│   │   ├── CollisionEvent.msg
│   │   ├── SystemHealth.msg
│   │   ├── ResourceStatus.msg
│   │   └── RecoveryAction.msg
│   ├── srv/
│   │   ├── EmergencyStop.srv
│   │   ├── SubmitTask.srv
│   │   ├── QueryResources.srv
│   │   ├── SafetyCheck.srv
│   │   └── RecoverFromFailure.srv
│   └── action/
│       ├── PickPlace.action
│       └── ExecuteTask.action
│
├── multi_arm_core/                  # 协调控制包 (ament_python)
│   └── multi_arm_core/
│       ├── coordinator_node.py      # 编排引擎（薄层）
│       ├── coordination/
│       │   ├── resource_manager.py
│       │   ├── capability_matcher.py
│       │   └── time_manager.py
│       ├── scheduler/
│       │   ├── scheduler.py
│       │   └── allocation_strategy.py
│       ├── task/
│       │   └── task_manager.py
│       └── safety/
│           └── safety_interface.py
│
├── multi_arm_world_model/           # 环境模型包
│   └── multi_arm_world_model/
│       ├── world_model_node.py
│       ├── object_tracker.py
│       └── state_database.py
│
├── multi_arm_task_planner/          # 任务规划包
│   └── multi_arm_task_planner/
│       ├── task_planner_node.py
│       ├── bt_xml/
│       │   ├── pick_place.xml
│       │   ├── assembly.xml
│       │   └── inspection.xml
│       └── bt_plugins/
│           ├── move_to_node.py
│           ├── grasp_node.py
│           ├── place_node.py
│           └── check_safety_node.py
│
├── multi_arm_safety/                # 安全平面包
│   └── multi_arm_safety/
│       ├── safety_supervisor.py
│       ├── speed_limiter.py
│       ├── workspace_limiter.py
│       └── collision_monitor.py
│
├── multi_arm_recovery/              # 故障恢复包
│   └── multi_arm_recovery/
│       ├── recovery_manager.py
│       ├── failure_detector.py
│       └── recovery_strategies/
│           ├── grasp_retry.py
│           ├── replan_motion.py
│           ├── communication_reset.py
│           └── collision_recovery.py
│
├── multi_arm_moveit_config/         # MoveIt2配置包
├── multi_arm_manipulation/          # 抓取操作包
├── multi_arm_perception/            # 视觉感知包
│
├── multi_arm_benchmark/             # 基准测试包
│   └── multi_arm_benchmark/
│       ├── benchmark_recorder.py
│       ├── metrics_collector.py
│       ├── report_generator.py
│       └── scenarios/
│           ├── pick_place_easy.yaml
│           ├── pick_place_dense.yaml
│           └── multi_arm_collision.yaml
│
├── order_manager/                   # [遗留] 过渡期保留
└── ur_simulation_gz/                # Gazebo仿真包
```

---

## 5. 核心模块详细架构

### 5.1 Coordinator（编排引擎）

```
coordinator_node.py (编排引擎 - 薄层)
├── 订阅：/world_model/state, /safety/status, /recovery/events
├── 发布：/coordinator/commands
├── 服务：/coordinator/submit_task, /coordinator/query_resources
│
├── 持有子模块（组合）：
│   ├── ResourceManager + CapabilityMatcher
│   ├── Scheduler + AllocationStrategy
│   ├── TaskManager
│   └── SafetyInterface
│
└── 编排流程：
    1. 接收任务请求（来自L6 TaskPlanner）
    2. 查询WorldModel获取环境认知
    3. CapabilityMatcher匹配任务需求与资源能力
    4. ResourceManager分配资源
    5. Scheduler调度时间
    6. SafetyInterface请求Safety Plane批准
    7. 请求L3 MotionPlanning生成轨迹
    8. 下发轨迹到L2 Control
    9. 监控执行结果
    10. 失败时通知Recovery层
```

### 5.2 ResourceManager + CapabilityMatcher

```python
class Resource:
    name: str
    resource_type: ResourceType      # ROBOT | ZONE | TOOL | SENSOR | FIXTURE
    state: ResourceState             # FREE | ALLOCATED | RESERVED | ERROR
    allocated_to: Optional[str]
    capabilities: Dict[str, Any]

class CapabilityMatcher:
    """匹配任务需求与资源能力。"""
    def match(self, requirement: TaskRequirement,
              resources: List[Resource]) -> List[Resource]:
        """返回满足需求的资源列表，按匹配度排序。"""
        ...
```

**资源能力配置**：
```yaml
resources:
  robots:
    - name: arm1
      type: ur5e
      capabilities:
        payload_kg: 5.0
        gripper: robotiq_2f85
        precision_mm: 0.1
        reachable_zones: [zone_a, zone_b, home]
    - name: arm2
      type: ur5e
      capabilities:
        payload_kg: 5.0
        gripper: robotiq_2f85
        precision_mm: 0.02
        reachable_zones: [zone_a, zone_c, home]
```

### 5.3 WorldModel（环境认知真相源）

```
WorldModelNode
├── 拥有：
│   ├── Objects (物体位姿、类型、置信度、跟踪状态)
│   ├── Environment (工作空间布局、静态障碍物)
│   └── Task Context (当前任务关联的环境快照)
│
├── 缓存（非拥有）：
│   └── Robot State (从/joint_states缓存，1-10Hz更新)
│
├── 不拥有：
│   ├── Real-time control state (→ ros2_control, 100-500Hz)
│   └── Safety state (→ SafetySupervisor, 事件驱动)
│
├── 订阅：
│   ├── /perception/object_poses
│   ├── /arm{N}/joint_states (缓存)
│   └── /environment/updates
│
├── 发布：
│   ├── /world_model/state (1Hz)
│   └── /world_model/changes (事件驱动)
│
└── 服务：
    ├── /world_model/query_objects
    └── /world_model/query_robot_pose
```

### 5.4 TaskPlanner（BehaviorTree.CPP）

**工程选型**：采用BehaviorTree.CPP + XML定义，不自造轮子。

```
TaskPlannerNode
├── BehaviorTree.CPP
│   ├── bt_xml/ (行为树XML定义)
│   │   ├── pick_place.xml
│   │   ├── assembly.xml
│   │   └── inspection.xml
│   └── bt_plugins/ (Python插件)
│       ├── MoveToNode
│       ├── GraspNode
│       ├── PlaceNode
│       ├── CheckSafetyNode
│       ├── QueryWorldNode
│       └── RecoverNode
│
├── Action Server: /task_planner/execute_task
└── Action Client: /coordinator/execute_subtask
```

**pick_place.xml示例**：
```xml
<BehaviorTree ID="PickPlace">
  <Sequence name="pick_place_sequence">
    <Selector name="grasp_strategy">
      <Sequence name="top_grasp">
        <MoveTo goal="{approach_top}"/>
        <Grasp approach="top"/>
      </Sequence>
      <Sequence name="side_grasp">
        <MoveTo goal="{approach_side}"/>
        <Grasp approach="side"/>
      </Sequence>
    </Selector>
    <Lift height="0.1"/>
    <MoveTo goal="{place_approach}"/>
    <Place/>
    <Retract/>
  </Sequence>
</BehaviorTree>
```

**优势**：Groot可视化、运行时调试、XML在线修改、子树复用。

### 5.5 SafetySupervisor（Safety Plane）

```
SafetySupervisor (横切平面实现)
├── 对L6 Task层：任务可行性检查 + SafetyCheck.srv
├── 对L3 Motion层：碰撞检测 + CollisionMonitor
├── 对L2 Control层：速度限制 + 工作空间边界 + E-Stop
│
├── 安全层级：
│   ├── Level 0: NORMAL
│   ├── Level 1: SPEED_LIMITED
│   ├── Level 2: PAUSED
│   └── Level 3: EMERGENCY_STOP
│
└── 实现阶段：
    ├── Phase 1-2: SafetyCheck Service
    ├── Phase 3+: Safety Proxy Controller
    └── 实体: Hardware Safety Interface
```

### 5.6 Recovery层（故障恢复）

**Safety ≠ Recovery**：Safety负责"检测危险→停止"，Recovery负责"诊断故障→恢复→继续"。

```
RecoveryManager
├── 订阅：/safety/collision_events, /coordinator/task_failures, /diagnostics
├── 发布：/recovery/events
├── 服务：/recovery/recover (RecoverFromFailure.srv)
│
└── Recovery策略库：
    ├── GraspRetry        # 抓取失败→重试(更换approach)
    ├── ReplanMotion      # 规划失败→重规划(放宽约束)
    ├── CommunicationReset # 通信超时→重连
    └── CollisionRecovery  # 碰撞→退回安全位→重规划
```

**恢复流程**：
```
故障 → FailureDetector(分类)
  ├── grasp_failed → GraspRetry (重试→换approach→AbortTask)
  ├── planning_failed → ReplanMotion (放宽时间→放宽容差→AbortTask)
  ├── comm_timeout → CommunicationReset (重连→E-Stop→人工)
  └── collision → CollisionRecovery (退回安全位→更新WorldModel→重规划)
```

### 5.7 multi_arm_interfaces（接口包 - 拆分版）

```
msg/
├── TaskDescription.msg    # 纯语义: task_id, task_type, description
├── TaskStatus.msg         # 运行状态: status, progress, elapsed_time, error_message
├── TaskRequirement.msg    # 资源需求: required_resources, capability_constraints, deadline
├── ObjectPose.msg
├── CollisionEvent.msg
├── SystemHealth.msg
├── ResourceStatus.msg
└── RecoveryAction.msg

srv/
├── EmergencyStop.srv
├── SubmitTask.srv          # 输入: TaskDescription + TaskRequirement
├── QueryResources.srv
├── SafetyCheck.srv         # 输入: arm_names, trajectory → 输出: approved, speed_scale
└── RecoverFromFailure.srv  # 输入: failure_type, task_id → 输出: strategy_used, success

action/
├── PickPlace.action
└── ExecuteTask.action      # Goal: TaskDescription → Feedback: TaskStatus → Result: success
```

### 5.8 Benchmark（场景化）

```
multi_arm_benchmark/
├── benchmark_recorder.py
├── metrics_collector.py
├── report_generator.py
└── scenarios/
    ├── pick_place_easy.yaml
    ├── pick_place_dense.yaml
    └── multi_arm_collision.yaml
```

**场景定义示例**：
```yaml
name: pick_place_dense
description: 多物体密集摆放，测试调度与避碰
duration_s: 120
objects:
  - id: box001, type: cube, pose: {x: 0.3, y: 0.1, z: 0.05}
  - id: box002, type: cube, pose: {x: 0.35, y: 0.15, z: 0.05}
tasks:
  - type: pick_place, object: box001, target: {x: -0.3, y: 0.1, z: 0.05}
metrics: [planning_time_ms, execution_time_ms, collision_count, throughput]
```

---

## 6. 数据流架构

### 6.1 完整任务执行数据流

```
L7 用户: "把红色方块放到B区"
    ▼
L6 TaskPlanner: BT执行 pick_place.xml
    ▼
L4 Coordinator: CapabilityMatcher→arm2 + ResourceManager分配 + SafetyCheck→approved
    ▼
L3 MoveIt2: 规划轨迹
    ▼
Safety Plane: 速度/边界检查→approved
    ▼
L2 JTC: 执行
    ▼
L1 Gazebo/Real: 运动
    │ /joint_states (100-500Hz → L2控制回路直接使用)
    │                (1-10Hz → L5 WorldModel缓存)
    ▼
L5 WorldModel: 更新位姿
```

### 6.2 故障恢复数据流

```
GraspNode → stalled → RecoveryManager
    ├── 重试1: 同approach → 失败
    ├── 重试2: side_approach → 成功 → BT继续
    └── 3次失败 → AbortTask → TaskPlanner重规划
```

### 6.3 Safety横切数据流

```
L6 TaskPlanner → SafetyCheck.srv → Safety Plane (任务可行性)
L4 Coordinator → Safety Plane (资源安全)
L3 MoveIt2 → Safety Plane (碰撞检测)
L2 JTC ← Safety Plane (速度限制 + E-Stop)
```

---

## 7. 参数架构

```yaml
# config/robots.yaml
robots:
  - name: arm1
    type: ur5e
    namespace: /arm1
    capabilities:
      payload_kg: 5.0
      gripper: robotiq_2f85
      precision_mm: 0.1
      reachable_zones: [zone_a, zone_b, home]
    controllers:
      joint_trajectory: /arm1/joint_trajectory_controller
      joint_state_broadcaster: /arm1/joint_state_broadcaster
      gripper: /arm1/gripper_controller
    safety:
      max_velocity_scale: 1.0
      workspace_bounds: [[-0.8, 0.8], [-0.8, 0.8], [0.0, 1.2]]

  - name: arm2
    type: ur5e
    namespace: /arm2
    capabilities:
      payload_kg: 5.0
      gripper: robotiq_2f85
      precision_mm: 0.02
      reachable_zones: [zone_a, zone_c, home]
    controllers:
      joint_trajectory: /arm2/joint_trajectory_controller
      joint_state_broadcaster: /arm2/joint_state_broadcaster
      gripper: /arm2/gripper_controller
    safety:
      max_velocity_scale: 1.0
      workspace_bounds: [[-0.8, 0.8], [-0.8, 0.8], [0.0, 1.2]]

resources:
  zones: [zone_a, zone_b, zone_c, home]
  tools: []
  sensors: []
  fixtures: []
```

---

## 8. 演进路线

| Phase | 内容 | 新增模块 |
|-------|------|----------|
| 1 | 基础重构 | interfaces(拆分Task) + core(拆分Coordinator) + ResourceManager + CapabilityMatcher + YAML化 + SafetyCheck Service |
| 2 | 安全+规划 | safety(SafetySupervisor) + moveit_config + CollisionMonitor |
| 3 | 环境+任务 | world_model(所有权边界) + task_planner(BT.CPP+XML) + Safety Proxy |
| 4 | 恢复+工程 | recovery(故障检测+策略) + benchmark(场景化) + CI/CD + 虚实同步 |
| 5 | 高级特性 | 学习调度 + 多相机 + 动态臂 + Hardware Safety + 产线验证 |

---

## 9. 关键设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| Safety架构 | 横切平面(Safety Plane) | 安全约束贯穿多层，非单向流水线 |
| Safety实现 | 分阶段(软件→Proxy→硬件) | 工程可行性，逐步升级 |
| WorldModel所有权 | 拥有认知+缓存控制 | 500Hz控制状态不进WorldModel |
| BehaviorTree | BehaviorTree.CPP + XML | Groot可视化/调试/在线修改/工业标准 |
| Task接口 | 拆分Description/Status/Requirement | 避免消息膨胀，职责分离 |
| Recovery | 独立Recovery层 | Safety≠Recovery，恢复需要策略 |
| CapabilityMatcher | 独立组件 | 任务需求→资源能力精确匹配 |
| Benchmark场景化 | YAML场景定义 | 可重复实验，科研平台基础 |
