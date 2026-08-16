# Robot URDF Evolution Plan v1.0

**Status**: FROZEN v1.0
**Date**: 2026-08-13
**Parent Document**: [robot_body_architecture.md](robot_body_architecture.md)
**Goal**: 平滑迁移路径 Phase 0 → Phase 3，不破坏 M5.7 FROZEN v1.0 接口

---

## 1. 演进总览

```
Phase 0 (当前)        Phase 1 (已完成-回退)     Phase 2 (近期)         Phase 3 (M8+)
[独立双臂]        →   [primitive visual]  →   [shoulder 实体化]  →   [完整移动机器人]
                                                                     
- 验证 Skill/Runtime     - 仅改 visual          - 引入 torso/head       - 加移动底盘
- 独立 namespace         - 不改 collision        - 引入 left/right      - 加电池/电源
- 1 个 robot             - 不改 link/joint       - 引入 sensor suite    - 完整外观
  (multi_arm_robot)        结构                 - MoveIt SRDF 重构      - 状态 LED 绑定
                                                  - namespace 替换
```

**核心约束**：
- ❌ 不破坏 M5.7 FROZEN v1.0 接口（ExecuteTask/SafetyCheck/QueryWorld/...）
- ❌ 不破坏现有 158+ 测试
- ✅ 平滑迁移，每步可验证

---

## 2. Phase 0（当前 — 已完成 M1-M7）

### 2.1 URDF 结构

```
world
└── base_link (M7.0, 含 4 固定轮)
    ├── front_panel
    ├── status_led
    ├── arm1_pillar
    │   └── ur_base_1
    │       └── ... UR5e chain (6 joints) ...
    │           └── tool0_1
    ├── arm2_pillar
    │   └── ur_base_2
    │       └── ... UR5e chain ...
    │           └── tool0_2
    ├── torso_link (M7.1, virtual frame)
    │   └── head_link (M7.1, virtual frame)
    │       └── head_camera_link (M7.1, 含 RGB-D sensor)
    ├── wheel_fl, wheel_fr, wheel_bl, wheel_br
    └── (无 shoulder mount, 无 left/right 命名)
```

### 2.2 关键状态

| 维度 | 状态 |
|------|------|
| 验证完成 | M1-M7 全部 ✅ |
| 测试数 | 158+ tests passing |
| 接口冻结 | M5.7 FROZEN v1.0 |
| Robot ID | `multi_arm_robot.xacro`（单 xacro 文件） |
| Namespace | `arm1` / `arm2` |
| Visual | primitive（已回退） |

### 2.3 当前限制

- **命名不一致**：`arm1` / `arm2` ≠ body_architecture v1.0 的 `left` / `right`
- **torso/head 是 virtual frame**：M7.1 加了 link，但 collision/visual 是占位
- **无 shoulder mount**：双臂直接挂在 pillar
- **传感器单一**：只有 head_camera_link（RGB-D 合一）

---

## 3. Phase 1（视觉层 — 已完成 + 已回退）

### 3.1 实施内容

**已完成**：
- 9 个 STL mesh 生成（torso_shell, head_shell, head_camera_lens, head_led_ring, chassis_shell, arm_pillar_shell, status_led_strip, head_display, head_camera_window）
- 4 个 xacro 文件修改（torso, head, wheeled_base, materials）
- CMakeLists.txt 安装配置
- multi_arm_sim.launch.py 注入 GZ_SIM_RESOURCE_PATH

**已回退**：
- torso.xacro visual: mesh → cylinder primitive
- head.xacro visual (head_link, head_camera_link, head_led_ring_link): mesh → primitive
- wheeled_base.xacro visual (base_link, status_led, arm1_pillar, arm2_pillar): mesh → primitive

**保留**：
- STL mesh 文件本身（install/.../meshes/ 下仍存在，可能 Phase 2 复用）
- 全部 link/joint 拓扑
- 全部 collision/inertial

### 3.2 回退原因

按 body_architecture v1.0 决策：
- shoulder frame 未确定前，**视觉无意义**
- Phase 2 引入 shoulder_mount 后，现有 mesh 与新拓扑不匹配
- 不重做是因为避免浪费

### 3.3 Phase 1 状态

- ✅ collision/inertial 100% 保持
- ✅ link/joint 拓扑 100% 保持
- ✅ xacro 编译通过
- ✅ 28 个 mesh 引用（UR 官方 12 + M7.1 已有 4 + 其他 12，无 Phase 1 新增 mesh）
- ⏸ visual = primitive（临时状态）

---

## 4. Phase 2（Shoulder 实体化 — 近期）

### 4.1 目标

```
引入 shoulder frame
引入 head sensor suite
引入 left/right 命名
```

