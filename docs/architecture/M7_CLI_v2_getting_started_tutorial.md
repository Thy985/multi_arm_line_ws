# Robot Runtime CLI v2 从零开始手把手教程

**目标**: 从空环境开始，用 `robot` 命令体验双臂机器人系统的完整能力——观察世界、诊断系统、执行任务、查看 Episode、回放失败、批量 Benchmark。
**预计耗时**: 20-30 分钟（含构建时间）
**环境**: WSL2 Ubuntu 24.04 + ROS2 Jazzy + Gazebo Harmonic
**版本**: CLI v2.1.0 — Robot OS Shell

---

## 一句话总览

```bash
# 1. 环境（一次性）
source /opt/ros/jazzy/setup.bash
export PATH=/usr/bin:$PATH ROS_HOME=/tmp/ros_home HOME=/tmp
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export GZ_SIM_SYSTEM_PLUGIN_PATH=/opt/ros/jazzy/lib:/opt/ros/jazzy/opt/gz_sim_vendor/lib/gz-sim-8/plugins

# 2. 构建（一次性）
cd ~/multi_arm_line_ws
colcon build --packages-select multi_arm_interfaces multi_arm_core multi_arm_safety \
  multi_arm_world_model multi_arm_task_planner multi_arm_moveit_config \
  multi_arm_recovery multi_arm_benchmark multi_arm_robot_description \
  multi_arm_perception multi_arm_manipulation multi_arm_skill_runtime \
  multi_arm_runtime_api multi_arm_experience multi_arm_simulation \
  multi_arm_tools ur_simulation_gz
source install/setup.bash
export PATH="$PATH:$(ros2 pkg prefix multi_arm_tools)/lib/multi_arm_tools"

# 3. 进入 Robot OS Shell
robot

# 4. 启动仿真（看到 GUI 选 --gui）
robot> start --gui --scene tabletop

# 5. 体验完整闭环
robot> status          # 观察：系统概览
robot> world           # 观察：世界模型中的物体
robot> vision status   # 观察：感知管线
robot> skills          # 观察：已注册的 Skills
robot> capability      # 观察：三层能力
robot> run pick_place red_cube zone_b  # 行动：执行 Pick-Place
robot> episodes        # 回顾：刚刚执行的任务
robot> analyze <id>    # 深入：分析 Episode
robot> benchmark pick_place --count 10  # 批量：跑 10 次统计成功率
robot> stop
robot> exit
```

**就这么简单。** 下面详细解释每一步，并且会覆盖 GUI/Headless 启动、配置、多场景、多臂操作、Episode 分析、批量 Benchmark。

---

## 第一步：环境准备 (2 分钟)

### 1.1 打开终端，source ROS2

```bash
source /opt/ros/jazzy/setup.bash
echo $ROS_DISTRO   # 应输出: jazzy
```

### 1.2 设置 WSL2 环境变量

```bash
export PATH=/usr/bin:$PATH
export ROS_HOME=/tmp/ros_home
export HOME=/tmp
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export GZ_SIM_SYSTEM_PLUGIN_PATH=/opt/ros/jazzy/lib:/opt/ros/jazzy/opt/gz_sim_vendor/lib/gz-sim-8/plugins
```

> **为什么用 CycloneDDS**: FastDDS 在 WSL2 下 SHM 通信有冲突，CycloneDDS 更稳定。

### 1.3 GUI 显示前置条件（仅 Windows/WSL2 用户）

如果你想看到 Gazebo GUI 或 RViz，需要满足：

| 方案 | 优点 | 缺点 |
|------|------|------|
| **WSLg**（WSL2 22.04+） | 自动集成，无需配置 | 性能略差 |
| **VcXsrv / X410** | 性能好 | 需手动配置 |
| **Headless（无 GUI）** | 性能最好，CI 友好 | 看不到视觉 |

**VcXsrv 配置**（如用 WSLg 跳过此步）：
1. Windows 启动 VcXsrv，`Display number=0`，勾选 `Disable access control`
2. WSL2 内执行：
   ```bash
   export DISPLAY=$(cat /etc/resolv.conf | grep nameserver | awk '{print $2}'):0
   # 或固定 IP
   export DISPLAY=192.168.1.100:0
   ```
3. 验证：
   ```bash
   sudo apt install -y x11-apps
   xeyes   # 应弹出窗口
   ```

