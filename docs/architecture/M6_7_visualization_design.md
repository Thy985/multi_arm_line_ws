# M6.7 Robot Runtime Visualization Layer — 设计文档

**日期**: 2026-08-09 (v2 — 根据架构评审反馈修订)
**阶段**: M6.7 Robot Runtime Observability Plane
**状态**: 设计完成(v2)，待实施

---

## 1. 定位与核心理念

### 1.1 不是UI，是Observability Plane

M6.7不是"做一个网页界面"，而是建立**Robot Runtime Observability Plane**——
类似Kubernetes Dashboard之于K8s，Prometheus之于微服务，OpenTelemetry之于分布式追踪。

**核心理念**:
```
Robot Runtime (M6.0-M6.5)
        |
        |  (所有运行时状态通过ROS2接口暴露)
        |
Visualization Layer (M6.7) — READ-ONLY
        |
 ┌───────┬───────────────┬───────────────────┐
 │ World │ Skill Timeline │ Episode Replay    │
 │ Model │ (Trace Viewer) │                   │
 │ Viewer│                │                   │
 └───────┴───────────────┴───────────────────┘
   Phase 2 (核心价值)        Phase 2 (核心价值)

 ┌───────┬───────────┐
 │ Robot │ Safety    │     Phase 3 (辅助)
 │ State │ Panel     │
 └───────┴───────────┘
```

### 1.2 只读原则（v2核心约束）

**M6.7是纯只读的Observability Plane，不包含任何控制能力。**

| 归属 | 能力 | 实现阶段 |
|------|------|----------|
| **Observability Plane (M6.7)** | 查询、展示、回放、监控 | 本阶段 |
| **Control Plane (未来 M7.x)** | execute skill, e-stop, release, submit_task_goals | 不在本阶段 |

控制命令（E-Stop、任务提交、Skill执行、资源释放）属于**Control Plane**，
将放到未来的M7.x Operator Console中实现。M6.7仅消费只读接口。

### 1.3 解决的问题

| 当前状态 | M6.7后 |
|---------|--------|
| 开发者看terminal logs | 可视化Dashboard实时展示 |
| "PASS"但不知道为什么成功 | Skill执行Trace展示决策链路 |
| 不知道机器人知道什么 | WorldModel Viewer展示认知状态 |
| 失败但不知道在哪里 | Episode回放定位失败点 |
| 无法交互查询 | Runtime Console即时只读查询 |

### 1.4 设计原则

1. **只读**: M6.7仅消费只读接口，不修改任何运行时状态
2. **零侵入**: 不修改任何现有M6.0-M6.5代码，纯消费已有接口
3. **实时+回放**: 实时监控 + Episode历史回放
4. **Interface Freeze遵守**: 仅使用M5.7冻结的v1.0接口
5. **无外部构建依赖**: Python后端 + 单页HTML前端，无需Node.js构建
6. **Trace优先**: Skill执行链路基于统一Trace模型，不单独维护时间线
7. **2D优先**: MVP阶段用2D Scene Graph，不做3D渲染（避免重新造RViz）

---

## 2. 架构设计

### 2.1 整体架构

```
┌─────────────────────────────────────────────────┐
│              Browser (单页HTML)                   │
│  ┌────────────┐ ┌────────────┐ ┌──────────────┐ │
│  │ WorldModel │ │  Skill     │ │  Episode     │ │
│  │  Viewer    │ │  Timeline  │ │  Replayer    │ │
│  │ (2D Scene) │ │ (Trace)    │ │              │ │
│  └────────────┘ └────────────┘ └──────────────┘ │
│  ┌────────────┐ ┌────────────┐ ┌──────────────┐ │
│  │ Robot State│ │ Safety     │ │ Runtime      │ │
│  │  Panel     │ │  Panel     │ │ Console(RO)  │ │
│  └────────────┘ └────────────┘ └──────────────┘ │
└────────────────────┬────────────────────────────┘
                     │ WebSocket (JSON)
                     │
┌────────────────────┴────────────────────────────┐
│           VizBridgeNode (ROS2 Node)               │
│                                                   │
│  ┌─────────────┐  ┌──────────────────────────┐  │
│  │DataCollector │  │WebSocketServer           │  │
│  │              │  │(tornado, port 8080)      │  │
│  │ Subscribes:  │  │                          │  │
│  │ /joint_states│  │ Broadcasts JSON:         │  │
│  │ /world_model │  │ {robot, world, safety,   │  │
│  │ /safety/*    │  │  traces, episodes}       │  │
│  │ /data/episode│  │                          │  │
│  │ /runtime/    │  │ REST endpoints (RO):     │  │
│  │   trace      │  │ GET /api/world           │  │
│  │              │  │ GET /api/skills          │  │
│  │ Queries(RO): │  │ GET /api/capability      │  │
│  │ /runtime/*   │  │ GET /api/episodes        │  │
│  │ /world_model │  │ GET /api/traces          │  │
│  │ /skill/*     │  │ GET /api/episode/:id     │  │
│  │ /experience  │  │ GET /api/trace/:id       │  │
│  └─────────────┘  └──────────────────────────┘  │
└───────────────────────────────────────────────────┘
                     │ ROS2
                     │
┌────────────────────┴────────────────────────────┐
│              M6 Runtime (现有)                    │
│  WorldModel | Coordinator | Safety | SkillRuntime │
│  Experience | Perception | Simulation             │
└───────────────────────────────────────────────────┘
```

