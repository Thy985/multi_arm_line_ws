# AGENTS.md - 项目规范与Agent约束

> 本文件定义AI Agent（如CodeArts）在本项目中工作时的约束、规范和上下文。Agent必须严格遵守以下规则。

---

## 项目概述

双UR5e多机械臂ROS2仿真与协调控制系统。ROS2 Jazzy + Gazebo Harmonic，运行在WSL2 (Ubuntu 24.04) 环境。目标架构为7层功能层 + Safety横切平面。

**当前阶段**: M5全部完成（含M5.6 Stress Test），进入M6 Sim2Real（远期）。

---

## 技术栈

| 类别 | 技术 |
|------|------|
| 框架 | ROS2 Jazzy Jalisco |
| 语言 | Python 3.12 (核心包), CMake (仿真包+接口包) |
| 仿真 | Gazebo Harmonic |
| 构建 | colcon (ament_python + ament_cmake) |
| 测试 | pytest + colcon test |
| 版本控制 | Git (main分支) |

---

## 系统架构（7层 + Safety Plane）

```
L7  应用层        PickPlace / Assembly / Inspection
L6  任务规划层    TaskManager + BehaviorTree.CPP
L5  环境模型层    WorldModel (Objects / Robots / Environment)
L4  协调层        ResourceManager + Scheduler + Coordinator
L3  运动规划层    MoveIt2 + IK + Collision + Trajectory
L2  控制层        ros2_control + JTC + GripperController
L1  硬件层        Gazebo / UR Driver / Sensors

══ Safety Plane (横切，贯穿L1-L7) ══
  SafetySupervisor + SpeedLimiter + WorkspaceLimiter + E-Stop

══ System Services (横向基础设施) ══
  Diagnostics + StructuredLogger + Benchmark + Recovery
```

**层间规则**：
- 只允许相邻层通信，禁止跨层调用
- 所有跨节点通信通过 `multi_arm_interfaces` 定义，禁止Python类直接共享
- Safety Plane横切所有层，可拦截L2控制层所有命令
- L5环境模型是世界认知真相源（拥有Objects/Environment/TaskContext），L2 ros2_control是实时控制真相源

---

## 目录结构

### 当前（M1-M3 + E2E 已通过）

```
multi_arm_line_ws/
├── src/
│   ├── multi_arm_interfaces/       # 接口定义包 (ament_cmake) - msg/srv/action
│   ├── multi_arm_core/             # 协调控制包 (ament_python)
│   ├── multi_arm_safety/           # 安全监督包 (SafetySupervisor独立)
│   ├── multi_arm_world_model/      # 环境模型包
│   ├── multi_arm_task_planner/     # 任务规划包 (BehaviorTree)
│   ├── multi_arm_moveit_config/    # MoveIt2配置包
│   ├── order_manager/              # [遗留] 过渡期保留
│   └── ur_simulation_gz/           # Gazebo仿真包 (ament_cmake)
├── docs/
│   ├── architecture/               # 架构验证文档
│   ├── validation/                 # M1-M3 + E2E 验证报告
│   └── benchmark/                  # 基准测试报告
├── output/                         # 设计文档
└── AGENTS.md
```

### 目标（Phase 3+）

```
multi_arm_line_ws/
├── src/
│   ├── multi_arm_interfaces/       # 接口定义包 (ament_cmake) - msg/srv/action
│   ├── multi_arm_core/             # 协调控制包 (ament_python)
│   │   └── multi_arm_core/
│   │       ├── coordinator_node.py # 编排引擎（薄层）
│   │       ├── coordination/       # resource_manager, time_manager
│   │       ├── scheduler/          # scheduler, allocation_strategy
│   │       ├── task/               # task_manager
│   │       └── safety/             # safety_interface
│   ├── multi_arm_world_model/      # 环境模型包
│   ├── multi_arm_task_planner/     # 任务规划包 (BehaviorTree)
│   ├── multi_arm_safety/           # 安全监督包 (SafetySupervisor独立)
│   ├── multi_arm_moveit_config/    # MoveIt2配置包
│   ├── multi_arm_manipulation/     # 抓取操作包
│   ├── multi_arm_perception/       # 视觉感知包
│   ├── multi_arm_recovery/         # 恢复框架包
│   ├── multi_arm_benchmark/        # 基准测试包
│   ├── order_manager/              # [遗留] 过渡期
│   └── ur_simulation_gz/           # Gazebo仿真包
├── docs/
│   ├── architecture/
│   ├── validation/
│   └── benchmark/
├── output/
└── AGENTS.md
```

---

## 构建命令

```bash
# 必须先source ROS环境
source /opt/ros/jazzy/setup.bash

# 构建所有包
colcon build --packages-select order_manager ur_simulation_gz

# 构建含接口包（Phase 1+）
colcon build --packages-select multi_arm_interfaces multi_arm_core ur_simulation_gz

# 构建所有multi_arm包
colcon build --packages-select multi_arm_interfaces multi_arm_core multi_arm_safety multi_arm_world_model multi_arm_task_planner multi_arm_moveit_config

# 运行测试
colcon test --packages-select order_manager

# 运行E2E测试
python3 -m pytest src/multi_arm_core/test/test_e2e_integration.py -v

# 查看测试结果
colcon test-result --verbose
```

**重要**：所有bash命令中涉及ROS2的，必须在子shell中先source环境：
```bash
bash -c "source /opt/ros/jazzy/setup.bash && source install/setup.bash && <命令>"
```

---

## Lint与检查命令

```bash
ruff check src/order_manager/ src/multi_arm_core/
mypy src/order_manager/ src/multi_arm_core/ --ignore-missing-imports
ament_flake8 src/order_manager/
ament_pep257 src/order_manager/
```

**每次修改代码后必须运行**：`colcon build` + `colcon test`

---

## 编码规范

### Python

- 遵循PEP 8，使用ruff格式化
- 类型注解：所有公开函数必须有参数和返回值类型注解
- 文档字符串：所有公开类和函数必须有docstring（Google风格）
- 不添加注释除非用户明确要求
- 不使用emoji除非用户明确要求
- import顺序：标准库 → 第三方 → ROS2 → multi_arm_interfaces → 项目内部

### ROS2

- 节点命名：`snake_case`，如 `coordinator_node`
- 话题命名：`/{namespace}/{topic}`，如 `/arm1/joint_states`
- 服务命名：`/{node_name}/{service}`，如 `/safety/emergency_stop`
- 参数命名：`snake_case`
- Launch文件：`snake_case.launch.py`
- 配置文件：`snake_case.yaml`

### 包规范

- 新增可执行节点必须同时更新 `setup.py` (entry_points) 和 `package.xml` (depend)
- 新增依赖必须更新 `package.xml`
- ament_python包的测试放在 `test/` 目录
- **跨包通信必须通过 `multi_arm_interfaces`**，禁止Python类直接共享
- 新增msg/srv/action必须更新 `multi_arm_interfaces` 的 `CMakeLists.txt` 和 `package.xml`

---

## 架构约束

### 核心架构规则

1. **Coordinator是编排引擎**，不包含业务逻辑，逻辑下沉到子模块
2. **SafetySupervisor独立于Coordinator**，拥有最终停止权，不依赖Coordinator运行
3. **WorldModel是世界认知真相源**，所有层读取环境状态必须从WorldModel获取
4. **ros2_control是实时控制真相源**，500Hz joint_states不进WorldModel
5. **ResourceManager统一管理所有资源**（Robot/Zone/Tool/Sensor/Fixture），Zone是特例
6. **参数YAML驱动**，新增臂/资源只需更新YAML，不修改代码

### 不可修改的文件

- `src/ur_simulation_gz/.github/` - CI配置
- `src/ur_simulation_gz/CONTRIBUTING.md`
- `src/ur_simulation_gz/LICENSE`
- `src/ur_simulation_gz/ur_simulation_gz/doc/` - 上游文档
- `src/ur_simulation_gz/ur_simulation_gz/test/` - 上游测试

### 可修改/新增的文件

