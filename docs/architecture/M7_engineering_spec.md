# M7 Embodied Manipulation Platform — 工程落地与验收标准

**版本**: v3.0 (最终版)
**日期**: 2026-08-10
**前置**: M6全部完成 (434+ tests, 18 packages), ADR-M6-Freeze ACCEPTED
**设计依据**: `docs/architecture/robot_body_upgrade_design.md` v3.0
**治理依据**: `docs/architecture/ADR-M6-Freeze.md` — M6接口冻结v1.0
**评审**: 五轮架构评审

---

## 0. 治理基线

**M6接口已冻结** (ADR-M6-Freeze v1.0):

| Tier | 接口数 | 规则 |
|------|--------|------|
| Tier 1 永不可破坏 | 13 | 字段类型/名称/语义不可变 |
| Tier 2 可扩展不可破坏 | 8 | 可追加可选字段, 已有字段不可变 |
| Tier 3 Runtime API契约 | 7 | 可新增命令, 已有命令语义不变 |
| Tier 4 架构约束 | 5 | Coordinator不膨胀/Safety独立/WorldModel真相源/跨包走接口/YAML驱动 |

**M7原则**: 扩展优先，修改最后。优先通过Tier 2追加可选字段实现需求。

---

## 1. 架构层次

```
                Agent Layer (M7.5+)
                     |
              Task Planner (M6, FROZEN)
                     |
           Capability Graph (M7.0.3, 声明层非规划器)
                     |
              Skill Runtime (M6, FROZEN)
                     |
        -------------------------
        |                       |
   World Model (M7.0.2)    Experience (M6, FROZEN)
        |
  Perception / Simulation (M7.2/M7.4)
        |
   Robot Description (M7.0.1/M7.1)
        |
  Physical Robot (Gazebo)

  ══ Safety Plane (M7.S, 横切) ══
  ══ Evaluation (M7.E, 横切) ══
```

**Capability Graph边界**: 是能力**声明层**，不是任务规划器。不自己造PDDL。

```
Task Planner → 拆任务 → Capability Graph → 检查能力 → Skill Runtime → 执行
```

---

## 2. 最终路线

```
M7.0 Foundation (拆为4个子阶段)
  ├── M7.0.1 Robot Description Refactor
  ├── M7.0.2 WorldModel Schema (含时间维度)
  ├── M7.0.3 Capability Graph (声明层)
  └── M7.0.4 Base Interface (契约定义)

M7.2 Scene Asset System
  └── M7.3 Task Benchmark
       └── M7.E Evaluation Infrastructure
            └── M7.4 Vision Grounding (含Calibration)
                 └── M7.1 Body Upgrade
                      └── M7.5 Skill Evolution (非Learning)
                           └── M7.6 Mobile Navigation

M7.S Safety Layer (横切, 贯穿所有阶段)
```

### 优先级理由

| 排序 | 理由 |
|------|------|
| M7.2 > M7.1 | 环境×任务×数据 >> 机器人外观 |
| M7.3 > M7.1 | 没有benchmark不知道机器人是否变强 |
| M7.E > M7.4 | Evaluation是Vision的验收基础 |
| M7.4 > M7.1 | Vision Grounding比躯干外观更有价值 |
| M7.1 > M7.5 | Body为Skill Evolution提供物理基础 |
| M7.5改名 | Episode→Analysis→Parameter Adjustment是Evolution不是Learning |

---

## 3. 总览

| 阶段 | 名称 | 新增测试 | 验收项 | 依赖 |
|------|------|----------|--------|------|
| M7.0.1 | Robot Description Refactor | 8 | 6 | M6 |
| M7.0.2 | WorldModel Schema | 5 | 4 | M6 |
| M7.0.3 | Capability Graph | 4 | 3 | M6 |
| M7.0.4 | Base Interface | 3 | 3 | M6 |
| M7.2 | Scene Asset System | 10 | 8 | M7.0 |
| M7.3 | Task Benchmark | 8 | 6 | M7.2 |
| M7.E | Evaluation Infrastructure | 6 | 5 | M7.3 |
| M7.4 | Vision Grounding | 10 | 8 | M7.E, M7.0 |
| M7.1 | Body Upgrade | 12 | 10 | M7.0 |
| M7.5 | Skill Evolution | 10 | 8 | M7.4, M7.1 |
| M7.6 | Mobile Navigation | 6 | 5 | M7.5 |
| M7.S | Safety Layer | 6 | 5 | M7.0 |

**总计**: 新增88 tests, 71验收项, 1新包

---

## M7.0 Foundation Layer (4个子阶段)

### M7.0.1 Robot Description Refactor

**范围**: URDF从单文件拆分为模块化xacro。