### 2.2 技术选型

| 层 | 技术 | 理由 |
|----|------|------|
| 后端 | Python + tornado | ROS2生态原生，async WebSocket，无额外构建 |
| 前端 | 单页HTML + vanilla JS + CSS | 零构建依赖，CDN加载轻量库 |
| 2D可视化 | Canvas 2D / SVG | 轻量Scene Graph，无需3D库 |
| 图表 | Chart.js (CDN) | 时间线/趋势图 |
| 通信 | WebSocket + REST | 实时推送 + 按需查询 |

**注意**: MVP阶段不使用Three.js 3D渲染。3D View推迟到Phase 4，
当前用2D Scene Graph（俯视图+侧视图）替代。

### 2.3 数据流

**实时推送** (WebSocket, 10Hz):
```
/joint_states → DataCollector → {robot: {joints, velocities}} → WS broadcast
/world_model/state → DataCollector → {world: {objects, relations}} → WS broadcast
/safety/status → DataCollector → {safety: {level, e_stop, speed}} → WS broadcast
/safety/collision_events → DataCollector → {safety: {collision}} → WS broadcast
/data/episode → DataCollector → {episode: {latest}} → WS broadcast
/runtime/trace → DataCollector → {trace: {current}} → WS broadcast
```

**按需查询** (REST — 全部只读):
```
GET /api/world → QueryWorld srv → 完整世界状态
GET /api/skills → ListSkills srv → 已注册Skill列表
GET /api/capability → GetCapability srv → 三层能力信息
GET /api/episodes → QueryExperience srv → 历史Episode列表
GET /api/episode/:id → Episode详情(JSON)
GET /api/traces → Trace列表(JSON)
GET /api/trace/:id → Trace详情(JSON)
```

---

## 3. Trace模型设计（v2新增）

### 3.1 为什么需要Trace模型

Skill Timeline不应单独维护事件列表，而应基于统一的**Trace模型**实现。
类似OpenTelemetry在分布式系统中的角色，Trace模型为机器人任务执行提供
**结构化的可观测性数据**。

| 方案 | 优点 | 缺点 |
|------|------|------|
| 单独维护Skill事件列表 | 简单 | 数据碎片化，无法关联Episode |
| **统一Trace模型** | 结构化、可关联、可回放 | 需设计Trace数据结构 |

### 3.2 Trace数据结构

```python
@dataclass
class TraceEvent:
    """单个Trace事件，类似OpenTelemetry Span Event."""
    timestamp: float
    event_type: str          # "task_received" | "skill_selected" |
                             # "precondition_check" | "safety_check" |
                             # "execute_start" | "execute_end" |
                             # "postcondition_check" | "recovery" |
                             # "success" | "failure"
    name: str                # 事件名称
    details: dict[str, Any]  # 事件详情（结构化）
    success: bool | None     # None=进行中, True=成功, False=失败

@dataclass
class Trace:
    """完整任务执行Trace，类似OpenTelemetry Trace."""
    trace_id: str            # 唯一标识 (UUID)
    parent_trace_id: str     # 父Trace (用于子任务)
    task_type: str           # "pick_place" | "assembly" | ...
    skill_name: str          # 选择的Skill
    robot_id: str            # 执行的机器人
    start_time: float
    end_time: float | None   # None=进行中
    status: str              # "running" | "success" | "failure" | "aborted"
    events: list[TraceEvent] # 有序事件列表
    recovery_count: int
    metadata: dict[str, Any] # 自定义元数据
```

### 3.3 Trace与Episode的关系

```
Episode (M6.4已实现)
  ├── execution_steps: [SkillTraceStep]  ← 已有步骤记录
  ├── recovery: [RecoveryRecord]         ← 已有恢复记录
  └── result, duration, timestamp        ← 已有元数据

Trace (M6.7新增)
  ├── events: [TraceEvent]               ← 更细粒度事件
  ├── trace_id ↔ episode_id             ← 双向关联
  └── parent_trace_id                   ← 支持子任务嵌套
```

**映射关系**: Episode是数据持久化层（SQLite），Trace是可观测性展示层。
一个Episode对应一个Trace，Trace的events从Episode的execution_steps +
recovery records + 额外的决策事件（skill选择、precondition检查等）构建。

