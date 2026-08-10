# Robot Runtime CLI 使用文档

**包**: `multi_arm_tools`
**命令**: `robot`
**版本**: 0.1.0
**定位**: 机器人的 kubectl — Runtime Developer Experience

---

## 1. 快速开始

### 1.1 前置条件

```bash
# 1. source ROS2 环境
source /opt/ros/jazzy/setup.bash

# 2. source 工作空间
source install/setup.bash

# 3. 添加 robot 命令到 PATH（每次新终端执行一次，或加入 ~/.bashrc）
export PATH="$PATH:$(ros2 pkg prefix multi_arm_tools)/lib/multi_arm_tools"

# 4. 确保 Runtime API 节点正在运行
ros2 launch multi_arm_runtime_api runtime_api.launch.py
```

> **替代方案**: 如果不想修改 PATH，可以用 `ros2 run multi_arm_tools robot` 代替 `robot`。

### 1.2 第一个命令

```bash
$ robot status

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

Episodes: 42 (40 success, 2 failure)
```

---

## 2. 命令详解

### 2.1 robot status — 系统概览

**用途**: 一眼看清机器人当前状态 — 世界、Skill、能力、Episode统计。

```bash
robot status
```

**输出示例**:
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

Episodes: 42 (40 success, 2 failure)
```

**数据源**:
- `/runtime/query_world` (世界状态)
- `/runtime/list_skills` (Skill列表)
- `/runtime/get_capability` (能力查询)
- `/runtime/query_experience` (Episode统计)

---

### 2.2 robot world — 世界状态查询

**用途**: 查看机器人"看到"的世界 — 物体位置、状态、关系。

#### 列出所有物体

```bash
robot world
```

**输出**:
```
Objects (3):
  red_cube         [ 0.42,  0.15,  0.05]  FREE       conf=0.94
  blue_cylinder    [ 0.30, -0.20,  0.10]  ATTACHED   conf=0.88  -> arm1
  table            [ 0.00,  0.00,  0.00]  STATIC     conf=1.00
```

#### 查看单个物体详情

```bash
robot world red_cube
```

**输出**:
```
Object: red_cube
  type:        cube
  position:    [0.420, 0.150, 0.050]
  orientation: [0.000, 0.000, 0.000, 1.000]
  grasp_state: FREE
  attached_to: (none)
  confidence:  0.94
```

#### 查看关系图

```bash
robot world --relations
```

**输出**:
```
Objects (3):
  red_cube         [ 0.42,  0.15,  0.05]  FREE       conf=0.94
  blue_cylinder    [ 0.30, -0.20,  0.10]  ATTACHED   conf=0.88  -> arm1
  table            [ 0.00,  0.00,  0.00]  STATIC     conf=1.00

Relations (4):
  red_cube         ON              table           conf=0.95  (dist=0.050m)
  blue_cylinder    ATTACHED_TO     arm1            conf=1.00
  arm1             NEAR            red_cube        conf=0.90  (dist=0.120m)
  arm2             FAR             red_cube        conf=0.95  (dist=0.850m)
```

**字段说明**:

| 字段 | 含义 |
|------|------|
| `position` | 物体在世界坐标系中的位置 [x, y, z] (米) |
| `grasp_state` | 抓取状态: FREE / ATTACHED / PLACED / STATIC |
| `attached_to` | 被哪个机械臂抓取 (arm1 / arm2 / 空) |
| `confidence` | 感知置信度 (0.0-1.0) |
| `predicate` | 关系类型: ON / ATTACHED_TO / NEAR / FAR / IN |

---

### 2.3 robot skills — Skill 列表

**用途**: 查看已注册的 Skill 及其性能指标。

```bash
robot skills
```

**输出**:
```
Registered Skills (3):

  pick_object        v1.0
    Pick up an object from a surface
    cost: 5.2s  success_rate: 0.87  risk: 0.15
    requires: manipulation, gripper, vision

  place_object       v1.0
    Place an object at a target location
    cost: 3.8s  success_rate: 0.92  risk: 0.08
    requires: manipulation, gripper

  move_object        v1.0
    Move object between two positions
    cost: 4.1s  success_rate: 0.95  risk: 0.05
    requires: manipulation, planning