> **Headless 模式**（推荐服务器/CI）：不需要任何 X server，启动快 5 倍。

### 1.4 进入工作空间

```bash
cd ~/multi_arm_line_ws
```

> **提示**: 将以上 export 命令加入 `~/.bashrc` 可避免每次手动输入。

---

## 第二步：构建所有包 (10-15 分钟)

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

构建完成后：

```bash
source install/setup.bash
export PATH="$PATH:$(ros2 pkg prefix multi_arm_tools)/lib/multi_arm_tools"
```

### 验证 robot 命令可用

```bash
robot --help
```

**预期输出**：

```
Robot Runtime CLI v2 — Operator Interface
...
  start               Start robot runtime session
  stop                Stop robot runtime session
  repair              Auto-repair runtime issues
  restart             Restart robot runtime
  sim                 Simulation lifecycle
  scene               Scene management
  doctor              System diagnosis
  status              System overview
  world               World model state
  vision              Perception layer
  skills              List registered skills
  capability          Three-layer capability
  task                Task management
  run                 Submit task (shorthand for task run)
  episode             Episode detail or subcommand
  episodes            Episode history (shorthand)
  analyze             Deep episode analysis
  safety              Safety supervisor
  traces              Trace history
  trace               Trace detail
  benchmark           Batch benchmark
  watch               Real-time dashboard
  evaluate            Run evaluation
```

如果看到 `command not found`，说明 PATH 没设好，见最后的"故障排查"。

---

## 第三步：运行单元测试 (1 分钟，不需仿真)

```bash
python3 -m pytest src/multi_arm_tools/test/test_cli.py -v
```

**预期输出**：

```
============================== 22 passed in 1.46s ==============================
```

✅ **22/22 通过** 说明 CLI 本身工作正常。

---

## 第四步：启动 Robot OS Shell (核心)

```bash
robot
```

**会发生什么**：

```
  ╭──────────────────────────────────────────╮
  │   M7 Embodied Robot OS                   │
  │   Dual UR5e · Gazebo · MoveIt2 · Skills  │
  ╰──────────────────────────────────────────╯

Checking environment...

  ✓ ROS2: ROS_DISTRO=jazzy
  ✓ Workspace: install/setup.bash
  ✓ DDS: CycloneDDS
  ✓ Runtime: no active session

  Ready.

robot>
```

看到了 `robot>` 提示符就成功。

> **如果看到 "Auto-repair?" 提示**：说明检测到残留进程，输入 `y` 让它自动清理。

---

## 第五步：启动仿真 (多种姿势)

### 5.1 Headless 启动（最快，推荐服务器/CI）

```bash
robot> start
```

**会发生什么**：
```
  Session: session-20260813-101954
  Domain:  40
  Scene:   tabletop
  Launching simulation...
  PID:     88287
  Waiting for nodes to initialize (30s)...
  [OK] Session started.
```

### 5.2 GUI 启动（看 Gazebo 3D 仿真）

```bash
robot> start --gui
```

会弹出 Gazebo GUI 窗口，看到双臂 UR5e + 桌子 + 物体。

### 5.3 切换场景 (4 种场景可选)

```bash
robot> start --scene lab        # 实验室场景
robot> start --scene warehouse  # 仓库场景
robot> start --scene home       # 家居场景
robot> start --scene tabletop   # 桌面场景（默认）
```

**查看所有场景**：
```bash
robot> scene list
```

### 5.4 分配特定 DDS Domain

```bash
robot> start --domain 42
```

> **Domain 范围**: 40-59（系统保留），避免冲突。

### 5.5 验证仿真运行

```bash
robot> status
```

应看到系统状态（3 Skills READY, N objects）。

---

## 第六步：观察 (OBSERVE) — 三大数据源

### 6.1 查看世界状态

```bash
robot> world
```

```
WORLD MODEL
------------------------------------------------------------
OBJECT          POSITION                     SOURCE       CONF   STATUS
  red_cube      (0.50, 0.00, 0.43)           ground_truth 1.00   FREE
  blue_cylinder (0.30, 0.20, 0.44)           ground_truth 1.00   FREE
  green_box     (0.40, -0.20, 0.44)          ground_truth 1.00   FREE
```

**查询单个物体**：
```bash
robot> world red_cube
```

**查看关系图（on/near/inside/attached）**：
```bash
robot> world --relations
```