### 3.4 Trace构建流程

```
任务执行
 ↓
ExperienceRecorder.record_step()  (M6.4已实现)
 ↓ 同时
TraceCollector.record_event()     (M6.7新增)
 ↓
Trace构建: task_received → skill_selected →
  precondition_check → safety_check →
  execute_start → execute_end →
  postcondition_check → success/failure
 ↓
Trace发布到 /runtime/trace (ROS2 topic)
 ↓
DataCollector订阅 → WebSocket → Skill Timeline前端
```

### 3.5 Trace不持久化

MVP阶段Trace是**实时流式数据**，不单独持久化。
历史Trace通过Episode回放重建（从Episode的execution_steps构建Trace events）。

未来如需Trace持久化，可扩展ExperienceRecorder将Trace events写入SQLite。

---

## 4. 模块设计

### 4.1 包结构

```
multi_arm_visualization/
├── multi_arm_visualization/
│   ├── viz_bridge_node.py          # ROS2节点 + WebSocket服务器
│   ├── data_collector.py            # ROS2数据聚合器
│   ├── trace_collector.py           # Trace收集器(构建Trace模型)
│   ├── trace_model.py               # Trace + TraceEvent数据结构
│   ├── episode_replay.py            # Episode回放引擎(重建Trace)
│   └── web_server.py                # HTTP/WebSocket服务器
├── web/
│   ├── index.html                   # 主页面(单页应用)
│   ├── css/
│   │   └── style.css                # 样式
│   └── js/
│       ├── app.js                   # 主逻辑
│       ├── world_model_viewer.js    # WorldModel查看器(2D Scene Graph)
│       ├── skill_timeline.js        # Skill执行时间线(基于Trace)
│       ├── episode_replayer.js      # Episode回放器
│       ├── robot_state.js           # 机器人状态面板(Phase 3)
│       ├── safety_panel.js          # 安全状态面板(Phase 3)
│       ├── runtime_console.js       # 只读查询控制台
│       └── scene_graph.js           # 2D Scene Graph渲染
├── launch/
│   └── visualization.launch.py      # 启动可视化
├── test/
│   ├── test_viz_bridge.py           # 桥接节点测试
│   ├── test_web_server.py           # Web服务器测试
│   ├── test_trace_model.py          # Trace模型测试
│   └── test_data_collector.py       # 数据收集器测试
├── package.xml
└── setup.py
```

### 4.2 VizBridgeNode

**职责**: ROS2数据聚合 + Trace收集 + WebSocket广播 + REST API (只读)

```python
class VizBridgeNode(Node):
    """Robot Runtime Visualization Bridge (READ-ONLY).

    Subscribes to all M6 runtime topics, collects traces,
    and broadcasts to web clients via WebSocket.
    Does NOT provide any control capabilities.
    """

    def __init__(self):
        super().__init__("viz_bridge")
        self._collector = DataCollector(self)
        self._trace_collector = TraceCollector(self)
        self._server = WebServer(
            self._collector, self._trace_collector, port=8080
        )

    # 订阅的topics (全部只读):
    # /joint_states → 机器人关节状态
    # /world_model/state → 世界模型状态
    # /safety/status → 安全状态
    # /safety/collision_events → 碰撞事件
    # /data/episode → Episode数据
    # /perception/object_poses → 感知输出
    # /runtime/trace → Trace事件流

    # 查询的services (全部只读):
    # /runtime/query_world → 完整世界状态
    # /runtime/list_skills → Skill列表
    # /runtime/get_capability → 能力信息
    # /runtime/query_experience → Episode历史
    # /safety/safety_check → 安全状态查询(只读)
```

### 4.3 DataCollector

**职责**: 收集所有ROS2数据，维护当前状态快照

```python
class DataCollector:
    """Aggregates all M6 runtime data into a single snapshot."""

    def __init__(self, node):
        self._robot_state = {}      # {arm1: {joints, velocities, state}}
        self._world_state = {}      # {objects, relations, scene}
        self._safety_state = {}     # {level, e_stop, speed_scale, collisions}
        self._episodes = []         # [EpisodeData] 最近N个
        self._perception = {}       # {object_id: ObjectPose}

    def get_snapshot(self) -> dict:
        """Get complete runtime snapshot for WebSocket broadcast."""
        return {
            "timestamp": time.time(),
            "robot": self._robot_state,
            "world": self._world_state,
            "safety": self._safety_state,
            "episodes": self._episodes[-10:],
            "perception": self._perception,
        }
```

### 4.4 TraceCollector

**职责**: 从ROS2事件流构建Trace模型