```

**字段说明**:

| 字段 | 含义 |
|------|------|
| `cost` | 预估执行时间 (秒) |
| `success_rate` | 历史成功率 (0.0-1.0) |
| `risk` | 风险评估 (0.0=安全, 1.0=高危) |
| `requires` | 所需能力列表 |

---

### 2.4 robot capability — 三层能力查询

**用途**: 查询机器人的三层能力 — Static / Dynamic / Context。

```bash
robot capability
```

**输出**:
```
Three-Layer Capability (8):

  [static]
    [x] manipulation              = true
    [x] gripper                   = true
    [x] vision                    = true
    [x] planning                  = true
    [x] safety_monitor            = true

  [dynamic]
    [x] arm1_available            = true
    [ ] arm2_available            = false  (arm2 in ERROR state)

  [context]
    [x] zone_a_accessible         = true
    [x] zone_b_accessible         = true
```

**三层能力说明**:

| 层 | 含义 | 示例 |
|----|------|------|
| `static` | 固有能力 (硬件决定) | manipulation, gripper, vision |
| `dynamic` | 运行时状态 | arm1_available, arm2_available |
| `context` | 环境约束 | zone_a_accessible, path_clear |

---

### 2.5 robot run — 提交任务 + 实时 Trace

**用途**: 提交任务并实时观察执行 Trace — 这是 CLI 的核心体验。

#### 基本用法

```bash
robot run pick_place red_cube zone_b
```

**输出** (实时流式):
```
Task submitted: pick_place(red_cube zone_b)

[10:01:22] goal_received (0%)
[10:01:23] skill_selected (10%)
[10:01:24] precondition_check (20%)
[10:01:25] safety_check (30%)
[10:01:26] executing_grasp (40%)
[10:01:29] executing_place (70%)
[10:01:30] postcondition_check (90%)
[10:01:30] completed (100%)

[OK] SUCCESS
  Success: 1/1
  episode_00043
```

#### 指定机械臂

```bash
robot run pick_place red_cube zone_b --arm arm2
```

#### 不显示 Trace (静默模式)

```bash
robot run move ready --no-trace
```

**输出**:
```
Success: True
  1/1
```

#### 任务类型与参数

| 任务类型 | 参数 | 示例 |
|----------|------|------|
| `pick_place` | `<object_id> <zone_name>` | `robot run pick_place red_cube zone_b` |
| `pick` / `grasp` | `<object_id> [<zone_name>]` | `robot run grasp red_cube` |
| `place` | `<zone_name> [<object_id>]` | `robot run place zone_b red_cube` |
| `move` / `lift` / `retract` / `inspect` | `<position_name> [<zone_name>]` | `robot run move ready` |

**可用 position_name**:
```
home, ready, extended, scan, inspect, place_high, place_low
```

**数据流**:
```
CLI
 ↓ SubmitTaskGoals action
/runtime/submit_task_goals
 ↓
RuntimeApiNode → ExecuteSkill → Coordinator → MoveIt → JTC → Gazebo
 ↓
Feedback (current_goal, progress) → CLI 实时打印
 ↓
Result (success, results, success_count, total_count)
```

---

### 2.6 robot episodes — Episode 历史

**用途**: 查看历史 Episode，快速定位失败案例。

#### 最近 Episode

```bash
robot episodes
```

**输出**:
```
Recent Episodes (20):
  episode_00043  pick_place      [OK]   7.44s  0 recovery
  episode_00042  pick_place      [OK]   7.21s  0 recovery
  episode_00041  pick_place      [FAIL] 7.18s  2 recovery (grasp_failed)
  episode_00040  pick_place      [OK]   7.35s  0 recovery
  episode_00039  pick_place      [OK]   7.28s  0 recovery
  ...
```

#### 仅查看失败

```bash
robot episodes --failures-only
```

**输出**:
```
Failed Episodes (3):
  episode_00041  pick_place      [FAIL] 7.18s  2 recovery (grasp_failed)
  episode_00028  pick_place      [FAIL] 5.32s  0 recovery
  episode_00015  pick_place      [FAIL] 8.91s  1 recovery (safety_rejected)
