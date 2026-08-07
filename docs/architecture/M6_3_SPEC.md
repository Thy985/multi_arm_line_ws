# M6.3 Skill Runtime SPEC — Interface Freeze v1.0

> M6 Gate 2 Baseline
> 版本: v1.0 (Interface Freeze)
> 日期: 2026-08-07
> 状态: FROZEN — 禁止破坏性修改，仅允许可选字段追加

---

## 1. Skill Manifest Schema (FROZEN v1.0)

### 1.1 Schema 定义

```yaml
# Skill Manifest Schema v1.0 (FROZEN)
skill:
  name: string                    # REQUIRED, 唯一标识, snake_case
  version: string                 # REQUIRED, 语义版本 "major.minor.patch"
  description: string             # OPTIONAL, 人类可读描述

  required_capabilities:          # REQUIRED, 依赖的机器人能力列表
    - string                      #   capability name (查询Capability Registry三层)

  input:                          # OPTIONAL, 输入参数定义
    <param_name>: string          #   param_name → type description

  output:                         # OPTIONAL, 输出参数定义
    <param_name>: string          #   param_name → type description

  cost:                           # REQUIRED, 成本估计 (Agent选择Skill依据)
    time: float                   #   预估执行时间(秒)
    risk: float                   #   风险等级(0.0-1.0)
    success_rate: float           #   历史成功率(0.0-1.0)

  preconditions:                  # OPTIONAL, 前置条件 (查询WorldModel Relation Layer)
    - string                      #   条件表达式

  execute:                        # REQUIRED, 执行步骤 (有序)
    - string                      #   step name

  postconditions:                 # OPTIONAL, 后置条件 (查询WorldModel Relation Layer)
    - string                      #   条件表达式

  recovery:                       # OPTIONAL, 恢复策略
    <failure_type>: string        #   failure_type → strategy expression
```

### 1.2 冻结字段

| 字段 | 类型 | 必填 | 冻结状态 | 说明 |
|------|------|------|----------|------|
| name | string | YES | FROZEN | 唯一标识，snake_case |
| version | string | YES | FROZEN | 语义版本 |
| description | string | NO | FROZEN | 人类可读描述 |
| required_capabilities | string[] | YES | FROZEN | 依赖能力列表 |
| input | dict | NO | FROZEN | 输入参数定义 |
| output | dict | NO | FROZEN | 输出参数定义 |
| cost | SkillCost | YES | FROZEN | 成本估计 |
| cost.time | float | YES | FROZEN | 预估时间(秒) |
| cost.risk | float | YES | FROZEN | 风险(0-1) |
| cost.success_rate | float | YES | FROZEN | 成功率(0-1) |
| preconditions | string[] | NO | FROZEN | 前置条件表达式 |
| execute | string[] | YES | FROZEN | 执行步骤(有序) |
| postconditions | string[] | NO | FROZEN | 后置条件表达式 |
| recovery | dict | NO | FROZEN | failure_type→strategy映射 |

**扩展规则**: M7可新增可选字段（如 `tags`, `author`, `dependencies`），只能追加到末尾且有默认值。禁止修改已有字段的类型、名称或语义。

### 1.3 验证规则

- `name` 非空，snake_case
- `version` 符合语义版本格式
- `execute` 至少1个步骤
- `cost.time` > 0
- `cost.risk` ∈ [0.0, 1.0]
- `cost.success_rate` ∈ [0.0, 1.0]

---

## 2. Skill Lifecycle Contract (FROZEN v1.0)

### 2.1 状态定义

```
SkillLifecycleState (FROZEN v1.0)
├── INSTALLED     "installed"      # 包已安装
├── REGISTERED    "registered"     # Registry已注册
├── VALIDATED     "validated"      # 能力+前置条件检查通过
├── READY         "ready"          # 可执行
├── EXECUTING     "executing"      # 正在执行
├── MONITORING    "monitoring"     # 执行后监控
├── UPDATING      "updating"       # 版本更新中
├── REMOVING      "removing"       # 卸载中
├── REMOVED       "removed"        # 已卸载
└── INVALID       "invalid"        # 验证失败
```

### 2.2 合法状态转换 (FROZEN v1.0)

```
INSTALLED  → {REGISTERED, REMOVED, INVALID}
REGISTERED → {VALIDATED, INVALID}
VALIDATED  → {READY, INVALID}
READY      → {EXECUTING, UPDATING, REMOVING}
EXECUTING  → {MONITORING, READY}
MONITORING → {READY, UPDATING}
UPDATING   → {READY, INVALID}
REMOVING   → {REMOVED}
REMOVED    → {} (终态)
INVALID    → {READY, REMOVING}
```

