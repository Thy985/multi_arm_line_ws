# PRD - 双UR5e多机械臂系统后续开发需求文档

| 字段 | 内容 |
|------|------|
| 版本 | v2.1 |
| 作者 | Thy985 |
| 日期 | 2026-08-05 |
| 状态 | Draft |
| 关联架构 | Architecture-MultiArm-202608051018.md v2.1 |

---

## 1. 背景与目标

当前双UR5e多机械臂ROS2仿真系统已完成基础功能。目标架构为7层功能层 + Safety横切平面，需逐步演进。

### 目标

1. 拆分Coordinator为编排引擎+子模块
2. 建立multi_arm_interfaces接口包
3. 实现WorldModel环境认知真相源
4. 集成MoveIt2 + Safety Plane
5. BehaviorTree.CPP任务规划 + Pick-Place
6. Recovery故障恢复 + Benchmark场景化
7. 虚实同步

---

## 2. 功能需求

### P0 - 基础重构

**FR-01: 接口包 + Coordinator拆分**
- multi_arm_interfaces: TaskDescription/TaskStatus/TaskRequirement拆分消息
- Coordinator仅编排，逻辑在ResourceManager/Scheduler/TaskManager
- 跨包通信走interfaces，禁止Python类共享

**FR-02: ResourceManager + CapabilityMatcher**
- 统一管理Robot/Zone/Tool/Sensor/Fixture五类资源
- CapabilityMatcher按任务需求匹配资源能力
- robots.yaml驱动，新增臂不改代码

### P1 - 安全+规划

**FR-03: Safety Plane横切安全**
- SafetySupervisor独立，横切L1-L7
- 对Task层: SafetyCheck.srv; 对Motion层: 碰撞检测; 对Control层: 速度限制+E-Stop
- 分阶段实现: 软件Check→Proxy→Hardware

**FR-04: MoveIt2多臂规划**
- SRDF双臂规划组，单臂<500ms，双臂<2s
- 替换硬编码，失败回退

### P2 - 环境+任务

**FR-05: WorldModel环境认知真相源**
- 拥有Objects/Environment/TaskContext，缓存Robot State(1-10Hz)
- 500Hz joint_states不进WorldModel

**FR-06: TaskPlanner + BehaviorTree.CPP**
- BT XML定义 + Python插件，不自造轮子
- Groot可视化/调试/在线修改

**FR-07: 夹爪 + Pick-Place**
- Robotiq 2F-85 + BT编排执行
- 抓取失败触发Recovery

### P3 - 恢复+工程化

**FR-08: Recovery故障恢复**
- 4种策略: GraspRetry/ReplanMotion/CommunicationReset/CollisionRecovery
- 集成到BT RecoverNode

**FR-09: Benchmark场景化**
- YAML场景定义 + 自动运行 + SQLite存储

**FR-10: CI/CD + 虚实同步**
- GitHub Actions + use_sim切换 + 安全降级

---

## 3. 非功能需求

| 编号 | 需求 | 指标 |
|------|------|------|
| NFR-01 | 状态机tick延迟 | < 10ms |
| NFR-02 | MoveIt2单臂规划 | < 500ms |
| NFR-03 | MoveIt2双臂规划 | < 2s |
| NFR-04 | E-Stop响应 | < 1s |
| NFR-05 | 碰撞检测响应 | < 50ms |
| NFR-06 | 连续运行 | > 72h |
| NFR-07 | 故障自动恢复 | < 10s |
| NFR-08 | 测试覆盖率 | > 80% |
| NFR-09 | 新增臂代码修改 | 0行 |

---

## 4. 里程碑

| 阶段 | 内容 |
|------|------|
| M1 | interfaces + core拆分 + ResourceManager + YAML化 |
| M2 | Safety Plane + MoveIt2 |
| M3 | WorldModel + BT.CPP + 夹爪 |
| M4 | Recovery + Benchmark + CI/CD + 虚实同步 |
| M5 | 学习调度 + 多相机 + 动态臂 + 实体部署 |