```

#### 限制数量

```bash
robot episodes --recent 5
```

---

### 2.7 robot episode — Episode 详情 + 回放

**用途**: 查看单个 Episode 的完整执行过程 — step-by-step 回放。

```bash
robot episode episode_00041
```

**输出**:
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
  [4] 2.3s  execute_grasp             [FAIL]
  [5] 1.5s  recovery_1                [FAIL]
  [6] 3.2s  recovery_2                [FAIL]

World State (initial):
  red_cube         [0.42, 0.15, 0.05]  FREE

World State (final):
  red_cube         [0.42, 0.15, 0.05]  FREE

Recovery attempts (2):
  [1] grasp_failed          strategy=retry                [FAIL]
  [2] grasp_failed          strategy=change_approach      [FAIL]
```

**用途场景**:
- 任务失败后，用 `robot episode <id>` 定位失败步骤
- 查看初始/最终世界状态对比，确认物体是否移动
- 分析 recovery 策略是否有效

---

### 2.8 robot traces — Trace 历史

**用途**: 查看执行 Trace 历史 (与 Episode 关联)。

```bash
robot traces --recent 10
```

**输出**:
```
Recent Traces (10):
  episode_00043      pick_place      [OK]   7.44s  6 events
  episode_00042      pick_place      [OK]   7.21s  6 events
  episode_00041      pick_place      [FAIL] 7.18s  6 events
  ...
```

---

### 2.9 robot trace — Trace 详情

**用途**: 查看单个 Trace 的完整事件链路。

```bash
robot trace episode_00043
```

**输出**:
```
Trace: episode_00043    Status: [OK]    Duration: 7.44s
Task: pick_place  Skill: pick_object  Recovery: 0

Events:
  [1] 0.1s  skill_select               [OK]
  [2] 0.0s  precondition               [OK]
  [3] 0.1s  safety_check               [OK]
  [4] 2.3s  execute_grasp              [OK]
  [5] 2.1s  execute_place              [OK]
  [6] 0.0s  postcondition              [OK]
```

---

### 2.10 robot benchmark — 批量 Benchmark

**用途**: 批量执行任务，统计成功率和性能指标。

#### 基本用法

```bash
robot benchmark pick_place --count 100
```

**输出**:
```
Running 100x pick_place...
[########################################] 100/100

Results:
  Total:        100
  Success:       96  (96.0%)
  Failure:        4  (4.0%)
  Avg duration:  7.20s
  Min/Max:       5.10s / 12.30s

Failure breakdown:
  grasp_failed:        3  (avg 7.50s)
  planning_failed:     1  (avg 5.30s)
```

#### 保存结果到文件

```bash
robot benchmark pick_place --count 50 --output results.json
```

**输出文件格式** (`results.json`):
```json
{
  "task_type": "pick_place",
  "count": 50,
  "timestamp": 1723207689.12,
  "results": [
    {"index": 0, "success": true, "duration": 7.24},
    {"index": 1, "success": false, "duration": 5.32, "reason": "planning_failed"}
  ],
  "summary": {
    "success_count": 48,
    "failure_count": 2,
    "avg_duration": 7.15
  }
}
```

**用途场景**:
- 验证架构稳定性 (100次任务 success rate > 80%)
- 测量性能基线 (avg duration, min/max)
- 分析失败模式 (failure breakdown)
- CI/CD 集成 (`--output` 导出 JSON 供脚本检查)

---

## 3. 典型工作流

### 3.1 开发调试流

```bash
# 1. 查看系统状态
robot status

# 2. 提交任务，观察执行
robot run pick_place red_cube zone_b

# 3. 查看刚才的 Episode
robot episodes --recent 1

# 4. 如果失败，查看详情
robot episode episode_00044

# 5. 查看世界状态是否正确
robot world --relations
```

### 3.2 失败分析流

