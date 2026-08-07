# Data Flow — 数据流图

> M5.7 Interface & Architecture Audit
> 版本: v1.0
> 日期: 2026-08-07

---

## 1. 任务执行主链路 (Task Execution Flow)

```
用户/Agent
    |
    | ExecuteTask.Goal (TaskGoal)
    ↓
TaskPlanner (/task_planner/execute_task)
    |
    | BT执行 (BehaviorTree)
    |--- AsyncCheckSafetyNode → SafetyCheck.srv → SafetySupervisor
    |--- AsyncQueryWorldNode → QueryResources.srv → WorldModel
    |--- AsyncMoveToNode → ExecuteTask.action → Coordinator
    ↓
Coordinator (/coordinator/execute_task)
    |
    | 1. SafetyCheck.srv → SafetySupervisor (审批)
    | 2. MoveGroup.action → MoveIt2 (规划)
    | 3. FollowJointTrajectory.action → JTC (执行)
    ↓
ros2_control (JTC)
    |
    | trajectory_msgs/JointTrajectory
    ↓
Gazebo / 真实机器人
    |
    | sensor_msgs/JointState (/joint_states, 500Hz)
    ↓
WorldModel (订阅/joint_states → 更新Robot State)
SafetySupervisor (订阅/{arm}/joint_states → 安全监控)
```

### 数据流详细

| 步骤 | 接口 | 数据 | 方向 |
|------|------|------|------|
| 1 | ExecuteTask.action | TaskGoal{action_type, arm_name, zone_name, position_name} | Agent→TaskPlanner |
| 2 | SafetyCheck.srv | {arm_names, trajectory} | BT→Safety |
| 3 | QueryResources.srv | {resource_types} | BT→WorldModel |
| 4 | ExecuteTask.action | TaskGoal | BT→Coordinator |
| 5 | SafetyCheck.srv | {arm_names, trajectory} | Coordinator→Safety |
| 6 | MoveGroup.action | {planning_group, target_pose} | Coordinator→MoveIt |
| 7 | FollowJointTrajectory.action | {trajectory} | Coordinator→JTC |
| 8 | /joint_states | JointState | Gazebo→Coordinator/WorldModel/Safety |

---

## 2. 安全监控数据流 (Safety Monitoring Flow)

```
Gazebo / 真实机器人
    |
    | /{arm}/joint_states (500Hz)
    ↓
SafetySupervisor
    |
    ├── 实时关节监控 → 速度/位置限制检查
    ├── SafetyCheck.srv (同步审批请求)
    ├── EmergencyStop.srv (E-Stop请求)
    ├── /safety/collision_events (碰撞事件广播)
    └── /safety/status (状态广播, latched)
         |
         ↓
    controller_manager (switch_controller, change_state)
```

### Safety 数据流

| 数据源 | 接口 | 消费者 | 频率 |
|--------|------|--------|------|
| Gazebo | /{arm}/joint_states | SafetySupervisor | 500Hz |
| Coordinator | SafetyCheck.srv | SafetySupervisor | 按需 |
| Coordinator | EmergencyStop.srv | SafetySupervisor | 按需 |
| SafetySupervisor | /safety/collision_events | (M6订阅) | 事件驱动 |
| SafetySupervisor | /safety/status | (M6订阅) | 状态变更 |
| SafetySupervisor | switch_controller | controller_manager | E-Stop时 |

---

## 3. 环境模型数据流 (World Model Flow)

```
Gazebo / 真实机器人
    |
    | /{arm}/joint_states (500Hz)
    ↓
WorldModel
    |
    ├── Robot State缓存 (关节位置)
    ├── QueryResources.srv (资源查询)
    └── /world_model/state (ObjectPose广播, latched)

(M6) Perception Server
    |
    | /perception/object_poses
    ↓
WorldModel (已订阅, M6实现Publisher即可接入)
```

### WorldModel 数据流

