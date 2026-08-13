# Robot Runtime CLI v2 — Operator Interface

## 概述

CLI v2 从"API调试器"升级为**Robot Control & Observability CLI** — M7/M8的操作面。

三层认知模型：

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

## 冻结的三大契约

### Command Contract

```text
robot
├── status              # 系统总览
├── doctor              # 系统诊断
├── world [object]      # 世界模型
├── vision              # 感知
│   ├── status
│   └── objects
├── skills              # Skill列表
├── capability          # Capability Graph
├── task                # 任务
│   ├── list
│   ├── positions
│   ├── run <task> [args]
│   └── history
├── run <task> [args]   # Shorthand for task run
├── episode             # Episode
│   ├── list
│   ├── show <id>
│   └── <id>            # Backward compat
├── episodes            # Shorthand
├── safety              # Safety
│   ├── status
│   ├── check
│   └── stop            # EMERGENCY STOP
├── benchmark <task>    # 批量测试
├── evaluate            # 独立评估
├── sim                 # 仿真
│   ├── start
│   ├── stop
│   └── status
├── traces / trace      # Trace历史
├── analyze <id>        # 深度分析
└── watch               # 实时仪表盘
```

### Output Contract

- 默认：人类可读格式
- `--json`：机器可读JSON

### Exit Code Contract

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Error (service unavailable, task failed) |
| 2 | Safety (emergency stop, safety violation) |
| 3 | Timeout |

## 命令详解

### OBSERVE 层

#### `robot status`

回答操作者的6个问题：机器人活着吗？身体正常吗？看得见吗？世界模型可信吗？能执行任务吗？上次执行怎么样？

```bash
robot status
```

```bash
robot status --json    # 机器可读
```

#### `robot doctor`

主动诊断所有子系统，报告健康状态和建议修复。

```bash
robot doctor
```

检查项：ROS2, Gazebo, Workspace, Nodes, Controllers, MoveIt, WorldModel, Safety, RuntimeAPI, Experience, Perception, Evaluation

### DIAGNOSE 层

#### `robot world`

WorldModel状态总览，含source/confidence/uncertainty/health。

```bash
robot world
robot world --relations
```

#### `robot world <object>`

WorldModel debugger — 展示belief、source、state、health。

```bash
robot world red_cube
```

输出包含：
- CURRENT BELIEF (mean, variance, confidence)
- SOURCE (vision/ground_truth/fused)
- STATE (type, grasp_state, attached_to)
- OBSERVATION (vision_error)
- HEALTH (stale, contradiction, uncertain, covariance)

#### `robot vision status`

感知层状态 — Camera + Detector + Objects + Quality。

```bash
robot vision status
robot vision objects
```

Vision ≠ WorldModel：
- Vision = 传感器当前看到什么
- WorldModel = 机器人当前相信世界是什么

#### `robot episode list / show`

Episode历史和详情。

```bash
robot episode list
robot episode show EP-0042
robot episode EP-0042          # Backward compat
robot episodes --failures-only
```

### ACT 层

#### `robot task run / robot run`

提交任务执行。

```bash
robot task run move ready --arm arm1
robot run pick_place red_cube zone_b --no-trace
robot run move ready --debug
```

#### `robot safety stop`

**紧急停止** — 直接调用SafetySupervisor，绕过RuntimeApi/Coordinator/Skill pipeline。

```bash
robot safety stop    # Exit code 2 (safety)
```

架构保证：
```
CLI → SafetySupervisor → STOP MOTION
```
而非：
```
CLI → RuntimeApi → Task → Coordinator → Safety
```

#### `robot safety status / check`

```bash
robot safety status
robot safety check
```

#### `robot benchmark`

批量测试。

```bash
robot benchmark move --count 100
robot benchmark pick_place --count 50 --output results.json
```

#### `robot evaluate`

独立评估。

```bash
robot evaluate
robot evaluate --db benchmark.db
```

## Agent / 脚本使用示例

### 基本工作流

```bash
# 1. 检查系统状态
robot status --json | jq '.system'

# 2. 查看世界模型
robot world --json | jq '.objects[] | .name'

# 3. 执行任务
robot run move ready --arm arm1 --no-trace
echo $?  # 0=success, 1=error

# 4. 查看结果
robot episode list --json | jq '.episodes[-1]'

# 5. 紧急停止
robot safety stop
echo $?  # 2=safety
```

### CI/CD 集成

```bash
# 系统健康检查
robot doctor || exit 1

# 执行测试任务
robot run move ready --no-trace || exit 1
robot run pick_place red_cube zone_b --no-trace || exit 1

# 批量benchmark
robot benchmark move --count 10 --output bm.json

# 独立评估
robot evaluate
```

### Agent 消费 JSON

```python
import subprocess, json

# 获取系统状态
result = subprocess.run(["robot", "status", "--json"], capture_output=True)
status = json.loads(result.stdout)
if status["system"] != "READY":
    print("System not ready")

# 获取世界模型
result = subprocess.run(["robot", "world", "--json"], capture_output=True)
world = json.loads(result.stdout)
for obj in world["objects"]:
    if obj["uncertain"]:
        print(f"Warning: {obj['name']} is uncertain")

# 提交任务
result = subprocess.run(
    ["robot", "run", "7 "pick_place", "red_cube", "zone_b", "--no-trace"],
    capture_output=True
)
if result.returncode == 0:
    print("Task succeeded")
elif result.returncode == 2:
    print("Safety stop triggered")
```

### 监控循环

```bash
#!/bin/bash
while true; do
    status=$(robot status --json)
    uncertain=$(echo "$status" | jq '.world.uncertain')
    conflicts=$(echo "$status" | jq '.world.conflicts')
    
    if [ "$conflicts" -gt 0 ]; then
        echo "WARNING: $conflicts conflicts detected"
        robot world --relations
    fi
    
    sleep 5
done
```

## 架构边界

CLI是**Operator Adapter**，不包含业务逻辑：

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

例外：`robot safety stop` 直接调用SafetySupervisor，体现Safety独立性架构约束。

## 向后兼容

| 旧命令 | 新命令 | 状态 |
|--------|--------|------|
| `robot run <task>` | `robot task run <task>` | 两者都可用 |
| `robot episodes` | `robot episode list` | 两者都可用 |
| `robot episode <id>` | `robot episode show <id>` | 两者都可用 |
| `robot world <obj>` | `robot world <obj>` | 不变 |
| `robot status` | `robot status` | 增强 |
| `robot doctor` | `robot doctor` | 增强 |