**交付物**:
- `urdf/robot.xacro` (顶层组装)
- `urdf/body/`, `urdf/arms/`, `urdf/sensors/`, `urdf/mobile_base/` (模块目录)
- `urdf/multi_arm_robot.xacro` (向后兼容wrapper)

**验收标准**:

| # | 验收项 | 通过条件 | 验证方法 |
|---|--------|----------|----------|
| 1 | 模块化目录 | body/arms/sensors/mobile_base/存在 | `ls` |
| 2 | 顶层组装 | `xacro robot.xacro`无错误 | exit 0 |
| 3 | 向后兼容 | wrapper输出与robot.xacro一致 | diff为空 |
| 4 | link/joint不变 | 拆分后数量不变 | grep count |
| 5 | 构建通过 | colcon build成功 | exit 0 |
| 6 | 现有测试不回归 | 全部通过 | 0 failures |

### M7.0.2 WorldModel Schema

**范围**: WorldModel 5层schema定义，含**时间维度**。

**关键**: 世界不是数据库，是不断过期的信息流。

**交付物**:
- `multi_arm_interfaces/msg/ObjectState.msg` 修改 (+confidence +uncertainty +source +timestamp +ttl)
- `multi_arm_robot_description/config/world_model_schema.yaml` 新增

**Schema**:
```yaml
layers:
  entities:
    fields: [id, type, pose, bbox]
  states:
    fields: [grasp_state, attached_to, moving]
  relations:
    types: [on, near, inside, attached, above, below]
  uncertainty:
    fields: [confidence, uncertainty_std, source, last_seen]
  history:
    fields: [seen_time, moved_time, state_changes]
  temporal:              # 新增: 时间维度
    fields: [observed_at, updated_at, frame_id, ttl]
    ttl_default: 5.0     # 信息5秒后过期
```

**验收标准**:

| # | 验收项 | 通过条件 | 验证方法 |
|---|--------|----------|----------|
| 1 | 5层schema | entities/states/relations/uncertainty/history | yaml检查 |
| 2 | 时间维度 | ObjectState含observed_at/updated_at/ttl | `ros2 interface show` |
| 3 | Tier 2扩展 | 仅追加可选字段, M6字段不变 | 接口对比 |
| 4 | TTL机制 | 超过ttl的对象标记expired | 单元测试 |

### M7.0.3 Capability Graph

**范围**: 能力声明层(非规划器)。描述"能做什么"，不负责"怎么做"。

**交付物**:
- `multi_arm_robot_description/config/capability_graph.yaml` 新增

**Schema**:
```yaml
hardware:              # 有什么
  arms: [ur5e, ur5e]
  grippers: [robotiq_2f_85, robotiq_2f_85]
  sensors: [rgbd_camera, wrist_camera, imu]

capabilities:         # 能做什么 (声明, 非规划)
  pick:
    requires: [gripper, arm, object_pose_perception]
    provides: [object_grasped]
    skill: grasp_v1
    cost: 2.5
  place:
    requires: [gripper, arm, target_pose, object_grasped]
    provides: [object_at_target]
    skill: place_v1
    cost: 2.0
```

**边界**: Task Planner负责拆任务，Capability Graph只负责检查`robot.can(pick)`，Skill Runtime负责执行。

**验收标准**:

| # | 验收项 | 通过条件 | 验证方法 |
|---|--------|----------|----------|
| 1 | Graph加载 | yaml含hardware/capabilities/requires/provides/cost | `yaml.safe_load` |
| 2 | 非规划器 | 不含task分解逻辑 | 代码检查 |
| 3 | `robot capability` | CLI输出能力列表 | CLI执行 |

### M7.0.4 Base Interface

**范围**: 移动底盘接口契约定义(实现后补M7.6)。

**交付物**:
- `multi_arm_interfaces/msg/BaseState.msg` 新增 (odom + velocity)
- 接口定义: cmd_vel, odom, tf

**验收标准**:

| # | 验收项 | 通过条件 | 验证方法 |
|---|--------|----------|----------|
| 1 | BaseState定义 | msg含odom/velocity字段 | `ros2 interface show` |
| 2 | cmd_vel契约 | /cmd_vel topic类型定义 | topic info |
| 3 | 轮子仍fixed | 接口定义但实现未到 | `xacro \| grep wheel.*fixed` |

### M7.0 Exit Criteria

- [ ] 全部子阶段验收通过
- [ ] 20/20新测试通过
- [ ] M6 Tier 1接口零修改
- [ ] M6 Tier 2仅追加可选字段

---

## M7.2 Scene Asset System

**范围**: 环境×物体×任务三层定义。

