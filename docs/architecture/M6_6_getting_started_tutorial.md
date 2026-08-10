# Robot Runtime CLI 从零开始手把手教程

**目标**: 从空环境开始，用 `robot` 命令跑通完整 Pick-Place 闭环。
**预计耗时**: 15-20 分钟（含构建时间）
**环境**: WSL2 Ubuntu 24.04 + ROS2 Jazzy + Gazebo Harmonic

---

## 第一步：环境准备 (2分钟)

### 1.1 打开终端，source ROS2 环境

```bash
source /opt/ros/jazzy/setup.bash
```

验证：
```bash
echo $ROS_DISTRO
# 应输出: jazzy
```

### 1.2 设置 WSL2 环境变量

```bash
export ROS_HOME=/tmp/ros_home
export HOME=/tmp
export PATH=/usr/bin:$PATH
export GZ_SIM_SYSTEM_PLUGIN_PATH=/opt/ros/jazzy/lib:/opt/ros/jazzy/opt/gz_sim_vendor/lib/gz-sim-8/plugins
```

### 1.3 进入工作空间

```bash
cd ~/multi_arm_line_ws
```

> **提示**: 将以上 export 命令加入 `~/.bashrc` 可避免每次手动输入。

---

## 第二步：构建所有包 (10-15分钟)

### 2.1 构建全部 multi_arm 包

```bash
source /opt/ros/jazzy/setup.bash

colcon build --packages-select \
  multi_arm_interfaces \
  multi_arm_core \
  multi_arm_safety \
  multi_arm_world_model \
  multi_arm_task_planner \
  multi_arm_moveit_config \
  multi_arm_recovery \
  multi_arm_benchmark \
  multi_arm_robot_description \
  multi_arm_perception \
  multi_arm_manipulation \
  multi_arm_skill_runtime \
  multi_arm_runtime_api \
  multi_arm_experience \
  multi_arm_simulation \
  multi_arm_tools \
  ur_simulation_gz
```

预期输出：
```
Starting >>> multi_arm_interfaces
Finished <<< multi_arm_interfaces
...
Starting >>> multi_arm_tools
Finished <<< multi_arm_tools
Summary: 17 packages finished
```

### 2.2 Source 构建结果

```bash
source install/setup.bash
```

### 2.3 添加 `robot` 命令到 PATH

colcon 的 `source install/setup.bash` 不会自动将 `lib/<package>` 加入 PATH。
需要手动添加一行（**每次新终端只需执行一次**）：

```bash
export PATH="$PATH:$(ros2 pkg prefix multi_arm_tools)/lib/multi_arm_tools"
```

> **注意**: 不要用 `~` 路径——`~` 在双引号内不展开，且 WSL2 环境下 `HOME` 可能被设为 `/tmp`。

> **提示**: 将此行加入 `~/.bashrc` 可一劳永逸（**需在 source ROS 环境之后**）：
> ```bash
> echo 'export PATH="$PATH:$(ros2 pkg prefix multi_arm_tools)/lib/multi_arm_tools"' >> ~/.bashrc
> ```

> **替代方案**: 如果不想修改 PATH，也可以用 `ros2 run multi_arm_tools robot` 代替 `robot`。

### 2.4 验证构建成功

```bash
robot --help
```

预期输出：
```
usage: robot [-h] {sim,doctor,status,world,skills,capability,task,run,episodes,episode,analyze,traces,trace,benchmark,watch} ...

Robot Runtime CLI — kubectl for robots
```

---

## 第三步：运行单元测试 (1分钟，无需 Gazebo)

```bash
python3 -m pytest src/multi_arm_tools/test/ -v
```

预期输出：
```
collected 57 items

src/multi_arm_tools/test/test_cli.py::test_cli_import PASSED
src/multi_arm_tools/test/test_analyzer.py::test_analyze_failure PASSED
...
src/multi_arm_tools/test/test_sim_manager.py::test_sim_manager_is_launch_not_running PASSED

============================== 57 passed in 0.93s ==============================
```

> **这验证了什么**: CLI 命令解析、仿真管理、环境诊断、任务管理、Episode分析、Trace渲染、Benchmark — 全部纯 Python 逻辑。

---

## 第四步：一键启动全栈仿真 (3分钟)

**这是最关键的一步** — 以前需要手动开多个终端、输入多条命令，现在只需要一条：

### 4.1 启动仿真

```bash
robot sim start
```

**内部执行流程**：
```
Robot Runtime Starting...

  [OK] ROS2 Jazzy detected
  [OK] Workspace built
  Starting Gazebo simulation...
  Waiting for nodes to be ready...
  [OK] WorldModel ready
  [OK] Safety ready
  [OK] Coordinator ready
  [OK] TaskPlanner ready
  Starting Runtime API node...
  [OK] All interfaces verified

  Runtime Status: READY

  Next steps:
    robot status
    robot world
    robot run pick_place red_cube zone_b
```