- `src/ur_simulation_gz/ur_simulation_gz/launch/` - 可新增launch文件
- `src/ur_simulation_gz/ur_simulation_gz/config/` - 可新增配置文件
- `src/ur_simulation_gz/ur_simulation_gz/urdf/` - 可新增URDF
- `src/ur_simulation_gz/ur_simulation_gz/scripts/` - 可新增脚本
- `src/order_manager/` - 全部可修改（过渡期）
- `src/multi_arm_*/` - 全部可修改（新包）

### 新增包规范

新增ROS2包必须：
1. 放在 `src/` 目录下
2. 包含 `package.xml` 和构建文件（`setup.py` 或 `CMakeLists.txt`）
3. 在 `package.xml` 中声明所有依赖（包括 `multi_arm_interfaces`）
4. 注册所有可执行节点
5. 包含至少一个冒烟测试
6. 跨包通信使用 `multi_arm_interfaces` 定义的msg/srv/action

---

## 测试规范

### 测试文件命名

- 单元测试：`test_<module>.py`，放在对应包的 `test/` 目录
- 集成测试：`test_integration.py`
- E2E测试：`test_system_e2e.py`
- 基准测试：`multi_arm_benchmark/` 包内

### 测试要求

- 每个新功能必须有对应测试
- 修改现有功能必须更新相关测试
- 测试不能依赖Gazebo运行（纯Python测试）
- 需要ROS2节点的测试使用 `rclpy` mock或最小节点
- 测试覆盖率目标 > 80%

### 测试运行

```bash
colcon test --packages-select order_manager
python3 -m pytest src/order_manager/order_manager/nodes/test_time_manager.py -v
```

---

## Git规范

### 提交信息格式

```
<type>: <简短描述>

<详细说明（可选）>
```

类型：`feat` / `fix` / `refactor` / `test` / `docs` / `chore`

### 分支策略

- `main`: 稳定分支，CI通过后才能合并
- `feat/<功能名>`: 功能开发分支
- `fix/<问题描述>`: 修复分支

### 禁止操作

- **禁止** `git push --force` 到main分支
- **禁止** 提交 `build/`、`install/`、`log/` 目录
- **禁止** 提交 `__pycache__/` 目录
- **禁止** 提交包含密钥/凭证的文件
- **禁止** 未经用户确认的commit

---

## WSL2环境注意事项

- Gazebo GUI需要X server（VcXsrv/WSLg）或使用headless模式
- SSH密钥可能需要从Windows侧复制：`cp /mnt/c/Users/<user>/.ssh/id_ed25519 ~/.ssh/`
- rqt插件缓存可能需要清除：`rm -rf ~/.local/share/rqt_gui/plugin_cache*`
- rqt启动需要 `--force-discover` 参数
- Docker/容器内可能存在uid问题，需要修复 `/etc/passwd`

---

## 常见问题处理

| 问题 | 解决方案 |
|------|----------|
| `ros2: command not found` | `source /opt/ros/jazzy/setup.bash` |
| `colcon build` 找不到ament_cmake | 先source ROS环境 |
| Gazebo启动黑屏 | 使用headless模式 + RViz可视化 |
| rqt插件找不到 | `rqt --force-discover` |
| SSH推送失败 | 检查 `~/.ssh/` 密钥和权限(600) |
| Python导入失败 | `source install/setup.bash` |
| 测试超时 | 检查是否有Gazebo依赖，测试应纯Python |

---

## 里程碑定义

### 已完成

| 里程碑 | 内容 | 测试 | 状态 |
|--------|------|------|------|
| M1 | Interface + Core Coordination | 109 | ✅ |
| M2 | Safety Plane + MoveIt2 Planning | 36 | ✅ |
| M3 | WorldModel + TaskPlanner + BT | 54 | ✅ |
| E2E | 跨包集成端到端 | 28 | ✅ |

**软件架构闭环验证完成**：Task → TaskPlanner → Coordinator → ResourceManager → WorldModel → SafetySupervisor → Motion Interface → Mock Controller 链路已证明可工作。

### M4: Simulation E2E Validation（当前阶段）

**目标**: 将Mock替换为真实仿真组件，证明架构在真实机器人运行约束下成立。

**完整链路**:
```
TaskPlanner → Coordinator → SafetySupervisor → MoveIt2
    → JointTrajectoryController → ros2_control → Gazebo UR5e
    → Joint States → WorldModel update
```

#### M4.1 单臂闭环

| 验收项 | 通过条件 |
|--------|----------|
| UR5e Gazebo单臂启动 | Gazebo加载UR5e模型+ros2_control |
| MoveIt2单臂规划执行 | home → target_pose → home 规划+执行成功 |
| JointState反馈 | 500Hz joint_states正确发布 |
| WorldModel同步 | WorldModel从joint_states更新Robot State |
| Safety批准 | SafetyCheck通过后执行运动 |

#### M4.2 双臂资源协调

| 验收项 | 通过条件 |
|--------|----------|
| 双臂Gazebo启动 | arm1 + arm2同时加载 |
| Zone资源竞争 | arm1占用zone_a时arm2排队 |
| 协调调度 | arm1完成后arm2自动分配执行 |
| MoveIt2双臂规划 | 双臂无碰撞轨迹规划成功 |

#### M4.3 安全闭环

| 验收项 | 通过条件 |
|--------|----------|
| 速度限制生效 | velocity_scale>1.0 → Safety限制到0.5 |
| E-Stop停止 | 运动中触发E-Stop → JTC halt → Robot ERROR |
| 碰撞检测 | 接近碰撞 → CollisionEvent → 轨迹停止 |
| Safety独立验证 | Coordinator crash后Safety仍可用 |

#### M4 Exit Criteria

| 项目 | 状态 |
|------|------|
| UR5e Gazebo启动 | ✅ 双臂arm1+arm2启动，JSB+JTC active |
| MoveIt2规划执行 | ✅ move_group启动，OMPL+KDL IK，arm1/arm2/dual_arm规划成功 |
| 单臂任务闭环 | ✅ MoveIt规划→JTC→Gazebo执行→关节位置验证 |
| 双臂资源竞争 | ✅ 双臂独立CM+命名空间架构验证 |
| Safety拦截 | ✅ E-Stop→JTC inactive，SafetyCheck approved |
| WorldModel同步真实状态 | ✅ /joint_states→WorldModel缓存 |
| Benchmark记录真实执行数据 | ⬜ |
| E2E报告 | ✅ docs/validation/M4_validation_report.md |

#### M4.5 Motion + Coordination Validation ✅

**目标**: 验证MoveIt2运动规划→JTC→Gazebo仿真闭环，以及双臂planning group。

| 验收项 | 状态 |
|--------|------|
| 合并URDF双臂启动 | ✅ multi_arm_robot.xacro，单CM 12关节 |
| MoveIt2 move_group启动 | ✅ OMPL planner + KDL IK + all adapters |
| arm1单臂规划执行 | ✅ home→ready规划+执行+位置验证 |
| arm2单臂规划执行 | ✅ home→ready规划+执行+位置验证 |
| dual_arm规划组 | ✅ 12关节同时规划，13轨迹点 |
| M4.5验证报告 | ✅ docs/validation/M4_5_validation_report.md |

#### M4.6 Autonomous Task Loop ✅

**目标**: 证明一个任务能够自主完成——closed-loop autonomy。

**核心缺口**: M4/M4.5验证了"组件存在且能工作"，但未证明"系统作为一个整体自主完成任务"。

**完整链路**:
```
用户任务(PickPlace)
 ↓ TaskPlanner生成BT
 ↓ BehaviorTree执行
 ↓ Coordinator调度
 ↓ ResourceManager分配
 ↓ WorldModel查询目标
 ↓ MoveIt规划
 ↓ Safety审批
 ↓ JTC执行
 ↓ Gazebo动作
 ↓ WorldModel更新
 ↓ BT状态更新
 ↓ 任务完成(Success/Failure)
```

