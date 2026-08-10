# M6.6 Runtime Developer Experience — 设计文档

**日期**: 2026-08-09
**阶段**: M6.6 Runtime Developer Experience
**状态**: 设计完成，待实施

---

## 1. 定位与核心理念

### 1.1 机器人的kubectl

M6.6是**Runtime Developer Experience** — 机器人的kubectl。
不是Web UI，不是展示界面，而是开发者日常使用的命令行工具集。

**核心理念**:
```
已有: 426+ tests, Simulation E2E, Skill Runtime, Experience Infrastructure
缺少: 让这些能力"可使用"的交互层

M6.6 = Python CLI (~500行) → 解决80%问题
M6.7 = Web Visualization → 未来展示层(实施后移)
```

### 1.2 为什么CLI优先于Web

| 维度 | Python CLI | Web Visualization |
|------|-----------|-------------------|
| 代码量 | ~500行 | ~3000行+前端 |
| 开发时间 | 1-2天 | 1-2周 |
| 适用场景 | 开发、调试、测试、CI | Demo、教学、运营监控 |
| 依赖 | 仅ROS2 | tornado + 浏览器 + WebSocket |
| 反馈速度 | 即时 | 需启动浏览器 |
| 类比 | kubectl | Grafana Dashboard |

**结论**: 当前阶段(开发验证)最需要的是CLI，Web Visualization推迟到需要对外展示时。

### 1.3 设计原则

1. **纯Python**: 无外部依赖，仅用ROS2 + 标准库
2. **零侵入**: 纯消费M5.7 FROZEN v1.0 + M6.5 Runtime API
3. **即时反馈**: 命令执行即时输出，支持实时Trace流式打印
4. **可组合**: 每个命令独立可用，可嵌入shell脚本/CI
5. **人类可读**: 终端友好输出(颜色、表格、树状结构)

---

## 2. 架构设计

### 2.1 包结构

```
multi_arm_tools/
├── multi_arm_tools/
│   ├── __init__.py
│   ├── cli.py                 # 主CLI入口 (argparse + 命令分发)
│   ├── runtime_client.py      # Runtime API客户端(封装ROS2 service/action)
│   ├── trace_viewer.py        # Trace终端渲染(树状/时间线)
│   ├── episode_viewer.py      # Episode Inspector(查看历史/失败案例)
│   ├── world_query.py         # WorldModel查询+展示
│   └── benchmark_runner.py    # 批量Benchmark(100 episodes → success rate)
├── test/
│   ├── test_cli.py            # CLI命令解析测试
│   ├── test_trace_viewer.py   # Trace渲染测试
│   ├── test_episode_viewer.py # Episode展示测试
│   ├── test_world_query.py    # 世界查询测试
│   └── test_benchmark_runner.py # Benchmark测试
├── package.xml
└── setup.py
```

### 2.2 命令架构

```
robot <command> [subcommand] [args] [options]

命令树:
├── status                    # 系统概览
├── world [object_id]         # 世界状态
│   └── --relations           # 关系图
├── skills                    # Skill列表
├── capability                # 三层能力
├── run <task_type> [args]    # 提交任务+实时Trace
│   └── --arm <name>          # 指定机械臂
│   └── --no-trace            # 不显示Trace
├── episodes                  # Episode历史
│   └── --failures-only       # 仅失败
│   └── --recent N            # 最近N个
├── episode <id>              # Episode详情+Trace回放
├── traces                    # Trace历史
│   └── --recent N            # 最近N个
├── trace <id>                # Trace详情
└── benchmark <task_type>     # 批量Benchmark
    └── --count N             # 执行次数(默认100)
    └── --output <file>       # 结果输出
```

### 2.3 数据流

```
用户命令
 ↓
cli.py (argparse解析)
 ↓
runtime_client.py (ROS2 service/action调用)
 ↓
Runtime API (/runtime/*)
 ↓
结果返回
 ↓
trace_viewer / episode_viewer / world_query (终端渲染)
 ↓
人类可读输出
```