### 6.2 查看感知管线

```bash
robot> vision status
```

**查看检测到的物体**：
```bash
robot> vision objects
```

### 6.3 查看 Skills 和能力

```bash
robot> skills
```

```
Registered Skills (3):
  pick_object         v1.0
    Pick an object from a zone
    cost: 12.0s  success_rate: 0.95
    requires: grasp, detect

  place_object        v1.0
    Place held object at a zone
    cost: 8.0s  success_rate: 0.98
    requires: move, place

  move_object         v1.0
    Move robot to a position
    cost: 5.0s  success_rate: 0.99
    requires: plan, execute
```

**查看三层能力 (Static/Dynamic/Context)**：
```bash
robot> capability
```

### 6.4 查看任务类型和位置

```bash
robot> task list
```

```
Available Task Types:
  pick_place  - Pick up an object and place it at a target zone
  pick        - Pick up an object
  place       - Place an object at a target zone
  move        - Move robot to a named position
  grasp       - Grasp an object
  lift        - Lift object to safe height
  retract     - Retract to safe position
  inspect     - Move to inspection position
```

```bash
robot> task positions
```

```
Available Positions:
  home, ready, extended, scan, inspect, place_high, place_low
```

---

## 第七步：行动 (ACT) — 6 种任务类型

### 7.1 移动到预设位置

```bash
robot> run move ready
robot> run move home
robot> run move extended
robot> run move scan
```

### 7.2 Pick-Place（最常用）

```bash
robot> run pick_place red_cube zone_b
robot> run pick blue_cylinder zone_a
robot> run place_zone green_box zone_c   # 当前持有的物体放到 zone_c
```

### 7.3 指定臂（arm1 或 arm2）

```bash
robot> run pick_place red_cube zone_b --arm arm1
robot> run pick_place blue_cylinder zone_a --arm arm2
```

### 7.4 完整任务流程示例

```bash
# arm1: 把红方块放到 zone_b
robot> run pick_place red_cube zone_b --arm arm1

# arm2: 把蓝圆柱放到 zone_a（并行）
robot> run pick_place blue_cylinder zone_a --arm arm2

# 移回 home
robot> run move home
```

---

## 第八步：诊断 (DIAGNOSE) — 23 项系统检查

### 8.1 完整诊断

```bash
robot> doctor
```

**输出**（节选）：
```
=== Robot Runtime Diagnosis ===

  ✓ ROS2: DDS communication (distro=jazzy)
  ✓ Gazebo: Binary gz available
  ✓ Build: 17 packages installed
  ✓ Nodes: 24 active nodes
  ✓ Controllers: arm1 JTC + arm2 JTC active
  ✓ MoveIt: move_group ready
  ✓ WorldModel: Query service available
  ✓ Safety: Supervisor online
  ✓ Runtime API: 6 services available
  ✓ Experience: Query service available
  ✓ Perception: ColorDetector online
  ✓ Evaluation: Engine ready
  ✓ Runtime Health: Session clean

Score: 23/23 (100%)
```

### 8.2 安全状态

```bash
robot> safety status
```

### 8.3 安全检查

```bash
robot> safety check
```

### 8.4 紧急停止（慎用！）

```bash
robot> safety stop
```

> ⚠️ `safety stop` 直接给 SafetySupervisor 发 E-Stop，会停掉所有运动。需 `robot restart` 才能恢复。

---

## 第九步：回顾 (REFLECT) — Episode & Trace

### 9.1 查看执行历史

```bash
robot> episodes
```

```
EPISODE ID                  TASK              RESULT      DURATION
  ep-20260813-101234        pick_place       SUCCESS     18.4s
  ep-20260813-101220        move             SUCCESS     5.2s
  ep-20260813-101200        pick_place       FAILURE     22.1s
```

**只看失败用例**：
```bash
robot> episodes --failures-only
```

**最近 N 条**：
```bash
robot> episodes --recent 5
```

### 9.2 深入分析单个 Episode

```bash
robot> analyze ep-20260813-101234
```