| 验收项 | 通过条件 | 状态 |
|--------|----------|------|
| PickPlace任务BT生成 | TaskPlanner输出Sequence(CheckSafety→QueryWorld→Grasp→Place) | ✅ |
| Coordinator调度执行 | Coordinator接收Task→分配arm→调用MoveIt | ✅ E2E验证 |
| Safety审批链路 | SafetyCheck approved→执行，rejected→abort | ✅ E2E验证 |
| Robot执行+WorldModel更新 | JTC执行后WorldModel同步真实关节状态 | ✅ |
| BT状态反馈 | Execute节点收到SUCCESS/Failure | ✅ E2E验证 |
| 双臂资源冲突 | arm1占用zone→arm2等待→arm1完成→arm2继续 | ✅ |
| M4.6验证报告 | docs/validation/M4_6_validation_report.md | ✅ |

**E2E测试结果**: 8/8 ALL PASS + 双臂冲突 8/8 ALL PASS（单元131 + 代码验证11 + E2E 8 + 双臂冲突8 = 158 total）

**架构注意**: M4.5暴露了Gazebo架构≠MoveIt架构问题（ADR-004）。

**已知限制**: ROS2 BT插件在async callback中创建临时节点会导致executor死锁，当前默认使用mock插件。M5需重构为共享Node的async插件。

**M4.6关键发现**: ResourceManager.allocate()在zone被占用时将请求者加入waiting_queue，release()时自动分配给队列下一个。但ExecuteTask是同步请求-响应模式，被拒绝的请求不会重试，导致zone被已放弃的请求者占用。修复：allocate失败后从waiting_queue移除task_id。

### M5: Reliability & Intelligence Layer（下一阶段）

**核心转变**: 从"能完成任务"进化到"任务失败时仍然可靠"。

**目标**: 系统面对失败不是退出，而是恢复。同时建立可量化的性能基线和自动化质量保障。

#### M5.1 Recovery Framework

**新增包**: `multi_arm_recovery`

```
multi_arm_recovery/
├── recovery_manager.py          # 恢复编排器
├── failure_classifier.py        # 失败分类器
└── handlers/
    ├── planning_failure.py      # 规划失败→放宽约束重规划
    ├── collision_handler.py     # 碰撞→退回安全位→重规划
    ├── resource_timeout.py      # 资源等待超时→释放→重新分配
    ├── controller_failure.py    # JTC inactive→切换控制器/abort
    └── grasp_retry.py           # 抓取失败→重试(最多3次)
```

**恢复链路**:
```
MoveIt失败
 ↓ RecoveryManager
 ↓ FailureClassifier → PlanningFailure
 ↓ PlanningFailureHandler → 放宽约束重规划
 ↓ 失败
 ↓ Strategy 2: 换grasp姿态
 ↓ 失败
 ↓ Strategy 3: 释放资源
 ↓ 失败
 ↓ SafeAbort
```

| 验收项 | 通过条件 |
|--------|----------|
| PlanningFailure→Replan | 规划失败→放宽约束重规划→成功 |
| CollisionRecovery | 碰撞→退回安全位→重规划→成功 |
| ResourceTimeout→Release | 资源等待超时→释放→重新分配 |
| ControllerFailure→Fallback | JTC inactive→切换控制器/abort |
| GraspRetry | 抓取失败→重试(最多3次) |
| Recovery集成到BT | BT Recover节点调用RecoveryManager |

#### M5.2 BT Plugin Architecture Refactor ✅

**问题**: 当前ROS2 BT插件在async callback中创建临时节点导致executor死锁。

**解决方案**: 共享Node + AsyncTick模式

```
TaskPlanner ROS2 Node (唯一)
    |
    +-- BT Plugin
          |
          async service/action client (共享Node)
          |
          tick → RUNNING (future pending)
          |
          next tick → check future → SUCCESS/FAILURE
```

类似BehaviorTree.CPP的`AsyncActionNode`模式：BT tick返回RUNNING直到ROS2 future完成。

**关键实现**:
- `AsyncActionNode`基类：`_make_completed_future()` + `_check_result()` 模板方法
- Sequence/Selector添加`_running_child_idx`记忆RUNNING子节点位置
- 8个async ROS2插件：AsyncMoveToNode, AsyncRetractNode, AsyncCheckSafetyNode, AsyncQueryWorldNode, AsyncGraspNode, AsyncPlaceNode, AsyncLiftNode, AsyncRecoverNode
- ActionClient非阻塞模式：`wait_for_server(timeout_sec=0.1)` + waiting retry
- TaskPlanner默认`use_ros2_plugins=True`，mock插件仅用于单元测试

| 验收项 | 通过条件 | 状态 |
|--------|----------|------|
| 共享Node插件 | BT插件使用TaskPlanner的Node，不创建临时节点 | ✅ |
| AsyncTick模式 | tick返回RUNNING→下次tick检查future→SUCCESS/FAILURE | ✅ |
| 无executor死锁 | 双臂并发BT执行无死锁 | ✅ E2E 8/8 + 双臂冲突 8/8 |
| 替换mock插件 | pick_place_ros2.xml成为默认，mock仅用于单元测试 | ✅ |

**M5.2关键发现**:
- BT XML中`{blackboard_key}`引用不被`_build_node()`解析，需使用扁平Sequence结构
- Sequence/Selector必须记忆RUNNING子节点位置，否则async节点被反复重置
- `wait_for_server()`在BT tick内部会阻塞executor，必须用非阻塞检查+retry
- `create_client`不能用于Action类型，必须用`rclpy.action.ActionClient`
- 服务不可用时AsyncQueryWorldNode返回SUCCESS（fallback），AsyncCheckSafetyNode返回FAILURE（安全优先）

**测试**: 286 tests ALL PASS (含27个async插件测试)

#### M5.3 Task Message Upgrade ✅

**问题**: 当前`description="arm1:zone_a:ready"`是字符串协议，不够灵活。

**方案**: 扩展multi_arm_interfaces，从字符串协议升级为领域模型。

新增msg:
```
TaskGoal.msg       # 任务目标（action_type, arm_name, zone_name, position_name, object_id, approach, constraints）
TaskConstraint.msg # 约束（max_time, safety_level, priority, allow_recovery, max_retries）
MotionRequest.msg  # 运动请求（arm_name, target_position, joint_positions, speed_scale, collision_check, max_velocity）
```

**ExecuteTask.action扩展**: 新增`TaskGoal goal`字段，保留`description`用于向后兼容。

**Coordinator解析优先级**: TaskGoal.arm_name非空 → 使用`_parse_task_goal()`；否则fallback到`_parse_task()`解析字符串。

**BT插件更新**: AsyncMoveToNode/AsyncRetractNode构造ExecuteTask.Goal时同时填充`description`和`goal`字段。

**TaskPlanner更新**: 从TaskGoal字段覆盖blackboard默认值（arm_name, zone_name, position_name, object_id, approach）。

| 验收项 | 通过条件 | 状态 |
|--------|----------|------|
| TaskGoal.msg定义 | 包含action_type, target, constraints字段 | ✅ |
| Coordinator解析TaskGoal | 替代_parse_task字符串解析 | ✅ _parse_task_goal() |
| 向后兼容 | 旧字符串格式仍可解析（fallback） | ✅ _parse_task()保留 |
| BT插件使用TaskGoal | MoveTo/Retract构造结构化goal | ✅ |
| MotionRequest.msg | 运动请求消息定义 | ✅ |

**测试**: 307 tests ALL PASS (含21个TaskGoal测试)

#### M5.4 Benchmark System ✅

**新增包**: `multi_arm_benchmark`

```
multi_arm_benchmark/
├── benchmark_node.py        # ROS2节点（场景执行+数据采集）
├── benchmark_recorder.py    # 采集执行数据→SQLite
├── scenario_runner.py       # 场景YAML→自动执行
├── regression_detector.py   # 性能退化检测
└── scenarios/
    ├── single_arm.yaml      # 单臂场景
    ├── dual_arm.yaml        # 双臂场景
    ├── conflict.yaml        # 资源冲突场景
    └── recovery.yaml        # 恢复场景
```