---

## 3. 模块设计

### 3.1 cli.py — 主CLI入口

```python
"""Robot Runtime CLI — 机器人的kubectl."""

import argparse
import sys

from multi_arm_tools.runtime_client import RuntimeClient
from multi_arm_tools.world_query import WorldQuery
from multi_arm_tools.trace_viewer import TraceViewer
from multi_arm_tools.episode_viewer import EpisodeViewer
from multi_arm_tools.benchmark_runner import BenchmarkRunner


def main():
    parser = argparse.ArgumentParser(prog="robot", description="Robot Runtime CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # robot status
    subparsers.add_parser("status", help="System overview")

    # robot world [object_id] [--relations]
    p_world = subparsers.add_parser("world", help="World state query")
    p_world.add_argument("object_id", nargs="?", default=None)
    p_world.add_argument("--relations", action="store_true")

    # robot skills
    subparsers.add_parser("skills", help="List registered skills")

    # robot capability
    subparsers.add_parser("capability", help="Query three-layer capability")

    # robot run <task_type> [args] [--arm] [--no-trace]
    p_run = subparsers.add_parser("run", help="Submit task with live trace")
    p_run.add_argument("task_type")
    p_run.add_argument("args", nargs="*")
    p_run.add_argument("--arm", default=None)
    p_run.add_argument("--no-trace", action="store_true")

    # robot episodes [--failures-only] [--recent N]
    p_eps = subparsers.add_parser("episodes", help="Episode history")
    p_eps.add_argument("--failures-only", action="store_true")
    p_eps.add_argument("--recent", type=int, default=20)

    # robot episode <id>
    p_ep = subparsers.add_parser("episode", help="Episode detail + trace replay")
    p_ep.add_argument("episode_id")

    # robot traces [--recent N]
    p_tr = subparsers.add_parser("traces", help="Trace history")
    p_tr.add_argument("--recent", type=int, default=20)

    # robot trace <id>
    p_t = subparsers.add_parser("trace", help="Trace detail")
    p_t.add_argument("trace_id")

    # robot benchmark <task_type> [--count N] [--output]
    p_bm = subparsers.add_parser("benchmark", help="Batch benchmark")
    p_bm.add_argument("task_type")
    p_bm.add_argument("--count", type=int, default=100)
    p_bm.add_argument("--output", default=None)

    args = parser.parse_args()
    _dispatch(args)


def _dispatch(args):
    client = RuntimeClient()

    if args.command == "status":
        client.print_status()
    elif args.command == "world":
        WorldQuery(client).print_world(args.object_id, args.relations)
    elif args.command == "skills":
        client.print_skills()
    elif args.command == "capability":
        client.print_capability()
    elif args.command == "run":
        client.run_task(args.task_type, args.args, args.arm, not args.no_trace)
    elif args.command == "episodes":
        EpisodeViewer(client).print_episodes(
            args.failures_only, args.recent
        )
    elif args.command == "episode":
        EpisodeViewer(client).print_episode_detail(args.episode_id)
    elif args.command == "traces":
        TraceViewer(client).print_traces(args.recent)
    elif args.command == "trace":
        TraceViewer(client).print_trace_detail(args.trace_id)
    elif args.command == "benchmark":
        BenchmarkRunner(client).run(args.task_type, args.count, args.output)


if __name__ == "__main__":
    main()
```

### 3.2 runtime_client.py — Runtime API客户端