```python
class TraceCollector:
    """Builds Trace models from runtime event stream."""

    def __init__(self, node):
        self._active_traces: dict[str, Trace] = {}  # trace_id → Trace
        self._completed_traces: list[Trace] = []     # 最近N个完成的

    def on_episode_data(self, msg: EpisodeData):
        """Build Trace from EpisodeData message."""
        trace = self._build_trace_from_episode(msg)
        self._completed_traces.append(trace)

    def get_current_trace(self) -> Trace | None:
        """Get currently running trace for real-time display."""
        if not self._active_traces:
            return None
        return next(iter(self._active_traces.values()))

    def get_trace_history(self, limit: int = 20) -> list[Trace]:
        """Get recent completed traces."""
        return self._completed_traces[-limit:]

    def _build_trace_from_episode(self, msg: EpisodeData) -> Trace:
        """Convert EpisodeData.msg → Trace with events."""
        events = []
        for step in msg.execution_steps:
            events.append(TraceEvent(
                timestamp=step.timestamp,
                event_type="execute_step",
                name=step.step_name,
                details=step.details,
                success=step.success,
            ))
        return Trace(
            trace_id=msg.episode_id,
            parent_trace_id="",
            task_type=msg.task_type,
            skill_name=msg.skill_name,
            robot_id=msg.robot_id,
            start_time=msg.timestamp,
            end_time=msg.timestamp + msg.duration,
            status=msg.result,
            events=events,
            recovery_count=msg.recovery_count,
            metadata={},
        )
```

### 4.5 WebServer

**职责**: HTTP静态文件服务 + WebSocket实时推送 + REST API (只读)

```python
class WebServer:
    """HTTP + WebSocket server for READ-ONLY visualization."""

    def __init__(self, collector, trace_collector, port=8080):
        self._collector = collector
        self._trace_collector = trace_collector
        self._app = tornado.web.Application([
            (r"/", MainHandler),
            (r"/ws", WebSocketHandler),
            # REST API — 全部只读 (GET only)
            (r"/api/world", WorldApiHandler),
            (r"/api/skills", SkillsApiHandler),
            (r"/api/capability", CapabilityApiHandler),
            (r"/api/episodes", EpisodesApiHandler),
            (r"/api/episode/(.+)", EpisodeDetailHandler),
            (r"/api/traces", TracesApiHandler),
            (r"/api/trace/(.+)", TraceDetailHandler),
            (r"/js/(.*)", StaticHandler),
            (r"/css/(.*)", StaticHandler),
        ])
```

---

## 5. 前端模块设计

### 5.1 WorldModel Viewer（Phase 2 — 核心价值）

**展示**: 机器人认知状态——Digital Twin Explorer

```
┌─── WorldModel Viewer ────────────────────────────────┐
│                                                      │
│  📦 Objects                                          │
│  ├── red_cube                                        │
│  │   ├── position: [0.42, 0.15, 0.05]               │
│  │   ├── orientation: [0, 0, 0, 1]                  │
│  │   ├── type: cube                                  │
│  │   ├── grasp_state: FREE                          │
│  │   ├── attached_to: (none)                        │
│  │   └── confidence: 0.94                           │
│  ├── blue_cylinder                                   │
│  │   ├── position: [0.30, -0.20, 0.10]              │
│  │   ├── grasp_state: ATTACHED                      │
│  │   ├── attached_to: arm1                          │
│  │   └── confidence: 0.88                           │
│  └── table                                           │
│                                                      │
│  🔗 Relations                                        │
│  ├── red_cube ON table (conf=0.95)                  │
│  ├── blue_cylinder ATTACHED_TO arm1 (conf=1.0)     │
│  └── arm1 NEAR red_cube (dist=0.12m)               │
│                                                      │
│  🎯 Task Context                                     │
│  ├── current_task: pick_place                        │
│  ├── progress: 60%                                   │
│  └── target: red_cube → zone_b                      │
│                                                      │
│  [2D Scene Graph — 俯视图]                           │
│  ┌─────────────────────────────┐                    │
│  │         zone_a    zone_b     │                    │
│  │      ┌──┐                   │                    │
│  │      │■│ red_cube           │                    │
│  │      └──┘     ● arm1        │                    │
│  │           ○ blue_cyl         │                    │
│  │  ────────── table ──────── │                    │
│  └─────────────────────────────┘                    │
│                                                      │
└──────────────────────────────────────────────────────┘
```

**数据源**: `/world_model/state` (实时) + `/runtime/query_world` (按需完整查询)

**2D Scene Graph**: 用Canvas 2D绘制俯视图，展示物体位置、机器人位置、
关系连线。不做3D渲染（避免重新造RViz）。

### 5.2 Skill Execution Timeline（Phase 2 — 核心价值，基于Trace）

**展示**: Skill执行决策链路——基于Trace模型的可解释性