**采集指标**:
```
task_start, planning_time, execution_time, success,
failure_reason, resource_wait_time, recovery_count,
collision_count, safety_rejections
```

**SQLite Schema**:
- `runs`表：run_id, scenario_name, start_time, end_time, total_duration, success_count, failure_count, git_hash, metadata
- `task_records`表：record_id, run_id, task_id, arm_name, action_type, description, planning_time, execution_time, total_time, success, failure_reason, resource_wait_time, recovery_count, collision_count, safety_rejections

**RegressionDetector**: 可配置阈值，支持success_rate/planning_time/execution_time/total_time退化检测，趋势分析。

| 验收项 | 通过条件 | 状态 |
|--------|----------|------|
| benchmark.db | SQLite记录每次任务执行数据 | ✅ |
| 场景YAML | 定义benchmark场景(单臂/双臂/冲突/恢复) | ✅ 4个场景 |
| 指标采集 | planning_time, execution_time, success_rate, collision_count, recovery_count, resource_wait_time | ✅ |
| 自动运行 | BenchmarkNode + ScenarioRunner | ✅ |
| 回归检测 | RegressionDetector比较历史运行 | ✅ |

**测试**: 341 tests ALL PASS (含34个benchmark测试)

#### M5.5 CI/CD Pipeline ✅

**四层质量保障**:

```
Layer 1: colcon build (所有包编译通过)
Layer 2: unit test (pytest + colcon test)
Layer 3: launch test (ros2 launch + node alive check)
Layer 4: E2E smoke test (提交任务→验证成功/失败)
```

**CI脚本**: `ci/run_ci.sh` — 支持`--layer`选择和`--skip-4`跳过Gazebo层

**GitHub Actions**: `.github/workflows/ci.yml` — 4个job（build→test→interface-compat→performance-regression）

| 验收项 | 通过条件 | 状态 |
|--------|----------|------|
| colcon build自动化 | GitHub Action: build all packages | ✅ |
| Interface兼容性检查 | multi_arm_interfaces变更触发全量测试 | ✅ |
| Launch smoke test | ros2 launch + node alive check | ✅ |
| E2E smoke test | 提交任务→验证成功/失败 | ✅ |
| Performance regression | benchmark对比上次结果 | ✅ |

**测试**: 355 tests ALL PASS (含14个CI pipeline测试)

#### M5.6 Simulation Stress Test

**核心转变**: 从"能完成任务"到"任务泛化+场景鲁棒性"。验证系统面对随机参数、失败注入、多任务调度时的表现。

**定位**: M1-M5.5验证了"架构闭环能力"（大脑、神经系统、脊柱连接正确），M5.6验证"大脑是否真的会思考和适应"。

**5个压力等级**:

```
Level 1: 任务参数变化 — RandomTaskGenerator
  object ∈ {cube, cylinder, box}
  location ∈ {zone_a, zone_b, zone_c}
  pose随机
  100次随机PickPlace → Success Rate / Planning Time / Recovery Count

Level 2: 动态障碍物 — Gazebo中移动障碍
  人经过 / 工具箱移动 / 第二臂占用空间
  WorldModel更新 → 重新规划 → 继续执行

Level 3: 失败注入测试 — 故意制造失败
  规划失败: 不可达目标 → PlanningFailure → Relax → Retry
  控制器故障: kill JTC → ControllerFailure → Switch/Abort
  Safety触发: velocity > limit → E-Stop → Abort

Level 4: 多任务调度 — 任务队列
  Task A: arm1 pick (priority=2)
  Task B: arm2 assembly (priority=1)
  Task C: arm1 inspect (priority=3)
  验证: Priority + Resource Allocation + Preemption

Level 5: 真正复杂操作 — 双臂协作
  双臂协作搬运: arm1 grasp left + arm2 grasp right → synchronized trajectory
  装配任务: pick screw → insert hole → tighten
  需要: 更精细规划 + 力控 + 接触检测
```

| 验收项 | 通过条件 | 状态 |
|--------|----------|------|
| L1 随机任务100次 | Success Rate > 80%, 无硬编码依赖 | ✅ 100次, Success Rate=100% (纯Python) |
| L1 Gazebo E2E 20次 | Success Rate > 80%, 真实运动执行 | ✅ 20次, Success Rate=100% |
| L3 规划失败注入 | PlanningFailure → Recovery → Success/Abort | ✅ 验证通过 |
| L3 控制器故障注入 | ControllerFailure → Fallback/Abort | ✅ 验证通过 |
| L3 Safety触发 | velocity超限 → E-Stop → Abort | ✅ 验证通过(不可恢复,正确abort) |
| L3 Gazebo E2E Safety | SafetyCheck服务正常 | ✅ approved=True, scale=1.0 |
| L4 多任务调度 | 优先级排序+资源分配+排队 | ✅ 3任务优先级队列验证 |
| L4 Gazebo E2E多任务 | 3任务全部成功 | ✅ |
| Benchmark记录压力数据 | SQLite记录所有压力测试指标 | ✅ |

**M5.6关键发现**:
- place_high初始值[-1.8, 1.2]被SafetySupervisor拒绝（关节超限），修正为[-1.5, 1.5]后通过——Safety在E2E场景中正确工作
- Gazebo E2E真实运动执行时间~2-5s，规划时间<0.1s
- RandomTaskGenerator参数空间：5物体×3区域×9位置×2臂×3接近方式

#### M5.7 Interface & Architecture Audit ✅

**目标**: 系统性盘点接口，冻结下一阶段演进接口（API Freeze / Architecture Review / ICD）。

**五项审计**:

1. **接口资产盘点**: 18个接口（8 Action/Srv/Topic FROZEN + 2 EXPERIMENTAL + 1 RESERVED）
2. **数据模型清算**: TaskGoal/TaskConstraint/ExecuteTask/SafetyCheck等核心数据结构冻结v1.0
3. **模块边界审计**: 7层架构映射，发现2处越层调用（BT插件直连Safety/WorldModel），接受为已知偏差
4. **M6/M7接口预留**: Perception Interface、Skill Interface、Agent Interface、Robot Hardware Interface
5. **版本治理**: Interface Freeze v1.0，禁止破坏性修改，CI interface-compat检查

| 验收项 | 通过条件 | 状态 |
|--------|----------|------|
| interface_catalog.md | 所有msg/srv/action盘点 | ✅ 18个接口 |
| data_flow.md | 任务/安全/环境/恢复数据流 | ✅ 8个数据流 |
| dependency_graph.md | 7层映射+依赖矩阵+边界审计 | ✅ 2处越层(接受) |
| api_contracts.md | 接口契约+数据模型冻结+M6/M7预留 | ✅ v1.0 Freeze |
| 模块边界审计 | 无越层调用(或已记录) | ✅ 2处已知偏差 |
| 数据模型冻结 | 核心结构不可变 | ✅ 13个FROZEN |
| M6/M7接口预留 | Perception/Skill/Agent/HW | ✅ 4组预留 |
| 版本治理 | Interface Freeze v1.0 | ✅ |

**M5.7关键发现**:
- BT插件直连SafetyCheck/QueryResources是越层调用（L6→Safety/L5），但为只读查询且避免Coordinator瓶颈，接受为已知偏差
- RecoveryManager是纯Python模块非ROS2节点，RecoverFromFailure.srv预留为M6分布式接口
- SafetyCheck不可用时Coordinator默认批准运动——M6需改为默认拒绝（安全优先）
- /perception/object_poses topic已由WorldModel订阅，M6实现Publisher即可接入感知

**Interface Freeze v1.0**: ExecuteTask, TaskGoal, TaskConstraint, SafetyCheck, EmergencyStop, QueryResources, RecoverFromFailure, CollisionEvent, ObjectPose, ResourceStatus, RecoveryAction, SystemHealth, MotionRequest + 3个Topic

### M6: Robot Platform Upgrade

