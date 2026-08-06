# M5.1 Recovery Framework — 验证报告

## 目标

系统面对失败不是退出，而是恢复。建立失败分类+渐进恢复策略链。

## 架构设计

### 核心组件

```
multi_arm_recovery/
├── failure_classifier.py     # 失败分类器（消息→FailureType）
├── recovery_manager.py       # 恢复编排器（策略链+执行+记录）
└── handlers/
    ├── planning_failure.py   # 规划失败→放宽约束→换姿态→释放→abort
    ├── collision_handler.py  # 碰撞→退回安全位→重规划→释放→abort
    ├── resource_timeout.py   # 资源超时→释放+重排队→abort
    ├── controller_failure.py # 控制器失败→等待重试→切换控制器→abort
    └── grasp_retry.py        # 抓取失败→重试(最多3次)→abort
```

### 失败分类

| FailureType | 模式匹配 | 可恢复 |
|-------------|----------|--------|
| PLANNING_FAILURE | moveit_error_*, goal_send_timeout, goal_rejected | ✅ |
| COLLISION_DETECTED | collision*, context:collision_detected | ✅ |
| RESOURCE_TIMEOUT | occupied*, context:resource_timeout | ✅ |
| CONTROLLER_FAILURE | jtc_*, error_code | ✅ |
| GRASP_FAILURE | grasp*, context:grasp_failed | ✅ |
| SAFETY_REJECTION | safety, e_stop | ❌ |
| EXECUTION_TIMEOUT | execution_timeout | ✅ |
| GOAL_REJECTED | goal_rejected | ✅ |
| UNKNOWN | 不匹配任何模式 | ✅ |

### 恢复链路

```
ExecuteTask失败
 ↓ RecoveryManager.classify_failure()
 ↓ FailureEvent(failure_type, recoverable)
 ↓ RecoveryManager.handle_failure()
 ↓ Handler.get_recovery_strategy()
 ↓ Strategy 1 → _execute_recovery_strategy() → success? → RECOVERED
 ↓ Strategy 2 → _execute_recovery_strategy() → success? → RECOVERED
 ↓ Strategy N → safe_abort → FAILED
```

### Coordinator集成

```python
# coordinator_node.py _on_execute_task()
if not success:
    success, msg = self._attempt_recovery(
        task_id, arm_name, msg, zone_name, position_name, task_internal_id
    )
```

## 新增文件

| 文件 | 说明 |
|------|------|
| `src/multi_arm_recovery/package.xml` | 包定义 |
| `src/multi_arm_recovery/setup.py` | 构建配置 |
| `src/multi_arm_recovery/multi_arm_recovery/failure_classifier.py` | 失败分类器 |
| `src/multi_arm_recovery/multi_arm_recovery/recovery_manager.py` | 恢复编排器 |
| `src/multi_arm_recovery/multi_arm_recovery/handlers/planning_failure.py` | 规划失败处理器 |
| `src/multi_arm_recovery/multi_arm_recovery/handlers/collision_handler.py` | 碰撞处理器 |
| `src/multi_arm_recovery/multi_arm_recovery/handlers/resource_timeout.py` | 资源超时处理器 |
| `src/multi_arm_recovery/multi_arm_recovery/handlers/controller_failure.py` | 控制器失败处理器 |
| `src/multi_arm_recovery/multi_arm_recovery/handlers/grasp_retry.py` | 抓取重试处理器 |
| `src/multi_arm_recovery/test/test_recovery.py` | 单元测试 (48 tests) |
| `src/multi_arm_recovery/test/test_smoke.py` | 冒烟测试 (12 tests) |

## 修改文件

| 文件 | 变更 |
|------|------|
| `coordinator_node.py` | 导入RecoveryManager + FailureEvent/FailureType + 初始化 + _attempt_recovery() + _execute_recovery_strategy() + 失败后调用recovery |
| `multi_arm_core/package.xml` | 新增multi_arm_recovery依赖 |

## 测试结果

### 单元测试

| 包 | 测试数 | 结果 |
|------|--------|------|
| multi_arm_recovery | 60 | ✅ ALL PASS |
| multi_arm_core | 109 | ✅ ALL PASS |
| E2E集成 | 28 | ✅ ALL PASS |
| **总计** | **197** | **✅ ALL PASS** |

### 单元测试覆盖

| 类别 | 测试数 | 覆盖内容 |
|------|--------|----------|
| FailureClassifier | 18 | 所有9种FailureType + context分类 + 字段保留 |
| PlanningFailureHandler | 7 | 3策略链 + exhausted + reset |
| CollisionHandler | 3 | 2策略链 + exhausted |
| ResourceTimeoutHandler | 2 | 2策略链 |
| ControllerFailureHandler | 2 | 2策略链 |
| GraspRetryHandler | 3 | 3次重试 + exhausted |
| RecoveryManager | 14 | 分类 + 可恢复/不可恢复 + executor + 历史记录 + 成功率 + 自定义handler + 时间戳 |
| 冒烟测试 | 12 | 导入 + 5种类型 + 5个handler注册 |

### 仿真E2E回归

| 测试 | 结果 |
|------|------|
| M4.6 E2E (8项) | ✅ ALL PASS |
| Recovery未触发（正常执行） | ✅ 预期行为 |

## 验收状态

| 验收项 | 通过条件 | 状态 |
|--------|----------|------|
| PlanningFailure→Replan | 规划失败→放宽约束重规划→成功 | ✅ Handler实现+测试 |
| CollisionRecovery | 碰撞→退回安全位→重规划→成功 | ✅ Handler实现+测试 |
| ResourceTimeout→Release | 资源等待超时→释放→重新分配 | ✅ Handler实现+测试 |
| ControllerFailure→Fallback | JTC inactive→切换控制器/abort | ✅ Handler实现+测试 |
| GraspRetry | 抓取失败→重试(最多3次) | ✅ Handler实现+测试 |
| Recovery集成到Coordinator | Coordinator失败后调用RecoveryManager | ✅ 集成+E2E回归通过 |

## 已知限制

1. **Recovery执行依赖MoveIt可用**: 当前`_execute_recovery_strategy`中relax_constraints/change_grasp_pose等策略都调用MoveIt。如果MoveIt本身不可用，恢复策略会失败。
2. **Safety rejection不可恢复**: E-Stop触发的失败直接abort，不尝试恢复（正确行为）。
3. **异步恢复未实现**: 当前恢复在`_on_execute_task`的async callback中同步执行，会阻塞executor线程。M5.2 BT重构后可改善。
4. **Recovery未集成到BT**: BT的Recover节点尚未调用RecoveryManager。M5.2 BT重构时集成。