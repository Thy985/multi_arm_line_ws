# HLD - 双UR5e多机械臂系统高层设计文档

| 字段 | 内容 |
|------|------|
| 版本 | v2.1 |
| 作者 | Thy985 |
| 日期 | 2026-08-05 |
| 状态 | Draft |
| 关联架构 | Architecture-MultiArm-202608051018.md v2.1 |

---

## 1. 系统架构（7层 + Safety Plane）

```
L7  应用层        PickPlace / Assembly / Inspection
L6  任务规划层    TaskManager + BehaviorTree.CPP
L5  环境模型层    WorldModel (Objects / Environment / TaskContext)
L4  协调层        ResourceManager + Scheduler + Coordinator
L3  运动规划层    MoveIt2 + IK + Collision + Trajectory
L2  控制层        ros2_control + JTC + GripperController
L1  硬件层        Gazebo / UR Driver / Sensors

══ Safety Plane (横切) ══
══ System Services (横向) ══  Diagnostics + Logger + Benchmark + Recovery
```

---

## 2. 模块分解

### 2.1 multi_arm_interfaces（接口包 - ament_cmake）

消息拆分：TaskDescription(语义) / TaskStatus(状态) / TaskRequirement(需求)
服务：EmergencyStop / SubmitTask / QueryResources / SafetyCheck / RecoverFromFailure
Action：PickPlace / ExecuteTask

### 2.2 multi_arm_core（协调控制包 - ament_python）

coordinator_node(编排引擎) + ResourceManager + CapabilityMatcher + TimeManager + Scheduler + TaskManager + SafetyInterface

### 2.3 multi_arm_world_model（环境模型包）

WorldModelNode(拥有Objects/Environment/TaskContext，缓存Robot State 1-10Hz) + ObjectTracker + StateDatabase

### 2.4 multi_arm_task_planner（任务规划包）

TaskPlannerNode + BT XML(bt_xml/) + Python Plugins(bt_plugins/: MoveTo/Grasp/Place/CheckSafety/Recover)
选型：BehaviorTree.CPP，不自造轮子

### 2.5 multi_arm_safety（安全平面包）

SafetySupervisor(横切L1-L7) + SpeedLimiter + WorkspaceLimiter + CollisionMonitor
分阶段：SafetyCheck Service → Safety Proxy → Hardware Safety

### 2.6 multi_arm_recovery（故障恢复包）

RecoveryManager + FailureDetector + 4种策略(GraspRetry/ReplanMotion/CommunicationReset/CollisionRecovery)

### 2.7 multi_arm_benchmark（基准测试包）

BenchmarkRecorder + MetricsCollector + ReportGenerator + scenarios/*.yaml

---

## 3. 技术选型

BehaviorTree.CPP(工业标准) | MoveIt2 OMPL | KDL IK | Safety Plane横切 | 分阶段安全实现 | 独立interfaces包 | CapabilityMatcher | YAML场景化

---

## 4. 数据流

任务：L7→L6(BT)→L4(编排)→L5(环境)→SafetyCheck→L3(规划)→Safety批准→L2→L1
恢复：故障→Recovery(分类+策略)→BT继续或Abort
安全：L6→SafetyCheck | L3→碰撞检测 | L2←速度限制+E-Stop

---

## 5. 风险

Safety Proxy工程量大→分阶段 | BT.CPP Python绑定→备选py_behavior_tree | WorldModel一致性→明确所有权边界