**核心理念**: M5=机器人OS内核 | M6=机器人OS运行时 | M7=机器人智能层
> 不是"给机器人加功能"，而是"把双臂控制系统升级为机器人操作系统运行时"

**前置依赖**: M5.7 Interface Freeze v1.0完成

**详细规划**: `docs/architecture/M6_platform_upgrade_plan.md` (第四轮架构评审后调整)

```
M6.0 Robot Description Layer      — robot.yaml + 动态Capability Registry + Hardware Adapter
M6.S Simulation Infrastructure    — 仿真平台 (提前, 横向贯穿M6.1-M6.6)
M6.1 Perception + WorldModel      — 感知 + 世界模型5层 (Entity/State/Relation/History/Prediction)
M6.2 Manipulation Layer           — Gripper + Object attachment + Force feedback
M6.3 Skill Runtime                — Skill五要素 + Manifest + Registry + Lifecycle
M6.5 Robot Runtime API            — 能力接口 (重命名, 非自然语言, 语言理解属M7)
M6.6 Mobile Base                  — 移动底盘 (后置)
Data Layer (横切)                 — Robot Data Pipeline (Sensor/Episode/Skill/Failure/WorldModel/Dataset)
```

**第四轮调整**: Capability动态服务(三层) + WorldModel Relation Layer(5层) + Skill Lifecycle + Sim提前 + Robot Runtime API重命名 + Data Layer横切

#### M6.0 Robot Description Layer

**目标**: Robot Infrastructure as Code — 不造平行系统，作为ROS模型上层管理

```
robot.yaml (结构) + capability.yaml (Static能力) + 动态Capability Registry (运行时能力服务) + Hardware Adapter
机器人差异主要不是结构而是能力: UR5e(joint_position,6DOF) vs Franka(joint_torque,7DOF) vs Humanoid(whole_body)
```

**动态Capability Registry三层**: Static Capability(固有能力) + Dynamic Capability(当前状态, payload_remaining/gripper_overheated) + Context Capability(环境限制, can_reach/can_grasp/path_clear)

| 验收项 | 通过条件 |
|--------|----------|
| robot.yaml | 声明所有组件，参数化驱动 |
| capability.yaml | 声明Static Capability（固有能力） |
| 动态Capability Registry | 三层能力: Static+Dynamic+Context, 运行时可查询 |
| Capability变化通知 | 能力变化时发布/capability/updates |
| 代码生成 | YAML → URDF/SRDF/controllers自动生成 |
| 向后兼容 | 现有multi_arm_robot.xacro仍可用 |
| 换硬件 | robot.yaml + capability.yaml + adapter，上层接口不变 |

#### M6.S Simulation Infrastructure (提前)

**目标**: 仿真本身是平台 — Robot Simulation OS，横向贯穿M6.1-M6.6

**提前理由**: M6.1+所有模块依赖仿真, Simulation是Runtime执行环境之一, 不是事后验证工具

| 验收项 | 通过条件 |
|--------|----------|
| 场景生成器 | 随机生成多样化场景 |
| Domain Randomization | 光照/纹理/位置/物理随机化 |
| Dataset Pipeline | Gazebo → 数据集自动采集 |
| Ground Truth | Gazebo提供精确标注 |
| 仿真/实体切换 | 共享robot.yaml, 仅Hardware Adapter不同 |

#### M6.1 Perception + WorldModel

**目标**: 感知与世界模型绑定 — 没有WorldModel的Perception不是机器人智能

```
Sensor → Perception → WorldModel → Reasoning → Action
WorldModel 5层: Entity Layer + State Layer + Relation Layer + History Layer + Prediction Layer
```

**Relation Layer是Skill判断的关键依赖**: on/near/inside/attached/above/below关系, Skill的precondition/postcondition查询Relation判断是否满足

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

#### M6.2 Manipulation Layer ✅

**目标**: 从"运动控制系统"进入"操作系统" — Gripper + Object attachment + Force feedback

| 验收项 | 通过条件 | 状态 |
|--------|----------|------|
| Robotiq URDF | Gazebo加载UR5e+Gripper模型 | ⬜ (M6.S仿真层) |
| Gripper Controller | open/close控制成功 | ✅ |
| 物理附着 | Gazebo中物体附着到Gripper | ✅ (模拟attach/detach) |
| Manipulation State | WorldModel更新object attached_to/grasp_state | ✅ |
| Relation更新 | WorldModel更新attached_to/on关系 | ✅ |
| 完整PickPlace | 检测→抓取→搬运→放置 全链路成功 | ✅ E2E 8/8 |
| 感知-认知-操作闭环 | Perception→WorldModel→Manipulation→反馈 | ✅ |

**测试**: 30 tests ALL PASS (22 unit + 8 E2E closed-loop)
**验证报告**: `docs/validation/M6_2_validation_report.md`

#### M6.3 Skill Runtime ✅ FROZEN v1.0

**目标**: Skill = Manifest + Capability + Preconditions + Execution + Postcondition + Recovery + Lifecycle (类似pip install, 机器人获得能力)

**Skill Lifecycle**: Install→Register→Validate→Ready→Execute→Monitor→Update→Remove (类似K8s Pod生命周期, 否则Skill Library变成文件仓库)

| 验收项 | 通过条件 | 状态 |
|--------|----------|------|
| Skill Manifest | 包含required_capabilities/input/output/cost/pre/post/recovery | ✅ |
| Skill Lifecycle | Install→Register→Validate→Ready→Execute→Monitor→Update→Remove | ✅ |
| Skill Registry | ListSkills返回READY状态Skill列表 | ✅ |
| Skill Runtime | ExecuteSkill.action执行成功 | ✅ |
| Capability检查 | Skill执行前查询动态Capability Registry三层 | ✅ |
| precondition/postcondition | 条件检查正确（查询WorldModel Relation Layer） | ✅ |
| recovery | Skill失败→恢复策略执行 | ✅ |
| 执行监控 | Monitor更新success_rate/cost → Data Layer | ✅ |
| BT兼容 | 现有BT XML可包装为Skill | ✅ |
| Skill组合 | 多Skill可串联（pick→move→place） | ✅ |
| 热更新 | Skill版本升级不中断当前执行 | ✅ |

**测试**: 102 tests ALL PASS (63 unit + 25 E2E + 12 跨层 + 2 smoke)
**验证报告**: `docs/validation/M6_3_validation_report.md`
**SPEC**: `docs/architecture/M6_3_SPEC.md` (12项冻结)
**ADR**: `docs/architecture/ADR-M6.3-Freeze.md`
**状态**: 🔒 FROZEN v1.0 — M6 Gate 2 Baseline, 禁止破坏性修改

#### M6.5 Robot Runtime API ✅

**目标**: M6只提供能力接口，不包含自然语言理解（语言理解属M7）

**重命名理由**: 旧名"Agent Capability Interface"误导(M6没有Agent), 新名"Robot Runtime API"准确反映M6提供的是Runtime能力接口

```
M6提供: ExecuteSkill, QueryWorld, GetCapability, ListSkills, ManageSkill, SubmitTaskGoals, QueryExperience
M7负责: 自然语言理解, 规划, 推理, 任务拆解, Agent决策, 从Experience学习
```

**新增包**: `multi_arm_runtime_api`

```
multi_arm_runtime_api/
├── runtime_api_node.py    # 统一聚合层节点
└── launch/runtime_api.launch.py
```

**新接口**:
- `SubmitTaskGoals.action` — 统一任务提交入口(TaskGoal[] → results[], success_count, total_count)

**7个Robot Runtime API** (统一入口 `/runtime/*`):

| API | 类型 | 话题 | 后端 |
|-----|------|------|------|
| SubmitTaskGoals | action | /runtime/submit_task_goals | → /skill/execute (ExecuteSkill) |
| QueryWorld | proxy | /runtime/query_world | → /world_model/query_world |
| GetCapability | proxy | /runtime/get_capability | → /capability/get_capability |
| ListSkills | proxy | /runtime/list_skills | → /skill/list |
| ManageSkill | proxy | /runtime/manage_skill | → /skill/manage |
| QueryExperience | proxy | /runtime/query_experience | → /experience/query |
| ExecuteSkill | action client | /skill/execute | 直接调用 |