**交付物**: `simulation/scenes/` 目录 (environments/objects/tasks/)

**验收标准**:

| # | 验收项 | 通过条件 | 验证方法 |
|---|--------|----------|----------|
| 1 | 三层目录 | environments/objects/tasks/ | `ls` |
| 2 | ≥4环境 | tabletop/home/warehouse/lab | count |
| 3 | ≥3物体 | 含size/graspable | yaml检查 |
| 4 | ≥3任务 | 含precondition/postcondition | grep |
| 5 | tabletop迁移 | 与m6_test_world一致 | diff |
| 6 | CLI scene list | `robot scene list`≥4 | CLI |
| 7 | CLI sim start | `robot sim start <scene>` | 进程启动 |
| 8 | 场景切换 | 不同场景不同world | home≠tabletop |

---

## M7.3 Task Benchmark

**范围**: RobotBench标准化任务集 + Episode数据。

**验收标准**:

| # | 验收项 | 通过条件 | 验证方法 |
|---|--------|----------|----------|
| 1 | 3个task_set | 含scene+tasks+repetitions | yaml |
| 2 | Episode模型 | 含task/params/steps/outcome/failure_reason | 结构 |
| 3 | Benchmark执行 | `robot benchmark task_set_basic`完成 | exit 0 |
| 4 | 成功率统计 | success_rate/avg_duration/failure_breakdown | stdout |
| 5 | Episode记录 | SQLite持久化 | `robot episodes`非空 |
| 6 | 失败分析 | `robot analyze <id>`有内容 | CLI |

---

## M7.E Evaluation Infrastructure

**范围**: "怎么知道它变强？" — 横切评估层。

**交付物**:
- `multi_arm_tools/evaluator.py` 新增
- `multi_arm_tools/cli.py` 修改 (+`robot evaluate`)

**验收标准**:

| # | 验收项 | 通过条件 | 验证方法 |
|---|--------|----------|----------|
| 1 | 评估执行 | `robot evaluate`输出报告 | CLI |
| 2 | 任务成功率 | per-task success_rate | 报告检查 |
| 3 | 失败分解 | perception/planning/grasp/timeout占比 | 报告检查 |
| 4 | 趋势对比 | 与上次评估对比 | 报告检查 |
| 5 | 回归检测 | 性能退化标记 | 报告检查 |

**输出示例**:
```
=== Robot Evaluation Report ===

Task Success Rate: 85%
  pick_object:   90% (18/20)
  place_object:  80% (16/20)

Failure Breakdown:
  40% perception
  30% planning
  20% grasp
  10% timeout

Trend vs Last: +5% (improving)
```

---

## M7.4 Vision Grounding

**范围**: Stage B: GT+Vision并行 + Calibration + 主动感知。

**新增Calibration Layer**:

```
GT pose: Gazebo world frame
Vision pose: camera frame
中间需要: camera extrinsic transform (TF)
```

**验收标准**:

| # | 验收项 | 通过条件 | 验证方法 |
|---|--------|----------|----------|
| 1 | 相机数据 | head_camera topic有数据 | `ros2 topic hz` |
| 2 | 感知输出 | vision_pose+confidence | `ros2 topic echo` |
| 3 | Calibration | camera→world TF定义 | `ros2 run tf2_echo` |
| 4 | GT+Vision并行 | WorldModel同时有两种pose | source字段 |
| 5 | 误差计算 | gt vs vision误差 | `robot world`显示error |
| 6 | 低置信度 | confidence<0.8标记uncertain | 状态检查 |
| 7 | 主动感知 | 低置信度→neck转向→confidence↑ | E2E |
| 8 | CLI显示 | `robot world`显示confidence/source | stdout |

---

## M7.1 Body Upgrade

**范围**: 躯干+头部+传感器。控制器拆分: torso_controller ≠ head_controller(→未来Attention Controller)。

**验收标准**:

| # | 验收项 | 通过条件 | 验证方法 |
|---|--------|----------|----------|
| 1 | 躯干 | torso_yaw_joint(revolute Z) | xacro grep |
| 2 | 头部 | neck_pitch_joint(revolute Y) | xacro grep |
| 3 | 头部RGB-D | head_camera sensor type=rgbd | xacro grep |
| 4 | 躯干IMU | torso_imu (不在head) | xacro grep |
| 5 | 控制器拆分 | torso≠head独立 | grep |
| 6 | ros2_control | 16 joints | count |
| 7 | SRDF torso组 | 独立 | grep |
| 8 | SRDF无全身组 | 不存在arm1_full | grep -c = 0 |
| 9 | Gazebo启动 | 无错误 | `robot sim start` |
| 10 | 控制器active | torso+head在list中 | `ros2 control list` |

