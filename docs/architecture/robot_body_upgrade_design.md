# Embodied Manipulation Platform Design

**版本**: v3.0
**日期**: 2026-08-10
**状态**: 设计完成（经三轮架构评审），待实施
**定位**: 构建可持续演化的具身智能机器人平台

---

## 0. 定位

> 不是"做一个人形机器人"，而是"构建具身智能开发平台"。

核心价值不是URDF形态，而是：

```
感知 → 世界模型 → 任务规划 → 技能执行 → 经验沉淀 → 自主改进
```

演化路线：

```
Mobile Dual-Arm Manipulator (当前, M6完成)
    ↓
Embodied Manipulation Platform (M7.0-M7.3)
    ↓
Vision-Grounded Agent (M7.4-M7.5)
    ↓
Mobile Manipulation Robot (M7.6)
    ↓
Humanoid (远期, 另一个项目)
```

视觉语言：**可靠、友好、模块化、工具化**，不追求仿人外观。

---

## 1. M7 路线图

```
M7.0 Robot Description Refactor    — URDF模块化 + robot.yaml代码生成
M7.1 Body Upgrade                  — torso/head/sensors物理结构
M7.2 Scene Asset System            — 场景+物体+任务+Episode
M7.3 Task Benchmark                — 标准化任务+成功率+失败分析
M7.4 Vision Grounding              — GT→Vision渐进迁移+置信度
M7.5 Skill Learning                — Skill Registry + Capability Graph
M7.6 Mobile Navigation             — 底盘动力学 + Navigation2
```

**优先级**: M7.2场景资产 + M7.3 Task Benchmark > M7.1头部外观

原因：没有任务，机器人只是模型；有任务，机器人开始成为智能体。

---

## 2. M7.0 Robot Description Refactor

### 2.1 URDF模块化

```
urdf/
├── robot.xacro                 # 顶层组装
├── body/
│   ├── torso.xacro             # 躯干 + torso_yaw_joint + IMU
│   ├── head.xacro              # 头部 + neck_pitch_joint + RGB-D
│   └── shoulder_mount.xacro    # 肩部横梁
├── arms/
│   └── dual_ur5e.xacro         # 双UR5e(不修改内部)
├── end_effectors/
│   └── robotiq_2f_85.xacro
├── sensors/
│   ├── camera.xacro
│   └── imu.xacro
├── mobile_base/
│   └── wheeled_base.xacro
└── materials.xacro
```

### 2.2 robot.yaml → 代码生成

```yaml
robot:
  type: mobile_manipulator

hardware:
  arms:
    type: ur5e
    count: 2
  gripper:
    type: robotiq_2f_85
    count: 2
  base:
    type: wheeled
  torso:
    joints: [torso_yaw]
  head:
    joints: [neck_pitch]
    sensors: [rgbd_camera]
  sensors:
    torso_imu: true
    wrist_camera: true
```

`robot_description_generator` 自动生成：URDF + SRDF + ros2_control + MoveIt config + capability.yaml

### 2.3 换硬件不变Runtime

```
robot.yaml: base: wheeled/biped/fixed
Runtime层(Skill/API/CLI/Experience)完全不变
```

---

## 3. M7.1 Body Upgrade

### 3.1 关节链路

```
world
 └─ base_link (fixed)
     ├─ wheels (fixed in M7.1, revolute in M7.6)
     └─ torso_link (torso_yaw_joint, Z旋转)
         ├─ shoulder_mount_link (fixed)
         │   ├─ arm1 → tool0 → robotiq
         │   └─ arm2 → tool0 → robotiq
         └─ head_link (neck_pitch_joint, Y俯仰)
             └─ head_camera_link (RGB-D)
     + torso_imu (on torso_link)
```

### 3.2 控制器拆分 — 身体控制 ≠ 感知注意

```
torso_controller (body control)
  └─ torso_yaw_joint
  语义: 调整操作姿态, 扩大工作空间

head_controller (perception attention)
  └─ neck_pitch_joint
  语义: "寻找红色杯子" → neck旋转 → camera重新观察
```

**不合并为一个controller**。头部属于Perception Attention System，不是身体控制。

### 3.3 MoveIt规划组 — 独立不合并

```xml
<group name="arm1">...</group>
<group name="arm2">...</group>
<group name="arm1_gripper">...</group>
<group name="arm2_gripper">...</group>
<group name="torso">
  <joint name="torso_yaw_joint"/>
</group>
```

**不做** `arm1_full`(torso+arm)。分层执行：

```
Step 1: torso调整姿态 (torso planning group)
Step 2: arm执行操作 (arm1/arm2 planning group)
```

未来需要Whole Body Control再引入。

### 3.4 传感器布局

```
head_link:
  └─ RGB-D Camera (前方感知, 1280x720@30Hz)

torso_link:
  └─ IMU (主体姿态, 100Hz)

arm1_wrist_3_link:
  └─ Camera (腕部视觉伺服, 640x480@10Hz)
```

IMU在torso不在head — 躯干姿态是主体姿态。

### 3.5 外观设计语言

