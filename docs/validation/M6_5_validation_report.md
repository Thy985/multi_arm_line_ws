# M6.5 Robot Runtime API 验证报告

**日期**: 2026-08-07  
**状态**: ✅ ALL PASS  
**测试**: 32 tests (9 mapping + 4 TaskGoal引用 + 8 接口可用性 + 4 backend不可用 + 5 SubmitTaskGoals链路 + 2 smoke)

---

## 1. 目标

M6只提供能力接口，不包含自然语言理解（语言理解属M7）。Robot Runtime API是M7 Agent访问M6所有能力的统一入口。

```
M6提供: ExecuteSkill, QueryWorld, GetCapability, ListSkills, ManageSkill, SubmitTaskGoals, QueryExperience
M7负责: 自然语言理解, 规划, 推理, 任务拆解, Agent决策, 从Experience学习
```

## 2. 实现内容

### 2.1 新接口

| 接口 | 类型 | 定义 |
|------|------|------|
| `SubmitTaskGoals.action` | action | 统一任务提交入口(TaskGoal[] → results[], success_count, total_count) |

**SubmitTaskGoals.action**:
```
multi_arm_interfaces/TaskGoal[] goals
---
bool success
string[] results
int32 success_count
int32 total_count
---
string current_goal
float32 progress
```

### 2.2 新包 (multi_arm_runtime_api)

```
multi_arm_runtime_api/
├── runtime_api_node.py    # 统一聚合层节点
└── launch/runtime_api.launch.py
```

### 2.3 7个Robot Runtime API

RuntimeApiNode作为统一聚合层，M7 Agent连接到这一个节点即可访问所有Runtime能力：

| API | 类型 | 统一入口 | 后端 | 说明 |
|-----|------|----------|------|------|
| SubmitTaskGoals | action server | /runtime/submit_task_goals | → /skill/execute | 接收TaskGoal列表，逐个路由到ExecuteSkill |
| QueryWorld | proxy service | /runtime/query_world | → /world_model/query_world | 代理世界状态查询 |
| GetCapability | proxy service | /runtime/get_capability | → /capability/get_capability | 代理能力查询(三层) |
| ListSkills | proxy service | /runtime/list_skills | → /skill/list | 代理Skill列表 |
| ManageSkill | proxy service | /runtime/manage_skill | → /skill/manage | 代理Skill管理 |
| QueryExperience | proxy service | /runtime/query_experience | → /experience/query | 代理Experience查询 |
| ExecuteSkill | action client | /skill/execute | 直接调用 | SubmitTaskGoals内部调用 |

### 2.4 action_type → skill_name映射

```python
ACTION_TYPE_TO_SKILL = {
    "pick_place": "pick_object",
    "pick": "pick_object",
    "place": "place_object",
    "move": "move_object",
    "grasp": "pick_object",
    "lift": "move_object",
    "retract": "move_object",
    "inspect": "move_object",
}
```

### 2.5 SubmitTaskGoals → ExecuteSkill链路

```
M7 Agent
 ↓ SubmitTaskGoals.Goal(goals=[TaskGoal(action_type="pick_place", ...)])
 ↓ RuntimeApiNode._handle_submit_task_goals()
 ↓ for each TaskGoal:
 ↓   skill_name = ACTION_TYPE_TO_SKILL[task_goal.action_type]
 ↓   ExecuteSkill.Goal(skill_name=skill_name, task_goal=task_goal)
 ↓   → /skill/execute (ExecuteSkill action)
 ↓   ← ExecuteSkill.Result(success, message)
 ↓ SubmitTaskGoals.Result(results=[], success_count, total_count)
 ↓
M7 Agent receives result
```

## 3. 测试结果

```
32 passed in 8.54s
```

### 3.1 TestActionTypeMapping (9 tests)

| 测试 | 验证内容 |
|------|----------|
| test_pick_place_mapping | pick_place → pick_object |
| test_pick_mapping | pick → pick_object |
| test_place_mapping | place → place_object |
| test_move_mapping | move → move_object |
| test_grasp_mapping | grasp → pick_object |
| test_lift_mapping | lift → move_object |
| test_retract_mapping | retract → move_object |
| test_inspect_mapping | inspect → move_object |
| test_all_actions_mapped | 所有8种action type已映射 |

### 3.2 TestTaskGoalReference (4 tests)

验证M5.7冻结的TaskGoal被正确引用：

| 测试 | 验证内容 |
|------|----------|
| test_submit_task_goals_uses_task_goal | SubmitTaskGoals.action引用TaskGoal |
| test_execute_skill_uses_task_goal | ExecuteSkill.action引用TaskGoal |
| test_task_goal_has_required_fields | TaskGoal含7个字段(action_type, arm_name, zone_name, position_name, object_id, approach, constraints) |
| test_task_constraint_has_required_fields | TaskConstraint含5个字段(max_time, safety_level, priority, allow_recovery, max_retries) |

### 3.3 TestRuntimeApiNodeInterfaces (8 tests)

验证RuntimeApiNode所有ROS2接口可用：

