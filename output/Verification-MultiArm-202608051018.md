# 验收文档 - 双UR5e多机械臂ROS2仿真系统

| 字段 | 内容 |
|------|------|
| 版本 | v2.1 |
| 作者 | Thy985 |
| 日期 | 2026-08-05 |
| 状态 | Draft |
| 关联架构 | Architecture-MultiArm-202608051018.md v2.1 |

---

## 1. 基线验收（已完成功能）

| 编号 | 验收项 | 状态 |
|------|--------|------|
| B-01~B-06 | 双臂Gazebo仿真环境 | ✅ |
| B-07~B-13 | 多臂协调控制 | ✅ |
| B-14~B-20 | 诊断与日志 | ✅ |
| B-21~B-26 | 测试套件(82项) | ✅ |

---

## 2. 增量验收（后续开发）

### M1: 接口包 + Coordinator拆分 + ResourceManager

| 编号 | 验收项 | 通过条件 |
|------|--------|----------|
| I-01 | multi_arm_interfaces构建 | ament_cmake构建成功 |
| I-02 | Task消息拆分 | TaskDescription/TaskStatus/TaskRequirement独立msg |
| I-03 | Coordinator拆分 | coordinator_node仅编排，逻辑在子模块 |
| I-04 | 跨包通信走interfaces | 无Python类直接共享 |
| I-05 | ResourceManager 5类资源 | Robot/Zone/Tool/Sensor/Fixture统一管理 |
| I-06 | CapabilityMatcher | 按需求匹配资源能力 |
| I-07 | robots.yaml驱动 | 新增臂仅改YAML不改代码 |
| I-08 | Zone兼容 | Zone Manager包装为ResourceManager特例 |

### M2: Safety Plane + MoveIt2

| 编号 | 验收项 | 通过条件 |
|------|--------|----------|
| I-09 | SafetySupervisor独立 | 不依赖Coordinator可运行 |
| I-10 | Safety横切L6 | SafetyCheck.srv任务可行性检查 |
| I-11 | Safety横切L3 | 碰撞检测+CollisionEvent发布 |
| I-12 | Safety横切L2 | 速度限制+工作空间边界+E-Stop |
| I-13 | E-Stop响应 | 所有臂停止<1s |
| I-14 | E-Stop拒绝新命令 | 命令返回False |
| I-15 | Safety独立于Coordinator | Coordinator crash后Safety仍运行 |
| I-16 | MoveIt2单臂规划 | <500ms (P95) |
| I-17 | MoveIt2双臂规划 | <2s (P95) |
| I-18 | 规划失败回退 | 回退到硬编码预设位置 |
| I-19 | RViz轨迹可视化 | 规划轨迹正确显示 |

### M3: WorldModel + BT.CPP + 夹爪

| 编号 | 验收项 | 通过条件 |
|------|--------|----------|
| I-20 | WorldModel拥有Objects | 物体位姿/类型/置信度可查询 |
| I-21 | WorldModel所有权边界 | 500Hz joint_states不进WorldModel |
| I-22 | WorldModel缓存Robot State | 1-10Hz缓存，供上层查询 |
| I-23 | ObjectTracker | 物体ID关联+运动预测 |
| I-24 | BT XML加载 | pick_place.xml行为树可执行 |
| I-25 | BT Python插件 | MoveTo/Grasp/Place/CheckSafety插件工作 |
| I-26 | Groot可视化 | 行为树可在Groot中查看/编辑 |
| I-27 | BT子树复用 | 子树可组合复用 |
| I-28 | 夹爪URDF+Gazebo | Robotiq 2F-85模型加载 |
| I-29 | 夹爪开合控制 | gripper_controller正常 |
| I-30 | BT Pick-Place | 完整流程通过BT编排执行 |

### M4: Recovery + Benchmark + CI/CD + 虚实同步

| 编号 | 验收项 | 通过条件 |
|------|--------|----------|
| I-31 | GraspRetry | 抓取失败自动重试(换approach) |
| I-32 | ReplanMotion | 规划失败放宽约束重规划 |
| I-33 | CollisionRecovery | 碰撞→退回安全位→更新WorldModel→重规划 |
| I-34 | Recovery集成BT | RecoverNode插件工作 |
| I-35 | 3次失败AbortTask | 重试3次后任务中止 |
| I-36 | Benchmark场景 | YAML场景定义+自动运行 |
| I-37 | Benchmark记录 | planning_time/execution_time/collision_count记录到SQLite |
| I-38 | CI自动触发 | push/PR自动运行 |
| I-39 | CI门禁 | lint+build+test全通过 |
| I-40 | use_sim切换 | true=仿真, false=实体 |
| I-41 | 实体安全降级 | 速度限制50% |

### M5: 高级特性

| 编号 | 验收项 | 通过条件 |
|------|--------|----------|
| I-42 | 学习型调度 | Benchmark数据驱动调度优化 |
| I-43 | 多相机融合 | 多相机数据融合到WorldModel |
| I-44 | 动态臂增减 | 运行时添加arm3 |
| I-45 | Hardware Safety | 实体模式ros2_control层安全 |
| I-46 | 产线连续作业 | 100次Pick-Place成功率>90% |

---

## 3. 非功能验收

| 编号 | 指标 | 通过条件 |
|------|------|----------|
| NF-01 | 状态机tick | < 10ms (P99) |
| NF-02 | MoveIt2单臂规划 | < 500ms (P95) |
| NF-03 | MoveIt2双臂规划 | < 2s (P95) |
| NF-04 | E-Stop响应 | < 1s |
| NF-05 | 碰撞检测 | < 50ms |
| NF-06 | 连续运行 | > 72h无崩溃 |
| NF-07 | 故障自动恢复 | < 10s |
| NF-08 | 测试覆盖率 | > 80% |
| NF-09 | 新增臂代码修改 | 0行 |

---

## 4. 验收流程

| 阶段 | 验收范围 | 编号 |
|------|----------|------|
| 基线 | 已完成功能 | B-01~B-26 |
| M1 | 接口+拆分+资源 | I-01~I-08 |
| M2 | Safety+MoveIt2 | I-09~I-19 |
| M3 | WorldModel+BT+夹爪 | I-20~I-30 |
| M4 | Recovery+Benchmark+CI | I-31~I-41 |
| M5 | 高级特性 | I-42~I-46 |

**判定**：✅全部通过 / ⚠️≤2项非功能不满足 / ❌任何功能项失败

---

## 5. 回归测试

每次M阶段验收后回归：构建+单元测试+仿真启动+协调控制+诊断日志
