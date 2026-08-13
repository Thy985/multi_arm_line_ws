# Robot Runtime CLI v2 使用文档

**包**: `multi_arm_tools`
**命令**: `robot`
**版本**: 2.0.0
**定位**: Robot Control & Observ2.0.0
**定位**: Robot Control & Observability CLI — M7/M8 Operator Interface

---

## 1. 概述

CLI v2 从"API调试器"升级为**Operator Interface**，围绕操作者的认知模型设计：

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

### 三大冻结契约

| 契约 | 内容 |
|------|------|
| **Command** | 固定子命令层次，不再随意增加 |
| **Output** | 人可读(默认) / 机可读(`--json`) |
| **Exit Code** | 0=success, 1=error, 2=safety, 3=timeout |

---

## 2. 快速开始

### 2.1 前置条件

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash
export PATH="/usr/bin:$PATH"
export ROS_HOME=/tmp/ros_home
export HOME=/tmp
``/tmp/ros_home
export HOME=/tmp
```

### 2.2 第一个命令

```bash
$ robot status

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
  Stale      0

OBJECTS
  red_cube         [  0.50,   0.00,   0.43]  conf=1.00  src=ground_truth
  blue_cylinder    [  0.30,   0.20,   0.44]  conf=1.00  src=ground_truth

LAST TASK
  move → SUCCESS
  duration: 5.3s
  episode: episode_00042

EPISODES: 42 (40 success, .3s
  episode: episode_00042

EPISODES: 42 (40 success, 2 failure)
```

### 2.3 JSON 输出

```bash
$ robot status --json
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
  "episodes": {"total": 42, "success": 40, "failure": 2}
}
```

---

## 3. 命令详解

### 3.1 OBSERVE 层

#### `robot status` — 系统总览

回答操作者的6个问题：机器人活着吗？身体正常吗？看得见吗？世界模型可信吗？能执行任务吗？上次执行怎么样？

```bash
robot status          # 人类可读
robot status --json   # 机器可读
```

#### `robot doctor` — 系统诊断

主动检查所有子系统，报告健康状态和建议修复。

```bash
robot doctor
```

检查项：ROS2, Gazebo, Workspace, Nodes, Controllers, MoveIt, WorldModel, Safety, RuntimeAPI, Experience, **Perception**, **Evaluation**

输出示例：
```
=== Robot Runtime Diagnosis ===

  [ROS2] [OK] DDS communication (distro=jazzy)
  [Simulation] [OK] Gazebo running
  [Controllers] [OK] joint_trajectory_controller ACTIVE
  [WorldModel] [OK] Query service available
  [Safety] [OK] Supervisor online
  [Perception] [OK] ColorDetector online
  [Evaluation] [OK] Safety check service available

  System Health: 93/100 (14/15 checks passed)

  Note: controller timeout 是 WSL2 已知限制，不影响其他功能。
```

---

### 3.2 DIAGNOSE 层

#### `robot world` — 世界模型总览

```bash
robot world
robot world --relations
```

输出示例：
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

#### `robot world <object>` — WorldModel Debugger

展示belief、source、state、health — 回答"为什么系统认为物体在这里？"

```bash
robot world red_cube
```

输出示例：
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

#### `robot vision status` — 感知层状态

Vision ≠ WorldModel：
- **Vision** = 传感器当前看到什么
- **WorldModel** = 机器人当前相信世界是什么

```bash
robot vision status
```

输出示例：
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

#### `robot vision objects` — 检测结果

```bash
robot vision objects
```

#### `robot episode list` — Episode历史

```bash
robot episode list
robot episode list --failures-only
robot episodes --recent 5          # 向后兼容
```

#### `robot episode show <id>` — Episode详情

```bash
robot episode show episode_00041
robot episode episode_00041        # 向后兼容
```

输出示例：
```
Episode: episode_00041
  Task:       pick_place
  Skill:      pick_object
  Robot:      arm1
  Result:     [FAIL] FAILURE
  Duration:   7.18s
  Recovery:   2 attempts

