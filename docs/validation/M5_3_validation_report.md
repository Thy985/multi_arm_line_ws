# M5.3 Task Message Upgrade — 验证报告

## 目标

将`description="arm1:zone_a:ready"`字符串协议升级为结构化领域模型（TaskGoal），提高类型安全性和可扩展性，同时保持向后兼容。

## 问题

当前ExecuteTask.action的`description`字段使用冒号分隔的字符串格式（如`"arm1:zone_a:ready"`），存在以下问题：
- 无类型安全，字段含义靠约定
- 无法表达约束（优先级、安全级别、超时等）
- 难以扩展新字段
- 解析逻辑分散在Coordinator._parse_task()中

## 架构设计

### 新增消息类型

```
TaskGoal.msg
├── action_type         # "move", "pick_place", "grasp", "place", "lift", "retract", "inspect"
├── arm_name            # "arm1", "arm2"
├── zone_name           # "zone_a", "zone_b"
├── position_name       # "home", "ready", "scan"
├── object_id           # "red_cube", "blue_box"
├── approach            # "top", "side", "front"
└── constraints         # TaskConstraint

TaskConstraint.msg
├── max_time            # 最大执行时间（秒）
├── safety_level        # 0=normal, 1=strict, 2=critical
├── priority            # 0=low, 1=normal, 2=high, 3=critical
├── allow_recovery      # 是否允许恢复
└── max_retries         # 最大重试次数

MotionRequest.msg
├── arm_name            # 目标臂
├── target_position     # 命名目标
├── joint_positions     # 关节位置（替代命名目标）
├── use_named_target    # True=命名目标, False=关节位置
├── speed_scale         # 速度缩放（0.0-1.0）
├── collision_check     # 是否碰撞检测
└── max_velocity        # 最大关节速度
```

### ExecuteTask.action扩展

```
string task_id
string task_type
string description                # Legacy: "arm1:zone_a:ready" (backward compatible)
multi_arm_interfaces/TaskGoal goal # Structured task goal (preferred)
---
bool success
string message
---
string status
float32 progress
string error_message
```

### Coordinator解析优先级

```python
# _on_execute_task()
task_goal = getattr(goal, 'goal', None)

if task_goal is not None and task_goal.arm_name:
    # 优先使用结构化TaskGoal
    arm_name, zone_name, position_name = self._parse_task_goal(task_goal)
else:
    # 向后兼容：解析字符串
    arm_name, zone_name, position_name = self._parse_task(task_type, description)
```

### TaskPlanner Blackboard传播

```python
# _on_execute_task() in TaskPlannerNode
task_goal = getattr(goal, 'goal', None)
if task_goal is not None and task_goal.arm_name:
    bb.set("arm_name", task_goal.arm_name)
    bb.set("target_zone", task_goal.zone_name)
    bb.set("target_position", task_goal.position_name)
    bb.set("object_id", task_goal.object_id)
    bb.set("approach", task_goal.approach)
    bb.set("target_goal", f"{arm}:{zone}:{pos}")
    bb.set("task_goal", task_goal)
```

### BT插件构造结构化Goal

```python
# AsyncMoveToNode._send_request()
goal = ExecuteTask.Goal()
goal.task_id = f"bt_move_{ts}"
goal.task_type = "move"
goal.description = f"{arm}:{zone}:{target}"  # 向后兼容

task_goal = TaskGoal()
task_goal.action_type = "move"
task_goal.arm_name = arm
task_goal.zone_name = zone
task_goal.position_name = target
task_goal.constraints = TaskConstraint()
task_goal.constraints.safety_level = 0
task_goal.constraints.priority = 1
task_goal.constraints.allow_recovery = True
task_goal.constraints.max_retries = 3
goal.goal = task_goal
```

## 新增文件