**输出**：
```
Episode: ep-20260813-101234
Task: pick_place red_cube zone_b
Result: SUCCESS
Duration: 18.4s

Skill Trace:
  1. detect(red_cube)        0.5s   ✓
  2. grasp(red_cube)         5.2s   ✓
  3. move(zone_b)            8.1s   ✓
  4. place(zone_b, red_cube) 4.6s   ✓

Recovery Actions: 0
Collision Events: 0
Safety Rejections: 0

World State Snapshot:
  Before: red_cube at (0.50, 0.00, 0.43), arm1 at home
  After:  red_cube at (0.30, 0.20, 0.44), arm1 at zone_b
```

### 9.3 Trace 详情

```bash
robot> traces --recent 10
robot> trace trace-20260813-101234
```

### 9.4 Benchmark（批量执行）

```bash
robot> benchmark pick_place --count 20
```

**输出**：
```
Benchmark: pick_place, 20 episodes
═══════════════════════════════════════
1/20  ✓ SUCCESS  17.2s
2/20  ✓ SUCCESS  18.5s
...
20/20 ✓ SUCCESS  16.8s

Success Rate: 20/20 (100%)
Avg Duration: 17.6s
P50: 17.2s
P95: 22.3s
Failures: 0
```

**保存到 JSON**：
```bash
robot> benchmark pick_place --count 50 --output /tmp/bench.json
```

---

## 第十步：实时监控 (WATCH)

```bash
robot> watch --duration 30
```

每 2 秒刷新一次系统状态（机器人+世界+Skills），类似 `top` 命令。

---

## 第十一步：场景与配置进阶

### 11.1 场景系统

系统内置 4 个场景：

| 场景 | 描述 | launch 文件 |
|------|------|-------------|
| `tabletop` | 桌面物体摆放（默认） | `m6_pick_place_sim.launch.py` |
| `lab` | 实验室环境 | `m6_pick_place_sim.launch.py` |
| `warehouse` | 仓库货架 | `m6_pick_place_sim.launch.py` |
| `home` | 家居场景 | `m6_pick_place_sim.launch.py` |

**查看场景详情**：
```bash
robot> scene show tabletop
```

### 11.2 配置文件位置

所有配置都用 YAML 驱动，更改无需重新编译：

| 配置 | 路径 | 作用 |
|------|------|------|
| `robots.yaml` | `src/multi_arm_core/config/robots.yaml` | 机械臂配置（双臂、控制器、Zone） |
| `robot.yaml` | `src/multi_arm_robot_description/config/robot.yaml` | 机器人结构（URDF 生成） |
| `capability.yaml` | `src/multi_arm_robot_description/config/capability.yaml` | 静态能力 |
| `safety_config.yaml` | `src/multi_arm_safety/config/safety_config.yaml` | 安全限制（速度、空间） |
| `perception_config.yaml` | `src/multi_arm_perception/config/perception_config.yaml` | 感知管线 |
| `domain_randomization.yaml` | `src/multi_arm_simulation/config/domain_randomization.yaml` | 域随机化 |

**双臂配置**（`robots.yaml`）：
```yaml
robots:
  - name: arm1
    type: ur5e
    namespace: /arm1
    capabilities:
      payload_kg: 5.0
      reachable_zones: [zone_a, zone_b, home]
  - name: arm2
    type: ur5e
    namespace: /arm2
    capabilities:
      payload_kg: 5.0
      reachable_zones: [zone_a, zone_c, home]
```

**添加新臂**：只需在 `robots.yaml` 加一项，无需改代码。

### 11.3 安全配置（`safety_config.yaml`）

```yaml
max_velocity_scale: 1.0      # 速度比例（0.0-1.0）
workspace_bounds: [[-0.8, 0.8], [-0.8, 0.8], [0.0, 1.2]]
collision_distance_threshold: 0.05
emergency_stop_timeout: 5.0
```

---

## 第十二步：完整场景演练

### 场景 A：双臂协作 Pick-Place

```bash
robot> start --gui --scene tabletop

# 1. 观察
robot> world
robot> world --relations

# 2. arm1 抓红方块到 zone_b
robot> run pick_place red_cube zone_b --arm arm1

# 3. arm2 抓蓝圆柱到 zone_a（并行）
robot> run pick_place blue_cylinder zone_a --arm arm2

# 4. 全部完成后回到 home
robot> run move home --arm arm1
robot> run move home --arm arm2

# 5. 回顾
robot> episodes
robot> analyze ep-XXX

# 6. 停止
robot> stop
robot> exit
```

### 场景 B：批量 Benchmark

