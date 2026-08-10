# ADR-M6-Freeze: M6 Platform Interface Freeze v1.0

> **Status**: ACCEPTED
> **Date**: 2026-08-10
> **Decision Maker**: Architecture Review (5th Round, Platform Governance)
> **Supersedes**: ADR-M6.3-Freeze (扩展冻结范围至全M6)
> **Superseded by**: None

---

## Context

M6全部完成（M6.0-M6.7 + L6 Simulation E2E），累计434+ tests ALL PASS, 18 packages。M6建立了完整的Robot Runtime基础设施：Skill Runtime + Runtime API + Experience + CLI + Visualization设计。

**问题**: M7将从"功能开发"进入"平台演化"阶段。如果不冻结M6接口，M7开发中可能因需求变化而修改核心接口，导致：
1. 已验证的434+ tests失效
2. M6已建立的Runtime闭环被破坏
3. M7各子阶段之间接口不稳定，产生架构债
4. 无法区分"接口扩展"(安全)和"接口破坏"(危险)

**触发条件**: M6全部完成，M7工程spec v2.0通过四轮架构评审。

---

## Decision

**冻结M6全部核心接口为v1.0**，建立M7 Platform Governance基线。

### 冻结范围

#### Tier 1: 永不可破坏 (13项)

这些接口是M6 Runtime闭环的基石，M7任何阶段都不得修改已有字段。

| # | 接口 | 类型 | 文件 | 冻结内容 |
|---|------|------|------|----------|
| 1 | ExecuteTask | Action | `action/ExecuteTask.action` | Goal/Result/Feedback字段 |
| 2 | TaskGoal | Msg | `msg/TaskGoal.msg` | 所有字段 |
| 3 | TaskConstraint | Msg | `msg/TaskConstraint.msg` | 所有字段 |
| 4 | SafetyCheck | Srv | `srv/SafetyCheck.srv` | Request/Response字段 |
| 5 | EmergencyStop | Srv | `srv/EmergencyStop.srv` | Request/Response字段 |
| 6 | QueryResources | Srv | `srv/QueryResources.srv` | Request/Response字段 |
| 7 | ExecuteSkill | Action | `action/ExecuteSkill.action` | Goal/Result/Feedback字段 |
| 8 | SubmitTaskGoals | Action | `action/SubmitTaskGoals.action` | Goal/Result/Feedback字段 |
| 9 | SkillManifest Schema | YAML | `skill_manifest.yaml` | 14字段结构 |
| 10 | SkillLifecycleState | Enum | `skill_lifecycle.py` | 10状态+转换矩阵 |
| 11 | ListSkills | Srv | `srv/ListSkills.srv` | Request/Response字段 |
| 12 | ManageSkill | Srv | `srv/ManageSkill.srv` | Request/Response字段 |
| 13 | QueryWorld | Srv | `srv/QueryWorld.srv` | Request/Response字段 |

#### Tier 2: 可扩展不可破坏 (8项)

这些接口可追加可选字段，但已有字段不可修改。

| # | 接口 | 类型 | 扩展规则 |
|---|------|------|----------|
| 14 | ObjectState | Msg | 可追加可选字段(如confidence, uncertainty) |
| 15 | ObjectPose | Msg | 可追加可选字段 |
| 16 | SceneState | Msg | 可追加可选字段 |
| 17 | Relation | Msg | 可追加可选字段 |
| 18 | CollisionEvent | Msg | 可追加可选字段 |
| 19 | ResourceStatus | Msg | 可追加可选字段 |
| 20 | RecoveryAction | Msg | 可追加可选字段 |
| 21 | SystemHealth | Msg | 可追加可选字段 |

#### Tier 3: Runtime API契约 (7项)

CLI和Runtime API的命令接口，M7可新增命令但已有命令语义不变。

| # | API | 扩展规则 |
|---|-----|----------|
| 22 | `robot status` | 输出格式可扩展，已有字段不变 |
| 23 | `robot world` | 查询语义不变 |
| 24 | `robot skills` | 列表语义不变 |
| 25 | `robot run <task>` | 提交语义不变 |
| 26 | `robot episodes` | 查询语义不变 |
| 27 | `robot traces` | 查询语义不变 |
| 28 | `robot benchmark` | 执行语义不变 |