| 测试 | 验证内容 |
|------|----------|
| test_node_created | 节点创建成功 |
| test_submit_task_goals_action_server | /runtime/submit_task_goals action server存在 |
| test_proxy_query_world_service | /runtime/query_world proxy service存在 |
| test_proxy_get_capability_service | /runtime/get_capability proxy service存在 |
| test_proxy_list_skills_service | /runtime/list_skills proxy service存在 |
| test_proxy_manage_skill_service | /runtime/manage_skill proxy service存在 |
| test_proxy_query_experience_service | /runtime/query_experience proxy service存在 |
| test_all_seven_apis_available | 7个API全部可用 |

### 3.4 TestProxyBackendUnavailable (4 tests)

验证后端不可用时proxy返回空响应（graceful degradation）：

| 测试 | 验证内容 |
|------|----------|
| test_proxy_query_world_returns_empty | QueryWorld后端不可用→空object_states |
| test_proxy_list_skills_returns_empty | ListSkills后端不可用→空skills列表 |
| test_proxy_get_capability_returns_empty | GetCapability后端不可用→空capabilities |
| test_proxy_query_experience_returns_empty | QueryExperience后端不可用→count=0 |

### 3.5 TestSubmitTaskGoalsChain (5 tests)

验证SubmitTaskGoals → ExecuteSkill完整链路（使用mock ExecuteSkill action server）：

| 测试 | 验证内容 |
|------|----------|
| test_empty_goals_succeeds | 空goal列表→success=True, count=0 |
| test_single_pick_place_goal | 单个pick_place→success_count=1, "pick_object" in result |
| test_multiple_goals | 3个move goal→success_count=3 |
| test_mixed_action_types | pick_place+move+place→正确映射到pick_object+move_object+place_object |
| test_task_goal_with_constraints | TaskGoal含constraints→正确传递 |

### 3.6 test_smoke.py (2 tests)

| 测试 | 验证内容 |
|------|----------|
| test_package_imports | 所有模块可导入 |
| test_action_type_mapping_non_empty | 映射表非空 |

## 4. 验收项

| 验收项 | 通过条件 | 状态 |
|--------|----------|------|
| Robot Runtime API | ExecuteSkill/QueryWorld/GetCapability/ListSkills/ManageSkill/SubmitTaskGoals | ✅ 7个API |
| TaskGoal引用 | 接口引用M5.7冻结的TaskGoal | ✅ SubmitTaskGoals.action + ExecuteSkill.action |
| 边界清晰 | M6不含自然语言理解，M7负责 | ✅ |
| Skill调用 | SubmitTaskGoals → ExecuteSkill链路 | ✅ E2E验证(mock ExecuteSkill server) |
| 能力查询 | GetCapability返回三层能力(Static+Dynamic+Context) | ✅ 代理到/capability/get_capability |

## 5. 架构说明

### 5.1 设计模式: Facade/Aggregation Layer

RuntimeApiNode是Facade模式实现：
- 不包含业务逻辑
- 将请求路由到后端节点
- M7 Agent只需连接一个节点
- 后端节点不可用时graceful degradation

### 5.2 ROS2 Jazzy适配

实施过程中发现并修复了3个ROS2 Jazzy API变更：
1. `rclpy.callback_group` → `rclpy.callback_groups` (复数)
2. `ServerGoalHandle.goal` → `ServerGoalHandle.request`
3. Action server callback中不需要调用`goal_handle.execute()`（Jazzy自动转换状态）
4. Executor已在spinning时用polling代替`rclpy.spin_until_future_complete`

### 5.3 边界定义

```
M6 Robot Runtime API (本层)
  ├── SubmitTaskGoals — 接收TaskGoal列表，路由到ExecuteSkill
  ├── QueryWorld — 代理世界状态查询
  ├── GetCapability — 代理能力查询
  ├── ListSkills — 代理Skill列表
  ├── ManageSkill — 代理Skill管理
  ├── QueryExperience — 代理Experience查询
  └── ExecuteSkill — action client to /skill/execute

M7 Agent (下一层)
  ├── 自然语言理解 → 生成TaskGoal列表
  ├── 规划/推理 → 决定调用顺序
  ├── 任务拆解 → 将复杂任务拆为TaskGoal
  ├── Agent决策 → 根据结果决定下一步
  └── 从Experience学习 → 查询QueryExperience
```

## 6. 结论

M6.5 Robot Runtime API全部完成，32 tests ALL PASS。系统现在提供：
1. 统一的Robot Runtime API入口（7个API，M7 Agent只需连接一个节点）
2. SubmitTaskGoals → ExecuteSkill完整链路（TaskGoal列表→逐个执行→汇总结果）
3. 5个proxy service代理后端接口（graceful degradation when backend unavailable）
4. 正确引用M5.7冻结的TaskGoal/TaskConstraint

**累计M6测试**: M6.0(30) + M6.S(44) + M6.1(40) + M6.2(30) + M6.3(102) + M6.4(48) + M6.5(32) = **326 tests ALL PASS**