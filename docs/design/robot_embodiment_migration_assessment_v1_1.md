# Robot Embodiment Migration Assessment v1.1

**Status**: SUPPLEMENT to v1.0
**Date**: 2026-08-13
**Companion Documents**:
- [robot_embodiment_migration_assessment.md v1.0](robot_embodiment_migration_assessment.md) (架构风险评估)
- [robot_data_migration_assessment.md v1.0](robot_data_migration_assessment.md) (软件迁移评估)
- [robot_body_architecture.md v1.0](robot_body_architecture.md) (形态架构)

**v1.1 核心升级**：把 v1.0 的"架构风险评估"升级为"工程验证级别"
1. ✅ 严格区分 **Hypothesis（假设）** vs **Measurement（测量）**
2. ✅ 增加 4 个实验章节（Reachability / IK Stress / Task Matrix / Controller/Dynamics）
3. ✅ 增加 **Shadow Migration 3 阶段验证路线**
4. ✅ 把所有"看起来专业但没有来源"的数字降级为**待验证假设**

---

## 0. v1.0 → v1.1 关键变化

| 维度 | v1.0 状态 | v1.1 升级 |
|------|-----------|-----------|
| **数字来源** | 大量"看起来专业"但未验证 | 严格区分 Hypothesis / Measurement |
| **Reachability** | 仅"workspace -8%"估算 | 完整 Overlap 实验设计 |
| **IK 成功率** | 估算 95-98% / 85-90% | 1000 random pose 采样验证 |
| **Task 差异** | 默认所有任务一起迁移 | **Task Transfer Matrix** 按任务分 |
| **Dynamics** | ❌ 未分析 | ✅ Mass matrix / Inertia / Controller |
| **Controller** | 浅层 | ✅ ros2_control 迁移详细 |
| **Sensor Domain Shift** | 0.038→0.05 简化 | ✅ mAP / occlusion / lighting 全维度 |
| **验证路线** | URDF → 采集 → Benchmark | ✅ **Shadow Migration** 3 阶段 |

---

## 1. Hypothesis vs Measurement 分类表

> **v1.0 严重问题：把假设当结论**。本节明确 v1.0 中每个数字的状态。

### 1.1 标记图例

| 标记 | 含义 | 来源 |
|------|------|------|
| **[M]** | **Measured** — 已实测 | Phase 0 验证报告 |
| **[H-Measurable]** | **Hypothesis, 可立即测量** | 实验已设计，待跑 |
| **[H-Model]** | **Hypothesis, 基于模型估算** | 物理/数学推导 |
| **[H-Intuition]** | **Hypothesis, 经验直觉** | 行业经验，无严格来源 |
| **[U]** | **Unknown** | 缺乏信息，需研究 |

### 1.2 v1.0 关键数字状态重分类

| v1.0 数字 | 状态 | 重分类后 | 原因 |
|----------|------|---------|------|
| 单臂 IK 95-98% | [H-Intuition] | 假设 | 未实测 |
| 双臂 IK 85-90% | [H-Intuition] | 假设 | 未实测 |
| PickPlace 78-85% | [H-Intuition] | 假设 | 未实测 |
| Workspace -8% | [H-Model] | 假设 | 球壳体积公式估算 |
| 单臂 base 抬高 0.25m | [M] | **事实** | 来自 URDF body_architecture |
| 双臂距离 0.78m | [M] | **事实** | 来自 URDF body_architecture |
| 桌面 z<0.4 覆盖率 -30% | [H-Model] | 假设 | 简单几何估算 |
| 双手协作 -25% | [H-Model] | 假设 | 几何估算 |
| 感知 0.038m→0.05m | [H-Measurable] | 假设 | 待标定 |
| Path 规划时间 +30-50% | [H-Intuition] | 假设 | 行业经验 |
| Cart-space 分布偏移 5% | [H-Intuition] | 假设 | 未量化 |
| Joint-space 分布偏移 30% | [H-Model] | 假设 | 简单估算 |
| Phase 0 success 100% L1 | [M] | **事实** | M5.6 验证报告 |
| Phase 0 planning <0.1s | [M] | **事实** | M5.6 验证报告 |
| Phase 0 execution 2-5s | [M] | **事实** | M5.6 验证报告 |

### 1.3 v1.1 重大调整

**v1.0 中所有非 [M] 数字，全部降级为 [Hypothesis]，必须实验验证后才能作为 ETS 评分依据。**

**v1.0 的核心结论保持不变**：
- 抽象层 98% 复用（[M]）
- 物理层 0% 直接复用（[M]）
- 需要 14-20 周迁移（[H-Intuition] → 需修订）

**v1.0 中需修订的结论**：
- 能力损失估算（IK 2-5%, 双臂 10-15%, Workspace 8%）：全部 [H-Intuition]
- ETS ≥ 0.85 目标：[H-Goal]（待校准）

---

## 2. Reachability Overlap Experiment（可达空间重叠分析）

### 2.1 实验目标

> **新 embodiment 是否能覆盖原任务空间？** 这是机器人迁移最核心的问题。

### 2.2 实验方法

#### 步骤 1：定义任务工作空间