#### Tier 4: 架构约束 (5项)

不可变架构决策，M7不得违反。

| # | 约束 | 规则 |
|---|------|------|
| 29 | Coordinator不膨胀 | Coordinator仅编排，业务逻辑下沉子模块 |
| 30 | Safety独立 | SafetySupervisor不依赖Coordinator运行 |
| 31 | WorldModel真相源 | 所有层读取环境状态从WorldModel获取 |
| 32 | 跨包走接口 | 跨包通信通过multi_arm_interfaces，禁止Python类直接共享 |
| 33 | 参数YAML驱动 | 新增臂/资源只需更新YAML，不修改代码 |

---

### 冻结规则

#### 永禁止 (Tier 1)

```
❌ 修改已有字段的类型、名称、语义
❌ 删除已有字段
❌ 修改Skill状态转换矩阵（减少合法转换）
❌ 修改ExecuteTask failure_modes语义
```

#### 允许扩展 (Tier 1)

```
✅ 追加可选字段到msg/srv/action末尾（必须有默认值）
✅ 新增Skill Lifecycle状态（只能扩展，不能修改已有转换）
✅ 新增recovery failure_type
```

#### 允许扩展 (Tier 2)

```
✅ 追加可选字段（必须有默认值）
✅ 新增枚举值（不修改已有值语义）
```

#### 允许扩展 (Tier 3)

```
✅ 新增CLI命令（如robot scene, robot capability, robot evaluate）
✅ 已有命令追加可选flag
❌ 已有命令修改位置参数语义
```

---

### 治理流程

```
M7开发中需要修改冻结接口时:

1. 提出ADR变更请求 (ADR-Change-Request)
2. 评估影响范围 (多少tests受影响)
3. 评估替代方案 (能否通过扩展而非修改)
4. 架构评审 (是否批准破坏性修改)
5. 如批准: 版本升级v1.0→v2.0, 全量回归测试
6. 如拒绝: 通过扩展实现需求
```

---

### CI强制检查

```
interface-compat CI job:
  1. 对比M6 freeze snapshot与当前接口定义
  2. Tier 1任何字段变化 → CI FAIL
  3. Tier 2字段删除 → CI FAIL
  4. Tier 2字段类型变化 → CI FAIL
  5. Tier 3命令删除 → CI FAIL
```

---

## Consequences

### 正面

1. M7开发有明确边界：知道什么能改，什么不能改
2. 434+ tests成为永久回归基线
3. M7各子阶段可以独立开发，接口契约保证集成
4. 未来M8/M9可以依赖稳定的M6 v1.0接口

### 负面

1. 某些M7需求可能需要通过"扩展"而非"修改"实现，设计成本略高
2. 如果确实需要破坏性修改，需要走ADR变更流程

### 风险缓解

1. Tier 2允许追加可选字段，覆盖大部分M7扩展需求
2. WorldModel的ObjectState扩展(confidence/uncertainty)属于Tier 2，安全
3. 新增接口(BaseState, EpisodeData等)不受冻结限制

---

## M7 Governance Principles

```
1. 接口先行，契约先行
   - M7.0先定义接口schema，后续阶段才实现
   - 新接口在multi_arm_interfaces中定义，禁止Python类直接共享

2. 扩展优先，修改最后
   - 优先通过追加可选字段扩展
   - 只有扩展无法满足时才走ADR变更

3. 每阶段冻结
   - M7.0完成后冻结Foundation接口
   - M7.1完成后冻结Body接口
   - 逐阶段建立不可逆基线

4. 回归基线永久有效
   - M6的434+ tests是永久基线
   - M7每阶段完成后，该阶段tests加入永久基线

5. Safety Plane横切不可绕过
   - M7.S Safety Layer贯穿所有阶段
   - 安全限制不可被任何M7功能绕过
```

---

## References

- `docs/architecture/interface_catalog.md` — M5.7接口资产盘点 (18接口)
- `docs/architecture/api_contracts.md` — M5.7接口契约+数据模型冻结
- `docs/architecture/ADR-M6.3-Freeze.md` — M6.3 Skill Runtime冻结 (本ADR扩展)
- `docs/architecture/M7_engineering_spec.md` — M7工程落地与验收标准
- `docs/architecture/robot_body_upgrade_design.md` — M7设计文档v3.0