```bash
robot> start

# 跑 20 次 Pick-Place
robot> benchmark pick_place --count 20

# 查看结果
robot> episodes --recent 20

# 跑 10 次复杂双任务
robot> benchmark pick_place --count 10 --arm arm1

robot> stop
robot> exit
```

### 场景 C：故障注入与恢复

```bash
robot> start

# 1. 正常任务
robot> run pick_place red_cube zone_b

# 2. 故意指定不存在的物体（应失败+恢复）
robot> run pick_place black_hole zone_b

# 3. 查看失败案例
robot> episodes --failures-only

# 4. 分析失败原因
robot> analyze ep-XXX

# 5. 清空失败记录
robot> stop
robot> exit
```

### 场景 D：E-Stop 紧急停止

```bash
robot> start

# 1. 启动一个长任务
robot> run pick_place red_cube zone_b &

# 2. 紧急停止
robot> safety stop

# 3. 查看状态（应显示 ERROR）
robot> status

# 4. 恢复
robot> restart
robot> exit
```

### 场景 E：WorldModel 深度查询

```bash
robot> start

# 1. 看所有物体
robot> world

# 2. 看某个物体的协方差和不确定性
robot> world red_cube

# 3. 看关系图
robot> world --relations

# 4. JSON 格式（给脚本用）
robot> world --json

# 5. JSON 看能力
robot> capability --json
```

---

## 第十三步：完整命令清单

### 生命周期

| 命令 | 做什么 |
|------|--------|
| `start [--gui] [--scene NAME] [--domain N]` | 启动仿真（可选 GUI/场景/Domain） |
| `stop` | 停止仿真（清理进程树） |
| `restart [--gui] [--scene NAME]` | 重启仿真 |
| `status` | 查看当前 session |
| `doctor` | 23 项系统诊断 |
| `repair` | 自动修复 Runtime 问题 |

### 仿真

| 命令 | 做什么 |
|------|--------|
| `sim start [--gui]` | 启动仿真（底层） |
| `sim stop` | 停止仿真（底层） |
| `sim status` | 仿真状态 |
| `scene list` | 列出所有场景 |
| `scene show NAME` | 查看场景详情 |

### 观察

| 命令 | 做什么 |
|------|--------|
| `world [OBJECT_ID] [--relations]` | 世界模型状态 |
| `world --json` | JSON 输出 |
| `vision status` | 感知管线状态 |
| `vision objects` | 检测到的物体 |
| `skills` | 已注册的 Skills |
| `capability` | 三层能力 |
| `task list` | 任务类型列表 |
| `task positions` | 预设位置列表 |

### 行动

| 命令 | 做什么 |
|------|--------|
| `run pick_place OBJECT ZONE [--arm ARM]` | Pick-Place |
| `run pick OBJECT` | 抓取 |
| `run place ZONE` | 放置 |
| `run move POSITION` | 移动 |
| `run lift POSITION` | 抬起 |
| `run retract POSITION` | 收回 |
| `run inspect POSITION` | 检查 |
| `run grasp OBJECT` | 抓取（别名） |

### 回顾

| 命令 | 做什么 |
|------|--------|
| `episode [ID]` | 单个 Episode 详情 |
| `episode list` | Episode 列表 |
| `episode show ID` | 显示 Episode |
| `episodes [--failures-only] [--recent N]` | Episode 历史 |
| `analyze EPISODE_ID` | 深度分析 |
| `traces [--recent N]` | Trace 列表 |
| `trace TRACE_ID` | Trace 详情 |

### 安全

| 命令 | 做什么 |
|------|--------|
| `safety status` | 安全状态 |
| `safety check` | 安全检查 |
| `safety stop` | 紧急停止 |

### 批量化

| 命令 | 做什么 |
|------|--------|
| `benchmark TASK --count N [--output FILE]` | 跑 N 次任务 |
| `watch --duration N` | 实时监控 N 秒 |
| `evaluate` | 系统评估 |

### Shell

| 命令 | 做什么 |
|------|--------|
| `help` | 查看所有命令 |
| `exit` / `quit` | 退出 Shell |

---

## 故障排查

### 问题 1: `robot: command not found`

**原因**: PATH 没设好。

**解决**:
```bash
source install/setup.bash
export PATH="$PATH:$(ros2 pkg prefix multi_arm_tools)/lib/multi_arm_tools"
```

