# M5.2 BT Plugin Architecture Refactor — 验证报告

## 目标

解决ROS2 BT插件在async callback中创建临时节点导致executor死锁的问题，实现共享Node + AsyncTick模式，使BT插件能安全地在ROS2 executor环境中运行。

## 问题根因

原`ros2_plugins.py`中每个BT插件在`_send_request()`时创建临时ROS2节点（`rclpy.create_node()`），在async callback中使用这些临时节点会导致executor死锁：
- 临时节点不在TaskPlanner的executor中注册
- Service/Action client的callback无法被executor调度
- 多个临时节点竞争executor资源

## 架构设计

### 核心模式：共享Node + AsyncTick

```
TaskPlanner ROS2 Node (唯一)
    |
    +-- _inject_node_to_tree() → 遍历所有BT节点
    |       |
    |       +-- AsyncActionNode._shared_node = TaskPlanner.node
    |
    +-- BT tick loop
          |
          +-- AsyncMoveToNode.tick()
          |     1st tick: send_goal() → return RUNNING
          |     2nd tick: check future → return SUCCESS/FAILURE
          |
          +-- AsyncCheckSafetyNode.tick()
                1st tick: call_service() → return RUNNING
                2nd tick: check response → return SUCCESS/FAILURE
```

### AsyncActionNode基类

```python
class AsyncActionNode(ActionNode):
    _shared_node: Optional[Node] = None

    def tick(self) -> NodeStatus:
        if self._future is None:
            self._future = self._send_request()
            return NodeStatus.RUNNING
        return self._check_result()

    def _make_completed_future(self, result: Any) -> Future:
        """创建已完成的future（用于同步结果）"""

    def _send_request(self) -> Optional[Future]:
        """发送ROS2请求，返回Future（子类实现）"""

    def _check_result(self) -> NodeStatus:
        """检查future结果，返回SUCCESS/FAILURE（子类实现）"""
```

### Sequence/Selector RUNNING记忆

```python
class Sequence(CompositeNode):
    def __init__(self):
        self._running_child_idx: int = 0

    def tick(self) -> NodeStatus:
        for i in range(self._running_child_idx, len(self.children)):
            status = self.children[i].tick()
            if status == NodeStatus.RUNNING:
                self._running_child_idx = i
                return NodeStatus.RUNNING
            elif status == NodeStatus.FAILURE:
                self._running_child_idx = 0
                return NodeStatus.FAILURE
        self._running_child_idx = 0
        return NodeStatus.SUCCESS
```

### 8个Async ROS2插件

| 插件 | 类型 | ROS2通信 | 非阻塞策略 |
|------|------|----------|-----------|
| AsyncMoveToNode | Action | ExecuteTask ActionClient | wait_for_server(0.1s) + retry |
| AsyncRetractNode | Action | ExecuteTask ActionClient | wait_for_server(0.1s) + retry |
| AsyncCheckSafetyNode | Condition | SafetyCheck ServiceClient | service_ready检查 + FAILURE(安全优先) |
| AsyncQueryWorldNode | Action | GetObjectState ServiceClient | service_ready检查 + SUCCESS(fallback) |
| AsyncGraspNode | Action | _make_completed_future | 简化实现 |
| AsyncPlaceNode | Action | _make_completed_future | 简化实现 |
| AsyncLiftNode | Action | _make_completed_future | 简化实现 |
| AsyncRecoverNode | Action | _make_completed_future | 简化实现 |

### ActionClient非阻塞模式

```python
def _send_request(self) -> Optional[Future]:
    if not self._action_client.wait_for_server(timeout_sec=0.1):
        return self._make_completed_future("waiting")

    goal = ExecuteTask.Goal()
    future = self._action_client.send_goal_async(goal)
    return future

def _check_result(self) -> NodeStatus:
    if self._future.result() == "waiting":
        if not self._action_client.wait_for_server(timeout_sec=0.1):
            return NodeStatus.RUNNING  # retry next tick
        # resend...
```

## 新增文件

| 文件 | 说明 |
|------|------|
| `src/multi_arm_task_planner/multi_arm_task_planner/bt_plugins/async_ros2_plugins.py` | 8个async ROS2 BT插件 |
| `src/multi_arm_task_planner/test/test_async_plugins.py` | async插件单元测试 (27 tests) |

## 修改文件

| 文件 | 变更 |
|------|------|
| `behavior_tree.py` | 新增`AsyncActionNode`基类 + `_make_completed_future()` + Sequence/Selector添加`_running_child_idx` |
| `task_planner_node.py` | 默认`use_ros2_plugins=True` + `_inject_shared_node()`注入共享Node + tick循环RUNNING处理(max_ticks=500) + `from typing import Any` + blackboard设置`target_goal`/`place_goal` |
| `bt_xml/pick_place.xml` | 简化为扁平Sequence（移除SubTree和`{...}`引用） |
| `bt_xml/pick_place_ros2.xml` | 同上 |
| `m4_6_task_loop.launch.py` | `use_ros2_plugins: True` |
| `m4_6_task_loop_test.py` | 添加ROS_HOME环境变量 |
| `m4_6_dual_arm_test.py` | 添加ROS_HOME环境变量 |
| `test_e2e_integration.py` | 更新`test_bt_subtree_reuse`适配新XML结构 |

