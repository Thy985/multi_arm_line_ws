# Robot Visual Identity v1.0

**Status**: FROZEN v1.0
**Date**: 2026-08-13
**Parent Document**: [robot_body_architecture.md](robot_body_architecture.md)

---

## 1. 风格定位

```
Industrial Research Robot
```

**关键词**：
- 简洁（clean lines）
- 模块化（visible module boundaries）
- 可信（industrial-grade quality）
- 非仿人（zero human resemblance）

**明确禁止**：
- ❌ 仿人皮肤色
- ❌ 卡通/萌系色彩
- ❌ 装饰性发光（除状态指示 LED）
- ❌ 拟人化造型（脸、表情）

---

## 2. 视觉参考

| 参考 | 借鉴点 | 避免点 |
|------|--------|--------|
| **Franka Emika Panda** | 白色外壳 + 暴露机械结构 + 模块边界清晰 | 关节处复杂曲线 |
| **Universal Robots (UR5e)** | 工业工具感 + 圆角关节 | 单调灰 |
| **ABB IRB 系列** | 工程感 + 显式功能分区 | 厚重感 |
| **KUKA LBR iiwa** | 白色 + 蓝色装饰 | 重复条纹 |

**取舍**：
- 借鉴 Franka 的"模块边界清晰"——视觉上能看出可拆卸
- 借鉴 UR 的"工业工具感"——避免学术/玩具感
- 借鉴 ABB 的"功能分区"——状态显示区域明显

---

## 3. 色彩系统 v1

### 3.1 主色板

| 模块 | 主色 | 辅助色 | 用途 |
|------|------|--------|------|
| base (底盘) | 哑光黑 #1A1A1A | — | 稳重、不抢眼 |
| torso (躯干) | 白色 #F5F5F5 | 灰色接缝 #808080 | 主视觉 |
| shoulder_mount (肩部) | 灰色 #4A4A4A | — | 工业感 |
| head (头部) | 白色 #F5F5F5 | 黑色传感器窗口 #0A0A0A | 与躯干协调 |
| UR5e arm | UR 官方色 (蓝灰 + 黑) | — | 保持 UR 辨识度 |
| gripper (夹爪) | 黑色 #1A1A1A | 黄色安全标识 #FFD700 | 工业安全色 |

### 3.2 状态色（LED + Display 专用）

| 状态 | 颜色 | HEX | 含义 |
|------|------|-----|------|
| READY | 绿 | #00C853 | 系统就绪 |
| RUNNING | 蓝 | #2962FF | 任务执行中 |
| FAILED | 红 | #D50000 | 任务失败 |
| SAFETY_STOP | 红闪烁 | #D50000 + blink | 安全停止 |
| OFFLINE | 灭 | — | 系统离线 |

**所有状态色必须**：
- 高对比度（Gazebo 仿真中可清晰辨识）
- 不与主色板冲突
- 工业感（不是 LED 装饰灯）

### 3.3 材质定义

| 材质 | 视觉特征 | 适用模块 |
|------|----------|----------|
| `metal_light` | 浅灰白，弱反光 | torso, head |
| `metal_dark` | 深灰，哑光 | base, shoulder_mount |
| `rubber` | 黑色，弱纹理 | gripper |
| `glass` | 黑色，弱反光 | 传感器窗口 |
| `panel_dark` | 深灰，平面 | LED 外壳 |

---

## 4. 模块级视觉规范

### 4.1 base (底盘)

```
视觉边界：1.4m × 0.5m × 0.3m
主色：metal_dark
装饰：前部状态 LED 条 (1.0m × 0.02m × 0.02m)
避免：圆形设计、卡通图案
```

### 4.2 torso (躯干)

```
视觉边界：0.3m 直径 × 0.5m 高（圆柱）
主色：metal_light
装饰：模块接缝、LED 条
约束：接缝在 0.25m 高度（视觉断开点）
```

### 4.3 shoulder_mount (肩部)

```
视觉边界：0.15m × 0.15m × 0.08m
主色：metal_dark
功能：明显的"机械结构过渡"——能看出 UR5e 装在这里
```

### 4.4 head (头部)

```
视觉边界：0.12m × 0.18m × 0.1m
主色：metal_light
传感器窗口：玻璃材质，居中
LED 环：前部，直径 0.06m
Display：可选（M7.x+ 实施）
```

### 4.5 UR5e arm

```
保持 UR 官方视觉（蓝灰 + 黑）
不修改（尊重厂商辨识度）
```