```
┌─── Skill Execution Timeline (Trace) ─────────────────┐
│                                                        │
│  Trace: episode_00003    Status: SUCCESS  ⏮ ▶ ⏭     │
│  Task: pick_place  Duration: 7.44s  Recovery: 0      │
│                                                        │
│  Timeline: ────●──────────────────────────            │
│           t=0      t=3.7s        t=7.4s               │
│                                                        │
│  ┌── Events ──────────────────────────────────────┐  │
│  │                                                 │  │
│  │  10:01:22  task_received                        │  │
│  │  │ task_type: pick_place                        │  │
│  │  │ target: red_cube → zone_b                    │  │
│  │  ↓                                              │  │
│  │  10:01:23  skill_selected                       │  │
│  │  │ reason:                                     │  │
│  │  │   capability: ✓ manip ✓ grip ✓ vision       │  │
│  │  │   cost: 5.2s  success_rate: 0.87             │  │
│  │  ↓                                              │  │
│  │  10:01:24  precondition_check                  │  │
│  │  │ ✓ object red_cube exists (conf=0.94)        │  │
│  │  │ ✓ arm1 is IDLE                               │  │
│  │  │ ✓ no collision in path                       │  │
│  │  ↓                                              │  │
│  │  10:01:25  safety_check                         │  │
│  │  │ ✓ approved (speed_scale=1.0)                │  │
│  │  ↓                                              │  │
│  │  10:01:26  execute_start: grasp                │  │
│  │  ↓                                              │  │
│  │  10:01:29  execute_end: grasp                  │  │
│  │  │ duration: 2.3s                               │  │
│  │  ↓                                              │  │
│  │  10:01:30  postcondition_check                 │  │
│  │  │ ✓ object attached to arm1                   │  │
│  │  ↓                                              │  │
│  │  10:01:30  success                             │  │
│  │                                                 │  │
│  └─────────────────────────────────────────────────┘  │
│                                                        │
└────────────────────────────────────────────────────────┘
```

**数据源**: Trace模型 (实时: `/runtime/trace` + 历史: 从Episode重建)

**实现**: 前端`skill_timeline.js`消费Trace JSON，渲染events列表。
不单独维护事件列表，全部从Trace模型获取。

### 5.3 Episode Replayer（Phase 2 — 核心价值）

**展示**: 历史Episode回放——类似自动驾驶数据回放

```
┌─── Episode Replay ────────────────────────────────────┐
│                                                        │
│  Episode: episode_00003    Result: SUCCESS  ⏮ ▶ ⏭   │
│  Task: pick_place  Duration: 7.44s                    │
│                                                        │
│  Timeline: ────●──────────────────────────            │
│           t=0      t=3.7s        t=7.4s               │
│                                                        │
│  ┌── t = 3.7s ────────────────────────────────────┐  │
│  │                                                │  │
│  │  Step: execution (grasp)                       │  │
│  │  Duration: 2.3s                                │  │
│  │  Success: true                                 │  │
│  │                                                │  │
│  │  World State (initial):                        │  │
│  │  ├── red_cube: [0.42, 0.15, 0.05] FREE        │  │
│  │  └── blue_cylinder: [0.30, -0.2, 0.1] FREE    │  │
│  │                                                │  │
│  │  World State (final):                         │  │
│  │  ├── red_cube: [0.42, 0.15, 0.05] ATTACHED    │  │
│  │  └── blue_cylinder: [0.30, -0.2, 0.1] FREE    │  │
│  │                                                │  │
│  │  Recovery: none                                │  │
│  │                                                │  │
│  └────────────────────────────────────────────────┘  │
│                                                        │
│  Episode List:                                        │
│  ├── episode_00001  pick_place  ✅  7.24s            │
│  ├── episode_00002  pick_place  ❌  7.21s            │
│  └── episode_00003  pick_place  ✅  7.44s ←          │
│                                                        │
└────────────────────────────────────────────────────────┘
```

**数据源**: `/runtime/query_experience` + SQLite dataset

**与Trace的关系**: Episode回放时，从execution_steps重建Trace events，
复用Skill Timeline的渲染逻辑。

### 5.4 Robot State Panel（Phase 3 — 辅助）

**展示**: 机器人实时状态

```
┌─── Robot State ───────────────────────┐
│                                       │
│  arm1                    arm2         │
│  ┌─────────────┐        ┌─────────┐  │
│  │ joint1  35° │        │ ...     │  │
│  │ joint2 -20° │        │         │  │
│  │ joint3  80° │        │         │  │
│  │ joint4   0° │        │         │  │
│  │ joint5  45° │        │         │  │
│  │ joint6  10° │        │         │  │
│  └─────────────┘        └─────────┘  │
│                                       │
│  Controller: ACTIVE     State: IDLE   │
│  Gripper: OPEN           E-Stop: OFF  │
│                                       │
│  [2D Scene Graph — 侧视图]            │
│                                       │
└───────────────────────────────────────┘
```

**数据源**: `/joint_states` (实时WebSocket)

### 5.5 Safety Panel（Phase 3 — 辅助，只读）

**展示**: 安全状态实时监控（只读，无控制按钮）