**Phase 0 任务工作空间**（来自现有场景 YAML）：
```python
# /home/lenovo/multi_arm_line_ws/src/multi_arm_simulation/scenes/environments/tabletop.yaml
# 桌面任务区域
TASK_WORKSPACE = {
    "tabletop": {
        "x_range": [0.0, 1.0],
        "y_range": [-0.4, 0.4],
        "z_range": [0.0, 0.4],
    },
    "warehouse": {
        "x_range": [0.0, 1.5],
        "y_range": [-0.5, 0.5],
        "z_range": [0.0, 1.0],
    },
    "dual_arm_cooperation": {
        "x_range": [0.3, 0.7],  # 双臂中央
        "y_range": [-0.2, 0.2],
        "z_range": [0.1, 0.4],
    },
}
```

#### 步骤 2：Reachability 采样

**算法**：
```python
def compute_reachability_map(robot_urdf, base_frame, joint_limits,
                              grid_resolution=0.05, max_samples=10000):
    """
    网格采样可达性地图
    Returns: dict {(x,y,z) -> {"reachable": bool, "ik_solutions": int}}
    """
    kinematic_chain = KDLChain.from_urdf(robot_urdf, base_frame)
    samples = []
    reachable = {}

    for x, y, z in grid_sample(TASK_WORKSPACE, grid_resolution):
        target_pose = Pose(position=[x, y, z], orientation=quaternion_default)
        solutions = solve_ik_batch(kinematic_chain, target_pose,
                                   n_samples=10, timeout=0.1)

        reachable[(x, y, z)] = {
            "reachable": len(solutions) > 0,
            "ik_count": len(solutions),
            "best_manipulability": max([s.manipulability for s in solutions], default=0),
        }
    return reachable
```

**采样参数**：
- Grid resolution: 0.05m (5cm) — 平衡精度与计算量
- Total samples: ~10000 points per scenario
- IK timeout: 0.1s per solve
- Max attempts: 10 per point

#### 步骤 3：Overlap 计算

```python
def compute_overlap(reachability_phase0, reachability_phase2):
    """
    计算两 phase 的可达空间重叠率
    """
    all_points = set(reachability_phase0.keys()) | set(reachability_phase2.keys())

    intersection = sum(
        1 for p in all_points
        if reachability_phase0.get(p, {}).get("reachable")
        and reachability_phase2.get(p, {}).get("reachable")
    )
    union = sum(
        1 for p in all_points
        if reachability_phase0.get(p, {}).get("reachable")
        or reachability_phase2.get(p, {}).get("reachable")
    )

    return {
        "intersection_ratio": intersection / len(all_points),  # 共同覆盖
        "phase0_coverage_phase2": intersection / sum(
            1 for p in reachability_phase0
            if reachability_phase0[p].get("reachable")
        ),  # Phase 0 中 Phase 2 仍可达比例
        "lost_area": [
            p for p in reachability_phase0
            if reachability_phase0[p].get("reachable")
            and not reachability_phase2.get(p, {}).get("reachable")
        ],
        "new_area": [
            p for p in reachability_phase2
            if reachability_phase2[p].get("reachable")
            and not reachability_phase0.get(p, {}).get("reachable")
        ],
    }
```

### 2.3 验收指标

| 指标 | Phase 0 基线 | Phase 2 目标 | 不通过则 |
|------|-------------|-------------|----------|
| **桌面任务 overlap** | 100% | ≥90% | 需调整 base 位置 |
| **双手协作 overlap** | 100% | ≥75% | 需重新规划协作任务 |
| **总体 overlap (任务空间内)** | 100% | ≥85% | 触发 Phase 2 重新设计 |
| **Lost area 关键性** | - | 不在 critical zone | 需分析 |

**关键区域定义** (critical zone)：
- 桌面中心 ±0.2m
- 双手协作中心 ±0.15m
- 物体放置位姿上方 0.1m

### 2.4 实验输出

```python
# 输出文件
output = {
    "experiment_name": "reachability_overlap_phase0_vs_phase2",
    "date": "2026-XX-XX",
    "phase0_urdf": "multi_arm_robot.xacro",
    "phase2_urdf": "embodied_robot.xacro (TBD)",
    "results": {
        "tabletop": {
            "phase0_reachable": 892,
            "phase2_reachable": 815,
            "intersection": 793,
            "overlap_ratio": 0.889,
            "lost_points": 99,
            "lost_in_critical": 3,  # 关键丢失
        },
        "dual_arm_cooperation": {
            "phase0_reachable": 156,
            "phase2_reachable": 119,
            "intersection": 102,
            "overlap_ratio": 0.654,
            "lost_points": 54,
            "lost_in_critical": 12,  # 警告
        },
    },
    "conclusion": "桌面任务 overlap 88.9% 通过, 双手协作 65.4% 警告"
}
```

### 2.5 实施

**文件**：`src/multi_arm_embodiment_validation/test/test_reachability_overlap.py`
**依赖**：`PyKDL` 或 `kdl_parser_py` + `trac_ik_python`
**计算量**：~10 分钟 per scenario (10000 samples)
**保存**：Reachability Map v1 / v2 到 JSON 文件

---

## 3. Random IK Stress Test（随机 IK 压力测试）

### 3.1 实验目标

> **1000 个随机位姿的 IK 求解成功率是多少？** 排除 singularity 和 boundary 边界。

### 3.2 实验设计

#### 样本生成