```python
"""Runtime API client — encapsulates ROS2 service/action calls."""

import rclpy
from rclpy.node import Node


class RuntimeClient:
    """ROS2 client for Runtime API (M6.5)."""

    def __init__(self):
        rclpy.init()
        self._node = Node("runtime_cli")
        # Service clients (M5.7 FROZEN v1.0 + M6.5)
        self._query_world = self._node.create_client(
            QueryWorld, "/runtime/query_world"
        )
        self._list_skills = self._node.create_client(
            ListSkills, "/runtime/list_skills"
        )
        self._get_capability = self._node.create_client(
            GetCapability, "/runtime/get_capability"
        )
        self._query_experience = self._node.create_client(
            QueryExperience, "/runtime/query_experience"
        )
        # Action client
        self._submit_task = self._node.create_client(
            SubmitTaskGoals, "/runtime/submit_task_goals"
        )

    def print_status(self):
        """Print system overview: robot + world + skills."""

    def print_skills(self):
        """Print registered skill list."""

    def print_capability(self):
        """Print three-layer capability."""

    def run_task(self, task_type, args, arm_name, show_trace):
        """Submit task and optionally stream live trace."""
```

### 3.3 trace_viewer.py — Trace终端渲染

```python
"""Trace viewer — renders Skill execution trace in terminal."""

from datetime import datetime


class TraceViewer:
    """Terminal renderer for Skill execution traces."""

    EVENT_ICONS = {
        "task_received": "📥",
        "skill_selected": "🎯",
        "precondition_check": "🔍",
        "safety_check": "🛡️",
        "execute_start": "⚡",
        "execute_end": "✅",
        "postcondition_check": "✔️",
        "recovery": "🔄",
        "success": "✅",
        "failure": "❌",
    }

    def print_trace_detail(self, trace_id):
        """Print full trace with all events."""

    def print_traces(self, recent):
        """Print trace history list."""

    def render_trace_tree(self, trace):
        """Render trace as tree structure."""
        # 📥 10:01:22  task_received
        # │  task_type: pick_place
        # ↓
        # 🎯 10:01:23  skill_selected
        # │  pick_object (cost=5.2s, success=0.87)
        # ↓
        # 🔍 10:01:24  precondition_check
        # │  ✓ object exists
        # │  ✓ arm IDLE
        # ↓
        # 🛡️ 10:01:25  safety_check
        # │  ✓ approved
        # ↓
        # ⚡ 10:01:26  execute_start: grasp
        # ↓
        # ✅ 10:01:29  execute_end (2.3s)
        # ↓
        # ✅ 10:01:30  success

    def render_trace_timeline(self, trace):
        """Render trace as horizontal timeline."""
        # [0s]═══════[2.3s]═══════[5.8s]═══════[7.4s]
        # task     execute      postcheck    success
```

### 3.4 episode_viewer.py — Episode Inspector

```python
"""Episode viewer — inspect historical episodes and failures."""

class EpisodeViewer:
    """Terminal viewer for episode history and replay."""

    def print_episodes(self, failures_only, recent):
        """Print episode list."""
        # episode_00001  pick_place  ✅  7.24s  0 recovery
        # episode_00002  pick_place  ❌  7.21s  2 recovery (grasp_failed)
        # episode_00003  pick_place  ✅  7.44s  0 recovery

    def print_episode_detail(self, episode_id):
        """Print episode detail with step-by-step replay."""
        # Episode: episode_00003
        # Task: pick_place  Result: SUCCESS  Duration: 7.44s
        #
        # Steps:
        #   [1] skill_select     (0.1s)  pick_object
        #   [2] precondition     (0.0s)  ✓ all passed
        #   [3] safety_check     (0.1s)  ✓ approved
        #   [4] execute_grasp    (2.3s)  ✓ success
        #   [5] execute_place    (2.1s)  ✓ success
        #   [6] postcondition    (0.0s)  ✓ object placed
        #
        # World State (initial → final):
        #   red_cube: [0.42,0.15,0.05] FREE → [0.30,-0.2,0.1] PLACED
        #
        # Recovery: none
```

### 3.5 world_query.py — WorldModel查询