```
┌─── Safety Plane (Read-Only) ──────┐
│                                    │
│  Safety Level: NORMAL  🟢         │
│  E-Stop: INACTIVE                  │
│  Speed Scale: 1.00                 │
│                                    │
│  Collision Monitor:                │
│  ├── arm1 ↔ arm2: 1.02m ✅        │
│  ├── arm1 ↔ table: 0.45m ✅       │
│  └── arm2 ↔ table: 0.38m ✅       │
│                                    │
│  Recent Events:                    │
│  ├── 10:01:15 proximity_warning    │
│  │   arm1 ↔ arm2 (0.08m)          │
│  └── 10:00:42 collision_detected   │
│      arm1 ↔ obstacle              │
│                                    │
│  (控制按钮已移除 — 属于Control     │
│   Plane, 见未来M7.x Operator       │
│   Console)                         │
│                                    │
└────────────────────────────────────┘
```

**数据源**: `/safety/status` + `/safety/collision_events`

### 5.6 Runtime Console（只读查询）

**展示**: 交互式只读查询控制台

```
┌─── Runtime Console (Read-Only) ───────────────────────┐
│                                                        │
│  > query robot capability                             │
│  {                                                    │
│    "manipulation": true,                              │
│    "vision": true,                                    │
│    "gripper": true,                                   │
│    "navigation": false                                │
│  }                                                    │
│                                                        │
│  > list skills                                        │
│  pick_object    v1.0  cost=5.2s  success=0.87         │
│  place_object   v1.0  cost=3.8s  success=0.92         │
│  move_object    v1.0  cost=4.1s  success=0.95         │
│                                                        │
│  > query world red_cube                               │
│  {                                                    │
│    "object_id": "red_cube",                           │
│    "type": "cube",                                    │
│    "position": [0.42, 0.15, 0.05],                   │
│    "grasp_state": "FREE",                             │
│    "attached_to": "",                                 │
│    "confidence": 0.94                                 │
│  }                                                    │
│                                                        │
│  > query episodes --failures-only                     │
│  episode_00002  pick_place  recovery_failed  7.21s   │
│                                                        │
│  > query traces --recent 5                            │
│  trace_00003  pick_place  success  7.44s  9 events   │
│  trace_00002  pick_place  failure  7.21s  12 events  │
│                                                        │
│  > _                                                   │
│                                                        │
│  (只读查询 — 控制命令已移至Control Plane)             │
│                                                        │
└────────────────────────────────────────────────────────┘
```

**命令映射** (全部只读):
| 命令 | 后端Service | 说明 |
|------|------------|------|
| `query robot capability` | `/runtime/get_capability` | 三层能力查询 |
| `list skills` | `/runtime/list_skills` | 已注册Skill列表 |
| `query world [object_id]` | `/runtime/query_world` | 世界状态查询 |
| `query episodes [--failures-only]` | `/runtime/query_experience` | Episode历史 |
| `query traces [--recent N]` | TraceCollector | Trace历史 |
| `safety status` | `/safety/safety_check` | 安全状态查询(只读) |

**已移除的命令** (属于Control Plane):
| 命令 | 原后端 | 移除原因 |
|------|--------|----------|
| `execute skill <name>` | `/runtime/submit_task_goals` | 控制能力 |
| `e-stop` | `/safety/emergency_stop` | 控制能力 |
| `release` | `/safety/emergency_stop` | 控制能力 |

---

## 6. 接口依赖

### 6.1 消费的ROS2接口（全部只读，M5.7 FROZEN v1.0）

**Topics (订阅)**:
| Topic | Type | 频率 | 用途 |
|-------|------|------|------|
| `/joint_states` | `JointState` | 500Hz | 机器人关节状态 |
| `/world_model/state` | `ObjectPose` | 1Hz | 世界模型状态 |
| `/safety/status` | `ResourceStatus` | 1Hz | 安全状态 |
| `/safety/collision_events` | `CollisionEvent` | 事件 | 碰撞事件 |
| `/data/episode` | `EpisodeData` | 事件 | Episode数据 |
| `/perception/object_poses` | `ObjectPose` | 10Hz | 感知输出 |

**Services (客户端 — 全部只读)**:
| Service | Type | 用途 |
|---------|------|------|
| `/runtime/query_world` | `QueryWorld` | 完整世界状态查询 |
| `/runtime/list_skills` | `ListSkills` | Skill列表 |
| `/runtime/get_capability` | `GetCapability` | 能力查询 |
| `/runtime/query_experience` | `QueryExperience` | Episode历史 |
| `/safety/safety_check` | `SafetyCheck` | 安全状态查询(只读) |

**已排除的接口** (属于Control Plane):
| 接口 | 类型 | 排除原因 |
|------|------|----------|
| `/safety/emergency_stop` | Service | 控制能力，不属于Observability |
| `/runtime/submit_task_goals` | Action | 控制能力，不属于Observability |

