# M5.7 Interface & Architecture Audit — 验证报告

## 目标

系统性盘点接口，冻结下一阶段演进接口（API Freeze / Architecture Review / ICD）。

## 五项审计

### 1. 接口资产盘点

**产出**: `docs/architecture/interface_catalog.md`

| 接口类型 | 总数 | FROZEN | EXPERIMENTAL | RESERVED |
|----------|------|--------|--------------|----------|
| Action | 2 | 1 | 1 | 0 |
| Service | 5 | 4 | 1 | 0 |
| Topic (内部) | 5 | 3 | 0 | 1 |
| Topic (外部) | 2 | 0 | 0 | 0 |
| 外部Action | 2 | 0 | 0 | 0 |
| 外部Service | 2 | 0 | 0 | 0 |
| **总计** | **18** | **8** | **2** | **1** |

### 2. 数据模型清算

**产出**: `docs/architecture/api_contracts.md`

冻结的核心数据结构 (v1.0):
- TaskGoal.msg — 任务目标领域模型
- TaskConstraint.msg — 任务约束
- ExecuteTask.action — 任务执行Action
- SafetyCheck.srv — 安全审批Service
- EmergencyStop.srv — 紧急停止
- QueryResources.srv — 资源查询
- RecoverFromFailure.srv — 恢复请求
- CollisionEvent.msg — 碰撞事件
- ObjectPose.msg — 物体位姿
- ResourceStatus.msg — 资源状态
- RecoveryAction.msg — 恢复动作
- SystemHealth.msg — 系统健康
- MotionRequest.msg — 运动请求
- PRESET_POSITIONS — 9个预设位置

### 3. 模块边界审计

**产出**: `docs/architecture/dependency_graph.md`

7层架构映射:
```
L7 应用层:        (BT XML表达)
L6 任务规划层:    multi_arm_task_planner
L5 环境模型层:    multi_arm_world_model
L4 协调层:        multi_arm_core
L3 运动规划层:    multi_arm_moveit_config
L2 控制层:        ros2_control + JTC
L1 硬件层:        ur_simulation_gz
Safety Plane:    multi_arm_safety
System Services: multi_arm_interfaces, multi_arm_recovery, multi_arm_benchmark
```

边界审计结果:
| 检查项 | 结果 |
|--------|------|
| TaskPlanner不直连ros2_control | ✅ PASS |
| Coordinator不直连Gazebo | ✅ PASS |
| Safety不依赖Core | ✅ PASS |
| WorldModel不依赖Core | ✅ PASS |
| Recovery不依赖TaskPlanner | ✅ PASS |
| BT插件直连SafetyCheck | ⚠️ 越层(接受) |
| BT插件直连QueryResources | ⚠️ 越层(接受) |

### 4. M6/M7接口预留

| 预留接口 | 用途 | 接入方式 |
|----------|------|----------|
| /perception/object_poses | M6.1感知 | WorldModel已订阅 |
| SceneUpdate.msg | M6.2世界模型 | 新增msg |
| ExecuteSkill.action | M6.3 Skill | 新增action |
| SubmitNaturalLanguage.srv | M7 Agent | 新增srv |
| ExecuteAgentGoal.action | M7 Agent | 新增action |

### 5. 版本治理

**Interface Freeze v1.0**:
- 13个核心数据结构冻结
- 3个Topic冻结
- 禁止破坏性修改（删除/修改/重命名字段）
- 允许兼容性新增（末尾追加字段+默认值）
- CI interface-compat检查保障

## 已知偏差 (Accepted Deviations)

1. **BT插件越层调用**: TaskPlanner BT插件直接调用SafetyCheck/QueryResources（L6→Safety/L5），为只读查询避免Coordinator瓶颈，接受
2. **RecoveryManager非ROS2节点**: 纯Python模块，RecoverFromFailure.srv预留为M6分布式接口
3. **SafetyCheck不可用默认批准**: Coordinator在Safety服务不可用时默认批准运动，M6需改为默认拒绝

## 产出文件

| 文件 | 说明 |
|------|------|
| `docs/architecture/interface_catalog.md` | 18个接口盘点+版本治理规则 |
| `docs/architecture/data_flow.md` | 8个数据流图+QoS策略+时序约束 |
| `docs/architecture/dependency_graph.md` | 7层映射+依赖矩阵+边界审计 |
| `docs/architecture/api_contracts.md` | 接口契约+数据模型冻结+M6/M7预留 |

## 验收状态

| 验收项 | 状态 |
|--------|------|
| 接口资产盘点 | ✅ 18个接口 |
| 数据模型冻结 | ✅ 13个FROZEN v1.0 |
| 模块边界审计 | ✅ 2处已知偏差 |
| M6/M7接口预留 | ✅ 4组预留 |
| 版本治理 | ✅ Interface Freeze v1.0 |

## 系统定位

> M5.7完成了Interface Freeze v1.0，为M6 Perception+Sim2Real和M7 Embodied Agent奠定了接口基础。系统从"能完成任务且鲁棒"进化到"接口稳定可扩展"。