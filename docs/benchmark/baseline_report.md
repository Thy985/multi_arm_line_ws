# Baseline Report Template

| 字段 | 内容 |
|------|------|
| 版本 | v0.1 |
| 日期 | 2026-08-05 |
| 状态 | Template (待M4填充数据) |

---

## 1. 测量环境

| 项目 | 值 |
|------|-----|
| OS | Ubuntu 24.04 (WSL2) |
| ROS2 | Jazzy Jalisco |
| Gazebo | Harmonic |
| CPU | TBD |
| RAM | TBD |

---

## 2. 性能基线

### 2.1 任务调度延迟

| 指标 | Mock (M1-M3) | Gazebo (M4) |
|------|-------------|-------------|
| Task提交→ALLOCATED | TBD | TBD |
| SafetyCheck延迟 | TBD | TBD |
| ResourceManager分配延迟 | TBD | TBD |

### 2.2 运动规划性能

| 指标 | 目标 | 实测 |
|------|------|------|
| 单臂规划时间 (P95) | < 500ms | TBD |
| 双臂规划时间 (P95) | < 2000ms | TBD |
| 规划成功率 | > 95% | TBD |

### 2.3 Safety响应时间

| 指标 | 目标 | 实测 |
|------|------|------|
| E-Stop→全臂停止 | < 1s | TBD |
| 速度限制生效延迟 | < 100ms | TBD |
| 碰撞检测延迟 | < 50ms | TBD |

### 2.4 WorldModel更新延迟

| 指标 | 目标 | 实测 |
|------|------|------|
| joint_states→WorldModel | < 100ms (1-10Hz) | TBD |
| ObjectTracker更新 | < 200ms | TBD |

---

## 3. 稳定性基线

| 指标 | 目标 | 实测 |
|------|------|------|
| 连续运行时长 | > 1h 无crash | TBD |
| 任务成功率 | > 90% | TBD |
| 内存泄漏 | < 10MB/h | TBD |

---

## 4. M4测试场景

### M4.1 单臂闭环

```
home → target_pose → home
```

测量: 规划时间 + 执行时间 + 偏差 + WorldModel同步延迟

### M4.2 双臂资源协调

```
Task A: arm1 + zone_a
Task B: arm2 + zone_a (竞争)
```

测量: 调度延迟 + 排队时间 + 资源利用率

### M4.3 安全闭环

```
Case 1: velocity_scale=1.5 → Safety限制到0.5
Case 2: arm moving → E-Stop → 全臂停止
```

测量: Safety响应时间 + 停止延迟 + 状态恢复