> **如果想看 Gazebo GUI**: `robot sim start --gui`
> **headless 模式** (无显示器/SSH): `robot sim start` (默认)

### 4.2 检查仿真状态

```bash
robot sim status
```

预期输出：
```
=== Simulation Status ===

  Simulation:  [RUNNING]
  Runtime API:  [RUNNING]

  Active Nodes (8):
    /coordinator_node
    /gazebo_ground_truth_node
    /runtime_api_node
    /safety_supervisor
    /task_planner_node
    /world_model_node
    ...
```

### 4.3 环境诊断

```bash
robot doctor
```

预期输出：
```
=== Robot Runtime Diagnosis ===

  [ROS2] [OK] DDS communication
  [Simulation] [OK] Gazebo running
  [Workspace] [OK] 17 packages built
  [ROS2] [OK] world_model_node online
  [ROS2] [OK] safety_supervisor online
  [ROS2] [OK] coordinator_node online
  [Controllers] [OK] arm1_joint_trajectory_controller ACTIVE
  [Controllers] [OK] arm2_joint_trajectory_controller ACTIVE
  [MoveIt] [OK] Planning scene available
  [WorldModel] [OK] Query service available
  [Safety] [OK] Supervisor online
  [Runtime API] [OK] 5 services available
  [Experience] [OK] Query service available

  System Health: 100/100 (12/12 checks passed)

  All checks passed. System is healthy.
```

> **如果有问题**: doctor 会显示失败项和修复建议，例如：
> ```
> [Controllers] [FAIL] arm2_controller active
>   Problem: State: inactive
>   Suggested fix: Run: ros2 control set_controller_state arm2_controller active
> ```

---

## 第五步：用 robot CLI 查询系统状态 (1分钟)

### 5.1 系统概览

```bash
robot status
```

预期输出：
```
=== Robot Runtime Status ===

World:
  Objects: 3  Relations: 4
  (red_cube, blue_cylinder, table)

Skills (3):
  pick_object         v1.0  (success=0.87)
  place_object        v1.0  (success=0.92)
  move_object         v1.0  (success=0.95)

Capability (5/5 available):
  [x] manipulation          (static)
  [x] gripper               (static)
  [x] vision                (static)
  [x] planning              (static)
  [x] safety_monitor        (static)

Episodes: 0
```

### 5.2 查看世界状态

```bash
robot world
```

预期输出：
```
Objects (3):
  red_cube         [ 0.50,  0.15,  0.05]  FREE       conf=0.94
  blue_cylinder    [ 0.30, -0.20,  0.10]  FREE       conf=0.88
  table            [ 0.00,  0.00,  0.00]  STATIC     conf=1.00
```

### 5.3 查看关系图

```bash
robot world --relations
```

### 5.4 查看可用任务类型

```bash
robot task list
```

预期输出：
```
Available Tasks:

  pick_place
    Pick up an object and place it at a target zone
    inputs: object_id, zone_name
    skills: detect -> grasp -> move -> place
    example: robot run pick_place red_cube zone_b

  move
    Move robot to a named position
    inputs: position_name
    skills: plan -> execute
    example: robot run move ready

  ...
```

### 5.5 查看预设位置

```bash
robot task positions
```

预期输出：
```
Available Positions:
  home
  ready
  extended
  scan
  inspect
  place_high
  place_low
```

---

## 第六步：执行任务 (3分钟)

### 6.1 提交一个 Move 任务（最简单）

```bash
robot run move ready
```

预期输出（实时 Trace）：
```
Task submitted: move(ready)

[10:01:22] goal_received (0%)
[10:01:23] planning (10%)
[10:01:24] executing (30%)
[10:01:27] completed (100%)

[OK] SUCCESS
  Success: 1/1
```

### 6.2 提交一个 Pick-Place 任务

```bash
robot run pick_place red_cube zone_b
```

预期输出：
```
Task submitted: pick_place(red_cube zone_b)

[10:01:30] goal_received (0%)
[10:01:31] skill_selected (10%)
[10:01:32] precondition_check (20%)
[10:01:33] safety_check (30%)
[10:01:34] executing_grasp (40%)
[10:01:37] executing_place (70%)
[10:01:38] postcondition_check (90%)
[10:01:38] completed (100%)

[OK] SUCCESS
  Success: 1/1
```

### 6.3 调试模式

```bash
robot run pick_place red_cube zone_b --debug
```