```bash
# 1. 查看所有失败 Episode
robot episodes --failures-only

# 2. 逐个查看失败详情
robot episode episode_00041
robot episode episode_00028

# 3. 查看对应 Trace
robot trace episode_00041

# 4. 检查当时世界状态
robot world
```

### 3.3 Benchmark 验证流

```bash
# 1. 运行 100 次 pick_place
robot benchmark pick_place --count 100 --output bench.json

# 2. 查看结果
cat bench.json | python -m json.tool

# 3. 对比不同任务
robot benchmark move --count 50 --output bench_move.json
robot benchmark pick_place --count 50 --output bench_pick.json
```

### 3.4 Skill 开发流

```bash
# 1. 查看已注册 Skill
robot skills

# 2. 查看能力是否满足
robot capability

# 3. 测试新 Skill
robot run pick_place red_cube zone_a

# 4. 批量验证
robot benchmark pick_place --count 20
```

---

## 4. 与其他工具的关系

### 4.1 robot CLI vs ros2 CLI

| 场景 | ros2 CLI | robot CLI |
|------|----------|-----------|
| 查看话题列表 | `ros2 topic list` | — |
| 查看世界状态 | `ros2 service call /runtime/query_world ...` | `robot world` |
| 提交任务 | `ros2 action send_goal /runtime/submit_task_goals ...` | `robot run pick_place red_cube zone_b` |
| 查看 Episode | `ros2 service call /runtime/query_experience ...` | `robot episodes` |

**robot CLI 封装了 ROS2 的底层调用**，提供人类友好的命令接口。

### 4.2 robot CLI vs RViz

| 维度 | RViz | robot CLI |
|------|------|-----------|
| 定位 | 3D 运动可视化 | Runtime 交互查询 |
| 适用 | 看机器人姿态/轨迹 | 看世界状态/Skill执行/Episode |
| 交互 | 鼠标拖拽 | 命令行 |
| 输出 | 图形界面 | 终端文本 |

**互补关系**: RViz 看 3D 运动状态，robot CLI 看 Runtime 语义状态。

### 4.3 robot CLI vs M6.7 Web Visualization

| 维度 | robot CLI (M6.6) | Web Viz (M6.7) |
|------|------------------|-----------------|
| 定位 | 开发/调试 | Demo/运营监控 |
| 代码量 | ~800行 | ~3000行+前端 |
| 依赖 | 仅 ROS2 | tornado + 浏览器 |
| 反馈 | 即时 | 需启动浏览器 |
| 类比 | kubectl | Grafana Dashboard |

**演进路径**: M6.6 CLI 背后的 Runtime API → 未来 M6.7 Web 消费同一组 API。

---

## 5. 故障排查

### 5.1 `robot: command not found`

**原因**: colcon 的 `source install/setup.bash` 不会自动将 `lib/<package>` 加入 PATH。

**解决**:
```bash
# 方法1: 添加到 PATH（推荐，加入 ~/.bashrc 一劳永逸）
# 注意: 不要用 ~ 路径，~ 在双引号内不展开且 HOME 可能被设为 /tmp
export PATH="$PATH:$(ros2 pkg prefix multi_arm_tools)/lib/multi_arm_tools"

# 方法2: 使用 ros2 run（无需修改 PATH）
ros2 run multi_arm_tools robot --help
```

### 5.2 服务不可用

```
ERROR: Service /runtime/query_world not available
```

**原因**: RuntimeApiNode 未启动。

**解决**:
```bash
# 启动 Runtime API
ros2 launch multi_arm_runtime_api runtime_api.launch.py

# 或启动完整 M6 栈
ros2 launch multi_arm_runtime_api runtime_api.launch.py
```

### 5.3 Action 不可用

```
ERROR: Action /runtime/submit_task_goals not available
```

**原因**: RuntimeApiNode 或后端 SkillRuntime 未启动。

**解决**:
```bash
# 检查节点是否运行
ros2 node list | grep runtime

# 检查 Action 是否存在
ros2 action list | grep submit_task_goals
```

### 5.4 无数据返回

```
No objects in world model.
```

**原因**: WorldModel 节点未启动或未收到感知数据。