| 数据源 | 接口 | 消费者 | 频率 |
|--------|------|--------|------|
| Gazebo | /{arm}/joint_states | WorldModel | 500Hz |
| (M6) Perception | /perception/object_poses | WorldModel | ~30Hz |
| BT插件 | QueryResources.srv | WorldModel | 按需 |
| WorldModel | /world_model/state | (M6订阅) | latched |

---

## 4. 恢复数据流 (Recovery Flow)

```
Coordinator (检测到失败)
    |
    | FailureEvent{type, task_id, context}
    ↓
RecoveryManager (纯Python, 非ROS2节点)
    |
    ├── FailureClassifier → FailureType
    ├── PlanningFailureHandler → 放宽约束重规划
    ├── CollisionHandler → 退回安全位重规划
    ├── ResourceTimeoutHandler → 释放重新分配
    ├── ControllerFailureHandler → 切换控制器
    └── GraspRetryHandler → 重试
    |
    | RecoveryAction{strategy, success}
    ↓
Coordinator (继续执行或abort)
```

### Recovery 数据流

| 触发条件 | 处理器 | 恢复策略 | 结果 |
|----------|--------|----------|------|
| MoveIt规划失败 | PlanningFailureHandler | relax→change_grasp→release | 重规划/abort |
| 碰撞检测 | CollisionHandler | retreat→replan | 退回重规划 |
| 资源超时 | ResourceTimeoutHandler | release→reallocate | 释放重分配 |
| JTC inactive | ControllerFailureHandler | wait_retry→switch | 切换/abort |
| 抓取失败 | GraspRetryHandler | retry(≤3) | 重试/abort |

---

## 5. Benchmark数据流 (Benchmark Flow)

```
ScenarioRunner (YAML场景)
    |
    | ExecuteTask.action
    ↓
Coordinator
    |
    | 执行结果
    ↓
BenchmarkRecorder
    |
    ├── SQLite (runs表 + task_records表)
    └── RegressionDetector (历史对比)
```

---

## 6. M6/M7 预留数据流

### 6.1 Perception Flow (M6.1)

```
Camera (传感器)
    |
    | raw_image
    ↓
Perception Server (M6新增)
    |
    | /perception/object_poses (ObjectPose[])
    ↓
WorldModel (已订阅)
    |
    | /world_model/state
    ↓
TaskPlanner / Coordinator
```

### 6.2 Skill Flow (M6.3)

```
Agent (M7)
    |
    | SkillRequest
    ↓
Skill Runtime (M6.3新增)
    |
    ├── precondition check → WorldModel
    ├── execute → Coordinator (ExecuteTask)
    ├── postcondition check → WorldModel
    └── recover → RecoveryManager
```

### 6.3 Agent Flow (M7)

```
LLM / Agent
    |
    | 自然语言指令
    ↓
Skill Runtime
    |
    | Skill序列
    ↓
TaskPlanner → Coordinator → ... → Robot
```

---

## 7. 数据流QoS策略

| Topic | QoS | 理由 |
|-------|-----|------|
| /joint_states | RELIABLE, depth=10 | 高频控制数据，不可丢失 |
| /safety/collision_events | RELIABLE, depth=10 | 安全事件不可丢失 |
| /safety/status | TRANSIENT_LOCAL, depth=10 | latched，新订阅者立即获取最新状态 |
| /world_model/state | TRANSIENT_LOCAL, depth=10 | latched，新订阅者立即获取最新状态 |
| /perception/object_poses | RELIABLE, depth=10 | 感知数据，允许少量丢失但默认可靠 |

---

## 8. 数据流时序约束

| 链路 | 最大延迟 | 超时处理 |
|------|----------|----------|
| SafetyCheck请求→响应 | 1.0s | 超时→安全拒绝 |
| ExecuteTask goal→accept | 5.0s | 超时→goal_send_timeout |
| MoveIt规划 | 10.0s | 超时→planning_failure |
| JTC轨迹执行 | 30.0s | 超时→execution_timeout |
| WorldModel查询 | 2.0s | 超时→fallback(空结果) |
| Recovery重规划 | 15.0s | 超时→abort |