# Dependency Graph — 模块依赖图

> M5.7 Interface & Architecture Audit
> 版本: v1.0
> 日期: 2026-08-07

---

## 1. 7层架构映射

```
L7  应用层         (暂无独立包; PickPlace/Assembly/Inspection由BT XML表达)
        ↑
L6  任务规划层      multi_arm_task_planner
        ↑
L5  环境模型层      multi_arm_world_model
        ↑
L4  协调层          multi_arm_core
        ↑
L3  运动规划层      multi_arm_moveit_config (MoveIt2配置)
        ↑
L2  控制层          ros2_control + JTC (在ur_simulation_gz中配置)
        ↑
L1  硬件层          ur_simulation_gz (Gazebo仿真) / UR Driver (M6)

══ Safety Plane (横切)     multi_arm_safety
══ System Services (横向)  multi_arm_interfaces, multi_arm_recovery, multi_arm_benchmark
```

---

## 2. 包依赖关系图

```
                    multi_arm_interfaces (v1.0 FROZEN)
                   /        |        |        |        |        |
                  /         |        |        |        |        |
                 ↓          ↓        ↓        ↓        ↓        ↓
          multi_arm_core  safety  world_model  task_planner  recovery  benchmark
                 |                                    |          ↑        ↑
                 |____________________________________|          |        |
                 |  (ExecuteTask action)                         |        |
                 |______________________________________________|        |
                 |  (ExecuteTask action)                                 |
                 |_______________________________________________ _____|
                    (ExecuteTask action)
```

### 详细依赖

| 包 | 依赖 | 依赖类型 | 架构层 |
|----|------|----------|--------|
| multi_arm_interfaces | builtin_interfaces, action_msgs | build | System Services |
| multi_arm_core | rclpy, control_msgs, trajectory_msgs, sensor_msgs, moveit_msgs, multi_arm_interfaces, multi_arm_recovery | exec | L4 |
| multi_arm_safety | rclpy, sensor_msgs, controller_manager_msgs, lifecycle_msgs, multi_arm_interfaces | exec | Safety Plane |
| multi_arm_world_model | rclpy, sensor_msgs, multi_arm_interfaces | exec | L5 |
| multi_arm_task_planner | rclpy, multi_arm_interfaces | exec | L6 |
| multi_arm_recovery | rclpy, multi_arm_interfaces | exec | System Services |
| multi_arm_benchmark | rclpy, multi_arm_interfaces | exec | System Services |

---

## 3. 运行时通信依赖图

```
                    ┌─────────────────────────┐
                    │    External Systems      │
                    │  (Gazebo/UR, MoveIt2,    │
                    │   ros2_control, JTC)     │
                    └────────┬────────────────┘
                             |
            ┌────────────────┼────────────────┐
            |                |                |
            ↓                ↓                ↓
    /joint_states    /move_action    /follow_joint_trajectory
            |                |                |
   ┌────────┼────────┐       |                |
   |        |        |       |                |
   ↓        ↓        ↓       ↓                ↓
┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐    ┌──────────┐
│Safety│ │World │ │Coord │ │Coord │    │  Safety  │
│  Sup │ │Model │ │  .   │ │  .   │    │   Sup    │
│      │ │      │ │      │ │      │    │          │
└──┬───┘ └──┬───┘ └──┬───┘ └──────┘    └──────────┘
   |        |        |
   |        |        | ExecuteTask.action
   |        |        ↓
   |        |   ┌──────────┐
   |        |   │TaskPlanner│
   |        |   │  (BT)    │
   |        |   └────┬─────┘
   |        |        |
   |←───────┼────────┘ SafetyCheck.srv (越层! 见审计)
   |        |
   |←───────┘ QueryResources.srv (越层! 见审计)
   |
   | /safety/collision_events, /safety/status
   ↓
  (M6订阅者)
```

---

## 4. 模块边界审计结果

### 4.1 审计检查项