**实施周期估算**：2-3 周（取决于 MoveIt SRDF 重构工作量）

### 4.2 URDF 重构

**当前 → 目标**：

```
当前:                       目标:
base_link                   base_link
├── arm1_pillar             ├── torso_link
│   └── ur_base_1           │   ├── head_link
│       └── ... UR5e ...    │   │   ├── head_rgb_link
├── arm2_pillar             │   │   ├── head_depth_link
│   └── ur_base_2           │   │   └── head_imu_link
│       └── ... UR5e ...    │   ├── left_shoulder_mount
├── torso_link (virtual)    │   │   └── ur_base_left
│   └── head_link (virtual) │   │       └── ... UR5e ...
│       └── head_camera_link│   └── right_shoulder_mount
                            │       └── ur_base_right
                            │           └── ... UR5e ...
                            ├── (保留 front_panel, status_led)
                            └── wheel_fl, wheel_fr, ...
```

### 4.3 Namespace 替换

| 当前 | 目标 |
|------|------|
| `arm1` | `left_arm` |
| `arm2` | `right_arm` |
| `arm1_pillar` | (删除, 由 left_shoulder_mount 替代) |
| `arm2_pillar` | (删除) |
| `ur_base_1` | `ur_base_left` |
| `ur_base_2` | `ur_base_right` |
| `tool0_1` | `tool0_left` |
| `tool0_2` | `tool0_right` |
| `head_camera_link` | `head_rgb_link` + `head_depth_link` |

### 4.4 MoveIt SRDF 重构

**当前**：
```xml
<group name="arm1">
  <chain base_link="base_link" tip_link="tool0_1" />
</group>
<group name="arm2">
  <chain base_link="base_link" tip_link="tool0_2" />
</group>
<group name="dual_arm">
  <chain base_link="base_link" tip_link="tool0_1" />
  <chain base_link="base_link" tip_link="tool0_2" />
</group>
```

**目标**：
```xml
<group name="left_arm">
  <chain base_link="base_link" tip_link="tool0_left" />
</group>
<group name="right_arm">
  <chain base_link="base_link" tip_link="tool0_right" />
</group>
<group name="dual_arm">
  <group name="left_arm" />
  <group name="right_arm" />
</group>
```

### 4.5 controller_manager 重构

**当前**：
- `/arm1/controller_manager` (per-arm CM)
- `/arm2/controller_manager`

**目标**：
- `/left_arm/controller_manager`
- `/right_arm/controller_manager`
- `/head/controller_manager`（新增）
- `/base/controller_manager`（占位，M8 实施）

### 4.6 验证矩阵

| 验收项 | 通过条件 |
|--------|----------|
| URDF 编译 | `xacro multi_arm_robot.xacro` 成功 |
| MoveIt 加载 | `ros2 launch multi_arm_moveit_config ...` 启动 |
| TF 树 | `ros2 run tf2_tools view_frames` 完整 |
| arm1 → left_arm | 所有 `/arm1/*` 引用替换为 `/left_arm/*` |
| head sensor | RGB + Depth + IMU topic 全部发布 |
| 现有 158 tests | 100% 仍通过 |
| 端到端 | 一次完整 PickPlace 任务成功 |

### 4.7 风险与回滚

**风险**：
- MoveIt SRDF 重构可能引入 collision 矩阵问题
- namespace 替换可能漏掉某些引用
- 158+ tests 可能因 TF 名称变化失败

**回滚策略**：
- Phase 2 启用独立分支 `feat/phase2-shoulder`
- 每个 commit 必须保持测试 100% 通过
- 失败立即 revert，不累积技术债

---

## 5. Phase 2.5（LED 状态绑定 — 紧随 Phase 2）

### 5.1 目标

将 `status_led` (base) 的颜色绑定到系统运行状态。
注：`head_led_ring_link` 已在 Phase 2.1 中替换为 `head_depth_link`，LED 绑定仅针对 `status_led`。

### 5.2 实施

**URDF 侧**（已就绪）：
- `status_led` material = `led_green`（当前绿色）
- 新增材质：`led_red`、`led_blue`、`led_off`（Phase 2.5 添加）

**Runtime 侧**（Phase 2.5 实施）：
- 新建 `led_status_node` 节点（`multi_arm_runtime_api` 包）
- 检查 `/safety/check` 服务和 `/execute_task` action 可用性
- 发布 `/led/status`（std_msgs/String）和 `/led/color`（std_msgs/ColorRGBA）
- 状态：INITIALIZING → READY → FAILED / SAFETY_STOP

**Gazebo 实施选项**：
- 选项 A：动态材质（Gazebo script plugin + material update）
- 选项 B：替换 link 颜色通过 ROS topic
- 选项 C：用 RViz Marker 替代视觉（仅 RViz 中可见）