| 文件 | 说明 |
|------|------|
| `src/multi_arm_interfaces/msg/TaskGoal.msg` | 结构化任务目标消息 |
| `src/multi_arm_interfaces/msg/TaskConstraint.msg` | 任务约束消息 |
| `src/multi_arm_interfaces/msg/MotionRequest.msg` | 运动请求消息 |
| `src/multi_arm_core/test/test_task_goal.py` | M5.3单元测试 (21 tests) |

## 修改文件

| 文件 | 变更 |
|------|------|
| `multi_arm_interfaces/CMakeLists.txt` | 新增3个msg到rosidl_generate_interfaces |
| `multi_arm_interfaces/action/ExecuteTask.action` | 新增`TaskGoal goal`字段 |
| `coordinator_node.py` | 新增`_parse_task_goal()` + `_on_execute_task`优先使用TaskGoal |
| `task_planner_node.py` | 从TaskGoal字段覆盖blackboard默认值 |
| `async_ros2_plugins.py` | AsyncMoveToNode/AsyncRetractNode构造结构化goal |
| `m4_6_code_validation.py` | 新增4个M5.3验证测试 |

## 测试结果

### 单元测试

| 包 | 测试数 | 结果 |
|------|--------|------|
| multi_arm_interfaces | 0 (CMake) | ✅ |
| multi_arm_core | 131 (含21 TaskGoal) | ✅ ALL PASS |
| multi_arm_safety | 36 | ✅ ALL PASS |
| multi_arm_world_model | 54 | ✅ ALL PASS |
| multi_arm_task_planner | 54 | ✅ ALL PASS |
| multi_arm_recovery | 60 | ✅ ALL PASS |
| **总计** | **307** | **✅ ALL PASS** |

### M5.3测试覆盖

| 类别 | 测试数 | 覆盖内容 |
|------|--------|----------|
| TaskGoalMsg | 4 | 导入 + 字段设置 + 默认值 + 嵌套约束 |
| TaskConstraintMsg | 3 | 导入 + 字段设置 + 默认值 |
| MotionRequestMsg | 3 | 导入 + 命名目标 + 关节位置 |
| ExecuteTaskWithGoal | 3 | goal字段存在 + 结构化goal + 向后兼容 |
| CoordinatorParseTaskGoal | 6 | 基本解析 + arm2 + 默认位置 + 无arm + 向后兼容 + 含object |
| BlackboardIntegration | 2 | TaskGoal→blackboard + fallback默认值 |
| **总计** | **21** | |

### Code Validation

| 测试 | 结果 |
|------|------|
| 15项 (含4项M5.3) | ✅ ALL PASS |

## 验收状态

| 验收项 | 通过条件 | 状态 |
|--------|----------|------|
| TaskGoal.msg定义 | 包含action_type, target, constraints字段 | ✅ |
| Coordinator解析TaskGoal | 替代_parse_task字符串解析 | ✅ _parse_task_goal() |
| 向后兼容 | 旧字符串格式仍可解析（fallback） | ✅ _parse_task()保留 |
| BT插件使用TaskGoal | MoveTo/Retract构造结构化goal | ✅ |
| MotionRequest.msg | 运动请求消息定义 | ✅ |

## 已知限制

1. **MotionRequest.msg未使用**: 当前定义了MotionRequest.msg但尚未在Coordinator/MoveIt中使用。M6 Sim2Real阶段需要用它替代直接构造JointTrajectory。

2. **TaskConstraint未执行**: TaskConstraint字段（max_time, safety_level, priority等）已定义但Coordinator尚未根据约束调整行为。后续需要在Coordinator中实现约束检查逻辑。

3. **BT插件仅MoveTo/Retract填充TaskGoal**: AsyncGraspNode/PlaceNode/LiftNode/RecoverNode仍使用_make_completed_future，未构造ExecuteTask.Goal。需要接入真实接口时补充。

4. **SubmitTask.srv未扩展**: SubmitTask.srv仍使用旧description字段，未添加TaskGoal。后续可扩展。

## 下一步

- **M5.4 Benchmark System**: 采集真实执行数据，建立性能基线
- **M5.5 CI/CD Pipeline**: 四层质量保障自动化