预期输出：
```
=== Debug Mode: pick_place(red_cube zone_b) ===

[debug] Building TaskGoal...
  action_type: pick_place
  arm_name: arm1
  object_id: red_cube
  zone_name: zone_b
  approach: top

[debug] Checking preconditions...
  [OK] object_id: red_cube
  [OK] zone_name: zone_b
  Checking object 'red_cube' in world model...
    [OK] Object found: red_cube
    position: [0.50, 0.15, 0.05]
    grasp_state: FREE
    confidence: 0.94

[debug] Submitting task...

[debug] Result analysis:
  success: True
  success_count: 1
  total_count: 1
```

### 6.4 指定 arm2 执行

```bash
robot run move ready --arm arm2
```

### 6.5 静默模式

```bash
robot run move home --no-trace
```

---

## 第七步：查看执行历史 (2分钟)

### 7.1 查看 Episode 历史

```bash
robot episodes
```

预期输出：
```
Recent Episodes (3):
  episode_00003  move            [OK]   3.20s  0 recovery
  episode_00002  pick_place      [OK]   7.44s  0 recovery
  episode_00001  move            [OK]   2.80s  0 recovery
```

### 7.2 查看 Episode 详情

```bash
robot episode episode_00002
```

预期输出：
```
Episode: episode_00002
  Task:       pick_place
  Skill:      pick_object
  Robot:      arm1
  Result:     [OK] SUCCESS
  Duration:   7.44s
  Recovery:   0 attempts

Steps (6):
  [1] 0.1s  skill_select              [OK]
  [2] 0.0s  precondition              [OK]
  [3] 0.1s  safety_check              [OK]
  [4] 2.3s  execute_grasp             [OK]
  [5] 2.1s  execute_place             [OK]
  [6] 0.0s  postcondition             [OK]

World State (initial):
  red_cube         [0.50, 0.15, 0.05]  FREE

World State (final):
  red_cube         [0.30, -0.20, 0.10]  PLACED
```

### 7.3 深度分析（AI Debugger）

```bash
robot analyze episode_00002
```

预期输出：
```
=== Episode Analysis ===
  ID: episode_00002
  Task: pick_place
  Skill: pick_object
  Result: SUCCESS
  Duration: 7.44s

  No failure detected — episode succeeded.

  Performance Breakdown:
    [1] skill_select              0.10s (1%) 
    [2] precondition              0.00s (0%) 
    [3] safety_check              0.10s (1%) 
    [4] execute_grasp             2.30s (31%) ######
    [5] execute_place             2.10s (28%) #####
    [6] postcondition             0.00s (0%) 

  World State Changes:
    red_cube: FREE -> PLACED
    red_cube moved: dx=-0.200 dy=-0.350 dz=0.050

  No improvements suggested — execution looks healthy.
```

### 7.4 查看失败案例

```bash
robot episodes --failures-only
```

如果有失败 Episode，用 `robot analyze` 深度分析：
```bash
robot analyze episode_00041
```

预期输出（失败分析）：
```
=== Episode Analysis ===
  ID: episode_00041
  Task: pick_place
  Result: FAILURE
  Duration: 7.18s

  Failure Point:
    Step 4: execute_grasp

    Context (previous steps):
      [2] precondition [OK]
      [3] safety_check [OK]

  Recovery Analysis (2 attempts):
    [1] grasp_failed -> strategy: retry [FAIL]
    [2] grasp_failed -> strategy: change_approach [FAIL]

  Suggested Improvements:
    -> Grasp failure: Increase perception frequency or adjust grasp tolerance
    -> High recovery count (2): Consider improving initial perception quality
```

---

## 第八步：实时监控仪表盘 (可选)

### 8.1 启动实时监控

```bash
robot watch
```

预期输出（实时刷新，类似 htop）：
```
=== Robot Runtime Monitor ===
  Uptime: 5.2s  |  Press Ctrl+C to stop

  Robot State:
    arm1:
      shoulder_pan_joint       35.2deg [#####-----]
      shoulder_lift_joint     -20.1deg [----##----]
      elbow_joint              80.3deg [######----]
      wrist_1_joint             0.0deg [-----#----]
      wrist_2_joint            45.0deg [######----]
      wrist_3_joint            10.2deg [-----#----]
    arm2:
      shoulder_pan_joint       0.0deg [-----#----]
      ...

  Legend: [#####-----] joint angle (-180 to +180)
```

按 `Ctrl+C` 退出。

### 8.2 限定时长监控

```bash
robot watch --duration 10
```

监控 10 秒后自动退出。

---

## 第九步：运行 Benchmark (2分钟)

### 9.1 批量执行 10 次 move 任务

```bash
robot benchmark move --count 10
```

预期输出：
```
Running 10x move...
[########################################] 10/10

Results:
  Total:        10
  Success:       10  (100.0%)
  Failure:        0  (0.0%)
  Avg duration:  3.20s
  Min/Max:       2.80s / 4.10s
```

