# Robot OS Shell — Runtime Manager 设计文档

**版本**: 1.0
**日期**: 2026-08-13
**定位**: 将 CLI 从"ROS 命令封装"升级为"机器人操作系统入口"

---

## 1. 问题陈述

### 1.1 现状

CLI v2.0 仍然是 ROS 工程师工作流：

```
人 → 设置环境变量 → source ROS → colcon build → source install →
检查 DDS → 检查节点 → 启动 Gazebo → 检查 controller → 执行 robot run
```

这种工作流存在 5 个根本问题：

| # | 问题 | 影响 |
|---|------|------|
| 1 | 多次启动仿真后残留 gz_sim / controller_manager 进程 | 端口冲突、内存泄漏 |
| 2 | DDS discovery 缓存过期节点 | 重复 action server、消息路由错误 |
| 3 | 用户手动 `killall`/`pkill` 误杀系统进程 | 不安全、不可预测 |
| 4 | 无法区分"自己启动的"和"别人启动的"进程 | 多用户/多实验互相干扰 |
| 5 | 每次启动都要重新检测环境 | 重复劳动、无一致性 |

### 1.2 根本原因

ROS2 默认没有 **Runtime Ownership** 概念：

> "这个机器人实例是谁启动的？"

ROS2 的 `ros2 launch` 只负责启动进程，不跟踪生命周期。第二次启动不知道第一次启动的进程是否还存在。

---

## 2. 解决方案：Runtime Manager

### 2.1 核心理念

引入 Session 概念，每次 `robot start` 创建一个独立 session：

```
Session = 一个完整的机器人运行时实例
       = 一个 manifest.yaml（包含 PID 树）
       + 一个 DDS domain（隔离的通信域）
       + 一个进程组（通过 PID 树追踪）
```

### 2.2 架构

```
                 robot CLI (v2.1)

                       │
                       ▼

              Runtime Manager

            ┌──────────┼──────────┐
            │          │          │
     Session Manager  PID Tree  DDS Allocator
            │          │          │
            ▼          ▼          ▼
       manifest.yaml  /proc  ROS_DOMAIN_ID
       ~/.robot/      walk    40-59 pool
       runtime/

            │
            ▼

      Lifecycle Operations
            │
     ┌──────┼──────┐
     │      │      │
   start  stop  repair
```

### 2.3 Session 目录结构

```
~/.robot/runtime/
    current -> session-20260813-101954/    # 符号链接
    session-20260813-101954/
        manifest.yaml       # session 元数据
        pid.lock            # launch 进程 PID
        logs/
            launch.log      # stdout/stderr
```

**manifest.yaml** 示例：

```yaml
session_id: session-20260813-101954
created_at: '2026-08-13T10:19:54'
domain_id: 40
launch_pid: 88287
processes:
  gazebo: 88301
  controller_manager: 88350
  skill_runtime_node: 88400
scene: tabletop
gui: false
status: running
```

### 2.4 PID 树管理

`stop_session()` 只杀自己拥有的进程树，绝不 `killall`：

```
robot runtime
    │
    ├── launch process (pid=88287)
    │       │
    │       ├── gazebo (pid=88301)
    │       │       └── gz sim (pid=88302)
    │       ├── controller_manager (pid=88350)
    │       ├── skill_node (pid=88400)
    │       └── ... 
    │
    └── sub-processes tracked via /proc/<pid>/stat
```

`robot stop` 流程：
1. SIGTERM → launch process（优雅退出）
2. wait 0.5s
3. SIGKILL → launch process + 所有子进程（兜底）
4. 清理 `current` 符号链接

---

## 3. Robot OS Shell

### 3.1 设计目标

类似 Claude Code / Flutter：

```
$ robot
```

无参数启动 = 进入交互环境。

### 3.2 Bootstrap 序列

```
Checking environment...

  ✓ ROS2: ROS_DISTRO=jazzy
  ✓ Workspace: install/setup.bash
  ✓ DDS: CycloneDDS
  ✓ Runtime: no active session

  Ready.
```

### 3.3 Auto-Repair 提示

如果检测到残留进程：

```
  ⚠ Runtime issues detected:

    Duplicate gazebo: PID 83719, 83751, 83753
    Stale DDS node: /head_camera_tf
    Stale DDS node: /skill_runtime_node

  Auto-repair? [Y/n] y

  ✓ Killed 2 stale process(es)
  ✓ Runtime repaired

robot>
```