**契约**:
- 非法转换返回 `False`，不抛异常
- 只有 `READY` 状态的Skill可以被 `execute()` 调用
- `EXECUTING → MONITORING → READY` 是标准执行循环
- `UPDATING → READY` 是热更新路径，保留execution stats
- `REMOVED` 是终态，不可恢复

### 2.3 执行统计 (FROZEN v1.0)

```
SkillLifecycleEntry (FROZEN v1.0)
├── skill_id: string               # 唯一ID (skill_0001格式)
├── name: string                   # Skill名称
├── version: string                # 当前版本
├── state: SkillLifecycleState     # 当前状态
├── installed_at: float            # 安装时间戳
├── last_executed: float           # 最后执行时间戳
├── total_executions: int          # 总执行次数
├── success_count: int             # 成功次数
├── execution_history: list        # 最近100条执行记录
└── validation_errors: string[]    # 验证错误信息

success_rate = success_count / total_executions (FROZEN)
execution_history 上限 = 100 条 (FROZEN)
```

---

## 3. Recovery Policy Contract (FROZEN v1.0)

### 3.1 恢复触发条件

| 失败类型 | failure_reason | 触发recovery? | 说明 |
|----------|---------------|---------------|------|
| 执行失败 | `execution_failed` | YES | 执行函数返回False或抛异常 |
| 后置条件失败 | `postcondition_failed` | YES | postcondition检查未通过 |
| 前置条件失败 | `precondition_failed` | NO | 不执行，不recovery |
| 能力缺失 | `missing_capabilities` | NO | 不执行，不recovery |
| 非READY状态 | `not_ready` | NO | 不执行，不recovery |
| Manifest不存在 | `manifest_not_found` | NO | 不执行，不recovery |

### 3.2 恢复策略匹配 (FROZEN v1.0)

```
恢复策略选择顺序:
  1. 匹配 failure_type in failure_reason → 优先尝试
  2. 匹配 failure_type == "default" → 次优先
  3. 其余策略 → fallback (按dict顺序)
  4. 全部失败 → 返回 FAILURE + recovery_attempts计数
```

**契约**:
- recovery_handler 是 `Callable(skill_name: str, failure: str) -> bool`
- 返回 `True` → `ExecutionStatus.RECOVERED`
- 返回 `False` → 继续尝试下一个策略
- 全部策略失败 → `ExecutionStatus.FAILURE`
- `recovery_attempts` 计录实际尝试次数

### 3.3 ExecutionStatus 枚举 (FROZEN v1.0)

```
ExecutionStatus (FROZEN v1.0)
├── SUCCESS    # 执行成功 + postcondition通过
├── FAILURE    # 执行失败 且 recovery失败/未触发
├── SKIPPED    # 跳过 (预留)
├── RECOVERED  # 执行失败 但 recovery成功
└── ABORTED    # 中止 (预留)
```

---

## 4. ROS2 接口冻结 (FROZEN v1.0)

### 4.1 ExecuteSkill.action

```
ExecuteSkill.action (FROZEN v1.0)
Goal:
├── skill_name: string             # Skill名称
├── parameters: string[]           # 执行参数
└── task_goal: TaskGoal            # 引用已冻结的TaskGoal (M5.7)

Result:
├── success: bool                  # 执行是否成功
├── message: string                # 人类可读消息
└── postcondition_results: bool[]  # 每个postcondition的检查结果

Feedback:
├── status: string                 # 当前状态描述
└── progress: float32              # 进度 0.0-1.0
```

**冻结理由**: ExecuteSkill是M6.5 Robot Runtime API的核心执行入口，M7 Agent将通过此Action执行Skill。task_goal引用M5.7冻结的TaskGoal，确保任务语义一致。

**扩展规则**: M7可在Goal追加可选字段（如 `priority`, `deadline`），追加到末尾且有默认值。

### 4.2 ListSkills.srv

```
ListSkills.srv (FROZEN v1.0)
Request:
├── required_capabilities: string[]  # 过滤: 必须包含所有指定能力
└── lifecycle_state: string          # 过滤: 仅返回指定状态 ("ready"等)

Response:
└── skills: SkillDescription[]       # 匹配的Skill列表
```

**契约**:
- `required_capabilities` 为空 → 不按能力过滤
- `lifecycle_state` 为空 → 默认返回 "ready" 状态
- 结果按 cost.time 升序、success_rate 降序排序

### 4.3 ManageSkill.srv