**action_type → skill_name映射**: pick_place→pick_object, place→place_object, move→move_object, grasp→pick_object, lift/retract/inspect→move_object

| 验收项 | 通过条件 | 状态 |
|--------|----------|------|
| Robot Runtime API | ExecuteSkill/QueryWorld/GetCapability/ListSkills/ManageSkill/SubmitTaskGoals | ✅ 7个API |
| TaskGoal引用 | 接口引用M5.7冻结的TaskGoal | ✅ SubmitTaskGoals.action + ExecuteSkill.action |
| 边界清晰 | M6不含自然语言理解，M7负责 | ✅ |
| Skill调用 | SubmitTaskGoals → ExecuteSkill链路 | ✅ E2E验证(mock ExecuteSkill server) |
| 能力查询 | GetCapability返回三层能力(Static+Dynamic+Context) | ✅ 代理到/capability/get_capability |

**测试**: 32 tests ALL PASS (9 mapping + 4 TaskGoal引用 + 8 接口可用性 + 4 backend不可用 + 5 SubmitTaskGoals链路 + 2 smoke)
**验证报告**: `docs/validation/M6_5_validation_report.md`

#### M6.6 Runtime Developer Experience ✅

**原M6.6 Mobile Base → 推迟到M7**: 移动底盘(Navigation2+SLAM)属于Navigation Capability，不属于Robot Runtime Platform，推迟到M7。

**M6.6重新定义**: Runtime Developer Experience — 机器人的kubectl。Python CLI工具集，让已有426+测试、Simulation E2E、Skill Runtime真正变成"可使用的平台"。

**定位**: 开发阶段最需要的不是Web UI(展示层)，而是CLI(交互层)。CLI成本低(~500行)，解决80%问题：架构验证、调试Runtime、快速体验闭环能力。M6.7 Web Visualization实施顺序后移，其设计仍有价值(未来展示层)。

**新增包**: `multi_arm_tools`

```
multi_arm_tools/
├── multi_arm_tools/
│   ├── cli.py                 # 主CLI入口 (robot命令)
│   ├── runtime_client.py      # Runtime API客户端(封装ROS2 service/action)
│   ├── trace_viewer.py        # Trace终端渲染(树状/时间线)
│   ├── episode_viewer.py      # Episode Inspector(查看历史/失败案例)
│   ├── world_query.py         # WorldModel查询+展示
│   └── benchmark_runner.py    # 批量Benchmark(100 episodes → success rate)
├── test/
│   ├── test_cli.py
│   ├── test_trace_viewer.py
│   └── test_benchmark_runner.py
├── package.xml
└── setup.py
```

**CLI命令** (机器人的kubectl):
```bash
robot status                    # 机器人+世界+Skill概览
robot world [object_id]         # 世界状态查询
robot world --relations         # 关系图
robot skills                    # 已注册Skill列表
robot capability                # 三层能力查询
robot run pick_place red_cube zone_b  # 提交任务+实时Trace
robot episodes [--failures-only]      # Episode历史
robot episode <id>              # Episode详情+Trace回放
robot traces [--recent N]       # Trace历史
robot benchmark pick_place --count 100  # 批量Benchmark
```

**4个核心工具**:

1. **Runtime CLI** — 任务提交、状态查询(robot status/world/skills/capability/run)
2. **Trace Viewer** — 终端渲染Skill执行决策链路(TaskGoal→Skill选择→Precondition→Execute→Recovery→Verification)
3. **Episode Inspector** — 查看历史Episode、失败案例、step-by-step回放
4. **Benchmark Runner** — 批量执行(100 episodes → success rate/avg duration/failure breakdown)

**接口依赖**: 纯消费M5.7 FROZEN v1.0 + M6.5 Runtime API接口，无新增ROS2接口

| 验收项 | 通过条件 | 状态 |
|--------|----------|------|
| Runtime CLI | robot status/world/skills/capability/run命令可用 | ✅ |
| Trace Viewer | 终端渲染Skill执行决策链路(树状/时间线) | ✅ |
| Episode Inspector | 查看历史Episode+失败案例+step回放 | ✅ |
| Benchmark Runner | 批量执行→success rate/duration/failure breakdown | ✅ |
| 闭环体验 | robot run → 实时Trace → Episode记录 → 验证 | ✅ |

**测试**: 57 tests ALL PASS (21 CLI + 7 Analyzer + 8 TaskManager + 6 SimManager + 5 Trace + 6 Episode + 6 WorldQuery + 5 Benchmark)
**验证报告**: `docs/validation/M6_6_validation_report.md`
**设计文档**: `docs/architecture/M6_6_runtime_cli_design.md`

#### M6.4 Robot Experience Infrastructure ✅

**目标**: Robot Experience Infrastructure — 系统产生的是Robot Experience（Episode, World State Snapshot, Skill Trace, Failure Memory, Dataset Export），不是普通数据。M7 Agent学习的数据来源。

**五类Experience**: Episode Data(完整任务执行记录) + World State Snapshot(执行前后世界状态) + Skill Trace(步骤级执行轨迹) + Failure Memory(失败案例+恢复) + Dataset Export(SQLite+JSON)

**新增包**: `multi_arm_experience`

```
multi_arm_experience/
├── episode.py               # Episode + WorldStateSnapshot + SkillTraceStep + RecoveryRecord
├── experience_recorder.py   # ExperienceRecorder: start/record/finish/capture/query
├── dataset_exporter.py      # DatasetExporter: SQLite + JSON导出
├── experience_node.py       # ROS2节点 (RecordEpisode + QueryExperience + /data/episode)
└── launch/experience.launch.py
```

**新接口**:
- `EpisodeData.msg` — episode完整记录
- `RecordEpisode.srv` — 记录完成的episode
- `QueryExperience.srv` — 查询experience数据

| 验收项 | 通过条件 | 状态 |
|--------|----------|------|
| Episode数据结构 | Episode+Snapshot+SkillTrace+RecoveryRecord | ✅ |
| ExperienceRecorder | start/record_step/record_recovery/finish/capture/query | ✅ |
| DatasetExporter | SQLite(episodes/failures/skill_traces表) + JSON导出 | ✅ |
| ROS2节点 | RecordEpisode服务 + QueryExperience服务 + /data/episode topic | ✅ |
| Episode Data记录 | 任务执行完整episode记录到SQLite | ✅ |
| Skill Trace记录 | 步骤级执行轨迹(名称/成功/耗时/详情) | ✅ |
| Failure Data记录 | 失败案例(原因/上下文/recovery结果) | ✅ |
| WorldModel Snapshot | 执行前后世界状态快照 | ✅ |
| Dataset导出 | SQLite结构化查询 + JSON人类可读 | ✅ |
| M7数据接口 | QueryExperience.srv供M7查询训练数据 | ✅ |

**测试**: 48 tests ALL PASS (12 DatasetExporter + 16 Episode + 18 ExperienceRecorder + 2 smoke)

#### M6.7 Robot Runtime Visualization Layer (设计完成 v2, 实施后移)

**目标**: Robot Runtime Observability Plane — 类似K8s Dashboard, 不是简单UI而是运行时可观测性平面

**定位调整(v3)**: M6.7是展示层(适合Demo/教学/运营监控)，当前开发阶段优先实施M6.6 Runtime CLI(交互层)。M6.7设计仍有价值，实施顺序后移到M6.6完成后。

**核心理念**: 横切平面(类似Safety Plane), **只读**消费所有M6运行时状态, 零侵入现有代码

**v2关键调整** (根据架构评审反馈):
1. **纯只读** — 移除所有控制能力(execute/e-stop/release/submit_task_goals), 控制属于Control Plane(M7.x)
2. **Trace模型** — 类似OpenTelemetry的trace_id+events结构, Skill Timeline基于Trace Viewer实现
3. **2D优先** — MVP不做3D渲染(避免重新造RViz), 用2D Scene Graph替代
4. **优先级调整** — WorldModel Viewer + Skill Timeline + Episode Replay为Phase 2核心, Robot State+Safety降为Phase 3

