# LLD - MoveIt2规划与Safety Plane模块详细设计

| 字段 | 内容 |
|------|------|
| 版本 | v2.1 |
| 作者 | Thy985 |
| 日期 | 2026-08-05 |
| 状态 | Draft |
| 关联架构 | Architecture-MultiArm-202608051018.md v2.1 |

---

## 1. 模块概述

MoveIt2多臂运动规划 + Safety Plane横切安全。Safety重构为横切平面，分阶段实现（软件Check→Proxy→Hardware）。

---

## 2. MoveIt2集成

### SRDF规划组

left_arm / right_arm / both_arms 三组，disable_collisions定义ACM。

### MoveItPlanner接口

```python
class MoveItPlanner:
    def plan_to_position(arm_name, position_name, planning_time=2.0) -> PlanResult
    def plan_to_pose(arm_name, pose, planning_time=2.0) -> PlanResult
    def plan_both_arms(arm1_target, arm2_target) -> Tuple[PlanResult, PlanResult]
    def check_collision(joint_positions) -> bool
```

### 协调器编排

```
plan = planner.plan_to_position(arm, target)
if plan.success:
    approved, scale = safety_interface.check(arm, plan.trajectory)
    if approved: send_trajectory(arm, plan.trajectory, speed_scale=scale)
else: fallback_to_preset(arm, target)
```

---

## 3. Safety Plane

### 横切架构

```
SafetySupervisor (独立节点，不依赖Coordinator)
├── L6 Task: SafetyCheck.srv (任务可行性)
├── L3 Motion: CollisionMonitor (碰撞检测)
└── L2 Control: SpeedLimiter + WorkspaceLimiter + E-Stop
```

### 分阶段实现

| Phase | 方案 | 说明 |
|-------|------|------|
| 1-2 | SafetyCheck Service | Coordinator发送前调用，非硬实时 |
| 3+ | Safety Proxy | Action拦截+转发 |
| 实体 | Hardware Safety | ros2_control层硬实时 |

### SafetyInterface（Coordinator侧）

```python
class SafetyInterface:
    def check(arm_name, trajectory) -> Tuple[bool, float]:
        """调用SafetyCheck.srv，返回(approved, speed_scale)"""
```

### SafetySupervisor（独立侧）

```python
class SafetySupervisor(Node):
    # 直接订阅joint_states（不经Coordinator）
    # SafetyCheck.srv: 检查E-Stop+速度+边界
    # EmergencyStop.srv: 触发/释放E-Stop
    # /safety/status: 发布安全等级
    # /safety/collision_events: 发布碰撞事件
```

### 安全层级

0:NORMAL → 1:SPEED_LIMITED → 2:PAUSED → 3:EMERGENCY_STOP

---

## 4. 错误处理

| 场景 | 处理 |
|------|------|
| MoveIt2规划超时 | 回退硬编码 |
| SafetyCheck拒绝 | 日志+通知Coordinator |
| E-Stop激活 | 拒绝所有命令 |
| SafetySupervisor crash | Coordinator降级+WARN |

---

## 5. 测试要点

test_planner_fallback / test_safety_check / test_estop / test_safety_independent / test_collision / test_dual_arm_plan