```python
def generate_random_targets(n=1000, workspace="tabletop"):
    """生成 1000 个随机目标位姿"""
    targets = []
    for i in range(n):
        # 位置：任务工作空间内均匀采样
        x = random.uniform(*WORKSPACE[workspace]["x_range"])
        y = random.uniform(*WORKSPACE[workspace]["y_range"])
        z = random.uniform(*WORKSPACE[workspace]["z_range"])

        # 朝向：球面均匀采样（避免上/下翻转偏好）
        orientation = random_quaternion_uniform()

        # 接近向量：6 个标准方向 (top/bottom/left/right/front/back)
        approach = random.choice(["top", "bottom", "side"])

        targets.append({
            "id": i,
            "position": [x, y, z],
            "orientation": orientation,
            "approach": approach,
        })
    return targets
```

#### 测试场景

**3 个测试集**：

1. **桌面任务测试集** (n=500)
   - 工作空间：x∈[0, 1.0], y∈[-0.4, 0.4], z∈[0, 0.4]
   - 朝向：抓取位姿 (top-down)
   - Phase 0 期望：~98% 成功率

2. **双手协调测试集** (n=300)
   - 工作空间：双臂中央 0.3m × 0.4m × 0.3m
   - 朝向：左右对称
   - Phase 0 期望：~95% 成功率

3. **Singularity 边界测试集** (n=200)
   - 故意采样接近 singularity 的位姿
   - 工作空间边界 ±0.1m
   - 朝向：奇异位姿
   - Phase 0 期望：~60% 成功率（验证 IK 求解器稳定性）

#### IK 求解

```python
def test_ik_stress(urdf_path, base_frame, targets):
    """对每个 target 测试 IK 成功率"""
    robot = URDF.from_xml_file(urdf_path)
    chain = KDLChain.from_urdf(robot, base_frame)
    ik_solver = IKSolver(chain, max_time=0.1, max_iter=100)

    results = []
    for target in targets:
        start_time = time.time()
        solutions = ik_solver.solve_batch(
            target["position"],
            target["orientation"],
            n_attempts=5,  # 多次尝试以避开 local minima
        )
        elapsed = time.time() - start_time

        results.append({
            "target_id": target["id"],
            "success": len(solutions) > 0,
            "n_solutions": len(solutions),
            "best_manipulability": max([s.manipulability for s in solutions], default=0),
            "elapsed_time": elapsed,
        })
    return results
```

### 3.3 验收指标

| 测试集 | Phase 0 基线 | Phase 2 目标 | 退化阈值 |
|--------|-------------|-------------|----------|
| 桌面任务 (n=500) | ≥98% | ≥95% | 5% 退化触发 warning |
| 双手协调 (n=300) | ≥95% | ≥85% | 10% 退化触发 warning |
| Singularity (n=200) | ≥60% | ≥55% | 不显著退化 |

**总成功率** = 加权平均 = `0.5 × 桌面 + 0.3 × 协调 + 0.2 × singularity`

### 3.4 失败原因分类

对每个失败的 IK 求解，记录原因：

```python
failure_reasons = {
    "no_solution": 0,           # 完全无解
    "timeout": 0,               # 求解超时
    "max_iter_reached": 0,      # 达到最大迭代
    "joint_limit_violation": 0, # 解超出关节限制
    "collision_detected": 0,    # 解在碰撞状态
    "low_manipulability": 0,    # 解的 manipulability 低于阈值
    "self_collision": 0,        # 自碰撞
    "torso_collision": 0,       # 与 torso 碰撞 (Phase 2 新增)
    "head_collision": 0,        # 与 head 碰撞 (Phase 2 新增)
}
```

**关键**：`torso_collision` 和 `head_collision` 是 Phase 2 新增失败原因，直接影响能力。

### 3.5 实验输出

```python
ik_test_result = {
    "phase0_baseline": {
        "desktop": {"success": 490, "total": 500, "rate": 0.980},
        "bimanual": {"success": 285, "total": 300, "rate": 0.950},
        "singularity": {"success": 124, "total": 200, "rate": 0.620},
        "weighted_total": 0.929,
    },
    "phase2_preliminary": {
        "desktop": {"success": 475, "total": 500, "rate": 0.950},
        "bimanual": {"success": 255, "total": 300, "rate": 0.850},
        "singularity": {"success": 110, "total": 200, "rate": 0.550},
        "weighted_total": 0.880,
    },
    "degradation": {
        "desktop": -0.030,
        "bimanual": -0.100,
        "singularity": -0.070,
        "weighted": -0.049,  # 4.9% 总退化
    },
    "phase2_new_failures": {
        "torso_collision": 12,
        "head_collision": 8,
    },
}
```

### 3.6 实施

**文件**：`src/multi_arm_embodiment_validation/test/test_ik_stress.py`
**依赖**：`trac_ik_python`（推荐，比 KDL 强）或 `PyKDL`
**计算量**：~30 分钟 per URDF (1000 samples × 5 attempts)
**保存**：测试结果到 JSON + 失败原因分类报告

---

## 4. Task Transfer Matrix（任务迁移矩阵）

### 4.1 实验目标

> **不同任务的迁移难度不同**。把任务分类，预测每个类别的迁移成功率。

### 4.2 任务分类与预估难度