### 3.4 交互命令

Shell 内可用命令：

| 命令 | 功能 |
|------|------|
| `start [--gui] [--scene]` | 启动 session |
| `stop` | 停止 session |
| `status` | 查看 session 状态 |
| `repair` | 自动修复 |
| `doctor` | 系统诊断 |
| `run <task> [args]` | 执行任务 |
| `world [object]` | 世界模型查询 |
| `skills` | 列出 Skills |
| `safety` | 安全命令 |
| `help` | 显示帮助 |
| `exit` / `quit` | 退出 |

未列出的命令会自动 passthrough 到 `robot <cmd>`。

---

## 4. 增强的 `robot doctor`

### 4.1 新增检查项

| 检查 | 类别 | 检测方法 |
|------|------|----------|
| Process duplicates | Runtime | `ps aux` + 分类 |
| DDS ghost nodes | DDS | `ros2 node list` 去重 |

### 4.2 输出示例

```
[Runtime] [FAIL] Process duplicates
  Problem: gazebo x3
  Suggested fix: Run: robot repair

[DDS] [FAIL] Ghost nodes
  Problem: 2 duplicate node(s): /head_camera_tf, /skill_runtime_node
  Suggested fix: Run: robot repair (restarts DDS daemon)
```

---

## 5. `robot repair` 自动修复

### 5.1 修复策略

| 问题 | 修复方式 |
|------|----------|
| 僵尸进程 (ppid=1) | SIGKILL |
| 重复进程 (同类型 >1) | SIGTERM 旧的，保留最新的 |
| DDS ghost nodes | `ros2 daemon stop/start` |
| Stale sessions | 标记 status=stale + 清理 current 链接 |

### 5.2 安全保证

- 只杀通过 `/proc` 验证的进程
- 不杀 ppid=0 或 kernel 进程
- 不杀当前 shell 的父进程
- 修复失败不会导致系统不可用

---

## 6. DDS 隔离

### 6.1 Domain ID 池

```
DOMAIN_POOL = [40, 41, 42, ..., 59]   # 20 个可用 domain
```

每个 session 自动分配一个未使用的 domain：

```
session-001 → domain 40
session-002 → domain 41
...
```

### 6.2 为什么不用 domain 0？

- domain 0 是 ROS2 默认域，所有未指定 domain 的进程都使用它
- 多 session 会互相干扰
- 使用 40-59 隔离不同实验/用户

---

## 7. 与旧 `robot sim start/stop` 的对比

| 维度 | `robot sim start` | `robot start` |
|------|-------------------|---------------|
| Session 跟踪 | ❌ | ✅ manifest.yaml |
| PID 树管理 | ❌ | ✅ launch_pid + 子进程 |
| DDS 隔离 | ❌ | ✅ 自动分配 domain 40-59 |
| 残留检测 | ❌ | ✅ stale session 检测 |
| 安全清理 | ❌（killall 风险） | ✅ 只杀自己的进程树 |
| Repair | ❌ | ✅ robot repair |

**向后兼容**: `robot sim start` 仍可用，但新代码推荐使用 `robot start`。

---

## 8. 实施状态

| 组件 | 状态 | 文件 |
|------|------|------|
| RuntimeManager | ✅ | `runtime_manager.py` |
| InteractiveShell | ✅ | `interactive_shell.py` |
| Lifecycle commands | ✅ | `cli.py:_dispatch_lifecycle` |
| Enhanced doctor | ✅ | `doctor.py:_check_runtime_health` |
| robot repair | ✅ | `runtime_manager.py:repair()` |
| Session manifest | ✅ | YAML 持久化 |
| DDS 隔离 | ✅ | Domain pool 40-59 |
| 22 CLI tests | ✅ | 全部通过 |

---

## 9. 未来扩展

| 优先级 | 任务 | 描述 |
|--------|------|------|
| ★★★★★ | Multi-session 并行 | 同时运行多个独立 session |
| ★★★★ | TUI 可视化 | 用 rich/textual 渲染实时状态 |
| ★★★ | Web Dashboard | M6.7 可视化层（已设计，后移） |
| ★★★ | Session 快照 | save/restore session 状态 |
| ★★ | Plugin 系统 | 支持第三方扩展 |