## 测试结果

### 单元测试

| 包 | 测试数 | 结果 |
|------|--------|------|
| multi_arm_task_planner | 54 (含27 async) | ✅ ALL PASS |
| multi_arm_core | 109 | ✅ ALL PASS |
| multi_arm_safety | 36 | ✅ ALL PASS |
| multi_arm_world_model | 54 | ✅ ALL PASS |
| multi_arm_recovery | 60 | ✅ ALL PASS |
| multi_arm_interfaces | 0 (CMake) | ✅ |
| **总计** | **286** | **✅ ALL PASS** |

### Async插件测试覆盖

| 类别 | 测试数 | 覆盖内容 |
|------|--------|----------|
| AsyncActionNode基类 | 5 | 共享Node注入 + _make_completed_future + 无Node时FAILURE |
| AsyncMoveToNode | 4 | 正常执行 + server不可用waiting + goal失败 + future异常 |
| AsyncRetractNode | 3 | 正常执行 + server不可用 + goal失败 |
| AsyncCheckSafetyNode | 4 | approved→SUCCESS + rejected→FAILURE + service不可用→FAILURE + 无Node→FAILURE |
| AsyncQueryWorldNode | 4 | 有数据→SUCCESS + 无数据→SUCCESS + 服务不可用→SUCCESS + 无Node→SUCCESS |
| AsyncGraspNode | 2 | SUCCESS + 无Node→FAILURE |
| AsyncPlaceNode | 2 | SUCCESS + 无Node→FAILURE |
| AsyncLiftNode | 2 | SUCCESS + 无Node→FAILURE |
| AsyncRecoverNode | 2 | SUCCESS + 无Node→FAILURE |
| **总计** | **27** | |

### 仿真E2E回归

| 测试 | 结果 |
|------|------|
| M4.6 E2E (8项) | ✅ ALL PASS |
| 双臂冲突 (8项) | ✅ ALL PASS (无死锁) |

## 验收状态

| 验收项 | 通过条件 | 状态 |
|--------|----------|------|
| 共享Node插件 | BT插件使用TaskPlanner的Node，不创建临时节点 | ✅ |
| AsyncTick模式 | tick返回RUNNING→下次tick检查future→SUCCESS/FAILURE | ✅ |
| 无executor死锁 | 双臂并发BT执行无死锁 | ✅ E2E 8/8 + 双臂冲突 8/8 |
| 替换mock插件 | pick_place_ros2.xml成为默认，mock仅用于单元测试 | ✅ |

## 关键发现

1. **BT XML中`{blackboard_key}`引用不被解析**: 自定义BT框架的`_build_node()`不解析XML属性中的`{...}`引用（不同于BehaviorTree.CPP），需使用扁平Sequence结构，插件直接从blackboard读取固定key。

2. **Sequence/Selector必须记忆RUNNING子节点位置**: 否则async节点在下次tick时被从头遍历重置，导致future丢失。添加`_running_child_idx`解决。

3. **`wait_for_server()`在BT tick内会阻塞executor**: `wait_for_server(timeout_sec=5.0)`会阻塞TaskPlanner的executor，导致Coordinator响应无法被处理。必须用`timeout_sec=0.1`非阻塞检查 + 返回RUNNING等待下次tick重试。

4. **`create_client`不能用于Action类型**: `ExecuteTask`是action不是service，使用`node.create_client(ExecuteTask, ...)`会抛出`The service type provided is not valid`。必须用`rclpy.action.ActionClient`。

5. **服务不可用时的安全策略**: AsyncQueryWorldNode服务不可用时返回SUCCESS（fallback，允许任务继续），AsyncCheckSafetyNode服务不可用时返回FAILURE（安全优先，阻止运动）。

## 已知限制

1. **简化插件未连接真实ROS2**: AsyncGraspNode/PlaceNode/LiftNode/RecoverNode使用`_make_completed_future`直接返回SUCCESS，未连接真实action/service。M5.3+需要接入真实接口。

2. **旧`ros2_plugins.py`仍存在**: 有死锁问题的旧版同步插件文件仍保留在代码库中，需要标记deprecated或删除。

3. **BT XML不支持SubTree**: 当前BT框架不支持SubTree引用，所有任务必须展开为扁平Sequence。后续可增强BT引擎支持。

4. **tick循环使用`time.sleep(0.05)`**: TaskPlanner的tick循环在单线程executor中运行，sleep期间无法处理其他callback。如果BT执行时间过长，可能影响其他节点的响应性。

## 下一步

- **M5.3 Task Message Upgrade**: 扩展multi_arm_interfaces，从字符串协议升级为领域模型（TaskGoal.msg, TaskConstraint.msg, MotionRequest.msg）
- **M5.4 Benchmark System**: 采集真实执行数据，建立性能基线
- **M5.5 CI/CD Pipeline**: 四层质量保障自动化