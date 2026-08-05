# AGENTS.md - 项目规范与Agent约束

> 本文件定义AI Agent（如CodeArts）在本项目中工作时的约束、规范和上下文。Agent必须严格遵守以下规则。

---

## 项目概述

双UR5e多机械臂ROS2仿真与协调控制系统。ROS2 Jazzy + Gazebo Harmonic，运行在WSL2 (Ubuntu 24.04) 环境。目标架构为7层功能层 + Safety横切平面，当前处于Phase 1（基础重构阶段）。

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

### 当前（Phase 1 过渡期）

```
multi_arm_line_ws/
├── src/
│   ├── order_manager/              # [遗留] 过渡期保留，逐步迁移到multi_arm_core
│   ├── ur_simulation_gz/           # Gazebo仿真包 (ament_cmake)
│   └── README_MULTI_ARM.md
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

# 运行测试
colcon test --packages-select order_manager

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

## 设计文档索引

| 文档 | 路径 | 说明 |
|------|------|------|
| 架构设计 | `output/Architecture-MultiArm-202608051018.md` | 8层架构+模块划分+数据流+通信+部署+演进 |
| PRD | `output/PRD-MultiArm-Dev-202608051004.md` | 产品需求，10项功能需求 |
| HLD | `output/HLD-MultiArm-Dev-202608051004.md` | 高层架构（待更新对齐8层） |
| LLD-1 | `output/LLD-MoveIt2-Safety-202608051004.md` | MoveIt2+安全模块详细设计 |
| LLD-2 | `output/LLD-PickPlace-Scheduler-202608051018.md` | 抓取+调度详细设计 |
| TDD | `output/TDD-SimRealSwitch-CICD-202608051004.md` | 虚实同步+CI/CD技术设计 |
| 验收 | `output/Verification-MultiArm-202608051018.md` | 验收标准，44项增量验收 |

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