```python
"""World query — query and display WorldModel state."""

class WorldQuery:
    """Terminal viewer for world model state."""

    def print_world(self, object_id, show_relations):
        """Print world state."""
        # Objects (3):
        #   red_cube     [0.42, 0.15, 0.05]  FREE      conf=0.94
        #   blue_cyl     [0.30,-0.20, 0.10]  ATTACHED  conf=0.88  →arm1
        #   table        [0.00, 0.00, 0.00]  STATIC    conf=1.00
        #
        # Relations:
        #   red_cube ON table        (conf=0.95)
        #   blue_cyl ATTACHED_TO arm1 (conf=1.00)
        #   arm1 NEAR red_cube        (dist=0.12m)

    def print_relations_graph(self, relations):
        """Render relations as ASCII graph."""
        #     table
        #    / | \
        #   ■  ○  arm1 ── blue_cyl
        #  red_cube
```

### 3.6 benchmark_runner.py — 批量Benchmark

```python
"""Benchmark runner — batch execute and statistics."""

class BenchmarkRunner:
    """Batch task execution with statistics."""

    def run(self, task_type, count, output_file):
        """Run N tasks and print statistics."""
        # Running 100x pick_place...
        # [████████████████████████████████████████] 100/100
        #
        # Results:
        #   Total:       100
        #   Success:     96  (96.0%)
        #   Failure:      4  (4.0%)
        #   Avg duration: 7.2s
        #   Min/Max:      5.1s / 12.3s
        #
        # Failure breakdown:
        #   grasp_failed:     3
        #   planning_failed:  1
        #
        # Saved to: benchmark_results.json
```

---

## 4. CLI命令详解

### 4.1 robot status — 系统概览

```bash
$ robot status

╔══ Robot Runtime Status ════════════════════╗
║                                            ║
║  Robot:                                    ║
║    arm1  READY   joints:[35°,-20°,80°,...] ║
║    arm2  IDLE    joints:[0°,0°,0°,...]     ║
║                                            ║
║  World:                                    ║
║    Objects: 3  (red_cube, blue_cyl, table) ║
║    Relations: 4                            ║
║                                            ║
║  Skills:                                   ║
║    pick_object   v1.0  READY               ║
║    place_object  v1.0  READY               ║
║    move_object   v1.0  READY               ║
║                                            ║
║  Safety: NORMAL  E-Stop: OFF               ║
║  Episodes: 42 (40 success, 2 failure)      ║
║                                            ║
╚════════════════════════════════════════════╝
```

### 4.2 robot world — 世界查询

```bash
$ robot world

Objects (3):
  red_cube     [0.42, 0.15, 0.05]  FREE      conf=0.94
  blue_cyl     [0.30,-0.20, 0.10]  ATTACHED  conf=0.88  →arm1
  table        [0.00, 0.00, 0.00]  STATIC    conf=1.00

$ robot world red_cube

Object: red_cube
  type:        cube
  position:    [0.42, 0.15, 0.05]
  orientation: [0, 0, 0, 1]
  grasp_state: FREE
  attached_to: (none)
  confidence:  0.94

$ robot world --relations

Relations (4):
  red_cube ON table         (conf=0.95, dist=0.05m)
  blue_cyl ATTACHED_TO arm1 (conf=1.00)
  arm1 NEAR red_cube        (conf=0.90, dist=0.12m)
  arm2 FAR red_cube         (conf=0.95, dist=0.85m)
```

### 4.3 robot run — 任务执行+实时Trace