### 问题 2: Shell 启动时显示 "Auto-repair? [Y/n]"

**原因**: 之前有残留进程。

**解决**: 输入 `y` 让它自动清理。

### 问题 3: `robot start --gui` 没弹出 GUI

**原因**: 没有 X server 或 DISPLAY 没设。

**解决**:
```bash
# WSL2 检查 WSLg
echo $DISPLAY   # 应有值

# 或安装 VcXsrv
export DISPLAY=$(cat /etc/resolv.conf | grep nameserver | awk '{print $2}'):0
```

**或用 headless 模式**：
```bash
robot> start   # 不要 --gui
```

### 问题 4: `robot run` 返回 "Skill not found or not READY"

**原因**: DDS 路由到了不存在的旧 node（ghost node）。

**解决**:
```bash
robot> repair
```

这会杀重复进程 + 重启 DDS daemon。

### 问题 5: `robot start` 卡在 "Waiting for nodes to initialize"

**原因**: Gazebo 启动慢（首次约 60s）。

**解决**: 等待 60 秒。如果还卡着，按 Ctrl+C 然后 `robot status` 查看详细状态。

### 问题 6: 服务调用返回 "context invalid"

**原因**: runtime_api_node 后端服务不响应（DDS 问题）。

**解决**:
```bash
robot> repair
robot> restart
```

### 问题 7: 一切正常但想"完全重置"

```bash
# 退出 Shell
robot> exit

# 清理所有 session 和进程
pkill -9 -f 'gz sim' 2>/dev/null
pkill -9 -f 'ros2' 2>/dev/null
sleep 3
rm -rf ~/.robot/runtime/current

# 重新进入
robot
```

> ⚠️ **慎用 `pkill`**: 这是最后的手段。正常情况下 `robot stop` + `robot repair` 就够了。

### 问题 8: Gazebo 启动失败 "Address already in use"

**原因**: 端口被占用。

**解决**:
```bash
# 查找占用端口的进程
lsof -i :11345

# 杀掉
kill -9 <PID>
```

---

## 验证状态表 (2026-08-13)

| 命令 | 状态 | 备注 |
|------|------|------|
| `robot` (无参数) | ✅ | 进入 Robot OS Shell |
| `robot --help` | ✅ | 24 个命令 |
| `robot> start` | ✅ | Session 创建 (domain=40) |
| `robot> start --gui` | ✅ | Gazebo 窗口弹出 |
| `robot> start --scene lab` | ✅ | 切换场景 |
| `robot> stop` | ✅ | 清理进程树 |
| `robot> repair` | ✅ | 杀重复 + 重启 DDS |
| `robot> doctor` | ✅ | 23 项检查 |
| `robot> status` | ✅ | 系统概览 |
| `robot> world` | ✅ | 世界模型 |
| `robot> world red_cube` | ✅ | 单物体详情 |
| `robot> world --relations` | ✅ | 关系图 |
| `robot> vision status` | ✅ | 感知状态 |
| `robot> skills` | ✅ | Skills 列表 |
| `robot> capability` | ✅ | 三层能力 |
| `robot> task list` | ✅ | 任务类型 |
| `robot> run move ready` | ✅ | 移动 |
| `robot> run pick_place red_cube zone_b` | ✅ | Pick-Place |
| `robot> run pick_place red_cube zone_b --arm arm1` | ✅ | 指定臂 |
| `robot> safety status` | ✅ | 安全状态 |
| `robot> safety stop` | ✅ | E-Stop |
| `robot> episodes` | ✅ | Episode 历史 |
| `robot> analyze ep-XXX` | ✅ | 深度分析 |
| `robot> benchmark pick_place --count 10` | ✅ | 批量 |
| `robot> watch` | ✅ | 实时监控 |
| `python3 -m pytest test_cli.py` | ✅ | 22/22 pass |

---

## 下一步

- **完整 CLI 文档**: `docs/architecture/M7_CLI_v2_usage_guide.md`
- **设计文档**: `docs/architecture/M7_CLI_v2_operator_interface.md`
- **Runtime Manager 设计**: `docs/architecture/Robot_OS_Shell_design.md`
- **Runtime Manager 验证**: `docs/validation/Robot_OS_Shell_validation_report.md`
- **场景系统**: `src/multi_arm_simulation/scenes/`
- **配置驱动**: `src/multi_arm_core/config/robots.yaml`