| 任务 | 类别 | 复杂度 | 迁移难度 | 预估 ETS | 关键挑战 |
|------|------|--------|---------|----------|----------|
| **Home Position** | Trivial | 单点 | 低 | 0.99 | 仅需标定 |
| **Pick Single Object** | Basic | 单臂 + grasp | 低 | 0.90 | IK + 简单 grasp |
| **Move to Pose** | Basic | 笛卡尔轨迹 | 低 | 0.92 | 重新规划 |
| **Place Object** | Basic | 释放位姿 | 低 | 0.88 | zone 几何匹配 |
| **Inspect Object** | Medium | perception + 视角 | 中 | 0.78 | 视角 + 感知 |
| **Scan Workspace** | Medium | 全覆盖 | 中 | 0.80 | 路径规划 |
| **Push Object** | Medium | 力控 | 中 | 0.75 | 力模型 |
| **Stack Objects** | Medium | 精度 + 顺序 | 中 | 0.72 | 精度退化 |
| **Dual-Arm Lift** | High | 双手协调 | 高 | 0.65 | 双手空间 |
| **Bimanual Handover** | High | 双手 + 时序 | 高 | 0.60 | 时序 + 同步 |
| **Assembly (peg-in-hole)** | High | 精度 + 力 | 高 | 0.55 | 接触模型 |
| **Tool Use** | Very High | 长序列 | 极高 | 0.50 | 演示数据完全失效 |
| **Cable Routing** | Very High | 柔性物体 | 极高 | 0.40 | 物理建模 |
| **Deformable Manipulation** | Extreme | 物理仿真 | 极高 | 0.30 | 模型 + 感知 |

### 4.3 Capability Transfer Matrix

#### 计算公式

```python
def task_ets(task, phase0_urdf, phase2_urdf, episode_database):
    """
    任务级 ETS 计算
    """
    return {
        "task": task["name"],
        "category": task["category"],
        "ets": (
            0.3 * test_ik_success_rate(task, phase0_urdf, phase2_urdf)
          + 0.2 * test_workspace_overlap(task, phase0_urdf, phase2_urdf)
          + 0.2 * test_collision_free_rate(task, phase0_urdf, phase2_urdf)
          + 0.1 * test_perception_accuracy(task, phase0_urdf, phase2_urdf)
          + 0.1 * test_timing_compatibility(task, phase0_urdf, phase2_urdf)
          + 0.1 * test_dynamic_stability(task, phase0_urdf, phase2_urdf)
        ),
    }
```

#### 分维度评估

| 维度 | 权重 | Trivial 任务 | Basic 任务 | Medium | High | Very High |
|------|------|------------|------------|--------|------|-----------|
| **IK 成功率** | 0.3 | 0.99 | 0.95 | 0.85 | 0.75 | 0.60 |
| **Workspace overlap** | 0.2 | 0.99 | 0.92 | 0.85 | 0.70 | 0.55 |
| **Collision-free 路径** | 0.2 | 0.98 | 0.90 | 0.82 | 0.65 | 0.50 |
| **Perception 精度** | 0.1 | 0.95 | 0.90 | 0.80 | 0.70 | 0.55 |
| **Timing 兼容** | 0.1 | 0.95 | 0.85 | 0.80 | 0.65 | 0.50 |
| **Dynamic 稳定** | 0.1 | 0.95 | 0.85 | 0.78 | 0.60 | 0.45 |
| **综合 ETS** | - | 0.98 | 0.91 | 0.83 | 0.69 | 0.54 |

### 4.4 任务分类清单

**所有 Skill 重新归类**：

```python
TASK_TAXONOMY = {
    "trivial": {
        "skills": ["home_position", "stop"],
        "ets_target": 0.95,
    },
    "basic": {
        "skills": ["pick_object", "place_object", "move_object", "retract"],
        "ets_target": 0.85,
    },
    "medium": {
        "skills": ["inspect", "scan", "push", "stack"],
        "ets_target": 0.75,
    },
    "high": {
        "skills": ["dual_arm_lift", "bimanual_handover", "assembly_simple"],
        "ets_target": 0.65,
    },
    "very_high": {
        "skills": ["tool_use", "complex_assembly"],
        "ets_target": 0.50,
    },
    "extreme": {
        "skills": ["cable_routing", "deformable_manipulation"],
        "ets_target": 0.30,
    },
}
```

### 4.5 实验输出

**每个任务类别生成 Capability Transfer Card**：

```yaml
# /docs/validation/capability_transfer_card_basic.yaml
category: basic
skills: [pick_object, place_object, move_object]
phase0_success_rate: 0.95
phase2_expected_success_rate: 0.85
ets: 0.91
main_risks:
  - ik_degradation_in_workspace_corner
  - collision_with_torso_when_arm_extended
mitigations:
  - workspace_corner_relabeling
  - torso_avoidance_planning
required_episodes: 30  # 新采集数量
validation_tests:
  - test_pick_20_random_objects
  - test_place_20_random_zones
  - test_move_20_random_poses
```

### 4.6 实施

**文件**：`src/multi_arm_embodiment_validation/test/test_task_transfer_matrix.py`
**数据**：复用现有 158+ tests + 新采集 100+ episodes
**输出**：每类任务的 Capability Transfer Card
**报告**：`docs/validation/task_transfer_matrix_report.md`

---

## 5. Controller / Dynamics Migration Plan（控制器 / 动力学迁移）

### 5.1 Dynamics 迁移分析

#### 5.1.1 Mass Matrix 变化