---

## M7.5 Skill Evolution

**范围**: Episode→FailureAnalysis→Skill参数调整。**不是机器学习**。

**命名**: "Evolution"而非"Learning"。真正的Learning(imitation/RL/diffusion)属M8。

**验收标准**:

| # | 验收项 | 通过条件 | 验证方法 |
|---|--------|----------|----------|
| 1 | 新Skill | pull/inspect/co_carry注册 | `robot skills` |
| 2 | 依赖检查 | requires检查 | E2E |
| 3 | 前后条件 | precondition/postcondition | E2E |
| 4 | Episode→Analysis | 失败→分析→建议 | `robot analyze` |
| 5 | 参数反馈 | 分析→Skill参数更新 | 验证 |
| 6 | Skill组合 | pick→place串联 | E2E |
| 7 | `robot capability` | 输出Graph | CLI |
| 8 | Cost估计 | 每capability有cost | yaml |

---

## M7.6 Mobile Navigation

**范围**: Base Interface实现(M7.0.4定义的契约)。

**验收标准**:

| # | 验收项 | 通过条件 | 验证方法 |
|---|--------|----------|----------|
| 1 | 轮关节 | wheel type=revolute | xacro grep |
| 2 | diff_drive | controller active | `ros2 control list` |
| 3 | cmd_vel | 可发布 | `ros2 topic pub` |
| 4 | 导航执行 | `robot move base <target>` | 位置变化 |
| 5 | Navigation2 | nav2节点 | `ros2 node list` |

---

## M7.S Safety Layer

**范围**: 横切Safety Plane，继承M6 SafetySupervisor。

**验收标准**:

| # | 验收项 | 通过条件 | 验证方法 |
|---|--------|----------|----------|
| 1 | 碰撞监控 | collision_monitor active | node list |
| 2 | 工作空间限制 | 越界→reject | 测试 |
| 3 | E-Stop | →所有运动停止 | E2E |
| 4 | Skill超时 | →abort | 超时测试 |
| 5 | Safety独立 | 不依赖Coordinator | M6约束保持 |

---

## 全局Exit Criteria

| # | 条件 | 验证 |
|---|------|------|
| 1 | 总测试 ≥ 522 (434+88) | count |
| 2 | 全部通过 | 0 failures |
| 3 | colcon build全包 | exit 0 |
| 4 | Gazebo含底盘+躯干+头部+双臂+夹爪+相机 | 视觉 |
| 5 | `robot scene list` ≥ 4 | CLI |
| 6 | `robot capability` 显示Graph | CLI |
| 7 | `robot evaluate` 输出报告 | CLI |
| 8 | `robot benchmark task_set_basic` | CLI |
| 9 | ADR-M6-Freeze Tier 1零破坏 | 接口对比 |
| 10 | ADR-M6-Freeze Tier 2仅扩展 | 接口对比 |
| 11 | Safety独立于Coordinator | 测试 |
| 12 | 验证报告 + AGENTS.md更新 | 文档 |

---

## 测试矩阵

| 阶段 | 单元 | 集成 | 冒烟 | 小计 |
|------|------|------|------|------|
| M7.0.1 | 5 | 0 | 3 | 8 |
| M7.0.2 | 3 | 0 | 2 | 5 |
| M7.0.3 | 2 | 0 | 2 | 4 |
| M7.0.4 | 1 | 0 | 2 | 3 |
| M7.2 | 6 | 2 | 2 | 10 |
| M7.3 | 4 | 2 | 2 | 8 |
| M7.E | 3 | 1 | 2 | 6 |
| M7.4 | 5 | 2 | 3 | 10 |
| M7.1 | 8 | 2 | 2 | 12 |
| M7.5 | 6 | 2 | 2 | 10 |
| M7.6 | 2 | 2 | 2 | 6 |
| M7.S | 4 | 0 | 2 | 6 |
| **总计** | **49** | **13** | **26** | **88** |

---

## 实施顺序

```
M7.0.1 → M7.0.2 → M7.0.3 → M7.0.4    (Foundation, 串行)
    ↓
M7.2 (Scene)
    ↓
M7.3 (Benchmark)
    ↓
M7.E (Evaluation)
    ↓
M7.4 (Vision, 含Calibration)
    ↓
M7.1 (Body)
    ↓
M7.5 (Skill Evolution)
    ↓
M7.6 (Navigation)

M7.S (Safety) 横切, 每阶段同步
```

每阶段完成后:
1. 运行该阶段测试
2. 运行全局回归(含M6 434+基线)
3. 检查ADR-M6-Freeze Tier 1/2合规
4. 更新验证报告
5. 更新AGENTS.md
