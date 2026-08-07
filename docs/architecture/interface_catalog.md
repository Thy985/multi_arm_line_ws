# Interface Catalog — 接口资产盘点

> M5.7 Interface & Architecture Audit
> 版本: v1.0 (Interface Freeze)
> 日期: 2026-08-07

---

## 1. Action 接口

### 1.1 ExecuteTask (FROZEN v1.0)

```yaml
name: ExecuteTask
type: ROS2 Action
file: multi_arm_interfaces/action/ExecuteTask.action
version: 1.0 (FROZEN)

producer:
  - task_planner_node (/task_planner/execute_task)
  - benchmark_node (/coordinator/execute_task, as client)
  - BT plugins (async_ros2_plugins.py, as client to coordinator)

consumer:
  - coordinator_node (/coordinator/execute_task)
  - task_planner_node (/task_planner/execute_task, as server)

goal:
  task_id: string          # 唯一任务标识
  task_type: string        # "move" | "pick_place" | "grasp" | "place" | "lift" | "retract" | "inspect"
  description: string      # Legacy: "arm1:zone_a:ready" (向后兼容)
  goal: TaskGoal           # 结构化任务目标 (preferred)

result:
  success: bool
  message: string

feedback:
  status: string
  progress: float32
  error_message: string

failure_modes:
  - timeout                # 执行超时
  - safety_rejected        # SafetyCheck拒绝
  - planning_failure       # MoveIt2规划失败
  - resource_unavailable   # 资源不可用
  - recovery_failed        # 恢复失败

freeze_policy: |
  task_id, task_type, description 字段冻结。
  TaskGoal goal 字段冻结，新增字段只能加在TaskGoal内部，
  不能修改ExecuteTask顶层字段。
```

### 1.2 PickPlace (EXPERIMENTAL, 未冻结)

```yaml
name: PickPlace
type: ROS2 Action
file: multi_arm_interfaces/action/PickPlace.action
version: 0.1 (EXPERIMENTAL)

goal:
  object_id: string
  target_zone: string
  approach: string
  duration: float64

result:
  success: bool
  message: string
  task_id: string

feedback:
  status: string
  progress: float32

note: |
  当前无节点使用此Action。保留作为M7应用层接口预留。
  M6/M7可能重构为Skill接口。
```

---

## 2. Service 接口

### 2.1 SafetyCheck (FROZEN v1.0)

```yaml
name: SafetyCheck
type: ROS2 Service
file: multi_arm_interfaces/srv/SafetyCheck.srv
version: 1.0 (FROZEN)

producer:
  - coordinator_node (via SafetyInterface)
  - task_planner_node (BT plugins: AsyncCheckSafetyNode)

consumer:
  - safety_supervisor

request:
  arm_names: string[]              # 待检查的臂名列表
  trajectory_joint_names: string[] # 轨迹关节名
  trajectory_positions: float64[]  # 轨迹位置
  trajectory_duration: float64     # 轨迹时长

response:
  approved: bool                   # 是否批准
  speed_scale: float32             # 速度缩放 (0.0-1.0)
  message: string                  # 拒绝原因

freeze_policy: |
  请求和响应字段冻结。
  M6如需扩展（如force_limit），新增字段不能破坏现有字段。
```

### 2.2 EmergencyStop (FROZEN v1.0)

```yaml
name: EmergencyStop
type: ROS2 Service
file: multi_arm_interfaces/srv/EmergencyStop.srv
version: 1.0 (FROZEN)

producer:
  - coordinator_node (via SafetyInterface)

consumer:
  - safety_supervisor

request:
  emergency: bool

response:
  success: bool
  message: string

freeze_policy: 冻结。E-Stop语义不可变。
```

### 2.3 QueryResources (FROZEN v1.0)

```yaml
name: QueryResources
type: ROS2 Service
file: multi_arm_interfaces/srv/QueryResources.srv
version: 1.0 (FROZEN)

producer:
  - task_planner_node (BT plugins: AsyncQueryWorldNode)

consumer:
  - world_model_node

request:
  resource_types: string[]

response:
  resource_names: string[]
  resource_types: string[]
  states: string[]
  allocated_to: string[]

freeze_policy: |
  冻结。M6 WorldModel升级时，新增查询类型通过resource_types扩展，
  不修改消息结构。
```

### 2.4 RecoverFromFailure (FROZEN v1.0)

```yaml
name: RecoverFromFailure
type: ROS2 Service
file: multi_arm_interfaces/srv/RecoverFromFailure.srv
version: 1.0 (FROZEN)

producer: (当前无直接调用者，RecoveryManager内部使用)

consumer: (当前无server，RecoveryManager纯Python调用)

request:
  failure_type: string
  task_id: string

response:
  strategy_used: string
  success: bool
  message: string

note: |
  当前RecoveryManager是纯Python模块（非ROS2节点）。
  此Service预留为M6分布式Recovery接口。
```

### 2.5 SubmitTask (EXPERIMENTAL, 未冻结)

```yaml
name: SubmitTask
type: ROS2 Service
file: multi_arm_interfaces/srv/SubmitTask.srv
version: 0.1 (EXPERIMENTAL)

request:
  task_id: string
  task_type: string
  description: string
  required_resources: string[]
  capability_constraints: string[]
  deadline: float64

response:
  accepted: bool
  message: string
  assigned_arm: string

note: |
  当前无节点使用此Service。ExecuteTask Action已覆盖此功能。
  保留作为M7 Agent层同步提交接口预留。
```