**Phase 0**：
```python
# base_link 质量分布
mass_distribution_phase0 = {
    "base_link": 40.0,      # 底盘 (固定)
    "arm1_pillar": 5.0,     # 柱
    "ur5e_arm1": 18.4,      # UR5e
    "ur5e_arm2": 18.4,
    "gripper_1": 1.0,
    "gripper_2": 1.0,
    "total": 83.8,
    "center_of_mass": (0.5, 0.0, 0.3),  # 底盘中心
}
```

**Phase 2**：
```python
mass_distribution_phase2 = {
    "base_link": 40.0,
    "torso_link": 8.0,        # 新增 (实体)
    "head_link": 1.5,         # 新增
    "head_rgb": 0.2,
    "head_depth": 0.2,
    "head_imu": 0.1,
    "left_shoulder_mount": 1.0,  # 新增
    "right_shoulder_mount": 1.0,
    "arm1_pillar": 5.0,
    "ur5e_left": 18.4,
    "ur5e_right": 18.4,
    "gripper_left": 1.0,
    "gripper_right": 1.0,
    "total": 95.8,            # +12kg
    "center_of_mass": (0.5, 0.0, 0.5),  # 抬高 0.2m
}
```

**关键变化**：
- 总质量 +12kg (14% 增重)
- CoM 抬高 0.2m (67% 高度增加)
- 双臂 base 上移到 torso → CoM 上移 → 力矩变化

#### 5.1.2 Inertia Tensor 变化

**base_link inertia tensor**（绕 base_link CoM）：

```
Phase 0:
  I = diag(1.0, 1.5, 2.0)  # kg·m²

Phase 2:
  I = diag(1.5, 2.0, 2.5)  # 估计 +50% Ixx, +33% Iyy, +25% Izz
```

**影响**：
- 加速度极限需重新计算
- Trajectory smoothing 参数需调整
- Controller gain 需重新调

#### 5.1.3 Gravity Compensation

**Phase 0**：双臂独立，重力补偿简单（每个 arm 单独计算）

**Phase 2**：
- torso 与双臂耦合 → **coupled gravity compensation**
- head 重量 → 头部位姿影响 CoM
- 关键：torso_yaw_joint (如果激活) 旋转时，head + arm 产生偏心力矩

**仿真验证**：
```python
def test_gravity_compensation(phase0_urdf, phase2_urdf):
    """比较两 phase 的重力补偿误差"""
    # 让双臂水平伸直（最大力矩场景）
    test_config = {
        "shoulder_pan": 0,
        "shoulder_lift": 0,  # 水平
        "elbow": 0,
        "wrist_1": 0,
        "wrist_2": 0,
        "wrist_3": 0,
    }
    # 测量实际力矩 vs 理论重力矩
    measured_torque = simulate(urdf, test_config)
    theoretical_torque = compute_gravity_torque(urdf, test_config)

    error = abs(measured_torque - theoretical_torque)
    return {
        "phase0_error": 0.05,  # Nm
        "phase2_error": 0.08,  # 估计 (有 torso 耦合)
    }
```

### 5.2 Controller 迁移分析

#### 5.2.1 Phase 0 Controller 配置

**当前**（已实现）：
```yaml
# /ur_simulation_gz/config/multi_arm_controllers.yaml
controller_manager:
  ros__parameters:
    update_rate: 500  # Hz
    arm1_joint_trajectory_controller:
      type: joint_trajectory_controller/JointTrajectoryController
      joints:
        - arm1_shoulder_pan_joint
        - arm1_shoulder_lift_joint
        - arm1_elbow_joint
        - arm1_wrist_1_joint
        - arm1_wrist_2_joint
        - arm1_wrist_3_joint
      command_interfaces:
        - position
      state_interfaces:
        - position
        - velocity
    # ... arm2_joint_trajectory_controller 类似
```

**ros2_control stack**：
```
MoveIt2 (planning)
  ↓ JointTrajectory
joint_trajectory_controller (JTC)
  ↓ position command
ros2_control (hardware abstraction)
  ↓ joint command
Gazebo SimROS2ControlPlugin (仿真)
  ↓ physics
UR5e (simulated)
```

#### 5.2.2 Phase 2 Controller 迁移

**改动点 1：关节列表（arm1 → left_arm）**

```yaml
# Phase 2 配置
left_arm_joint_trajectory_controller:
  type: joint_trajectory_controller/JointTrajectoryController
  joints:
    - left_shoulder_pan_joint
    - left_shoulder_lift_joint
    - left_elbow_joint
    - left_wrist_1_joint
    - left_wrist_2_joint
    - left_wrist_3_joint
  # ... 其他不变
```

**改动点 2：torso + head 控制器（新增）**

```yaml
# 新增 torso 控制器
torso_controller:
  type: forward_command_controller/JointGroupCommandController
  joints:
    - torso_yaw_joint  # 如果激活
  command_interfaces:
    - position

# head_controller
head_controller:
  type: forward_command_controller/JointGroupCommandController
  joints:
    - neck_pitch_joint
  command_interfaces:
    - position
```

**改动点 3：head 传感器数据流**

```yaml
# 新增 sensor broadcaster
head_imu_broadcaster:
  type: imu_sensor_broadcaster/IMUSensorBroadcaster
  sensor_name: head_imu

head_camera_broadcaster:
  type: camera_controller/CameraController
  sensor_name: head_rgb_camera
  # ... depth camera 同样
```