Steps (6):
  [1] 0.1s  skill_select              [OK]
  [2] 0.0s  precondition              [OK]
  [3] 0.1s  safety_check              [OK]
?  [4] 2.3s  execute_grasp             [FAIL]
  [5] 1.5s  recovery_1                [FAIL]
  [6] 3.2s  recovery_2                [FAIL]

Recovery attempts (2):
  [1] grasp_failed          strategy=retry                [FAIL]
  [2] grasp_failed          strategy=change_approach      [FAIL]
```

#### `robot skills` — Skill列表

```bash
robot skills
robot skills --json
```

#### `robot capability` — 三层能力

```bash
robot capability
```

---

### 3.3 ACT 层

#### `robot task run` / `robot run` — 提交任务

```bash
robot task run pick_place red_cube zone_b
robot run pick_place red_cube zone_b          # 向后兼容shorthand
robot run move ready --arm arm1 --no-trace
robot run move ready --debug
```

任务类型与参数：

| 任务类型 | 参数 | 示例 |
|----------|------|------|
| `pick_place` | `<object_id> <zone_name>` | `robot run pick_place red_cube zone_b` |
| `pick` / `grasp` | `<object_id> [<zone_name>]` | `robot run grasp red_cube` |
| `place` | `<zone_name> [<object_id>]` | `robot run place zone_b red_cube` |
| `move` / `lift` / `retract` / `inspect` | `<position_name>` | `robot run move ready` |

#### `robot task history` — 任务历史

```bash
robot task history
```

#### `robot safety status` — 安全状态

```bash
robot safety status
```

输出示例：
```
SAFETY
----------------------------------------
  Supervisor       ● ACTIVE
  Speed scale      1.00
  Message          OK

Authority:
  Safety > Coordinator > Skill > Task
```

#### `robot safety check` — 安全检查

```bash
robot safety check
robot safety check --json
```

#### `robot safety stop` — 紧急停止

**最高优先级操作** — 直接调用SafetySupervisor，绕过RuntimeApi/Coordinator/Skill pipeline。

```bash
robot safety stop
echo $?    # 2 (safety)
```

架构保证：
```
CLI → SafetySupervisor → STOP MOTION
```
而非：
```
CLI → RuntimeApi → Task → Coordinator → Safety
```

#### `robot benchmark` — 批量测试

```bash
robot benchmark move --count 100
robot benchmark pick_place --count 50 --output results.json
```

#### `robot evaluate` — 独立评估

```bash
robot evaluate
robot evaluate --db benchmark.db
```

---

## 4. 退出码契约

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

## 5. 典型工作流

### 5.1 开发调试流

```bash
# 1. 查看系统状态
robot status

# 2. 提交任务，观察执行
robot run pick_place red_cube zone_b

# 3. 查看刚才的 Episode
robot episode list --recent 1

# 4. 如果失败，查看详情
robot episode show episode_00044

# 5. 查看世界状态
robot world --relations

# 6. 查看感知状态
robot vision status
```

### 5.2 失败分析流

```bash
robot episode list --failures-only
robot episode show episode_00041
robot trace episode_00041
robot world red_cube
```

### 5.3 安全应急流

```bash
# 紧急停止
robot safety stop

# 检查安全状态
robot safety status

# 确认系统状态
robot doctor
```

### 5.4 Benchmark 验证流

```bash
robot benchmark pick_place --count 100 --output bench.json
robot evaluate
```

### 5.5 Agent 自动化流

```bash
#!/bin/bash
# CI/CD 集成
robot doctor || exit 1
robot run move ready --no-trace || exit 1
robot run pick_place red_cube zone_b --no-trace || exit 1
robot benchmark move --count 10 --output bm.json
robot evaluate
```

---

## 6. Agent / 脚本消费

### 6.1 Python 消费 JSON

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

### 6.2 Shell 监控循环

```bash
#!/bin/bash
4
while true; do
    uncertain=$(robot status --json | jq '.world.uncertain')
    if [ "$uncertain" -gt 0 ]; then
        echo "WARNING: $uncertain objects uncertain"
        robot world
    fi
    sleep 5