| # | 检查项 | 结果 | 详情 |
|---|--------|------|------|
| 1 | TaskPlanner不直接调用ros2_control/controller_manager | PASS | 无相关import |
| 2 | TaskPlanner不直接调用moveit_msgs | PASS | 无相关import |
| 3 | Coordinator不直接控制Gazebo | PASS | 无gazebo/gz_sim引用 |
| 4 | SafetySupervisor不依赖multi_arm_core | PASS | 无from multi_arm_core import |
| 5 | WorldModel不依赖multi_arm_core | PASS | 无from multi_arm_core import |
| 6 | Recovery不依赖multi_arm_task_planner | PASS | 无from multi_arm_task_planner import |
| 7 | TaskPlanner BT插件不直连SafetyCheck | **FAIL** | async_ros2_plugins.py:267 越层L6→Safety |
| 8 | TaskPlanner BT插件不直连QueryResources | **FAIL** | async_ros2_plugins.py:306 越层L6→L5 |

### 4.2 越层调用分析

**越层调用 #7, #8**: TaskPlanner BT插件直接调用SafetyCheck和QueryResources

```
当前 (越层):
  TaskPlanner → SafetyCheck.srv → SafetySupervisor
  TaskPlanner → QueryResources.srv → WorldModel

正确 (经Coordinator):
  TaskPlanner → ExecuteTask.action → Coordinator → SafetyCheck → Safety
  TaskPlanner → ExecuteTask.action → Coordinator → QueryResources → WorldModel
```

**根因**: M5.2 BT Async插件设计时，为避免Coordinator成为通信瓶颈，允许BT插件直接查询Safety和WorldModel。

**影响评估**:
- 功能正确性: 无影响（Safety和WorldModel服务可正常响应）
- 架构纯洁性: 违反"只允许相邻层通信"规则
- M6影响: 如果M6 Agent通过TaskPlanner接入，Agent间接依赖Safety和WorldModel接口
- 性能: 直连比经Coordinator中转更快（减少一跳）

**处置决策**: **接受为已知偏差 (Accepted Deviation)**

理由:
1. BT插件查询Safety/WorldModel是只读查询（不控制），不影响安全链路
2. Coordinator的ExecuteTask action内部仍会独立调用SafetyCheck（安全审批不绕过）
3. 修改为经Coordinator中转会引入额外延迟和Coordinator单点瓶颈
4. 文档化为已知偏差，M6重构时评估是否需要改

---

## 5. 依赖矩阵 (Build-time)

```
                    iface  core  safety  world  planner  recovery  benchmark
multi_arm_interfaces   -     -     -      -      -        -         -
multi_arm_core         1     -     -      -      -        1         -
multi_arm_safety       1     -     -      -      -        -         -
multi_arm_world_model  1     -     -      -      -        -         -
multi_arm_task_planner 1     -     -      -      -        -         -
multi_arm_recovery     1     -     -      -      -        -         -
multi_arm_benchmark    1     -     -      -      -        -         -
```

- `1` = 依赖
- `-` = 不依赖
- **关键观察**: multi_arm_interfaces是所有包的根依赖，无循环依赖

---

## 6. 依赖矩阵 (Runtime Communication)

```
                    coord  safety  world  planner  recovery  benchmark  moveit  jtc  gazebo
coordinator           -      S       -      A        P         -         A      A     T
safety_supervisor     -      -       -      -        -         -         -      S     T
world_model           -      -       -      -        -         -         -      -     T
task_planner          A      S       S      -        -         -         -      -     -
recovery              P      -       -      -        -         -         -      -     -
benchmark             A      -       -      -        -         -         -      -     -
```

- `A` = Action Client/Server
- `S` = Service Client/Server
- `T` = Topic Subscriber
- `P` = Python import (非ROS2通信)

---

## 7. M6/M7 预留依赖

```
M6.1 Perception:
  multi_arm_perception → multi_arm_interfaces (新增ObjectPose publisher)
  WorldModel已订阅 /perception/object_poses (无需修改)

M6.2 WorldModel升级:
  multi_arm_world_model → multi_arm_interfaces (新增msg)
  不影响其他包

M6.3 Skill Runtime:
  multi_arm_skills → multi_arm_interfaces, multi_arm_core (ExecuteTask)
  不修改现有包

M7 Agent:
  multi_arm_agent → multi_arm_skills, multi_arm_task_planner
  不修改现有包
```