### 6.2 新增接口

**无新增ROS2接口**。M6.7纯消费M5.7冻结接口。

Trace模型是M6.7内部数据结构，不定义新的ROS2 msg/srv/action。
Trace从已有的`EpisodeData.msg`构建。

### 6.3 新增依赖

| 依赖 | 用途 | package.xml |
|------|------|-------------|
| `tornado` | WebSocket + HTTP服务器 | `<exec_depend>python-tornado</exec_depend>` |
| `multi_arm_interfaces` | ROS2接口 | `<depend>multi_arm_interfaces</depend>` |
| `multi_arm_runtime_api` | Runtime API | `<exec_depend>multi_arm_runtime_api</exec_depend>` |

---

## 7. 验收标准

### 7.1 功能验收

| 验收项 | Phase | 通过条件 |
|--------|-------|----------|
| VizBridgeNode启动 | 1 | 节点启动 + WebSocket服务器监听8080 |
| Runtime Snapshot | 1 | DataCollector聚合所有topic数据 |
| WorldModel Viewer | 2 | 显示物体+关系+任务上下文+2D Scene Graph |
| Skill Timeline | 2 | 基于Trace模型显示Skill执行决策链路 |
| Episode Replayer | 2 | 回放历史Episode(step-by-step) |
| Robot State Panel | 3 | 实时显示关节状态(10Hz更新) |
| Safety Panel | 3 | 显示安全状态+碰撞事件(只读) |
| Runtime Console | 2 | 只读查询(capability/skills/world/episodes/traces) |
| Web界面可访问 | 2 | 浏览器访问 http://localhost:8080 |

### 7.2 测试验收

| 测试 | 通过条件 |
|------|----------|
| test_viz_bridge | VizBridgeNode启动 + 数据收集 |
| test_web_server | HTTP + WebSocket服务可用 |
| test_data_collector | 所有topic订阅 + 数据聚合 |
| test_trace_model | Trace构建 + Event映射 + Episode关联 |
| test_episode_replay | Episode回放 + Trace重建 |

---

## 8. 实施计划

### Phase 0: 接口验证

验证所有依赖的ROS2接口可用，确认数据格式。

1. 编写接口探测脚本，验证所有topic/service可连接
2. 确认数据结构（ObjectState, Relation, EpisodeData等字段）
3. 确认Trace可从EpisodeData构建

### Phase 1: Runtime Snapshot（后端基础，不用Web）

实现数据收集核心，不依赖Web前端。

4. 创建`multi_arm_visualization`包
5. 实现`DataCollector`（订阅所有topic，聚合状态）
6. 实现`trace_model.py`（Trace + TraceEvent数据结构）
7. 实现`TraceCollector`（从EpisodeData构建Trace）
8. 实现`VizBridgeNode`（ROS2节点入口）
9. 单元测试：DataCollector + TraceModel + TraceCollector

### Phase 2: Web Dashboard（核心价值面板）

实现三个高价值面板：WorldModel Viewer + Skill Timeline + Episode Replay。

10. 实现`WebServer`（tornado HTTP + WebSocket）
11. `index.html`主页面布局
12. `world_model_viewer.js` — WorldModel查看器 + 2D Scene Graph
13. `skill_timeline.js` — Skill时间线(基于Trace模型)
14. `episode_replayer.js` — Episode回放器
15. `runtime_console.js` — 只读查询控制台
16. REST API端点（全部GET，只读）
17. 集成测试：Web Dashboard端到端

### Phase 3: 辅助面板（Robot State + Safety）

实现降优先级的辅助面板。

18. `robot_state.js` — 机器人状态面板
19. `safety_panel.js` — 安全状态面板(只读，无控制按钮)
20. 集成测试：辅助面板

### Phase 4: 3D View（未来，不在当前MVP范围）

3D可视化推迟到未来阶段，当前用2D Scene Graph替代。

21. Three.js 3D机器人渲染（俯视/侧视/自由视角）
22. 3D Scene Graph（物体3D模型展示）

**注意**: Phase 4不在当前M6.7 MVP范围内。3D渲染价值有限且
与RViz功能重叠，优先确保2D Scene Graph + Trace + Episode回放的
核心可观测性能力。

---

## 9. 与现有架构的关系

```
L7  应用层        PickPlace / Assembly / Inspection
L6  任务规划层    TaskManager + BehaviorTree.CPP
L5  环境模型层    WorldModel (Objects / Robots / Environment)
L4  协调层        ResourceManager + Scheduler + Coordinator
L3  运动规划层    MoveIt2 + IK + Collision + Trajectory
L2  控制层        ros2_control + JTC + GripperController
L1  硬件层        Gazebo / UR Driver / Sensors

══ Safety Plane (横切) ══
══ System Services (横向) ══
══ Visualization Plane (M6.7, 横切, READ-ONLY) ══    ← NEW
    Diagnostics + StructuredLogger + Benchmark + Recovery
    + Visualization (M6.7)
```

