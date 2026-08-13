# Robot Runtime CLI v2 从零开始手把手教程

**目标**: 从空环境开始，用 `robot` 命令跑通完整 Pick-Place 闭环，体验三层认知模型。
**预计耗时**: 15-20 分钟（含构建时间）
**环境**: WSL2 Ubuntu 24.04 + ROS2 Jazzy + Gazebo Harmonic
**版本**: CLI v2.0.0 — Operator Interface

---

## 实测验证状态 (2026-08-12)

| 命令 | 状态 | 说明 |
|------|------|------|
| `robot --help` | ✅ | 正常显示所有命令 |
| `python3 -m pytest test_cli.py` | ✅ | 22 tests pass (1.1s) |
| `robot sim start` | ✅ | 全栈启动，Runtime API ready |
| `robot doctor` | ✅ | 14/15 checks pass (controller timeout 是已知限制) |
| `robot status` | ✅ | 显示系统概览（skills/capability 可能显示 0/0） |
| `robot world` | ✅ | 世界模型查询（可能无物体） |
| `robot vision status` | ✅ | 感知层状态，显示检测到的物体 |
| `robot task list` | ✅ | 显示 8 种任务模板 |
| `robot task positions` | ✅ | 显示 7 个预设位置 |
| `robot safety status` | ✅ | 安全状态（可能显示 TRIGGERED） |
| `robot episode list` | ✅ | Episode 历史 |
| `robot skills` | ⚠️ | 需要 Skill Runtime 节点响应 |
| `robot capability` | ⚠️ | 需要 Capability Registry 节点响应 |

> **注意**: `skills`/`capability` 命令依赖 Runtime API 服务响应。如果服务不响应，命令返回 exit code 1。确保 `runtime_api_node` 和 `capability_registry_node` 正常运行。

---

## CLI v2 三层认知模型

```
             HUMAN
               │
       ┌───────┴────────┐
       │                │
   OBSERVE            ACT
       │                │
 status/doctor      task/safety
       │
    DIAGNOSE
       │
 world/vision/episode
```

| 层 | 命令 | 回答的问题 |
|----|------|-----------|
| OBSERVE | `status`, `doctor` | 系统活着吗？健康吗？ |
| DIAGNOSE | `world`, `vision`, `episode` | 世界是什么？看到什么？上次怎么样？ |
| ACT | `task run`, `safety stop` | 做什么？紧急停止？ |

**三大契约**: Command（固定层次）+ Output（`--json`）+ Exit Code（0/1/2/3）

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
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
```

> **为什么用 CycloneDDS**: FastDDS 在 WSL2 下 SHM 通信有冲突，CycloneDDS 更稳定。

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
usage: robot [-h] [--json] {sim,scene,doctor,status,world,vision,skills,capability,task,run,episode,episodes,analyze,safety,traces,trace,benchmark,watch,evaluate} ...

Robot Runtime CLI v2 — Operator Interface
```

---

## 第三步：运行单元测试 (1分钟，无需 Gazebo)

```bash
python3 -m pytest src/multi_arm_tools/test/test_cli.py -v
```

预期输出：
```
collected 22 items

src/multi_arm_tools/test/test_cli.py::test_cli_import PASSED
src/multi_arm_tools/test/test_cli.py::test_cli_argparse_status PASSED
...
src/multi_arm_tools/test/test_cli.py::test_cli_no_command_fails PASSED

============================== 22 passed in 1.08s ==============================
```

> **这验证了什么**: CLI v2 命令解析、三层认知模型、--json 输出契约、退出码契约 — 全部纯 Python 逻辑。

> **完整测试**: `python3 -m pytest src/multi_arm_tools/test/ -v` 收集 284 个测试，但部分需要 Gazebo 全栈运行（M7.FINAL 场景测试），纯 CLI 测试为 22 个。

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
  [OK] Perception ready
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
    /color_detector_node
    ...
```

### 4.3 环境诊断 (OBSERVE 层)

```bash
robot doctor
```

预期输出：
```
=== Robot Runtime Diagnosis ===

  [ROS2] [OK] DDS communication (distro=jazzy)
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
  [Perception] [OK] ColorDetector online
  [Evaluation] [OK] Safety check service available

  System Health: 93/100 (14/15 checks passed)

  Failures:
    [Controllers] Controller manager
      Problem: ros2 control list_controllers timed out (15s)
      Suggested fix: Check controller_manager is running: ros2 node list | grep controller_manager