**新增包**: `multi_arm_visualization`

```
multi_arm_visualization/
├── viz_bridge_node.py          # ROS2节点 + WebSocket服务器(tornado)
├── data_collector.py            # ROS2数据聚合器(订阅所有topic)
├── trace_collector.py           # Trace收集器(构建Trace模型)
├── trace_model.py               # Trace + TraceEvent数据结构
├── episode_replay.py            # Episode回放引擎(重建Trace)
├── web_server.py                # HTTP/WebSocket服务器(只读REST)
├── web/                         # 单页HTML前端(零构建, CDN加载)
│   ├── index.html
│   ├── js/
│   │   ├── world_model_viewer.js # WorldModel Viewer(2D Scene Graph, Phase 2核心)
│   │   ├── skill_timeline.js    # Skill时间线(基于Trace模型, Phase 2核心)
│   │   ├── episode_replayer.js  # Episode回放器(Phase 2核心)
│   │   ├── runtime_console.js   # 只读查询控制台
│   │   ├── robot_state.js       # 机器人状态面板(Phase 3辅助)
│   │   ├── safety_panel.js      # 安全状态面板(Phase 3辅助, 只读)
│   │   └── scene_graph.js       # 2D Scene Graph渲染
│   └── css/style.css
└── launch/visualization.launch.py
```

**6个可视化面板** (按优先级排序):
1. **WorldModel Viewer** (Phase 2核心) — Objects+Relations+Task Context+2D Scene Graph(Digital Twin Explorer)
2. **Skill Timeline** (Phase 2核心) — 基于Trace模型的Skill执行决策链路(可解释性)
3. **Episode Replayer** (Phase 2核心) — 历史Episode回放(step-by-step, 类似自动驾驶数据回放)
4. **Runtime Console** (Phase 2) — 只读查询控制台(query capability/list skills/query world/query episodes/query traces)
5. **Robot State Panel** (Phase 3辅助) — 关节状态+控制器+Gripper(实时10Hz WebSocket)
6. **Safety Panel** (Phase 3辅助, 只读) — 安全状态+碰撞监控(无控制按钮, E-Stop/Release属于Control Plane)

**技术选型**: Python tornado(WebSocket) + 单页HTML/vanilla JS(零构建) + Canvas 2D/SVG(2D Scene Graph) + Chart.js CDN(图表)

**Trace模型**: 类似OpenTelemetry, Trace(trace_id+events[])从EpisodeData构建, 不单独持久化, 支持历史回放重建

**接口依赖**: 纯消费M5.7 FROZEN v1.0只读接口, 无新增ROS2接口。已排除EmergencyStop和SubmitTaskGoals(属于Control Plane)

**实施顺序**: Phase 0接口验证 → Phase 1 Runtime Snapshot(不用Web) → Phase 2 Web Dashboard(WMV+Timeline+Replay) → Phase 3 Robot State+Safety → Phase 4 3D View(未来)

| 验收项 | Phase | 通过条件 | 状态 |
|--------|-------|----------|------|
| VizBridgeNode | 1 | ROS2节点+WebSocket服务器(port 8080) | ⬜ |
| Runtime Snapshot | 1 | DataCollector聚合所有topic数据 | ⬜ |
| WorldModel Viewer | 2 | 物体+关系+任务上下文+2D Scene Graph | ⬜ |
| Skill Timeline | 2 | 基于Trace模型显示Skill执行决策链路 | ⬜ |
| Episode Replayer | 2 | 历史Episode回放(step-by-step) | ⬜ |
| Runtime Console | 2 | 只读查询(capability/skills/world/episodes/traces) | ⬜ |
| Robot State Panel | 3 | 实时显示关节状态(10Hz) | ⬜ |
| Safety Panel | 3 | 安全状态+碰撞事件(只读) | ⬜ |
| Web界面可访问 | 2 | http://localhost:8080 | ⬜ |

**设计文档**: `docs/architecture/M6_7_visualization_design.md` (v2)

#### M6 Sim2Real (贯穿)

| 验收项 | 通过条件 |
|--------|----------|
| UR Driver集成 | ur_robot_driver连接真实UR5e |
| 参数统一 | 仿真/实体配置同一YAML(仅hardware_interface不同) |
| Safety实体验证 | 真实E-Stop按钮→控制器停止 |
| Sim2Real gap测量 | benchmark对比仿真vs实体执行数据 |

---

## 项目成熟度

| 里程碑 | 状态 | 说明 |
|--------|------|------|
| M1 Interface Architecture | ✅ | 109 tests |
| M2 Safety + Motion Foundation | ✅ | 36 tests |
| M3 WorldModel + TaskPlanner | ✅ | 54 tests |
| M4 Gazebo Integration | ✅ | 7/8 (缺Benchmark数据) |
| M4.5 MoveIt Validation | ✅ | 双臂规划+执行验证 |
| M4.6 Autonomous Task Loop | ✅ 超额完成 | 158 tests (单元131+代码11+E2E8+双臂8) |
| M5 Reliability & Intelligence | ✅ 全部完成 | M5.1-M5.5 ✅ (355), M5.6 Stress Test ✅ (383+Gazebo E2E), M5.7 Audit ✅ |
| M6 Robot Platform Upgrade | ✅ Gate 2基线 | M6.0 ✅ (30), M6.S ✅ (44), M6.1 ✅ (40), M6.2 ✅ (30, E2E 8/8), M6.3 ✅ FROZEN v1.0 (102, E2E 25/25, 跨层 12/12), M6.4 ✅ (48), M6.5 ✅ (32), M6 E2E ✅ (17, 5节点7链路), M6 Full-Chain E2E ✅ (12, 全组件协同+可视化), L6 Simulation E2E ✅ Phase 1+2+3+4+5 (22 tests), M6.6 ✅ Runtime Developer Experience (57 tests, Runtime CLI: 机器人的kubectl, 5阶段全部完成: sim+doctor+task+analyze+watch), M6.7设计完成v2 (只读Observability Plane+Trace模型+2D优先, 实施后移) |
| M7 Embodied Manipulation | ✅ 全部完成 | M7.INT ✅ (68), M7.EXEC ✅ (8), M7.1 ✅ Body Upgrade (10), M7.4 ✅ Vision Grounding (8), M7.5 ✅ Real Perception (9), M7.6 ✅ WorldModel Intelligence (26), M7.FINAL ✅ System Acceptance (23 tests, 15场景+7不变量, GT隔离+独立Evaluation层, 10/10连续任务100%, Exit Gate PASSED), M7.CLI ✅ Operator Interface v2 (22 tests, 三层认知+命令/输出/退出码契约冻结+--json+safety stop直连), **Robot OS Shell ✅ Runtime Manager (22 CLI tests + 5 E2E: start/stop/repair/restart/shell, Session manifest + PID 树 + DDS 隔离 domain 40-59, auto-repair, 增强 doctor 含 Runtime+DDS ghost 检测)** — M7 Total 196 tests |

---

## 设计文档索引