```bash
$ robot run pick_place red_cube zone_b

[10:01:22] Task submitted: pick_place(red_cube → zone_b)
[10:01:22] 📥 task_received
           │ task_type: pick_place
           │ target: red_cube → zone_b
           ↓
[10:01:23] 🎯 skill_selected
           │ pick_object (cost=5.2s, success_rate=0.87)
           ↓
[10:01:24] 🔍 precondition_check
           │ ✓ object red_cube exists (conf=0.94)
           │ ✓ arm1 is IDLE
           │ ✓ no collision in path
           ↓
[10:01:25] 🛡️ safety_check
           │ ✓ approved (speed_scale=1.0)
           ↓
[10:01:26] ⚡ execute_start: grasp
[10:01:29] ✅ execute_end (2.3s)
           ↓
[10:01:30] ✔️ postcondition_check
           │ ✓ object attached to arm1
           ↓
[10:01:30] ✅ SUCCESS

Episode: episode_00043  Duration: 7.44s  Recovery: 0
```

### 4.4 robot episodes — Episode历史

```bash
$ robot episodes --recent 5

Recent Episodes (5):
  episode_00043  pick_place  ✅  7.44s  0 recovery
  episode_00042  pick_place  ✅  7.21s  0 recovery
  episode_00041  pick_place  ❌  7.18s  2 recovery (grasp_failed)
  episode_00040  pick_place  ✅  7.35s  0 recovery
  episode_00039  pick_place  ✅  7.28s  0 recovery

$ robot episodes --failures-only --recent 10

Failed Episodes (3):
  episode_00041  pick_place  ❌  7.18s  grasp_failed (2 recovery attempted)
  episode_00028  pick_place  ❌  5.32s  planning_failed (0 recovery)
  episode_00015  pick_place  ❌  8.91s  safety_rejected (1 recovery attempted)
```

### 4.5 robot episode — Episode详情

```bash
$ robot episode episode_00041

Episode: episode_00041
  Task:       pick_place
  Robot:      arm1
  Result:     ❌ FAILURE
  Duration:   7.18s
  Recovery:   2 attempts (grasp_failed)

Steps (6):
  [1] 0.1s  skill_select     → pick_object
  [2] 0.0s  precondition     → ✓ all passed
  [3] 0.1s  safety_check     → ✓ approved
  [4] 2.3s  execute_grasp    → ❌ grasp_failed
  [5] 1.5s  recovery_1       → retry grasp (❌ failed)
  [6] 3.2s  recovery_2       → change approach (❌ failed)

World State (initial):
  red_cube: [0.42, 0.15, 0.05] FREE

World State (final):
  red_cube: [0.42, 0.15, 0.05] FREE (unchanged)

Failure Reason: grasp_failed
  - Gripper did not achieve force threshold
  - 2 recovery strategies attempted, all failed
  - Task aborted
```

### 4.6 robot benchmark — 批量Benchmark

```bash
$ robot benchmark pick_place --count 100

Running 100x pick_place...
[████████████████████████████████████████] 100/100

Results:
  Total:        100
  Success:       96  (96.0%)
  Failure:        4  (4.0%)
  Avg duration:  7.2s
  Min/Max:       5.1s / 12.3s

Failure breakdown:
  grasp_failed:      3  (avg 7.5s)
  planning_failed:   1  (avg 5.3s)

Performance:
  Planning time:  avg 0.08s  (min 0.05s, max 0.15s)
  Execution time: avg 7.1s   (min 4.9s, max 12.2s)
  Recovery count: avg 0.08   (0 in 96, 1-2 in 4)

Saved to: benchmark_pick_place_100.json
```

---

## 5. 接口依赖

### 5.1 消费的ROS2接口（全部M5.7 FROZEN v1.0 + M6.5）

**Services (客户端)**:
| Service | Type | 用途 |
|---------|------|------|
| `/runtime/query_world` | `QueryWorld` | 世界状态查询 |
| `/runtime/list_skills` | `ListSkills` | Skill列表 |
| `/runtime/get_capability` | `GetCapability` | 能力查询 |
| `/runtime/query_experience` | `QueryExperience` | Episode历史 |

**Actions (客户端)**:
| Action | Type | 用途 |
|--------|------|------|
| `/runtime/submit_task_goals` | `SubmitTaskGoals` | 任务提交 |