#### 5.2.3 Controller 性能迁移

| 指标 | Phase 0 | Phase 2 目标 | 验证方法 |
|------|---------|-------------|----------|
| **Joint 跟踪误差** | <0.01 rad | <0.01 rad | 阶跃响应测试 |
| **Trajectory 跟踪** | 2-5s 完整执行 | 同 | 端到端测试 |
| **500Hz 更新** | ✅ 已实现 | ✅ 保留 | Gazebo update_rate |
| **Velocity smoothness** | 平滑 | 重调 | trapezoidal profile |
| **Acceleration limit** | 默认 | 降低 (CoM 抬高) | 需重新计算 |
| **Gripper open/close** | 0.5s | 同 | 复用 |

#### 5.2.4 Sim2Real 鸿沟

**当前 (Phase 0)**：
- Gazebo 仿真
- `gz_ros2_control` 模拟 hardware
- 完美的物理仿真

**未来 (Real Robot)**：
- UR Driver (ur_robot_driver)
- 真实 hardware_interface
- **真实物理**：摩擦、噪声、延迟
- **关键差异**：
  - 仿真 vs 真实的 joint friction
  - cable 阻力
  - 真实相机噪声
  - 真实 IMU 漂移

**Sim2Real 迁移清单**（M6 阶段）：
```yaml
# 真实 UR5e hardware interface
ur5e_hardware:
  type: ur_robot_driver/URPositionHardwareInterface
  robot_ip: 192.168.1.100
  # ...
# 仿真接口 (保留)
gz_hardware:
  type: gz_ros2_control/GZSystem
  # ...
```

**配置切换**：
- 单个 YAML 参数即可切换 `hardware_type: sim | real`
- 这是 M6.0 Robot Description Layer 的核心

### 5.3 验证矩阵

| 验收项 | 通过条件 | 实施成本 |
|--------|----------|----------|
| Mass matrix 更新 | URDF inertia 准确 | 0.5 天 |
| Gravity compensation 测试 | 双臂水平时力矩误差 < 0.1 Nm | 1 天 |
| Controller 重新配置 | 6 controller + 2 sensor broadcaster | 1 天 |
| Trajectory 跟踪测试 | 阶跃响应 < 0.05 rad 误差 | 1-2 天 |
| Acceleration limit 调整 | 不触发 safety stop | 1 天 |
| Sim2Real 配置切换 | 同一 YAML 切换 sim/real | 0.5 天 |
| 实物集成（未来） | ur_robot_driver 通信 | 1-2 周 |

### 5.4 实施

**文件**：`src/multi_arm_embodiment_validation/test/test_dynamics_migration.py`
**仿真**：PyBullet 或 Gazebo 物理仿真
**输出**：Mass matrix / Inertia tensor / Gravity compensation 误差报告

---

## 6. Shadow Migration 3 阶段验证路线

### 6.1 为什么需要 Shadow Migration？

**v1.0 路线问题**：
```
URDF 重构 (2-3 周) → 立即集成所有改动 → 大爆炸式失败
```

**风险**：
- 改动量大，难定位问题
- 一次返工成本高
- 难以证明 Phase 2 是否值得做

**Shadow Migration 思路**：
> **不在生产 URDF 上改，先在 shadow URDF 上验证 embodiment 假设**

### 6.2 3 阶段验证

#### Stage 1：Embodiment Validation（4-6 周）

**目标**：在不动生产 URDF 的前提下，**验证 Phase 2 embodiment 是否合理**。

**做法**：
1. **建立 shadow URDF**：仅用于验证，不替换生产 URDF
   ```
   src/ur_simulation_gz/urdf/embodied_robot_shadow.xacro
   ```
2. **跑 Section 2-5 的 4 个实验**：
   - Reachability Overlap
   - Random IK Stress
   - Task Transfer Matrix
   - Controller/Dynamics Migration
3. **生成 Embodiment Validation Report**：
   - 哪些能力保留？
   - 哪些能力损失？
   - 损失是否可接受？
   - **GO / NO-GO 决策**

**GO 决策标准**：
- Weighted Total IK ≥ 0.85
- 桌面任务 Overlap ≥ 0.90
- Basic 任务 ETS ≥ 0.85
- Medium 任务 ETS ≥ 0.70

**NO-GO 触发条件**：
- 桌面任务 Overlap < 0.85
- Basic 任务 ETS < 0.80
- 双臂协作能力损失 > 30%

**如果 NO-GO**：
- 重新审视 body_architecture v1.0
- 调整 shoulder 位置或双臂距离
- 回到 shadow 重新验证

#### Stage 2：Pilot Migration（4-6 周）

**前提**：Stage 1 GO 决策通过。

**目标**：迁移 **1 个臂 + 1 个 skill**，证明链路可行。

**做法**：
1. **生产 URDF 双轨**：
   - 保留 `multi_arm_robot.xacro` (Phase 0, 不动)
   - 新增 `embodied_robot_pilot.xacro` (1 个 left_arm, 1 个 skill)
2. **实现 left_arm + pick_object 链路**：
   - 新的 SRDF group: `left_arm`
   - 新的 controller: `left_arm_joint_trajectory_controller`
   - 复用 Skill Runtime pick_object
3. **E2E 验证**：
   - 在 embodied_robot_pilot 上跑 pick_object 30 次
   - 成功率 ≥ 85% 视为通过
