# M7.0 Foundation 验证报告

**日期**: 2026-08-10
**状态**: ✅ 全部完成
**测试**: 207 tests ALL PASS (86 new + 121 existing)

---

## 概览

M7.0 Foundation为M7 Embodied Manipulation Platform奠定基础，包含4个子阶段：

| 子阶段 | 内容 | 新测试 | 现有测试 | 状态 |
|--------|------|--------|----------|------|
| M7.0.1 | Robot Description Refactor (URDF模块化) | 27 | 28 | ✅ |
| M7.0.2 | WorldModel Schema (5层+时间维度) | 19 | 63 | ✅ |
| M7.0.3 | Capability Graph (声明层) | 26 | 30 | ✅ |
| M7.0.4 | Base Interface (契约定义) | 14 | 0 | ✅ |
| **总计** | | **86** | **121** | **✅** |

---

## M7.0.1 Robot Description Refactor

**目标**: 将337行单文件`multi_arm_robot.xacro`拆分为模块化URDF结构。

**成果**:
- 13个模块化xacro文件，按功能分组到7个子目录
- `robot.xacro`作为新顶层入口点
- `multi_arm_robot.xacro`保留为向后兼容wrapper
- 占位宏模式（torso/head/imu）为M7.1/M7.4预留扩展点

**URDF验证**: 48 links, 61 joints, 20 revolute, 6 mimic, 14 ros2_control joints, check_urdf ✅

---

## M7.0.2 WorldModel Schema

**目标**: 为WorldModel添加时间维度和不确定性字段。

**成果**:
- `ObjectState.msg`扩展: observed_at, updated_at, ttl, position_covariance[9], orientation_uncertainty
- `Relation.msg`扩展: ttl
- `QueryWorld.srv`扩展: at_time（时间查询）
- `TrackedObject` dataclass扩展: 5个新字段
- `is_stale()`方法使用ttl优先策略
- `update_object_pose()`自动填充observed_at/updated_at

**接口合规**: Tier 2扩展（追加可选字段，不破坏已有字段）✅

---

## M7.0.3 Capability Graph

**目标**: 从扁平字典升级为声明层图结构，支持依赖/组合/冲突。

**成果**:
- `capability.yaml`扩展: requires, composed_of, conflicts_with字段
- `CapabilityInfo.msg`扩展: 3个图字段
- `Capability` dataclass扩展: 3个图字段
- 图查询API: `get_dependencies()`, `get_dependents()`, `is_satisfied()`, `get_conflicts()`
- 失败传播: `propagate_failure()`递归标记依赖者为不可用

**关键关系**:
- manipulation requires arm_reachable
- skills requires manipulation + gripper
- force_control conflicts_with manipulation
- can_grasp requires gripper
- can_reach requires manipulation

---

## M7.0.4 Base Interface

**目标**: 定义移动底盘接口契约（cmd_vel/odom/tf），轮子仍fixed。

**成果**:
- `BaseState.msg`新增: position, orientation, linear/angular_velocity, is_moving, steering_mode
- `base_interface.yaml`契约配置: TF frames, topics, wheels, differential drive params, safety
- 契约一致性验证: wheel names匹配URDF, base_frame匹配URDF, mobile capability匹配config

**M7.0状态**: steering_mode=fixed, is_movable=false, wheels joint_type=fixed
**M7.6将激活**: steering_mode=differential, is_movable=true, wheels joint_type=revolute

---

## 接口变更汇总

| 接口 | 变更类型 | 新增字段 | 冻结层级 |
|------|----------|----------|----------|
| ObjectState.msg | Tier 2扩展 | observed_at, updated_at, ttl, position_covariance[9], orientation_uncertainty | Tier 2 |
| Relation.msg | Tier 2扩展 | ttl | Tier 2 |
| QueryWorld.srv | 请求扩展 | at_time | - |
| CapabilityInfo.msg | 扩展 | requires[], composed_of[], conflicts_with[] | - |
| BaseState.msg | 新增 | (全部) | 不受冻结 |

**向后兼容**: 所有扩展均为追加可选字段，默认值为0/空，不影响现有消费者 ✅

---

## 为后续阶段奠定基础

| 后续阶段 | M7.0提供 | 扩展方式 |
|----------|----------|----------|
| M7.1 Body | torso.xacro + head.xacro占位 | 填充宏内容 |
| M7.2 Scene | WorldModel时间维度 | 场景资产有时间戳 |
| M7.4 Perception | imu.xacro占位 + camera.xacro | 填充IMU + 多相机 |
| M7.5 Skill Evolution | Capability Graph | Skill依赖Capability图 |
| M7.6 Navigation | Base Interface契约 | 激活differential drive |