```

> **controller timeout 是已知限制**: `ros2 control list_controllers` 在 WSL2 环境下可能超时。这不影响其他功能，控制器状态可通过 `ros2 control list_controllers` 手动检查。

> **如果有其他问题**: doctor 会显示失败项和修复建议，例如：
> ```
> [Controllers] [FAIL] arm2_controller active
>   Problem: State: inactive
>   Suggested fix: Run: ros2 control set_controller_state arm2_controller active
> ```

---

## 第五步：OBSERVE — 用 robot CLI 查询系统状态 (1分钟)

### 5.1 系统概览

```bash
robot status
```

预期输出：
```
╭──────────────────────────────────────────────╮
│ ROBOT STATUS                                 │
├──────────────────────────────────────────────┤
│ System       ● READY                         │
│ Skills       3/3 READY                       │
│ Capability   5/5 AVAILABLE                   │
╰──────────────────────────────────────────────╯

WORLD
  Objects    2
  Observed   2
  Uncertain  0
  Conflicts  0
  Stale       0

OBJECTS
  red_cube         [  0.50,   0.00,   0.43]  conf=1.00  src=ground_truth
  blue_cylinder    [  0.30,   0.20,   0.44]  conf=1.00  src=ground_truth

LAST TASK
  (none)

EPISODES: 0
```

### 5.2 JSON 输出（机器可读）

```bash
robot status --json
```

预期输出：
```json
{
  "system": "READY",
  "world": {
    "objects": 2,
    "uncertain": 0,
    "conflicts": 0,
    "stale": 0
  },
  "skills": {"ready": 3, "total": 3},
  "capability": {"available": 5, "total": 5},
  "episodes": {"total": 0, "success": 0, "failure": 0}
}
```

> **--json 是全局 flag**: 任何命令都可以加 `--json`，用于脚本消费。

---

## 第六步：DIAGNOSE — 查看世界与感知 (1分钟)

### 6.1 查看世界状态

```bash
robot world
```

预期输出：
```
WORLD MODEL
------------------------------------------------------------

OBJECT          POSITION                    SOURCE       CONF   STATUS
  red_cube       (0.50, 0.00, 0.43)         ground_truth 1.00   FREE
  blue_cylinder  (0.30, 0.20, 0.44)         ground_truth 1.00   FREE

HEALTH
  tracked:     2
  uncertain:   0
  stale:       0
  conflicts:   0
```

### 6.2 查看物体详情（WorldModel Debugger）

```bash
robot world red_cube
```

预期输出：
```
OBJECT: red_cube

CURRENT BELIEF
  Position
    mean:       (0.500, 0.000, 0.435)
    variance:   0.001000
    confidence: 1.00

SOURCE
  ground_truth

STATE
  type:        cube
  grasp_state: FREE
  attached_to: (none)
  orientation: [0.000, 0.000, 0.000, 1.000]

HEALTH
  stale:        NO
  contradiction:NO
  uncertain:    NO
  covariance:   [0.001000, ...]
```

> **这回答了什么**: "为什么系统认为 red_cube 在这里？" — belief、source、confidence、health 全可见。

### 6.3 查看关系图

```bash
robot world --relations
```

### 6.4 查看感知层状态 (Vision ≠ WorldModel)

```bash
robot vision status
```

预期输出：
```
VISION STATUS
----------------------------------------

Camera
  topic:    /head_camera/image_raw/image
  status:   ● ACTIVE

Detector
  topic:    /perception/vision_poses
  status:   ● READY

Objects
  red_cube          conf=0.92
  blue_cylinder     conf=0.95

Quality
  high confidence    2
  uncertain          0
  rejected           0
```

> **Vision vs WorldModel**:
> - **Vision** = 传感器当前看到什么
> - **WorldModel** = 机器人当前相信世界是什么（融合了 vision + ground_truth + history）

### 6.5 查看检测结果

```bash
robot vision objects
```

### 6.6 查看可用 Skill 与 Capability

```bash
robot skills
robot capability
```

---

## 第七步：ACT — 执行任务 (3分钟)

### 7.1 查看可用任务类型

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

### 7.2 查看预设位置

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

### 7.3 提交一个 Move 任务（最简单）

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

> **退出码**: `echo $?` 输出 `0`（成功）。

### 7.4 提交一个 Pick-Place 任务

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

### 7.5 显式 task run 形式

```bash
robot task run pick_place red_cube zone_b
```

> `robot run` 是 `robot task run` 的 shorthand，两者完全等价。

### 7.6 调试模式

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

### 7.7 指定 arm2 执行

```bash
robot run move ready --arm arm2
```

### 7.8 静默模式（不显示 Trace）

```bash
robot run move home --no-trace
```

---

## 第八步：DIAGNOSE — 查看执行历史 (2分钟)

### 8.1 查看 Episode 历史

```bash
robot episode list
```

预期输出：
```
Recent Episodes (3):
  episode_00003  move            [OK]   3.20s  0 recovery
  episode_00002  pick_place      [OK]   7.44s  0 recovery
  episode_00001  move            [OK]   2.80s  0 recovery