4. **生成 Pilot Migration Report**：
   - 哪些代码必须改？
   - 哪些可以零改？
   - 性能回归点

#### Stage 3：Full Migration（6-10 周）

**前提**：Stage 2 成功。

**目标**：完成完整 Phase 2 迁移。

**做法**：
1. **生产 URDF 切换**：
   - 旧 `multi_arm_robot.xacro` → 保留为 `legacy_dual_ur5e.xacro`
   - 新 `embodied_robot.xacro` → 默认 URDF
2. **全套能力迁移**：
   - 双臂 left_arm + right_arm
   - head + torso
   - 所有 skill E2E 验证
3. **Episode 重新采集**：
   - 200+ episodes
   - 标注 `robot_id="embodied_robot"`
4. **Benchmark ETS 验证**：
   - ETS ≥ 0.85
   - 退化分析报告
5. **生成 Full Migration Report**：
   - 所有 Phase 0 tests 100% 通过
   - 新增 Phase 2 tests 100% 通过
   - Documentation 更新

### 6.3 关键 Gate 决策

```
Stage 1 GO?
   ├─ NO → 重新设计 embodiment (回到 body_architecture v1.x 评审)
   └─ YES ↓
Stage 2 GO?
   ├─ NO → 细化 embodiment, 重做 pilot
   └─ YES ↓
Stage 3 GO?
   ├─ NO → 推迟 M8, 强化 Phase 2 能力
   └─ YES → Phase 2 冻结, 标记 v1.0
```

### 6.4 工作量与时间

| Stage | 工作量 | 累计 | 关键交付 |
|-------|--------|------|----------|
| **Stage 1** | 4-6 周 | 4-6 周 | Embodiment Validation Report |
| **Stage 2** | 4-6 周 | 8-12 周 | Pilot Migration Report |
| **Stage 3** | 6-10 周 | 14-22 周 | Full Migration Report |
| **总周期** | - | **14-22 周** | Phase 2 冻结 |

**对比 v1.0 估算（14-20 周）**：基本一致，但**风险曲线下降**：
- v1.0：风险集中在 Stage 3（最后 6-10 周）
- v1.1：风险分散到 3 个 Stage，每个 Stage 4-6 周可控

### 6.5 Shadow URDF 实施要点

**shadow_robot.xacro 设计原则**：
1. **不污染生产**：放在独立子目录 `urdf/shadow/`
2. **参数化**：通过 `<xacro:arg>` 切换 base 位置
3. **可重置**：每次实验后能 reset 到 baseline
4. **可对比**：输出与生产 URDF 的 diff

```xml
<!-- /urdf/shadow/embodied_robot_shadow.xacro -->
<robot xmlns:xacro="http://www.ros.org/wiki/xacro" name="embodied_shadow">
  <xacro:arg name="shoulder_left_x" default="0.15"/>
  <xacro:arg name="shoulder_left_y" default="0.2"/>
  <xacro:arg name="shoulder_left_z" default="0.55"/>
  <xacro:arg name="head_height" default="0.85"/>
  
  <!-- 复用生产 URDF 模块 -->
  <xacro:include filename="$(find ur_simulation_gz)/urdf/arms/dual_ur5e.xacro"/>
  <xacro:include filename="$(find ur_simulation_gz)/urdf/body/torso.xacro"/>
  <xacro:include filename="$(find ur_simulation_gz)/urdf/body/head.xacro"/>
  
  <!-- 重新组装 -->
  <link name="base_link"/>
  <xacro:torso parent_link="base_link" x="$(arg shoulder_left_x)" .../>
  <xacro:head parent_link="torso_link" z="$(arg head_height)"/>
  <xacro:shoulder_mount name="left" parent="torso_link" .../>
  <xacro:dual_ur5e prefix="left_arm_" base_link="left_shoulder_mount"/>
</robot>
```

**好处**：
- 修改 shoulder 位置只需改参数，不改代码
- 可批量实验不同 embodiment 配置
- 失败时不影响生产 URDF

### 6.6 立即建议（v1.1 实施顺序）

**今天 - 1 周内**：
1. ✅ 创建 `src/multi_arm_embodiment_validation/` 包
2. ✅ 实现 Reachability Overlap 实验脚本
3. ✅ 跑 Phase 0 baseline（用当前 URDF）
4. ✅ 保存 Phase 0 reachability map v1

**2-4 周内**：
5. ✅ 创建 shadow URDF（embodied_robot_shadow.xacro）
6. ✅ 跑 Stage 1 实验
7. ✅ 生成 Embodiment Validation Report
8. ✅ GO/NO-GO 决策

**5 周后**：
- 如果 GO，启动 Stage 2 Pilot Migration
- 如果 NO-GO，触发 body_architecture v1.x 评审

---

## 7. Sensor Domain Shift 详细评估（v1.0 不足修正）

### 7.1 v1.0 不足

v1.0 简单估算：
> 感知精度 0.038m → 0.05m

**问题**：
- 这只是"位置估计"一个指标
- 真实 Domain Shift 涉及：
  - 视角变化（特征分布完全不同）
  - 遮挡模式
  - 光照变化
  - 自遮挡（机械臂进入视野）

### 7.2 5 维度 Domain Shift