**当前实现**：发布 `/led/color` topic，Gazebo 动态材质留作未来增强

### 5.3 验证

| 状态 | 期望 LED 颜色 |
|------|---------------|
| Runtime READY | 绿 |
| Task RUNNING | 蓝 |
| Task FAILED | 红 |
| SAFETY_STOP | 红闪烁 |

---

## 6. Phase 3（完整移动机器人 — M8+）

### 6.1 目标

加入移动底盘 + 完整外观 + 电池/电源管理。

### 6.2 依赖

- M8 移动底盘决策（差速/全向/腿式）
- M8 决策 → base_link 下的具体结构

### 6.3 URDF 演进

**当前（Phase 2 完成后）**：
```
base_link
└── torso_link
    ├── head_link
    ├── left_shoulder_mount
    └── right_shoulder_mount
```

**目标**：
```
base_link (Phase 3 引入)
├── battery_link
├── power_board_link
├── (M8 决策: 差速底盘)
│   ├── wheel_left_drive
│   ├── wheel_right_drive
│   ├── wheel_left_front_caster (可选)
│   └── wheel_right_front_caster (可选)
└── torso_link
    └── (同 Phase 2)
```

### 6.4 新增 namespace

- `/base` — 移动底盘控制
- `/power` — 电源管理（未来 M8+）

### 6.5 验证

- 移动 + 操作联合任务：navigate to position → pick object → move to next position → place
- WorldModel 集成 base_link pose
- Capability Registry 暴露 base 能力

---

## 7. 测试与验证

### 7.1 Phase 0 验证（已完成）

- ✅ 158+ tests passing
- ✅ E2E PickPlace 闭环
- ✅ M4-M7 全部 ✅

### 7.2 Phase 2 验证（待实施）

| 测试 | 数量 |
|------|------|
| URDF 解析 | 5 tests |
| TF 树完整性 | 8 tests |
| MoveIt SRDF 加载 | 6 tests |
| namespace 替换 | 12 tests |
| E2E PickPlace | 8 tests |
| 现有 158 tests | 158 tests |
| **总计** | **197 tests** |

### 7.3 Phase 3 验证（M8+）

- 移动 + 操作联合任务 E2E
- Battery/Safety 集成测试

---

## 8. 接口冻结保障

### 8.1 M5.7 FROZEN v1.0 接口不变

所有跨包通信接口**不依赖 URDF link 名**：

| 接口 | 依赖 | 是否受 URDF 变化影响 |
|------|------|----------------------|
| ExecuteTask.action | arm_name (string) | 否 |
| SafetyCheck.srv | 不依赖 link 名 | 否 |
| QueryWorld.srv | 不依赖 link 名 | 否 |
| TaskGoal.msg | arm_name (string) | 否 |

**关键**：`arm_name` 字段是字符串，可以是 `"arm1"` / `"arm2"` / `"left_arm"` / `"right_arm"`。
**迁移时**：
- 新代码可以用 `left_arm` / `right_arm`
- 旧代码仍可以用 `arm1` / `arm2`（仅作字符串标识）
- WorldModel 内部映射表维护两套命名

### 8.2 WorldModel 兼容

WorldModel 的 Robot State Cache 维护**逻辑命名**（left_arm/right_arm），URDF 物理 link 名变化不影响。

### 8.3 Capability Registry 兼容

Capability 名（如 `arm_left.can_reach`）是**逻辑能力名**，URDF 物理结构变化不影响查询接口。

---

## 9. 时间线

```
2026-08-13  Phase 0 完成 + Phase 1 mesh 回退 + body_architecture v1.0 冻结
            ↓
2026-08-20  Phase 1.5 准备（design review, M7.2+ sensor 实施）
            ↓
2026-09-01  Phase 2 启动（shoulder + head sensor + namespace 替换）
            ↓
2026-09-15  Phase 2 完成（197 tests pass, MoveIt SRDF 重构）
            ↓
2026-09-20  Phase 2.5 LED 状态绑定
            ↓
2026-10-01  Phase 3 启动（依赖 M8 决策）
```

---

## 10. 冻结声明

本文档 v1.0 冻结以下内容：
- ✅ Phase 0-3 演进路径
- ✅ Phase 2 namespace 替换表
- ✅ Phase 2.5 LED 状态绑定
- ✅ Phase 3 移动底盘依赖
- ✅ 接口冻结保障策略
- ✅ 时间线

**禁止破坏性修改**。如需调整 Phase 顺序或新增 Phase，进入 v1.1 评审。

---

**End of Robot URDF Evolution Plan v1.0**