done
```

### 6.3 jq 查询示例

```bash
# 所有不确定的物体
robot world --json | jq '.objects[] | select(.uncertain == true)'

# 最近失败的Episode
robot episode list --json | jq '.episodes[] | select(.result == "failure")'

# Capability可用率
robot capability --json | jq '.capabilities | map(.available) | add / length'
```

---

## 7. 故障排查

### 7.1 `robot: command not found`

```bash
export PATH="$PATH:$(ros2 pkg prefix multi_arm_tools)/lib/multi_arm_tools"
# 或
4
ros2 run multi_arm_tools robot --help
```

### 7.2 服务不可用

```
ERROR: Service /runtime/query_world not available
```

**解决**: 启动 RuntimeApiNode 或完整仿真栈。

### 7.3 安全服务不可用

```
✗ Emergency stop failed: Safety service not available
```

**解决**: 确认 SafetySupervisor 正在运行。

```bash
ros2 node list | grep safety
```

### 7.4 Episode 查询为空

先执行一个任务再查询：

```bash
robot run move ready --no-trace
robot episode list
```

---

## 8. 命令速查表

```bash
# OBSERVE
robot status                          # 系统总览
robot doctor                          # 系统诊断

# DIAGNOSE
robot world                           # 世界模型
robot world red_cube                  # 物体详情 (belief/health)
robot world --relations               # 关系图
robot vision status                   # 感知状态
robot vision objects                  # 检测结果
robot skills                          # Skill列表
robot capability                      # 三层能力
robot episode list                    # Episode历史
robot episode show <id>               # Episode详情
robot traces                          # Trace历史

# ACT
robot run pick_place red_cube zone_b  # 提交任务
robot task run move ready --arm arm1  # 显式任务提交
robot safety status                   # 安全状态
robot safety check                    # 安全检查
robot safety stop                     # 紧急停止
robot benchmark move --count 100      # 批量测试
robot evaluate                        # 独立评估

# GLOBAL
--json                                # 机器可读输出
```

---

## 9. 架构边界

CLI 是 **Operator Adapter**，不包含业务逻辑：

```
                robot CLI
                    │
              CLI command layer
                    │
             RuntimeClient
                    │
             RuntimeApiNode
                    │
       ┌────────────┼────────────┐
       ↓            ↓            ↓
   WorldModel    SkillRuntime   Safety
```

**例外**: `robot safety stop` 直接调用 SafetySupervisor，体现 Safety 独立性架构约束。

---

## 10. 向后兼容

| 旧命令 | 新命令 | 状态 |
|--------|--------|------|
| `robot run <task>` | `robot task run <task>` | 两者都可用 |
| `robot episodes` | `robot episode list` | 两者都可用 |
| `robot episode <id>` | `robot episode show <id>` | 两者都可用 |
| `robot world <obj>` | `robot world <obj>` | 不变 |
| `robot status` | `robot status` | 增强 |
| `robot doctor` | `robot doctor` | 增强 |

---

## 11. �>## 11. 环境变量

| 变量 | 默认 | 说明 |
|------|------|------|
| `ROS_HOME` | `~/.ros` | ROS2 日志/缓存目录 |
| `HOME` | 用户主目录 | 影响配置文件路径 |
| `RMW_IMPLEMENTATION` | (DDS默认) |> | `RMW_IMPLEMENTATION` | (DDS默认) | 建议用 `rmw_cyclonedds_cpp` |
| `GZ_SIM_SYSTEM_PLUGIN_PATH`6) | Gazebo插件路径 |

---

## 12. 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| 0.1.0 | 2026-08-09 | 初始版本: 11个命令, 36 tests |
| 2.0.0 | 2026-08-12 | Operator Interface v2: 三层认知模型, --json, 退出码契约, vision/safety/task/episode命名空间, 22 tests |