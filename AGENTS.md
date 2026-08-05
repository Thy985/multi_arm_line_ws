# AGENTS.md - 项目规范与Agent约束

> 本文件定义AI Agent（如CodeArts）在本项目中工作时的约束、规范和上下文。Agent必须严格遵守以下规则。

---

## 项目概述

双UR5e多机械臂ROS2仿真与协调控制系统。ROS2 Jazzy + Gazebo Harmonic，运行在WSL2 (Ubuntu 24.04) 环境。目标架构为7层功能层 + Safety横切平面。

**当前阶段**: M1-M3 + E2E已通过（软件架构闭环验证完成），进入M4 Simulation E2E Validation。

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

### M5: Reliability Engineering（后续）

**目标**: 从"能跑"到"跑得稳"。Recovery+Benchmark+CI/CD三位一体。

#### M5.1 Recovery

| 验收项 | 通过条件 |
|--------|----------|
| PlanningFailure→Replan | 规划失败→放宽约束重规划 |
| CollisionRecovery | 碰撞→退回安全位→重规划 |
| ResourceTimeout→Release | 资源等待超时→释放→重新分配 |
| ControllerFailure→Fallback | JTC inactive→切换控制器/abort |
| GraspRetry | 抓取失败→重试(最多3次) |

#### M5.2 Benchmark

| 验收项 | 通过条件 |
|--------|----------|
| benchmark.db | SQLite记录每次任务执行数据 |
| 场景YAML | 定义benchmark场景(单臂/双臂/冲突/恢复) |
| 指标采集 | planning_time, execution_time, success_rate, collision_count, recovery_count, resource_wait_time |
| 自动运行 | `ros2 launch multi_arm_benchmark benchmark.launch.py scenario:=pick_place` |
| 回归检测 | 修改后自动跑benchmark，检测性能退化 |

#### M5.3 CI/CD

| 验收项 | 通过条件 |
|--------|----------|
| colcon build自动化 | GitHub Action: build all packages |
| Interface兼容性检查 | multi_arm_interfaces变更触发全量测试 |
| Launch smoke test | ros2 launch + node alive check |
| E2E smoke test | 提交任务→验证成功/失败 |
| Performance regression | benchmark对比上次结果 |

### M6: Sim2Real（远期）

**前置依赖**: 控制接口稳定 + 参数化完成 + Recovery存在 + Benchmark存在

| 验收项 | 通过条件 |
|--------|----------|
| UR Driver集成 | ur_robot_driver连接真实UR5e |
| 参数统一 | 仿真/实体配置同一YAML(仅hardware_interface不同) |
| Safety实体验证 | 真实E-Stop按钮→控制器停止 |
| Sim2Real gap测量 | benchmark对比仿真vs实体执行数据 |

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