```
ManageSkill.srv (FROZEN v1.0)
Request:
├── action: string              # "install"|"remove"|"update"|"validate"
├── skill_package: string       # install: YAML文件路径
├── skill_id: string            # 其他: Skill ID
└── version: string             # update: 目标版本

Response:
├── success: bool
├── skill_status: SkillStatus   # 操作后的Skill状态
└── message: string             # 人类可读消息
```

**契约**:
- `install`: 解析YAML → install → register → validate → ready
- `remove`: 等待当前执行完成 → REMOVING → REMOVED
- `update`: READY → UPDATING → READY (热更新，保留stats)
- `validate`: 重新检查required_capabilities

### 4.4 SkillDescription.msg

```
SkillDescription.msg (FROZEN v1.0)
├── name: string                    # Skill名称
├── version: string                 # 版本
├── description: string             # 描述
├── required_capabilities: string[] # 依赖能力
├── preconditions: string[]         # 前置条件
├── postconditions: string[]        # 后置条件
├── parameters: string[]            # 参数名列表
├── cost_time: float64              # 预估时间
├── cost_risk: float64              # 风险
└── success_rate: float64           # 成功率
```

### 4.5 SkillStatus.msg

```
SkillStatus.msg (FROZEN v1.0)
├── skill_id: string                # 唯一ID
├── name: string                    # Skill名称
├── version: string                 # 当前版本
├── lifecycle_state: string         # 生命周期状态
├── last_executed: float64          # 最后执行时间
├── total_executions: int32         # 总执行次数
└── success_count: int32            # 成功次数
```

---

## 5. Skill Composition Contract (FROZEN v1.0)

### 5.1 组合规则

```
CompositeSkill = Step1 → Step2 → ... → StepN

Step:
├── skill_id: string        # 要执行的Skill ID
├── parameters: dict        # 执行参数
└── optional: bool          # True: 失败不中断链; False: 失败中断
```

**契约**:
- 链按顺序执行，前一步的输出可通过context传递给后一步
- 非optional步骤失败 → 链停止，`completed_steps` 计数
- optional步骤失败 → 记入结果但链继续
- `CompositeResult.success = (completed_steps == total_steps)`

### 5.2 BT兼容规则

```
BT XML → BTSkillWrapper → SkillManifest
├── name = BT文件名 (stem)
├── required_capabilities = ["manipulation"] (默认)
├── execute_steps = ["bt_execute(<filename>)"]
├── cost = {time: 10.0, risk: 0.15, success_rate: 0.90} (默认)
└── recovery = {"default": "retry(1) → abort"} (默认)
```

**契约**: BT XML可通过bt_xml_to_skill_manifest()包装为Skill，保持向后兼容。

---

## 6. 冻结接口汇总

| 接口 | 类型 | 冻结版本 | 依赖 |
|------|------|----------|------|
| SkillManifest (Schema) | Data Model | v1.0 | — |
| SkillLifecycleState (10 states) | Enum | v1.0 | — |
| VALID_TRANSITIONS | State Machine | v1.0 | SkillLifecycleState |
| ExecutionStatus (5 values) | Enum | v1.0 | — |
| Recovery Policy | Contract | v1.0 | ExecutionStatus |
| ExecuteSkill.action | Action | v1.0 | TaskGoal (M5.7 FROZEN) |
| ListSkills.srv | Service | v1.0 | SkillDescription |
| ManageSkill.srv | Service | v1.0 | SkillStatus |
| SkillDescription.msg | Message | v1.0 | — |
| SkillStatus.msg | Message | v1.0 | — |
| Skill Composition | Contract | v1.0 | SkillRuntime |
| BT Compatibility | Contract | v1.0 | SkillManifest |

**总计**: 12项冻结 (5 ROS2接口 + 4数据模型/枚举 + 3契约)

---

## 7. M6.5 依赖声明

M6.5 Robot Runtime API 将依赖以下M6.3冻结接口:

| M6.5 API | 依赖的M6.3接口 | 依赖类型 |
|----------|---------------|----------|
| ExecuteSkill | ExecuteSkill.action | 直接使用 |
| ListSkills | ListSkills.srv | 直接使用 |
| ManageSkill | ManageSkill.srv | 直接使用 |
| GetCapability | SkillManifest.required_capabilities | 间接(通过Skill验证) |
| SubmitTaskGoals | ExecuteSkill.action + TaskGoal | 组合(TaskGoal→Skill选择→执行) |
| QueryWorld | SkillManifest.preconditions/postconditions | 间接(条件查询) |

**约束**: M6.5只能消费M6.3冻结接口，不能修改。M7 Agent层同理。