---

## 3. Topic 接口

### 3.1 /joint_states (EXTERNAL, 不可控)

```yaml
name: /joint_states
type: sensor_msgs/msg/JointState
publisher: ros2_control / Gazebo (L1/L2)
subscribers:
  - coordinator_node
qos: default (RELIABLE, depth=10)
frequency: ~500Hz (仿真) / ~125Hz (真实UR)
note: 标准ROS2 topic，外部系统提供。
```

### 3.2 /{arm_name}/joint_states (EXTERNAL)

```yaml
name: /{arm_name}/joint_states
type: sensor_msgs/msg/JointState
publisher: ros2_control (per-arm namespace)
subscribers:
  - safety_supervisor
  - world_model_node
qos: default
frequency: ~500Hz
note: 每臂独立命名空间。
```

### 3.3 /safety/collision_events (FROZEN v1.0)

```yaml
name: /safety/collision_events
type: multi_arm_interfaces/msg/CollisionEvent
publisher: safety_supervisor
subscribers: (当前无)
qos: RELIABLE, depth=10
freeze_policy: 冻结。M6碰撞检测模块必须使用此topic。
```

### 3.4 /safety/status (FROZEN v1.0)

```yaml
name: /safety/status
type: multi_arm_interfaces/msg/ResourceStatus
publisher: safety_supervisor
subscribers: (当前无)
qos: TRANSIENT_LOCAL, depth=10 (latched)
freeze_policy: 冻结。Safety状态广播接口。
```

### 3.5 /world_model/state (FROZEN v1.0)

```yaml
name: /world_model/state
type: multi_arm_interfaces/msg/ObjectPose
publisher: world_model_node
subscribers: (当前无)
qos: TRANSIENT_LOCAL, depth=10 (latched)
freeze_policy: 冻结。WorldModel状态广播接口。
```

### 3.6 /perception/object_poses (RESERVED for M6)

```yaml
name: /perception/object_poses
type: multi_arm_interfaces/msg/ObjectPose
publisher: (M6 Perception Server, 未实现)
subscribers:
  - world_model_node
qos: RELIABLE, depth=10
note: |
  M6.1 Environment Perception 预留接口。
  WorldModel已订阅此topic，M6实现Publisher即可接入。
```

---

## 4. 外部 Action 接口 (非multi_arm_interfaces)

### 4.1 /move_action (MoveIt2)

```yaml
name: /move_action
type: moveit_msgs/action/MoveGroup
client: coordinator_node (via MoveItInterface)
server: move_group (MoveIt2)
note: L4→L3 标准MoveIt2接口，不可冻结（外部依赖）。
```

### 4.2 /{arm}_joint_trajectory_controller/follow_joint_trajectory

```yaml
name: /{arm_name}_joint_trajectory_controller/follow_joint_trajectory
type: control_msgs/action/FollowJointTrajectory
client: coordinator_node
server: ros2_control JTC
note: L4→L2 标准ros2_control接口。
```

### 4.3 controller_manager services

```yaml
name: /{arm}/controller_manager/change_state
type: lifecycle_msgs/srv/ChangeState
client: safety_supervisor
server: ros2_control controller_manager

name: /{arm}/controller_manager/switch_controller
type: controller_manager_msgs/srv/SwitchController
client: safety_supervisor
server: ros2_control controller_manager
note: Safety Plane→L2 控制器管理接口。
```

---

## 5. 接口统计

| 类型 | 总数 | FROZEN v1.0 | EXPERIMENTAL | RESERVED |
|------|------|-------------|--------------|----------|
| Action | 2 | 1 (ExecuteTask) | 1 (PickPlace) | 0 |
| Service | 5 | 4 | 1 (SubmitTask) | 0 |
| Topic (内部) | 5 | 3 | 0 | 1 (perception) |
| Topic (外部) | 2 | 0 | 0 | 0 |
| 外部Action | 2 | 0 | 0 | 0 |
| 外部Service | 2 | 0 | 0 | 0 |
| **总计** | **18** | **8** | **2** | **1** |

---

## 6. 版本治理规则

### FROZEN v1.0 接口

以下接口在 M5.7 后进入 **Interface Freeze** 状态：

1. `ExecuteTask.action` — 顶层字段冻结
2. `SafetyCheck.srv` — 请求/响应字段冻结
3. `EmergencyStop.srv` — 冻结
4. `QueryResources.srv` — 冻结
5. `RecoverFromFailure.srv` — 冻结
6. `/safety/collision_events` — 冻结
7. `/safety/status` — 冻结
8. `/world_model/state` — 冻结

### 修改规则

| 操作 | 允许 | 条件 |
|------|------|------|
| 新增msg字段 | ✅ | 只能追加到末尾，有默认值 |
| 修改已有字段类型 | ❌ | 禁止 |
| 删除已有字段 | ❌ | 禁止 |
| 重命名字段 | ❌ | 禁止 |
| 新增msg/srv/action文件 | ✅ | 需更新此catalog |
| 新增topic | ✅ | 需更新此catalog |

### 新增接口流程 (M6+)

1. 在 `multi_arm_interfaces` 中定义新msg/srv/action
2. 更新此catalog文档
3. 更新 `api_contracts.md` 添加契约
4. 更新 `dependency_graph.md` 添加依赖关系
5. 通过CI interface-compat检查