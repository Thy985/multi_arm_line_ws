# Phase 2 双臂改名规划方案（arm1/arm2 → left_arm/right_arm）

> 状态：待执行（已评审，方案已冻结）
> 关联文档：`docs/design/robot_data_migration_assessment.md`（§8.1 数据迁移评估，本方案为 §8.1(2)-(6) 的执行细化）
> 权威依据：`docs/design/robot_body_architecture.md`（双臂身份词 `left_arm`/`right_arm`）
> 决策锚点：main @ `3be64d5`（含本体 P0、运行时 P0、robot_id 微改动）

---

## 0. 决策结论（已裁定）

用户已确认采用**全量改名（含物理 prefix）**策略：

1. **prefix 必须一起改**。`arm1_` → `left_arm_`，`arm2_` → `right_arm_`。理由见 §1。
2. **型号名保留**。`dual_ur5e`（UR 型号）、`dual_ur5e_platform`（robot.name 平台身份）、`ur5e`/`ur_description`（UR 包名）**不替换**，仅 arm 标识改名。

---

## 1. 为什么必须全量改名（含物理 prefix）

代码与物理 prefix 强耦合，仅改逻辑名会破坏 ROS 接口：

| 耦合点 | 文件:行 | 机制 |
|---|---|---|
| 控制器话题拼接 | `coordinator_node.py` | `f"/{arm_name}_joint_trajectory_controller"` |
| joint 名下发 | `multi_arm_coordinator.py:129` | `trajectory.joint_names = ARM_JOINT_NAMES[arm_name]` |
| URDF joint frame 生成 | `robot_description_generator.py:84,125,165` | `prefix = arm.get("prefix", ...)` + `f"{prefix}{jn}"` |
| xacro 物理 prefix | `dual_ur5e.xacro:27,41,46,60` | `tf_prefix="arm1_"` 硬编码 |

若逻辑名改 `left_arm` 而 prefix 仍是 `arm1_`：
- 控制器话题拼成 `/left_arm_joint_trajectory_controller`，实际 `/arm1_...` → **控制失效**
- joint frame 变 `left_arm_shoulder_pan_joint`，实际 `arm1_...` → **运动规划失败**

当前系统是割裂态（逻辑 `left_arm` + 物理 `arm1_` + sensor `arm1_gripper` + xacro `arm1_`），全量改名才对齐设计文档。

---

## 2. 改名映射表（机械替换规则）

| 旧 | 新 | 适用范围 |
|---|---|---|
| `arm1` | `left_arm` | 逻辑标识 / dict key / 变量 / yaml 键 / launch 引用 |
| `arm2` | `right_arm` | 同上 |
| `arm1_` | `left_arm_` | prefix / joint 名 / 话题 / controller 名 / sensor·EE 名 / xacro tf_prefix / pillar |
| `arm2_` | `right_arm_` | 同上 |
| `arm1_shoulder_pan_joint` …(6) | `left_arm_shoulder_pan_joint` … | `ARM_JOINT_NAMES` value（两份） |
| `arm1_gripper` / `arm1_wrist_camera` / `arm1_tool0` / `arm1_robotiq_left_knuckle_joint` | `left_arm_*` | robot.yaml + xacro |
| `arm1_pillar` / `base_to_arm1_pillar` | `left_arm_pillar` / `base_to_left_arm_pillar` | `wheeled_base.xacro` |
| `torso_imu`（xacro 残留） | `head_imu` | `robot.xacro:74`（修复与 robot.yaml 割裂） |

**替换顺序强制要求**：`arm1_` 必须先于 `arm1` 处理（用词边界正则 `(?<![\w])arm1_(?![\w])` 先，`(?<![\w])arm1(?![\w])` 后），否则产生 `left_arm__` 双下划线误伤。

---

## 3. 影响范围（已盘点，共 167 文件）

| 类型 | 数量 | 关键文件 |
|---|---|---|
| `.py` | 108 | 含 **2 份** `ARM_JOINT_NAMES`：`multi_arm_core/robot_constants.py:6-23`、`order_manager/.../arm_state.py` |
| `.yaml` | 38 | robot.yaml sensors/EE、moveit 配置、controller、scenario |
| `.xacro` | 6 | `robot.xacro`、`arms/dual_ur5e.xacro`、`mobile_base/wheeled_base.xacro`、`sensors/camera.xacro`、`end_effectors/robotiq_2f_85.xacro`、`ros2_control/multi_arm_ros2_control.xacro` |
| `.launch.py` | 13 | 各 launch 引用 |
| `.srdf` | 2 | `multi_arm_moveit_config/config/multi_arm.srdf`、`single_arm.srdf` |
| **源头** | — | `multi_arm_coordinator.py:45` `self.arm_names=['arm1','arm2']`（arm 名唯一起源，驱动 `arm_status` 键 + `TaskScheduler` + `ARM_JOINT_NAMES[arm_name]` 索引） |

---

## 4. 两条 URDF 路径的割裂风险（必须同步处理）