不追求仿人，追求"机器人身份"：

```
头部 → 简单视觉模块(不是人脸)
躯干 → 圆角外壳(可靠感)
肩部 → 保护罩(工具感)
底盘 → 隐藏机械结构
```

---

## 4. M7.2 Scene Asset System

### 4.1 动机

> 机器人智能 = 机器人 × 环境 × 任务

没有任务的机器人只是模型。

### 4.2 结构

```
simulation/scenes/
├── environments/
│   ├── home/
│   │   ├── world.sdf          # 桌子+椅子+柜子
│   │   └── layout.yaml        # 物体布局
│   ├── warehouse/
│   │   ├── world.sdf          # 货架+箱子
│   │   └── layout.yaml
│   ├── lab/
│   │   ├── world.sdf          # 实验台+器材
│   │   └── layout.yaml
│   └── tabletop/              # 当前m6_test_world迁移
│       ├── world.sdf
│       └── layout.yaml
├── objects/
│   ├── cup.yaml               # 杯子(可抓取)
│   ├── drawer.yaml            # 抽屉(可开合)
│   ├── box.yaml               # 箱子(可搬运)
│   └── screw.yaml             # 螺丝(精密操作)
├── tasks/
│   ├── pick_object.yaml       # 抓取任务定义
│   ├── open_drawer.yaml       # 开抽屉
│   ├── clean_table.yaml       # 清桌面
│   └── inspect_part.yaml      # 检查零件
└── episodes/
    └── (运行时生成, Episode数据)
```

### 4.3 任务定义示例

```yaml
# tasks/pick_object.yaml
task:
  name: pick_object
  type: manipulation
  params:
    object_id: string
    target_location: string

  precondition:
    - object_exists(object_id)
    - gripper_empty
    - can_reach(object_id)

  postcondition:
    - object_at(object_id, target_location)

  skill: pick_place
  max_retries: 3
  timeout_sec: 30
```

### 4.4 CLI扩展

```bash
robot scene list                    # 列出可用场景
robot sim start home                # 启动home场景
robot sim start warehouse           # 启动warehouse场景
robot task list                     # 列出可用任务
robot task run pick_object cup      # 执行任务
```

---

## 5. M7.3 Task Benchmark

### 5.1 标准化任务集

```yaml
# benchmark/task_set.yaml
benchmarks:
  manipulation_basic:
    scene: tabletop
    tasks:
      - { task: pick_object, object: red_cube,   target: zone_a }
      - { task: pick_object, object: blue_cylinder, target: zone_b }
    repetitions: 10

  manipulation_hard:
    scene: home
    tasks:
      - { task: open_drawer,  drawer: kitchen_drawer }
      - { task: clean_table,  table: dining_table }
    repetitions: 5

  multi_arm:
    scene: warehouse
    tasks:
      - { task: co_carry, object: large_box, arms: [arm1, arm2] }
    repetitions: 3
```

### 5.2 指标

```
per_task:
  success_rate
  avg_duration
  failure_breakdown: { planning_fail, execution_fail, timeout, collision }

per_scene:
  task_completion_rate
  recovery_count
  human_intervention_count
```

### 5.3 Episode数据模型

```json
{
  "episode_id": "ep_001",
  "scene": "home",
  "task": "pick_object",
  "params": { "object": "cup", "target": "table" },
  "steps": [
    { "skill": "perceive", "success": true, "duration": 0.3 },
    { "skill": "plan_grasp", "success": true, "duration": 0.5 },
    { "skill": "execute_grasp", "success": false, "duration": 2.1,
      "failure_reason": "gripper_slipped" }
  ],
  "outcome": "failure",
  "failure_reason": "gripper_slipped",
  "recovery_attempted": true,
  "recovery_success": false
}
```

连接 `robot analyze episode_001` — Analyze有数据来源。

---

## 6. M7.4 Vision Grounding

### 6.1 三阶段迁移

**Stage A (M7.1, 保持)**:

```
Gazebo GroundTruth → WorldModel
```

**Stage B (M7.4)**:

```
RGB-D Camera → Perception → vision_pose + confidence
Gazebo GroundTruth → gt_pose

WorldModel:
  object: red_cube
    gt_pose:        [0.50, 0.15, 0.30]
    vision_pose:    [0.51, 0.16, 0.31]
    confidence:     0.93
    error:          1.4cm
0
```

**Stage C (M7.4后续)**:

```
RGB-D Camera → Perception → WorldModel (GT关闭)
```

### 6.2 置信度模型

Agent决策需要知道"我看到的是不是可信"：

```yaml
object:
  id: red_cube
  pose: [0.5, 0.2, 0.3]
  confidence: 0.93
  uncertainty: 0.014  # 标准差
  source: vision      # vs ground_truth
  last_seen: 0.1s_ago
```

低置信度 → 主动观察（head转向物体重新感知）。

---

## 7. M7.5 Skill Learning

### 7.1 Capability Graph

比capability.yaml高一级 — 描述能力依赖关系：