**解决**:
```bash
# 检查 WorldModel 节点
ros2 node list | grep world_model

# 检查话题是否有数据
ros2 topic echo /world_model/state --once
```

### 5.5 Episode 查询为空

```
No episodes found.
```

**原因**: ExperienceRecorder 未启动或没有任务被执行过。

**解决**:
```bash
# 先执行一个任务
robot run move ready

# 再查询
robot episodes
```

---

## 6. 环境变量

| 变量 | 默认 | 说明 |
|------|------|------|
| `ROS_HOME` | `~/.ros` | ROS2 日志/缓存目录 |
| `HOME` | 用户主目录 | 影响配置文件路径 |

**WSL2 推荐设置**:
```bash
export ROS_HOME=/tmp/ros_home
export HOME=/tmp
```

---

## 7. 命令速查表

```bash
# 查询类
robot status                          # 系统概览
robot world                           # 所有物体
robot world red_cube                  # 单个物体详情
robot world --relations               # 关系图
robot skills                          # Skill列表
robot capability                      # 三层能力

# 执行类
robot run pick_place red_cube zone_b  # 提交任务+实时Trace
robot run move ready --arm arm2       # 指定机械臂
robot run move ready --no-trace       # 静默模式

# 历史类
robot episodes                        # 最近20个Episode
robot episodes --failures-only        # 仅失败
robot episodes --recent 5             # 最近5个
robot episode episode_00043           # Episode详情+回放
robot traces                          # Trace历史
robot trace episode_00043             # Trace详情

# Benchmark类
robot benchmark pick_place --count 100              # 100次pick_place
robot benchmark pick_place --count 50 --output out.json  # 保存结果
```

---

## 8. 技术细节

### 8.1 架构

```
用户终端
  ↓
robot (cli.py, argparse)
  ↓
RuntimeClient (runtime_client.py)
  ↓ ROS2 service/action
/runtime/* (RuntimeApiNode, M6.5)
  ↓
WorldModel / SkillRuntime / Experience / Coordinator
```

### 8.2 接口依赖

| 接口 | 类型 | 用途 |
|------|------|------|
| `/runtime/query_world` | Service (QueryWorld) | 世界状态 |
| `/runtime/list_skills` | Service (ListSkills) | Skill列表 |
| `/runtime/get_capability` | Service (GetCapability) | 能力查询 |
| `/runtime/query_experience` | Service (QueryExperience) | Episode历史 |
| `/runtime/submit_task_goals` | Action (SubmitTaskGoals) | 任务提交 |

### 8.3 TaskGoal 构建

CLI 参数到 TaskGoal 消息的映射:

```
robot run pick_place red_cube zone_b
       ↓            ↓        ↓
  action_type    object_id  zone_name

robot run move ready
       ↓      ↓
  action_type  position_name
```

### 8.4 实时 Trace 实现

`robot run` 使用 Action feedback 实现实时输出:

```python
def on_feedback(feedback):
    print(f"[{time}] {feedback.current_goal} ({feedback.progress*100:.0f}%)")

result = client.submit_task(task_type, args, on_feedback=on_feedback)
```

Action 执行过程中，RuntimeApiNode 发布 feedback (current_goal, progress)，
CLI 回调实时打印进度。

---

## 9. 扩展指南

### 9.1 添加新命令

1. 在 `cli.py` 的 `main()` 中添加 subparser:
```python
p_new = subparsers.add_parser("newcmd", help="New command")
p_new.add_argument("arg1")
```

2. 在 `_dispatch()` 中添加处理:
```python
elif args.command == "newcmd":
    _cmd_new(client, args.arg1)
```

3. 实现处理函数:
```python
def _cmd_new(client: RuntimeClient, arg1: str) -> None:
    response = client.query_world(entity_id=arg1)
    # ... 渲染输出
```

### 9.2 添加新任务类型

在 `runtime_client.py` 的 `_build_task_goal()` 中添加解析:

```python
elif task_type == "new_task":
    if len(args) >= 1:
        goal.object_id = args[0]
```

---

## 10. 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| 0.1.0 | 2026-08-09 | 初始版本: 11个命令, 36 tests |