```

> **向后兼容**: `robot episodes` 也可用，等价于 `robot episode list`。

### 8.2 查看 Episode 详情

```bash
robot episode show episode_00002
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

> **向后兼容**: `robot episode episode_00002` 也可用，等价于 `robot episode show episode_00002`。

### 8.3 深度分析（AI Debugger）

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

### 8.4 查看失败案例

```bash
robot episode list --failures-only
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

## 第九步：ACT — 安全操作 (1分钟)

### 9.1 查看安全状态

```bash
robot safety status
```

预期输出：
```
SAFETY
----------------------------------------
  Supervisor       ● ACTIVE
  Speed scale      1.00
  Message          OK

Authority:
  Safety > Coordinator > Skill > Task
```

### 9.2 安全检查

```bash
robot safety check
```

### 9.3 紧急停止（最高优先级）

**`robot safety stop` 直接调用 SafetySupervisor，绕过 RuntimeApi/Coordinator/Skill pipeline。**

```bash
robot safety stop
echo $?
```

预期输出：
```
[OK] Emergency stop activated
2
```

> **退出码 2 = Safety**: 这是退出码契约的安全专用码。

> **架构保证**:
> ```
> CLI → SafetySupervisor → STOP MOTION
> ```
> 而非：
> ```
> CLI → RuntimeApi → Task → Coordinator → Safety
> ```
> 这体现了 Safety 独立性架构约束 — SafetySupervisor 拥有最终停止权，不依赖 Coordinator 运行。

---

## 第十步：实时监控仪表盘 (可选)

### 10.1 启动实时监控

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

### 10.2 限定时长监控

```bash
robot watch --duration 10
```

监控 10 秒后自动退出。

---

## 第十一步：运行 Benchmark 与独立评估 (2分钟)

### 11.1 批量执行 10 次 move 任务

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

### 11.2 批量执行并保存结果

```bash
robot benchmark pick_place --count 20 --output /tmp/bench.json
```

### 11.3 独立评估

```bash
robot evaluate
```

> **`robot evaluate` 是什么**: 独立评估层，不参与决策链，只做事后验收。M7.FINAL 的 15 场景 + 7 不变量就是通过独立评估层验证的。

---

## 第十二步：停止仿真 (1分钟)

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

## 退出码契约

CLI v2 冻结的退出码契约，可用于脚本自动化：

| Code | Meaning | 示例 |
|------|---------|------|
| 0 | Success | 任务成功 |
| 1 | Error | 服务不可用、任务失败 |
| 2 | Safety | 紧急停止、安全违规 |
| 3 | Timeout | 服务超时 |

```bash
robot run move ready --no-trace
case $? in
  0) echo "Success" ;;
  1) echo "Error" ;;
  2) echo "Safety stop" ;;
  3) echo "Timeout" ;;
esac
```

---

## 完整流程速查

```bash
# === 一次性复制粘贴版 ===

# 1. 环境
source /opt/ros/jazzy/setup.bash
export ROS_HOME=/tmp/ros_home HOME=/tmp PATH=/usr/bin:$PATH
export GZ_SIM_SYSTEM_PLUGIN_PATH=/opt/ros/jazzy/lib:/opt/ros/jazzy/opt/gz_sim_vendor/lib/gz-sim-8/plugins
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
cd ~/multi_arm_line_ws

# 2. 构建（如已构建可跳过）
colcon build --packages-select multi_arm_interfaces multi_arm_core multi_arm_safety multi_arm_world_model multi_arm_task_planner multi_arm_moveit_config multi_arm_robot_description multi_arm_perception multi_arm_manipulation multi_arm_skill_runtime multi_arm_runtime_api multi_arm_experience multi_arm_simulation multi_arm_tools ur_simulation_gz
source install/setup.bash
export PATH="$PATH:$(ros2 pkg prefix multi_arm_tools)/lib/multi_arm_tools"

# 3. 单元测试
python3 -m pytest src/multi_arm_tools/test/ -v

# 4. 一键启动仿真
robot sim start

# 5. OBSERVE: 诊断+查询
robot doctor
robot status
robot status --json

# 6. DIAGNOSE: 世界+感知
robot world
robot world red_cube
robot world --relations
robot vision status
robot vision objects
robot skills
robot capability

# 7. ACT: 执行任务
robot task list
robot task positions
robot run move ready
robot run pick_place red_cube zone_b
robot run pick_place red_cube zone_b --debug
robot run move ready --arm arm2

# 8. DIAGNOSE: 历史+分析
robot episode list
robot episode list --failures-only
robot episode show episode_00001
robot analyze episode_00001

# 9. ACT: 安全
robot safety status
robot safety check
# robot safety stop    # 紧急停止（取消注释执行）

# 10. 监控
robot watch --duration 10

# 11. Benchmark + 评估
robot benchmark move --count 10
robot benchmark pick_place --count 20 --output /tmp/bench.json
robot evaluate