### 4.6 gripper (夹爪)

```
主色：rubber (黑)
安全标识：黄色条纹（仅夹爪前端 0.02m 区域）
警告：不要做"手"造型
```

---

## 5. 状态表达系统（与软件绑定）

### 5.1 LED Ring（head 前部）

| Runtime 状态 | 颜色 | 模式 | 频率 |
|--------------|------|------|------|
| READY | 绿 | 常亮 | — |
| RUNNING | 蓝 | 常亮 | — |
| FAILED | 红 | 常亮 | — |
| SAFETY_STOP | 红 | 闪烁 | 2 Hz |
| OFFLINE | 灭 | — | — |

### 5.2 LED Strip（base 前部）

| Runtime 状态 | 颜色 | 模式 | 含义 |
|--------------|------|------|------|
| READY | 绿 | 慢闪 (0.5 Hz) | 系统就绪，待命 |
| RUNNING | 蓝 | 流光 | 任务执行中 |
| FAILED | 红 | 快闪 (4 Hz) | 任务失败 |
| SAFETY_STOP | 红 | 闪烁 (2 Hz) | 安全停止 |

**与 head LED 区别**：
- head LED 表达"系统状态"
- base LED 表达"任务状态"（人眼近距离观察底盘时更明显）

### 5.3 Head Display（可选 v1.1+）

显示内容（如果实施）：

```
READY
========
Task: none
Last: pick_cube -> success
```

| 状态 | 显示 |
|------|------|
| READY | "READY" |
| RUNNING | "Task ID + Progress" |
| FAILED | "Failed: 原因缩写" |
| SAFETY_STOP | "E-STOP" |
| OFFLINE | "OFFLINE" |

**实施位置**：Phase 3 头部屏幕 UI（v1.0 预留，不实施）

---

## 6. 视觉一致性原则

### 6.1 跨模块一致性

- 同一类材料在不同模块必须**视觉一致**（metal_light 在 torso/head 必须相同）
- 圆角半径 ≤ 5mm（小圆角，工业感）
- 接缝宽度 ≤ 2mm（精细）
- 螺栓、接缝可见但不过度

### 6.2 不可变规则

1. **不引入装饰图案**（条纹、logo、文字除状态显示）
2. **不修改 UR5e 官方视觉**（尊重厂商）
3. **状态色不用于装饰**（只能用 LED/Display 表达状态）
4. **不使用金属漆/电镀效果**（高反光与工业感冲突）

### 6.3 实施检查清单

每个新视觉元素提交前必须验证：
- [ ] 主色属于已批准色板
- [ ] 不引入新材质
- [ ] 圆角 ≤ 5mm
- [ ] 不含装饰图案
- [ ] 不含文字（除状态显示）

---

## 7. 与 Robot OS 的对应

```
Robot OS
    |
Runtime State (READY/RUNNING/FAILED/SAFETY_STOP)
    |
Physical Expression
    |--- LED Ring (head): 系统状态
    |--- LED Strip (base): 任务状态
    +--- Head Display (optional): 详细状态
```

**关键原则**：物理表达是软件状态的**唯一**视觉表达通道。
不要让用户"猜"机器人状态——通过 LED 模式就能立刻知道。

---

## 8. Phase 实施时序

| Phase | 视觉任务 | 依赖 |
|-------|----------|------|
| Phase 0 | 无（primitive visual） | — |
| Phase 1.0（当前回退） | 全部 primitive | — |
| Phase 1.5（未来） | 简单 box + 颜色，无 mesh | body_architecture v1.0 ✅ |
| Phase 2 | 引入正式 mesh（保留 visual ≠ collision） | shoulder frame 锁定 |
| Phase 2.5 | LED 颜色绑定 Runtime State | Runtime Manager 暴露状态 topic |
| Phase 3 | 完整外观 + head display | Display 实施 |

**当前**：Phase 1.0 已完成（primitive visual），等 Phase 2 shoulder frame 锁定后做正式 mesh。

---

## 9. 冻结声明

本文档 v1.0 冻结以下内容：
- ✅ 风格定位 = Industrial Research Robot
- ✅ 主色板（5 模块色 + 5 状态色 + 5 材质）
- ✅ 状态表达通道（LED ring + LED strip + Display）
- ✅ 视觉一致性原则
- ✅ Phase 实施时序

**禁止破坏性修改**。如需新增视觉元素，进入 v1.1 评审。

---

**End of Robot Visual Identity v1.0**