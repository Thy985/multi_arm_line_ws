# M4.6 Autonomous Task Loop — 设计文档

## 目标

证明一个PickPlace任务能够自主完成——closed-loop autonomy。

## 当前状态 vs 目标状态

| 链路段 | 当前 | M4.6目标 |
|--------|------|----------|
| TaskPlanner→BT | BT插件只写blackboard | BT插件调用真实ROS2服务 |
| BT→Coordinator | 无ROS2连接 | Coordinator暴露SubmitTask action |
| Coordinator→MoveIt | 只有预设位置+JTC直发 | Coordinator调用MoveIt2规划 |
| Safety审批 | CheckSafety读blackboard | CheckSafety调用/safety/safety_check |
| WorldModel查询 | QueryWorld读blackboard | QueryWorld调用/world_model/query_objects |
| Robot→WorldModel | ✅ joint_states→缓存 | ✅ 已完成 |
| BT状态反馈 | 无 | Execute节点收到SUCCESS/FAILURE |

## 实现策略：最小侵入式

**原则**: 不重写现有组件，在现有Mock插件上添加ROS2服务调用层。

### 层1: Coordinator暴露ROS2 Action Server

**接口**: `multi_arm_interfaces/action/ExecuteTask`

Coordinator新增:
- `ExecuteTask` action server（`/coordinator/execute_task`）
- Goal: task_id, task_type, description
- Feedback: status, progress
- Result: success, message

内部流程:
```
ExecuteTask goal received
 ↓ 解析task_type → 确定arm + zone + position
 ↓ ResourceManager.allocate(zone, task_id)
 ↓ SafetyInterface.check_safety_sync(...)
 ↓ MoveIt2规划（新增MoveItInterface子模块）
 ↓ JTC执行
 ↓ ResourceManager.release(zone, task_id)
 ↓ 返回Result(success=True/False)
```

### 层2: MoveItInterface子模块

Coordinator新增子模块 `moveit_interface.py`:
- 调用 `/plan_kinematic_path` 服务获取轨迹
- 或调用 `/move_action` action执行规划+执行
- 输入: group_name, target_joints
- 输出: success, trajectory

**设计选择**: 优先使用 `/move_action`（规划+执行一体化），失败时回退到预设位置。

### 层3: BT插件ROS2化

将8个Mock插件改为调用真实服务:

| 插件 | Mock行为 | M4.6行为 |
|------|----------|----------|
| MoveTo | 写blackboard | 调用Coordinator action（内部MoveIt规划+执行） |
| Grasp | 写blackboard | 调用GripperController（或简化为关节目标） |
| Place | 写blackboard | 调用Coordinator action |
| Lift | 写blackboard | 调用Coordinator action |
| Retract | 写blackboard | 调用Coordinator action |
| CheckSafety | 读blackboard | 调用/safety/safety_check |
| QueryWorld | 读blackboard | 调用/world_model/query_objects |
| Recover | 写blackboard | 调用Coordinator reset |

**实现方式**: 每个BT插件节点内部创建ROS2 client，在tick()中同步调用。

### 层4: TaskPlanner task_type→XML映射

在`_on_execute_task`中:
```python
XML_MAP = {
    "pick_place": "pick_place.xml",
    "assembly": "assembly.xml",
    "inspection": "inspection.xml",
}
```

### 层5: 完整闭环测试

```
submit_task(pick_place, red_cube, zone_a)
 ↓ TaskPlanner加载pick_place.xml
 ↓ BT tick: CheckSafety → /safety/safety_check → approved
 ↓ BT tick: QueryWorld → /world_model/query_objects → object_pose
 ↓ BT tick: MoveTo(pre_grasp) → Coordinator → MoveIt → JTC → Gazebo
 ↓ BT tick: Grasp → GripperController
 ↓ BT tick: Lift → Coordinator → MoveIt → JTC → Gazebo
 ↓ BT tick: MoveTo(zone_a) → Coordinator → MoveIt → JTC → Gazebo
 ↓ BT tick: Place → GripperController
 ↓ BT tick: Retract → Coordinator → MoveIt → JTC → Gazebo
 ↓ BT: SUCCESS
 ↓ ExecuteTask Result: success=True
```

## 文件变更清单

### 新增

| 文件 | 说明 |
|------|------|
| `src/multi_arm_core/multi_arm_core/moveit_interface.py` | MoveIt2规划+执行接口 |
| `src/multi_arm_task_planner/multi_arm_task_planner/bt_plugins/ros2_plugins.py` | ROS2化BT插件 |
| `src/multi_arm_task_planner/multi_arm_task_planner/bt_xml/pick_place_ros2.xml` | 使用ROS2插件的BT |
| `src/multi_arm_moveit_config/scripts/m4_6_task_loop_test.py` | M4.6测试脚本 |

### 修改

| 文件 | 变更 |
|------|------|
| `coordinator_node.py` | 新增ExecuteTask action server + MoveItInterface集成 |
| `task_planner_node.py` | task_type→XML映射 + ROS2插件注册 |
| `pick_place_plugins.py` | 保留Mock插件（测试用），新增ROS2插件 |

### 不修改

| 文件 | 原因 |
|------|------|
| `multi_arm_interfaces/` | ExecuteTask.action已定义 |
| `safety_supervisor.py` | SafetyCheck.srv已实现 |
| `world_model_node.py` | query_objects已实现 |
| `resource_manager.py` | Zone分配机制已验证 |

## 验收测试

| 测试 | 通过条件 |
|------|----------|
| Coordinator ExecuteTask action | 提交pick_place任务→返回success=True |
| MoveIt规划集成 | Coordinator调用MoveIt规划→JTC执行→Gazebo运动 |
| Safety审批 | CheckSafety调用/safety/safety_check→approved |
| WorldModel查询 | QueryWorld获取object_pose |
| BT全链路 | PickPlace BT从CheckSafety到Retract全部SUCCESS |
| 双臂资源冲突 | arm1占用zone_a→arm2等待→arm1完成→arm2继续 |
| M4.6报告 | docs/validation/M4_6_validation_report.md |