- **路径 A（generator）**：`robot_description_generator.py` 读 `robot.yaml.prefix` 动态拼 `<xacro:ur_robot prefix=...>`，prefix 来自 yaml。
- **路径 B（手写 xacro）**：`ur_simulation_gz/.../robot.xacro` → `dual_ur5e.xacro`(`tf_prefix="arm1_")` + `wheeled_base.xacro`(`arm1_pillar`)。

两条路径 prefix 必须一致；Phase 2 改 prefix 时两条都改，并回归确认系统实际用哪条（`robot_description` 来源）。

---

## 5. 执行策略（AGENTS.md 大重构约束）

- 新 worktree + 分支：
  ```bash
  git worktree add ../multi_arm_line_ws-phase2 -b feat/phase2-naming
  cd ../multi_arm_line_ws-phase2
  ```
- **必须进 sandbox/Container**（大重构 + ROS2 调整，AGENTS.md §1/§2）。
- 不进主工作树直接改；机械替换用脚本批量，但每条规则人工 review diff。
- 现有 worktree `agent/body-p0`(@`10f7056`)、`agent/runtime-p0`(@`425b9d1`) 均已合并，可清理。

---

## 6. 有序执行阶段（含回滚里程碑）

| 阶段 | 内容 | 回滚点 | 验证 |
|---|---|---|---|
| **M0** | worktree+sandbox；冻结锚点 `3be64d5`；导出受影响文件清单（§3 grep 命令） | commit 锚点 | 环境就绪 |
| **M1** | robot.yaml：prefix、sensor/EE、`arm1_*`→`left_arm_*` | tag `phase2-m1` | generator 输出仅 prefix 变，YAML 合法 |
| **M2** | xacro 链：dual_ur5e tf_prefix、wheeled_base pillar、robot.xacro sensor/topic、camera/robotiq/ros2_control | tag `phase2-m2` | xacro 渲染成功、joint 前缀一致 |
| **M3** | 代码源头：`self.arm_names=['left_arm','right_arm']` + 两份 `ARM_JOINT_NAMES`（key+value） | tag `phase2-m3` | colcon build + import |
| **M4** | 全量机械替换：108 py + 38 yaml + 13 launch + 2 srdf 的 `arm1`/`arm2`/`arm1_`/`arm2_` 字面量 | tag `phase2-m4` | grep 零残留（白名单除外） |
| **M5** | 测试同步：`test_robot_description_generator.py` prefix 断言、`test_base_interface`、`order_manager` 全套、world_model relation | tag `phase2-m5` | 单测 PASS |
| **M6** | 全量回归：colcon build 全包；启 `multi_arm_sim` 验证 `/left_arm/*`、`/right_arm/*` 话题、`/left_arm_joint_trajectory_controller` 可达；M1–M7 验收（23 项）ALL PASS | merge `feat/phase2-naming` → main | 端到端 |

### 受影响文件清单生成命令（M0 导出）

```bash
# 各类型含 arm1|arm2 的文件（执行前导出、执行后复检）
grep -rln "arm1\|arm2" --include=*.py   src | sort > /tmp/phase2_py.txt
grep -rln "arm1\|arm2" --include=*.yaml src | sort > /tmp/phase2_yaml.txt
grep -rln "arm1\|arm2" --include=*.xacro src | sort > /tmp/phase2_xacro.txt
grep -rln "arm1\|arm2" --include=*.launch.py src | sort > /tmp/phase2_launch.txt
grep -rln "arm1\|arm2" --include=*.srdf src | sort > /tmp/phase2_srdf.txt
```

### 残留复检命令（M4 后）

```bash
# 应只剩白名单残留（dual_ur5e / dual_ur5e_platform / ur5e / ur_description）
grep -rn "arm1\|arm2" --include=*.py --include=*.yaml --include=*.xacro --include=*.launch.py --include=*.srdf src
```

---

## 7. 白名单（合法残留，不可替换）

- `dual_ur5e`：UR 型号名，保留
- `dual_ur5e_platform`（`robot.yaml` robot.name）：平台身份，保留
- `ur5e` / `ur_description`：UR 包名，保留
- `arm1_platform` 等组合：逐案排查，避免误伤

---

## 8. 与设计文档偏差说明

- 设计文档 §3.2「随 `ARM_JOINT_NAMES` 改 key 即可（0 代码改动，values 可保持原值）」**不成立**：代码硬编码 `arm1`/`arm2`，且 prefix 改名要求 joint 字符串同步改（见 §1）。
- 设计文档未明确物理 prefix 命名策略；本方案采用 `prefix = 逻辑名 + 下划线`（`left_arm_`），维持 name 与 prefix 一致，消除割裂。

---

## 9. 风险与检查项

- [ ] 替换顺序：`arm1_` 先于 `arm1`（词边界正则）
- [ ] 两条 URDF 路径 prefix 一致性（§4）
- [ ] `ros2_control` joint 名必须与 URDF 完全一致（否则硬件接口初始化失败）
- [ ] moveit `.srdf` 中 arm 规划组、碰撞矩阵引用旧 joint 名需同步
- [ ] `test_robot_description_generator.py:24,31,111` 的 `prefix: "arm1_"` 断言需同步改
- [ ] `test_base_interface.py` 读取 `wheeled_base.xacro` 断言，pillar 改名后复检
- [ ] 现有 worktree（`agent/body-p0`、`agent/runtime-p0`）合并后清理

---

## 10. 执行前确认（已裁定）

| 决策点 | 结论 |
|---|---|
| prefix 是否改 | **改**（全量改名） |
| `dual_ur5e` / `dual_ur5e_platform` 是否保留 | **保留**型号名 |