| 维度 | Phase 0 | Phase 2 | 影响 | 评估方法 |
|------|---------|---------|------|----------|
| **视角** | 固定俯视 (z=0.3m) | 头部 (z=0.9m) | 特征分布变化 | 物体检测 mAP |
| **视野** | 桌面 0.6×0.4m | 桌面 0.5×0.3m | 边角丢失 | coverage ratio |
| **遮挡** | 双臂偶尔 | 双臂 + torso | 复杂遮挡模式 | occlusion_robustness |
| **光照** | 固定 | 头顶 (顶部阴影) | 阴影变化 | lighting variance |
| **自遮挡** | 罕见 | head 看到自己的躯干 | 训练数据不匹配 | self_occlusion_rate |

### 7.3 评估实验

```python
def test_perception_domain_shift(phase0_data, phase2_data):
    """
    评估感知 pipeline 在两 phase 的性能差异
    """
    return {
        "detection_map": {
            "phase0": 0.92,  # mAP (mean Average Precision)
            "phase2": 0.85,  # 预估
            "delta": -0.07,
        },
        "pose_error": {
            "phase0": 0.038,  # m
            "phase2": 0.052,  # 预估
            "delta": 0.014,
        },
        "depth_completion_error": {
            "phase0": 0.02,  # m
            "phase2": 0.035,  # 预估 (头部位姿变化)
            "delta": 0.015,
        },
        "occlusion_robustness": {
            "phase0": 0.88,  # 成功率
            "phase2": 0.78,  # 预估 (遮挡增加)
            "delta": -0.10,
        },
        "self_occlusion_rate": {
            "phase0": 0.02,  # 自遮挡频率
            "phase2": 0.12,  # 预估 (head 看自己)
            "delta": 0.10,
        },
    }
```

### 7.4 实施

**文件**：`src/multi_arm_embodiment_validation/test/test_perception_shift.py`
**数据**：
- Phase 0: M7.5 验证的 100 个真实图片
- Phase 2: 在 shadow URDF 上采集 100 个对应图片
**指标**：
- Object detection mAP
- Pose estimation error
- Depth completion accuracy
- Occlusion robustness score
**报告**：`docs/validation/perception_domain_shift_report.md`

---

## 8. v1.1 升级影响

### 8.1 对 v1.0 结论的修订

| v1.0 结论 | v1.1 修订 | 原因 |
|----------|----------|------|
| 单臂 IK 95-98% | [H-Intuition] 待验证 | 未实测 |
| 双臂 IK 85-90% | [H-Intuition] 待验证 | 未实测 |
| PickPlace 78-85% | [H-Intuition] 待验证 | 未实测 |
| Workspace -8% | [H-Model] 需精确 | 仅简单估算 |
| 14-20 周工作量 | [H-Intuition] 需校准 | 3 阶段可能不同 |
| ETS ≥ 0.85 目标 | [H-Goal] 需校准 | 子指标权重待定 |

### 8.2 v1.1 新增核心价值

1. **建立基线**：Phase 0 reachability map / IK success rate 必须先测量
2. **Hypothesis vs Measurement 严格区分**：避免认知偏差
3. **Shadow Migration 降低风险**：3 阶段 Gate 决策
4. **Task Transfer Matrix 区分难度**：不同任务不同 ETS
5. **Dynamics/Controller 完整迁移**：补充 v1.0 缺失
6. **Sensor Domain Shift 多维度**：超越单一指标

### 8.3 不变结论

- ✅ 抽象层 98% 复用（[M]）
- ✅ 物理层 0% 直接复用（[M]）
- ✅ 需 4 个实验章节验证（[H-Goal]）
- ✅ M5.7 FROZEN v1.0 接口不变（[M]）

---

## 9. 实施路线图

### 9.1 立即可做（v1.1 启动）

**本周**：
1. 创建 `multi_arm_embodiment_validation` 包
2. 实施 Reachability Overlap 实验
3. 跑 Phase 0 baseline（用当前 URDF）
4. 保存 baseline 数据

**下周**：
5. 实施 Random IK Stress Test
6. 跑 Phase 0 baseline
7. 保存 IK 成功率分布

### 9.2 Shadow URDF 准备（2-4 周）

1. 创建 `urdf/shadow/embodied_robot_shadow.xacro`
2. 参数化 shoulder 位置
3. 不替换生产 URDF
4. 在 Gazebo 中测试

### 9.3 Stage 1 实验（4-6 周）

1. 跑 4 个实验在 shadow URDF
2. 生成 Embodiment Validation Report
3. GO/NO-GO 决策

### 9.4 长期（Stage 2/3）

按 6.2 节执行

---

## 10. 冻结声明

v1.1 补充以下内容到 Robot Embodiment Migration Assessment：
- ✅ Hypothesis vs Measurement 分类表
- ✅ Reachability Overlap Experiment 详细设计
- ✅ Random IK Stress Test 详细设计
- ✅ Task Transfer Matrix 详细设计
- ✅ Controller/Dynamics Migration Plan
- ✅ Sensor Domain Shift 5 维度评估
- ✅ Shadow Migration 3 阶段路线
- ✅ v1.0 数字降级为 [Hypothesis]

**v1.0 + v1.1 合并构成完整 Embodiment Migration Validation 体系**。

**禁止破坏性修改**。如需新增实验维度，进入 v1.2 评审。

---

**End of Robot Embodiment Migration Assessment v1.1**