| 文档 | 路径 | 说明 |
|------|------|------|
| 架构设计 | `output/Architecture-MultiArm-202608051018.md` | 8层架构+模块划分+数据流+通信+部署+演进 |
| 架构验证 | `docs/architecture/system_architecture_v2.md` | v2.0架构验证总结 |
| PRD | `output/PRD-MultiArm-Dev-202608051004.md` | 产品需求，10项功能需求 |
| HLD | `output/HLD-MultiArm-Dev-202608051004.md` | 高层架构（待更新对齐8层） |
| LLD-1 | `output/LLD-MoveIt2-Safety-202608051004.md` | MoveIt2+安全模块详细设计 |
| LLD-2 | `output/LLD-PickPlace-Scheduler-202608051018.md` | 抓取+调度详细设计 |
| TDD | `output/TDD-SimRealSwitch-CICD-202608051004.md` | 虚实同步+CI/CD技术设计 |
| 验收 | `output/Verification-MultiArm-202608051018.md` | 验收标准，44项增量验收 |
| M1验证 | `docs/validation/M1_validation_report.md` | M1验证报告 (109 tests) |
| M2验证 | `docs/validation/M2_validation_report.md` | M2验证报告 (36 tests) |
| M3验证 | `docs/validation/M3_validation_report.md` | M3验证报告 (54 tests) |
| E2E验证 | `docs/validation/E2E_validation_report.md` | E2E集成验证报告 (28 tests) |
| 基准 | `docs/benchmark/baseline_report.md` | 性能基线模板 (待M4填充) |
| M4验证 | `docs/validation/M4_validation_report.md` | M4验证报告 |
| M4.5验证 | `docs/validation/M4_5_validation_report.md` | M4.5 Motion+Coordination验证报告 |
| M4.6验证 | `docs/validation/M4_6_validation_report.md` | M4.6 Autonomous Task Loop验证报告 |
| M5.1验证 | `docs/validation/M5_1_validation_report.md` | M5.1 Recovery Framework验证报告 |
| M5.2验证 | `docs/validation/M5_2_validation_report.md` | M5.2 BT Plugin Architecture验证报告 |
| M5.3验证 | `docs/validation/M5_3_validation_report.md` | M5.3 Task Message Upgrade验证报告 |
| M5.4验证 | `docs/validation/M5_4_validation_report.md` | M5.4 Benchmark System验证报告 |
| M5.5验证 | `docs/validation/M5_5_validation_report.md` | M5.5 CI/CD Pipeline验证报告 |
| M5.6验证 | `docs/validation/M5_6_validation_report.md` | M5.6 Simulation Stress Test验证报告 |
| 接口目录 | `docs/architecture/interface_catalog.md` | M5.7 接口资产盘点 (18接口) |
| 数据流 | `docs/architecture/data_flow.md` | M5.7 数据流图 (8流) |
| 依赖图 | `docs/architecture/dependency_graph.md` | M5.7 模块依赖+边界审计 |
| API契约 | `docs/architecture/api_contracts.md` | M5.7 接口契约+数据模型冻结+M6/M7预留 |
| M5.7验证 | `docs/validation/M5_7_validation_report.md` | M5.7 Interface & Architecture Audit验证报告 |
| M6.2验证 | `docs/validation/M6_2_validation_report.md` | M6.2 Manipulation Layer验证报告 (30 tests, E2E 8/8) |
| M6.3验证 | `docs/validation/M6_3_validation_report.md` | M6.3 Skill Runtime验证报告 (90 tests, E2E 25/25) |
| M6.3 SPEC | `docs/architecture/M6_3_SPEC.md` | M6.3 Skill Runtime接口冻结SPEC (12项冻结) |
| M6.3 ADR | `docs/architecture/ADR-M6.3-Freeze.md` | M6.3 Interface Freeze决策记录 |
| M6.4验证 | `docs/validation/M6_4_validation_report.md` | M6.4 Robot Experience Infrastructure验证报告 (48 tests) |
| M6.5验证 | `docs/validation/M6_5_validation_report.md` | M6.5 Robot Runtime API验证报告 (32 tests) |
| M6 E2E验证 | `docs/validation/M6_system_e2e_validation_report.md` | M6 System-Level E2E: 5节点真实ROS2集成 (17 tests, 7条链路) |
| M6 Full-Chain E2E | `docs/validation/M6_full_chain_e2e_validation_report.md` | M6全链路E2E: 全部M6组件协同工作+可视化 (12 tests, 0.87s) |
| L6 Simulation E2E | `docs/validation/M6_simulation_e2e_validation_report.md` | L6仿真E2E: Gazebo场景+全栈Pick-Place闭环+失败恢复+Domain Randomization+Episode记录+Dataset导出 (22 tests, Phase 1+2+3+4+5) |
| M6规划 | `docs/architecture/M6_platform_upgrade_plan.md` | M6 Robot Platform Upgrade阶段规划 |
| M6.6验证 | `docs/validation/M6_6_validation_report.md` | M6.6 Runtime Developer Experience验证报告 (36 tests, Runtime CLI: 机器人的kubectl) |
| M6.6设计 | `docs/architecture/M6_6_runtime_cli_design.md` | M6.6 Runtime Developer Experience设计文档 (Runtime CLI: 机器人的kubectl) |
| M6.6使用文档 | `docs/architecture/M6_6_cli_usage_guide.md` | M6.6 Robot Runtime CLI使用文档 (命令详解+工作流+故障排查) |
| M7.CLI教程 | `docs/architecture/M7_CLI_v2_getting_started_tutorial.md` | M7.CLI v2 从零开始手把手教程 (12步: 环境→构建→测试→仿真→OBSERVE→DIAGNOSE→ACT→安全→Benchmark, 含 Robot OS Shell 快速上手) |
| Robot OS Shell设计 | `docs/architecture/Robot_OS_Shell_design.md` | Runtime Manager + Robot OS Shell 设计文档 (Session manifest + PID 树 + DDS 隔离 + auto-repair) |
| Robot OS Shell验证 | `docs/validation/Robot_OS_Shell_validation_report.md` | Runtime Manager 验证报告 (22 CLI tests + 5 E2E: start/stop/repair/restart/shell) |
| M6.7设计 | `docs/architecture/M6_7_visualization_design.md` | M6.7 Robot Runtime Visualization Layer设计文档 (v2: 只读Observability Plane+Trace模型+2D优先, 实施后移) |
| M7.INT验证 | `docs/validation/M7_INT_validation_report.md` | M7.INT Integration Validation (68 tests) |
| M7.EXEC验证 | `docs/validation/M7_EXEC_validation_report.md` | M7.EXEC Execution Validation (8 tests, 100% success) |
| M7.1验证 | `docs/validation/M7_1_validation_report.md` | M7.1 Body Upgrade验证报告 (10 tests, torso+head+RGB-D+IMU) |
| M7.4验证 | `docs/validation/M7_4_validation_report.md` | M7.4 Vision Grounding验证报告 (8 tests, GT+Vision并行, error=0.015m) |
| M7.5验证 | `docs/validation/M7_5_validation_report.md` | M7.5 Real Perception验证报告 (6 tests, image→OpenCV→pose, error=0.038m) |
| M7.6验证 | `docs/validation/M7_6_validation_report.md` | M7.6 WorldModel Intelligence验证报告 (26 tests, 概率belief+多源融合+6缺陷修复) |
| M7.FINAL验证 | `docs/validation/M7_FINAL_validation_report.md` | M7.FINAL System Acceptance验证报告 (23 tests, 15场景+7不变量, GT隔离+独立Evaluation层, Exit Gate PASSED) |
| M7.CLI设计 | `docs/architecture/M7_CLI_v2_operator_interface.md` | M7.CLI Operator Interface v2设计文档 (三层认知+三大契约+命令详解+Agent使用示例) |

---

## Agent行为约束

1. **修改前先理解**：修改任何文件前，必须先阅读相关上下文（imports、调用链、测试）
2. **遵循现有模式**：新代码必须模仿现有代码风格和架构模式
3. **不引入未声明的依赖**：使用任何新库前，先检查package.xml是否已声明
4. **跨包通信走接口**：新增加跨包通信必须通过 `multi_arm_interfaces`，禁止Python类直接共享
5. **构建验证**：每次修改后必须运行 `colcon build` 验证
6. **测试验证**：修改功能代码后必须运行相关测试
7. **不自动commit**：除非用户明确要求
8. **不自动push**：除非用户明确要求
9. **安全优先**：SafetySupervisor相关代码必须保守处理，安全限制不可绕过
10. **中文回复**：始终使用简体中文回复用户
11. **简洁输出**：回答控制在4行以内，除非用户要求详细说明
12. **Coordinator不膨胀**：Coordinator仅做编排，新增业务逻辑必须下沉到子模块
