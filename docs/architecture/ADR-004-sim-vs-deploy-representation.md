# ADR-004: Simulation Representation vs Deployment Representation Separation

**Status**: Accepted
**Date**: 2026-08-05
**Context**: M4.5 Motion + Coordination Validation

## Context

M4.5暴露了一个架构问题：Gazebo仿真架构与MoveIt2规划架构不兼容。

### Gazebo世界（M4验证用）

```
Entity: arm1 (ur_gz.urdf.xacro)
Entity: arm2 (ur_gz.urdf.xacro)
CM: /arm1/controller_manager
CM: /arm2/controller_manager
JTC: /arm1/joint_trajectory_controller
JTC: /arm2/joint_trajectory_controller
JSB: /arm1/joint_states, /arm2/joint_states
```

优势：接近真实工业部署，每个机器人独立生命周期。

### MoveIt2世界（M4.5验证用）

```
Entity: multi_arm (multi_arm_robot.xacro)
CM: /controller_manager (根)
JTC: /arm1_joint_trajectory_controller
JTC: /arm2_joint_trajectory_controller
JSB: /joint_states
Planning groups: arm1, arm2, dual_arm
```

优势：多机械臂规划简单，collision checking自然，single planning scene。

### 问题

MoveIt2要求single robot_description包含所有机械臂关节。这导致：

1. 仿真必须用合并URDF（multi_arm_robot.xacro）
2. 但真实部署应该是独立控制器架构（每个UR5e + ur_robot_driver）
3. 扩展机器人数量时，合并URDF会变得不可维护

## Decision

**分离仿真表示与部署表示**：

1. **仿真层**：允许使用合并URDF + 单CM架构，简化MoveIt2集成
2. **部署层**：保持多控制器架构，每个机器人独立生命周期
3. **参数YAML驱动**：通过YAML配置切换仿真/实体模式，仅hardware_interface不同
4. **MoveIt2适配**：MoveIt2始终使用合并robot_description，但执行层通过命名空间映射到正确的控制器

### 架构映射

```
仿真模式:
  Gazebo entity: multi_arm (合并URDF)
  CM: /controller_manager
  MoveIt2: /move_group → /arm1_joint_trajectory_controller/follow_joint_trajectory

部署模式:
  Hardware: arm1_driver + arm2_driver
  CM: /arm1/controller_manager + /arm2/controller_manager
  MoveIt2: /move_group → /arm1/joint_trajectory_controller/follow_joint_trajectory
```

### 关键约束

- MoveIt2的robot_description始终包含所有机械臂（规划需要全局collision checking）
- 控制器命名空间通过参数YAML配置，不硬编码
- WorldModel从/joint_states读取，不关心底层是仿真还是实体
- SafetySupervisor通过controller_manager服务操作，命名空间通过参数配置

## Consequences

### 正面

- 仿真简洁：单entity + 单CM + MoveIt2直接兼容
- 部署灵活：每个UR5e独立driver + 独立CM
- 扩展性好：新增机械臂只需更新YAML + URDF宏
- 架构一致：WorldModel/Safety/Coordinator层与底层表示解耦

### 负面

- 两种架构需要维护两套控制器YAML
- MoveIt2的moveit_controllers.yaml需要根据模式切换action_ns
- 测试需要覆盖两种模式

### 缓解

- 参数YAML统一：`sim_controllers.yaml` vs `real_controllers.yaml`
- Launch文件通过`use_sim_time`+`simulation`参数自动选择配置
- CI/CD覆盖两种模式的smoke test