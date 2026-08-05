# TDD - 虚实同步、CI/CD与Benchmark技术设计

| 字段 | 内容 |
|------|------|
| 版本 | v2.1 |
| 作者 | Thy985 |
| 日期 | 2026-08-05 |
| 状态 | Draft |
| 关联架构 | Architecture-MultiArm-202608051018.md v2.1 |

---

## 1. 虚实同步

use_sim:=true/false切换，Coordinator零修改。实体模式安全降级(速度50%)。Safety分阶段: Service→Proxy→Hardware。

## 2. CI/CD

GitHub Actions: lint(ruff+mypy) + build(colcon) + test(pytest+colcon test)。PR门禁: 全部通过才能合并。

## 3. Benchmark场景化

YAML场景定义(pick_place_easy/dense/collision)。BenchmarkRecorder订阅任务/碰撞事件→SQLite。自动运行: ros2 launch multi_arm_benchmark run_scenario.launch.py scenario:=xxx。

## 4. 可观测性

/diagnostics扩展: +multi_arm/safety +multi_arm/planner +multi_arm/recovery。SystemMetricsNode→/system_metrics。ros2bag录制关键话题。

## 5. 实施步骤

1. CI配置 2. lint配置 3. Benchmark+scenarios 4. Diagnostics扩展 5. use_sim切换 6. 安全降级 7. Safety升级
