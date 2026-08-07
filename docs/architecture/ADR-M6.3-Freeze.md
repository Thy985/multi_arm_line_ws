# ADR-M6.3-Freeze: Skill Runtime Interface Freeze v1.0

> **Status**: ACCEPTED
> **Date**: 2026-08-07
> **Decision Maker**: Architecture Review (4th Round)
> **Supersedes**: None
> **Superseded by**: None

---

## Context

M6.0-M6.3已完成实施，累计234 tests ALL PASS。M6.3 Skill Runtime引入了5个新ROS2接口和4个数据模型/枚举，这些接口将被M6.5 Robot Runtime API和M7 Agent层直接依赖。

**问题**: 如果不冻结M6.3接口，后续M6.5/M7开发中可能因需求变化而修改Skill Manifest结构或Lifecycle状态机，导致已验证的234 tests失效，且M6.5依赖不稳定。

**触发条件**: M6.3完成90 tests ALL PASS (63 unit + 25 E2E + 2 smoke)，E2E验证了Skill生命周期、失败恢复、状态验证三大核心场景。

---

## Decision

**冻结M6.3 Skill Runtime接口为v1.0**，建立M6 Gate 2基线。

### 冻结范围 (12项)

1. **SkillManifest Schema** — 14个字段，结构不可变
2. **SkillLifecycleState** — 10个状态，枚举不可变
3. **VALID_TRANSITIONS** — 状态转换矩阵不可变
4. **ExecutionStatus** — 5个值，枚举不可变
5. **Recovery Policy** — 触发条件+匹配顺序+返回值语义不可变
6. **ExecuteSkill.action** — Goal/Result/Feedback字段不可变
7. **ListSkills.srv** — Request/Response字段不可变
8. **ManageSkill.srv** — Request/Response字段不可变
9. **SkillDescription.msg** — 所有字段不可变
10. **SkillStatus.msg** — 所有字段不可变
11. **Skill Composition Contract** — 链式执行+optional规则不可变
12. **BT Compatibility Contract** — BT→Skill包装规则不可变

### 冻结规则

- **禁止**: 修改已有字段的类型、名称、语义
- **禁止**: 删除已有字段
- **禁止**: 修改状态转换矩阵（减少合法转换）
- **允许**: 追加可选字段到末尾（必须有默认值）
- **允许**: 新增状态（只能扩展，不能修改已有转换）
- **允许**: 新增recovery failure_type

---

## Rationale

### 为什么现在冻结

1. **M6.5直接依赖**: M6.5 Robot Runtime API的ExecuteSkill/ListSkills/ManageSkill/SubmitTaskGoals全部依赖M6.3冻结的接口。不冻结则M6.5开发无稳定基础。

2. **234 tests验证通过**: M6.0(30)+M6.S(44)+M6.1(40)+M6.2(30)+M6.3(90)=234 tests ALL PASS，接口行为已充分验证。

3. **E2E闭环验证**: 25个E2E测试验证了Skill生命周期(4)、TaskGoal→Skill选择(3)、组合执行(3)、失败恢复(5)、状态验证(5)、热更新(3)、卸载(2)——覆盖了所有核心场景。

4. **与M5.7一致**: M5.7已冻结v1.0（18个接口），M6.3冻结延续同一治理策略。

### 为什么不等到M6.5

M6.5是M6.3的消费者，不是协作者。M6.5开发期间不应修改M6.3接口——如果M6.5需要新字段，应通过"可选字段追加"扩展规则实现，而非修改冻结接口。

### 风险评估

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| M7需要新字段 | 中 | 低 | 扩展规则允许追加可选字段 |
| Lifecycle状态不足 | 低 | 中 | 扩展规则允许新增状态 |
| Recovery策略不够 | 低 | 低 | 扩展规则允许新增failure_type |
| 接口设计有误 | 低 | 高 | 234 tests验证+25 E2E覆盖核心场景 |

---

## Consequences

### 正面

- M6.5开发有稳定接口基础
- M7 Agent层可以基于冻结接口规划
- CI可以添加interface-compat检查（M6.3接口变更触发全量测试）
- 234 tests作为Gate 2基线回归测试

### 负面

- M6.5/M7不能修改M6.3接口（只能扩展）
- 如果发现设计缺陷，需要走变更审批流程（见api_contracts.md §5.2）

### 中性

- SkillManifest YAML格式固定，用户编写skill.yaml时有明确预期
- Skill Lifecycle 10状态固定，文档和代码一致

---

## Implementation

### 已完成

- [x] `docs/architecture/M6_3_SPEC.md` — 完整SPEC文档
- [x] `docs/architecture/ADR-M6.3-Freeze.md` — 本决策记录
- [x] `docs/validation/M6_3_validation_report.md` — 验证报告 (90 tests)
- [x] 234 tests ALL PASS (M6.0-M6.3)

### 待完成

- [ ] 更新 `docs/architecture/api_contracts.md` — 添加M6.3 FROZEN章节
- [ ] 更新 `docs/architecture/interface_catalog.md` — 盘点M6.3接口
- [ ] CI添加interface-compat检查 — M6.3接口变更触发全量测试

---

## References

- M5.7 Interface Freeze: `docs/architecture/api_contracts.md` §7
- M6.3 SPEC: `docs/architecture/M6_3_SPEC.md`
- M6.3 验证报告: `docs/validation/M6_3_validation_report.md`
- M6 规划: `docs/architecture/M6_platform_upgrade_plan.md` §M6.3
- E2E测试: `src/multi_arm_skill_runtime/test/test_e2e_skill_runtime.py` (25 tests)