**Topics (订阅 — 实时Trace)**:
| Topic | Type | 用途 |
|-------|------|------|
| `/data/episode` | `EpisodeData` | Episode完成事件 |

### 5.2 新增接口

**无新增ROS2接口**。M6.6纯消费已有接口。

### 5.3 新增依赖

| 依赖 | 用途 |
|------|------|
| `multi_arm_interfaces` | ROS2接口 |
| `multi_arm_runtime_api` | Runtime API |

---

## 6. 验收标准

| 验收项 | 通过条件 |
|--------|----------|
| robot status | 显示机器人+世界+Skill+Safety+Episode概览 |
| robot world | 显示物体列表+位置+状态 |
| robot world --relations | 显示关系图 |
| robot skills | 显示已注册Skill列表 |
| robot capability | 显示三层能力(Static+Dynamic+Context) |
| robot run | 提交任务+实时Trace流式输出 |
| robot episodes | 显示Episode历史列表 |
| robot episodes --failures-only | 仅显示失败Episode |
| robot episode <id> | 显示Episode详情+step-by-step |
| robot traces | 显示Trace历史 |
| robot trace <id> | 显示Trace详情+events |
| robot benchmark | 批量执行+统计+结果导出 |
| 闭环体验 | robot run → 实时Trace → Episode记录 → robot episode查看 |

---

## 7. 实施计划

### Phase 1: 基础框架

1. 创建`multi_arm_tools`包
2. 实现`runtime_client.py`（ROS2客户端封装）
3. 实现`cli.py`主入口（argparse命令分发）
4. `robot status` / `robot skills` / `robot capability` 基础命令

### Phase 2: 查询工具

5. 实现`world_query.py`（世界状态查询+展示）
6. `robot world` / `robot world --relations`

### Phase 3: 任务执行+Trace

7. 实现`trace_viewer.py`（Trace终端渲染）
8. `robot run`（任务提交+实时Trace流式输出）
9. `robot traces` / `robot trace <id>`

### Phase 4: Episode Inspector

10. 实现`episode_viewer.py`（Episode查看+回放）
11. `robot episodes` / `robot episode <id>`

### Phase 5: Benchmark Runner

12. 实现`benchmark_runner.py`（批量执行+统计）
13. `robot benchmark`

### Phase 6: 测试与集成

14. 单元测试（CLI解析、Trace渲染、Episode展示）
15. 集成测试（与M6仿真栈）
16. 验证报告

---

## 8. 与M6.7的关系

```
M6.6 Runtime CLI (当前优先)     M6.7 Web Visualization (未来)
         ↓                              ↓
    交互层 (开发/调试)             展示层 (Demo/运营)
         ↓                              ↓
    Python CLI ~500行            Web ~3000行+前端
         ↓                              ↓
    即时反馈                      浏览器可视化
         ↓                              ↓
    kubectl                       Grafana Dashboard
```

**演进路径**: M6.6 CLI背后的Runtime API → 未来M6.7 Web消费同一组API。
M6.6先验证API可用性和数据完整性，M6.7在此基础上增加可视化展示。

---

## 9. 关键设计决策

### 9.1 为什么用argparse而非click/typer?

| 方案 | 优点 | 缺点 |
|------|------|------|
| argparse | 标准库，零依赖 | API较verbose |
| click | API优雅 | 需额外依赖 |
| typer | 最现代 | 需typer+click |

选择argparse：零外部依赖，ROS2生态友好。

### 9.2 为什么不用rich/colorama?

终端颜色用ANSI escape codes手动实现，避免外部依赖。
如果未来需要更丰富的终端UI，可按需引入rich。

### 9.3 为什么Trace实时流式输出?

`robot run`执行时，Trace事件通过ROS2 topic实时到达，
CLI逐条打印（类似`docker build`的进度输出），而非等任务完成后一次性输出。
这给开发者即时反馈，是CLI的核心体验优势。