# 12. 停止
robot sim stop
```

---

## Agent / 脚本自动化示例

### Python 消费 JSON

```python
import subprocess, json

# 系统状态
result = subprocess.run(["robot", "status", "--json"], capture_output=True)
status = json.loads(result.stdout)
if status["world"]["conflicts"] > 0:
    print("WARNING: WorldModel conflicts detected")

# 提交任务
result = subprocess.run(
    ["robot", "run", "pick_place", "red_cube", "zone_b", "--no-trace"],
    capture_output=True
)
if result.returncode == 0:
    print("Task succeeded")
elif result.returncode == 2:
    print("Safety stop triggered")
```

### Shell CI/CD 集成

```bash
#!/bin/bash
# CI/CD 集成
robot doctor || exit 1
robot run move ready --no-trace || exit 1
robot run pick_place red_cube zone_b --no-trace || exit 1
robot benchmark move --count 10 --output bm.json
robot evaluate
```

### jq 查询示例

```bash
# 所有不确定的物体
robot world --json | jq '.objects[] | select(.uncertain == true)'

# 最近失败的Episode
robot episode list --json | jq '.episodes[] | select(.result == "failure")'

# Capability可用率
robot capability --json | jq '.capabilities | map(.available) | add / length'
```

---

## 常见问题

### Q1: `robot: command not found`

```bash
source /opt/ros/jazzy/setup.bash
colcon build --packages-select multi_arm_tools
source install/setup.bash
export PATH="$PATH:$(ros2 pkg prefix multi_arm_tools)/lib/multi_arm_tools"
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
robot episode list --failures-only

# 深度分析失败原因
robot analyze <失败的episode_id>

# 查看世界状态（物体可能漂移）
robot world red_cube
```

### Q6: `robot doctor` 显示某些服务不可用

按 doctor 的建议修复：
```
[Runtime API] [FAIL] Services available
  Problem: Only 0 /runtime/* services found
  Suggested fix: Run: ros2 run multi_arm_runtime_api runtime_api_node
```

### Q7: `robot safety stop` 失败

```
✗ Emergency stop failed: Safety service not available
```

**解决**: 确认 SafetySupervisor 正在运行。

```bash
ros2 node list | grep safety
```

### Q8: DDS 通信问题

```bash
# 切换到 CycloneDDS
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp

# 验证
ros2 daemon stop
ros2 daemon start
```

---

## 命令速查表

```bash
# OBSERVE 层
robot status                          # 系统总览
robot status --json                   # 机器可读
robot doctor                          # 系统诊断

# DIAGNOSE 层
robot world                           # 世界模型
robot world red_cube                  # 物体详情 (belief/health)
robot world --relations               # 关系图
robot vision status                   # 感知状态
robot vision objects                  # 检测结果
robot skills                          # Skill列表
robot capability                      # 三层能力
robot episode list                    # Episode历史
robot episode list --failures-only    # 失败Episode
robot episode show <id>               # Episode详情
robot traces                          # Trace历史
robot trace <id>                      # Trace详情

# ACT 层
robot task list                       # 可用任务
robot task positions                  # 预设位置
robot task run <task> [args]          # 显式任务提交
robot run <task> [args]               # shorthand
robot run <task> --debug              # 调试模式
robot run <task> --no-trace           # 静默模式
robot run <task> --arm arm2           # 指定机械臂
robot safety status                   # 安全状态
robot safety check                    # 安全检查
robot safety stop                     # 紧急停止 (exit code 2)
robot benchmark <task> --count N      # 批量执行
robot evaluate                        # 独立评估

# 仿真管理
robot sim start [--gui]               # 一键启动
robot sim stop                        # 停止
robot sim status                      # 状态

# 监控
robot watch [--duration N]            # 实时仪表盘

# 深度分析
robot analyze <id>                    # AI Debugger

# GLOBAL
--json                                # 机器可读输出
```

---

## 向后兼容

| 旧命令 | 新命令 | 状态 |
|--------|--------|------|
| `robot run <task>` | `robot task run <task>` | 两者都可用 |
| `robot episodes` | `robot episode list` | 两者都可用 |
| `robot episode <id>` | `robot episode show <id>` | 两者都可用 |
| `robot world <obj>` | `robot world <obj>` | 不变（增强） |
| `robot status` | `robot status` | 增强（+--json） |
| `robot doctor` | `robot doctor` | 增强（+Perception/Evaluation） |

---

## 下一步

- **完整 CLI 文档**: `docs/architecture/M7_CLI_v2_usage_guide.md`
- **设计文档**: `docs/architecture/M7_CLI_v2_operator_interface.md`
- **M7.FINAL 验证报告**: `docs/validation/M7_FINAL_validation_report.md`
- **M6.6 验证报告**: `docs/validation/M6_6_validation_report.md`