```yaml
# capabilities/capability_graph.yaml
robot:
  can:
    - pick
    - place
    - inspect
    - navigate   # M7.6+

  capabilities:
    pick:
      requires:
        perception: [object_pose]
        hardware: [gripper, arm]
        skill: grasp_v1
      provides: [object_at_grasp]
      cost: 2.5  # 预计耗时

    place:
      requires:
        perception: [target_pose]
        hardware: [gripper, arm]
        skill: place_v1
        precondition: object_at_grasp
      provides: [object_at_target]
      cost: 2.0

    open_drawer:
      requires:
        perception: [drawer_handle_pose]
        hardware: [gripper, arm]
        skill: pull_v1
      provides: [drawer_open]
      cost: 3.0
```

Agent查询Capability Graph：
- "当前机器人有什么能力？" → `can`列表
- "缺什么能力？" → `requires`未满足
- "如何组合技能？" → `provides`→`precondition`链

### 7.2 Skill Registry

```
skills/
├── grasp_v1/
│   ├── manifest.yaml         # 能力需求+前后条件+cost
│   ├── behavior_tree.xml     # BT执行逻辑
│   └── recovery.yaml         # 恢复策略
├── place_v1/
├── pull_v1/                  # 开抽屉
├── inspect_v1/
└── co_carry_v1/              # 双臂协作搬运
```

### 7.3 从Experience学习

```
Episode(失败) → FailureAnalysis → Skill参数调整 → 重新Benchmark
```

连接M6.4 Experience Infrastructure + M6.6 CLI `robot analyze`。

---

## 8. M7.6 Mobile Navigation

### 8.1 底盘升级

```
Phase 1 (M7.1): wheel = fixed joint (视觉)
Phase 2 (M7.6): wheel = revolute joint (动力学)
```

### 8.2 Navigation2集成

```
Navigation2 → cmd_vel → base_controller → Gazebo → robot movement
```

CLI:
```bash
robot move base kitchen       # 导航到厨房
robot move arm ready          # 手臂到ready位
robot task run clean_table    # 执行任务(导航+操作)
```

---

## 9. 实施计划

### M7.0 Robot Description Refactor

- [ ] URDF模块化目录结构
- [ ] robot.xacro顶层组装
- [ ] robot.yaml代码生成器接入launch
- [ ] multi_arm_robot.xacro向后兼容wrapper

### M7.1 Body Upgrade

- [ ] torso.xacro (torso_link + torso_yaw_joint + shoulder_mount + IMU)
- [ ] head.xacro (head_link + neck_pitch_joint + RGB-D)
- [ ] ros2_control: 14→16 joints
- [ ] **torso_controller + head_controller分开**
- [ ] SRDF: torso独立规划组
- [ ] 外观: 圆角外壳, 非仿人

### M7.2 Scene Asset System

- [ ] scenes/environments/ (home/warehouse/lab/tabletop)
- [ ] scenes/objects/ (cup/drawer/box)
- [ ] scenes/tasks/ (pick/open/clean/inspect)
- [ ] CLI: `robot scene list` / `robot sim start <scene>`

### M7.3 Task Benchmark

- [ ] benchmark/task_set.yaml标准化任务
- [ ] Episode数据模型(连接M6.4)
- [ ] CLI: `robot benchmark <task_set>`

### M7.4 Vision Grounding

- [ ] Stage B: GT + Vision并行 + confidence
- [ ] WorldModel扩展: confidence/uncertainty/source
- [ ] 主动观察: 低置信度→head转向

### M7.5 Skill Learning

- [ ] Capability Graph (capability_graph.yaml)
- [ ] Skill Registry扩展 (grasp/place/pull/inspect/co_carry)
- [ ] Episode→FailureAnalysis→Skill调整闭环

---

## 10. 不做什么

- ❌ 不改UR5e内部结构
- ❌ 不做全身MoveIt规划
- ❌ 不合并torso/head controller
- ❌ 不马上替代GroundTruth (Stage A保持)
- ❌ 不做双足
- ❌ 不做力控
- ❌ 不改Runtime层
- ❌ 不追求仿人外观(人脸/仿人皮肤)
- ❌ 不做全身外壳注塑细节

---

## 11. 与M6架构的关系

```
M6完成: Robot Runtime (Skill + API + CLI + Experience)
  ↓ 不变
M7.0: Robot Description模块化
M7.1: Body物理结构 + 传感器
M7.2: Scene资产(环境×物体×任务)
M7.3: Task Benchmark(标准化评测)
M7.4: Vision Grounding(真实感知)
M7.5: Skill Learning(能力图+经验闭环)
M7.6: Mobile Navigation(移动能力)

核心资产: Runtime + WorldModel + Skill + Experience闭环
URDF只是这一闭环的物理载体
```

---

## 12. 评审历史

| 版本 | 评价 | 关键调整 |
|------|------|----------|
| v1.0 | 6/10 | 基础方案，"加身体"思路 |
| v2.0 | 9/10 | 从Humanoid→Embodied Platform, GT渐进迁移, 独立planning groups |
| v3.0 | - | controller拆分, Capability Graph, Scene+Task优先, M7路线定义 |