M6.7是**横切平面**，类似Safety Plane，贯穿L1-L7所有层，**只读**消费所有运行时状态。

---

## 10. 关键设计决策

### 10.1 为什么是只读的Observability Plane?

| 方案 | 优点 | 缺点 |
|------|------|------|
| 可读可写(含控制) | 一个界面完成所有操作 | 职责混合，安全风险 |
| **纯只读Observability** | 职责清晰，安全无风险 | 控制需单独的Operator Console |

选择纯只读：Observability和Control是两个不同的关注点。
控制能力（E-Stop、任务提交）属于Control Plane，放到未来M7.x Operator Console。
M6.7专注于"看见"而非"操作"。

### 10.2 为什么用Trace模型而非单独事件列表?

| 方案 | 优点 | 缺点 |
|------|------|------|
| 单独Skill事件列表 | 简单 | 数据碎片化，无法关联Episode |
| **统一Trace模型** | 结构化、可关联Episode、可回放 | 需设计数据结构 |

选择Trace模型：类似OpenTelemetry，Trace提供结构化的执行链路可观测性。
Trace从已有的EpisodeData构建，不增加持久化负担，且支持历史回放。

### 10.3 为什么MVP用2D而非3D?

| 方案 | 优点 | 缺点 |
|------|------|------|
| Three.js 3D | 直观，沉浸感 | 重，与RViz重叠，开发成本高 |
| **2D Scene Graph** | 轻量，快速实现，不重叠 | 不如3D直观 |

选择2D：MVP阶段核心价值是Runtime Observability（WorldModel认知状态、
Skill决策链路、Episode回放），而非3D运动可视化（RViz已覆盖）。
3D View推迟到Phase 4，优先确保核心可观测性能力。

### 10.4 为什么不用rosbridge_suite?

| 方案 | 优点 | 缺点 |
|------|------|------|
| rosbridge_suite | 成熟，通用 | 重，全话题暴露，无业务逻辑聚合 |
| **自建VizBridge** | 轻，按需聚合，业务语义 | 需自己实现WebSocket |

选择自建：需要业务语义聚合（WorldModel Viewer不是简单topic镜像），且避免额外依赖。

### 10.5 为什么不用React构建?

| 方案 | 优点 | 缺点 |
|------|------|------|
| React + Node.js | 组件化，生态丰富 | 需Node.js构建，增加CI复杂度 |
| **单页HTML + vanilla JS** | 零构建，CDN加载 | 无组件化(用Custom Elements替代) |

选择单页HTML：项目是Python-first，不引入Node.js构建链。用ES6 Custom Elements实现组件化。

### 10.6 为什么用tornado?

| 方案 | 优点 | 缺点 |
|------|------|------|
| **tornado** | async, 轻量, pip安装 | 需额外pip依赖 |
| aiohttp | async, 现代 | 需额外pip依赖 |
| Flask + flask-socketio | 简单 | 同步模型，不适合实时推送 |

选择tornado：async WebSocket原生支持，轻量，ROS2生态常用。

---

## 11. 风险与缓解

| 风险 | 缓解 |
|------|------|
| tornado未安装 | setup.py声明依赖 + 降级到HTTP polling |
| 浏览器兼容性 | 目标Chrome/Edge, ES6+ |
| 高频数据过载 | DataCollector降采样(10Hz) + WebSocket批量 |
| 安全性(远程访问) | 默认localhost-only + 可配置 |
| 与RViz功能重叠 | 定位不同: RViz=3D运动, Viz=Runtime Observability |
| Trace数据量大 | MVP不持久化Trace，实时流式 + 从Episode重建历史 |
| 2D不够直观 | Phase 4可扩展3D，MVP优先核心可观测性 |

---

## 12. M6.6重新定义（v2调整）

### 原M6.6: Mobile Base → 推迟到M7

移动底盘（Navigation2 + SLAM）复杂度高，且属于**Navigation Capability**，
不属于Robot Runtime Platform。推迟到M7 Navigation Capability阶段。

### M6.6重新定义: Runtime Integration

M6.6可重新定义为**Runtime Integration** — 将M6.0-M6.5 + M6.7整合为
完整的Robot Runtime Platform，验证全栈协同工作。

| 验收项 | 通过条件 |
|--------|----------|
| 全栈启动 | M6.0-M6.5 + M6.7一键启动 |
| 端到端验证 | 任务提交→执行→可视化展示→Episode记录 |
| Observability验证 | Web Dashboard实时展示所有运行时状态 |
| 集成测试 | 全栈集成测试通过 |

**注意**: L6 Simulation E2E已部分验证了全栈协同（Phase 1-5），
M6.6 Runtime Integration将在此基础上增加M6.7可视化层的集成验证。