### 9.2 批量执行并保存结果

```bash
robot benchmark pick_place --count 20 --output /tmp/bench.json
```

查看结果：
```bash
python3 -c "import json; d=json.load(open('/tmp/bench.json')); print(f'Success: {d[\"summary\"][\"success_count\"]}/{d[\"count\"]}')"
```

---

## 第十步：停止仿真 (1分钟)

```bash
robot sim stop
```

预期输出：
```
Stopping Robot Runtime...
  [OK] Runtime API stopped
  [OK] Simulation stopped
```

---

## 完整流程速查

```bash
# === 一次性复制粘贴版 ===

# 1. 环境
source /opt/ros/jazzy/setup.bash
export ROS_HOME=/tmp/ros_home HOME=/tmp PATH=/usr/bin:$PATH
export GZ_SIM_SYSTEM_PLUGIN_PATH=/opt/ros/jazzy/lib:/opt/ros/jazzy/opt/gz_sim_vendor/lib/gz-sim-8/plugins
cd ~/multi_arm_line_ws

# 2. 构建（如已构建可跳过）
colcon build --packages-select multi_arm_interfaces multi_arm_core multi_arm_safety multi_arm_world_model multi_arm_task_planner multi_arm_moveit_config multi_arm_robot_description multi_arm_perception multi_arm_manipulation multi_arm_skill_runtime multi_arm_runtime_api multi_arm_experience multi_arm_simulation multi_arm_tools ur_simulation_gz
source install/setup.bash

# 3. 单元测试
python3 -m pytest src/multi_arm_tools/test/ -v

# 4. 一键启动仿真
robot sim start

# 5. 诊断+查询
robot doctor
robot status
robot world
robot task list

# 6. 执行任务
robot run move ready
robot run pick_place red_cube zone_b
robot run pick_place red_cube zone_b --debug

# 7. 查看历史+分析
robot episodes
robot episode episode_00001
robot analyze episode_00001

# 8. 实时监控
robot watch --duration 10

# 9. Benchmark
robot benchmark move --count 10

# 10. 停止
robot sim stop
```

---

## 常见问题

### Q1: `robot: command not found`

```bash
source /opt/ros/jazzy/setup.bash
colcon build --packages-select multi_arm_tools
source install/setup.bash
```

### Q2: `robot sim start` 后节点未就绪

```bash
# 检查环境
robot doctor

# 查看仿真状态
robot sim status

# 查看ROS2节点
ros2 node list
```

### Q3: Gazebo 黑屏 / 无法启动

使用 headless 模式（默认）：
```bash
robot sim start
```

### Q4: `robot run` 卡住不动

```bash
# 诊断环境
robot doctor

# 检查控制器
ros2 control list_controllers

# 检查move_group
ros2 node list | grep move_group
```

### Q5: 任务执行失败

```bash
# 查看失败Episode
robot episodes --failures-only

# 深度分析失败原因
robot analyze <失败的episode_id>
```

### Q6: `robot doctor` 显示某些服务不可用

按 doctor 的建议修复：
```
[Runtime API] [FAIL] Services available
  Problem: Only 0 /runtime/* services found
  Suggested fix: Run: ros2 run multi_arm_runtime_api runtime_api_node
```

---

## 命令速查表

```bash
# 仿真管理
robot sim start [--gui]         # 一键启动
robot sim stop                  # 停止
robot sim status                # 状态

# 诊断
robot doctor                    # 环境诊断

# 查询
robot status                    # 系统概览
robot world [object_id]         # 世界状态
robot world --relations         # 关系图
robot skills                    # Skill列表
robot capability                # 三层能力
robot task list                 # 可用任务
robot task positions            # 预设位置

# 执行
robot run <task> [args]         # 提交任务+Trace
robot run <task> --debug        # 调试模式
robot run <task> --no-trace     # 静默模式
robot run <task> --arm arm2     # 指定机械臂

# 历史+分析
robot episodes [--failures-only]  # Episode历史
robot episode <id>              # Episode详情
robot analyze <id>              # 深度分析(AI Debugger)
robot traces [--recent N]       # Trace历史
robot trace <id>                # Trace详情

# Benchmark
robot benchmark <task> --count N  # 批量执行

# 监控
robot watch [--duration N]      # 实时仪表盘
```

---

## 下一步

- **完整 CLI 文档**: `docs/architecture/M6_6_cli_usage_guide.md`
- **设计文档**: `docs/architecture/M6_6_runtime_cli_design.md`
- **验证报告**: `docs/validation/M6_6_validation_report.md`
- **M6.7 Web Visualization** (未来): `docs/architecture/M6_7_visualization_design.md`
