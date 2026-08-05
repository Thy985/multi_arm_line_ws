# LLD - 抓取操作与动态调度模块详细设计

| 字段 | 内容 |
|------|------|
| 版本 | v1.0 |
| 作者 | Thy985 |
| 日期 | 2026-08-05 |
| 状态 | Draft |
| 关联HLD | HLD-MultiArm-Dev-202608051004.md |

---

## 1. 模块概述

本模块包含两部分：
1. **抓取操作**：夹爪集成 + Pick-Place状态机
2. **动态调度**：可插拔任务分配策略 + 动态臂数量支持

---

## 2. 详细设计目标

1. 实现完整的Pick-Place操作流水线
2. 支持多种夹爪类型（Robotiq 2F-85为默认）
3. 任务分配策略可插拔替换
4. 支持运行时增减机械臂数量

---

## 3. 数据模型

### 3.1 抓取任务数据类

```python
@dataclass
class GraspTarget:
    object_id: str
    pose: PoseStamped
    grasp_approach_axis: str = 'z'  # approach方向
    grasp_width: float = 0.08       # 夹爪开合宽度(m)
    grasp_effort: float = 50.0      # 夹紧力(N)

@dataclass
class PickPlaceTask:
    task_id: str
    arm_name: str
    pick_target: GraspTarget
    place_pose: PoseStamped
    priority: TaskPriority = TaskPriority.MEDIUM
    status: str = 'PENDING'
```

### 3.2 调度策略数据类

```python
@dataclass
class ArmCapability:
    arm_name: str
    max_payload: float = 5.0        # kg
    reachable_zones: List[str] = field(default_factory=list)
    current_load: float = 0.0       # 0.0-1.0
    distance_to: Dict[str, float] = field(default_factory=dict)
```

---

## 4. 核心类/接口定义

### 4.1 PickAndPlaceNode

```python
class PickAndPlaceNode(Node):
    """Pick-Place操作状态机节点。"""

    STATES = Enum('PickPlaceStates', [
        'IDLE', 'APPROACHING', 'GRASPING', 'LIFTING',
        'TRANSITING', 'PLACING', 'RETRACTING', 'ERROR'
    ])

    def __init__(self):
        super().__init__('pick_and_place')
        self._state = self.STATES.IDLE
        self._planner: MoveItPlanner = None
        self._gripper_clients: Dict[str, ActionClient] = {}

    def execute(self, arm_name: str, pick: GraspTarget,
                place: PoseStamped) -> bool:
        """执行完整的Pick-Place流程。"""
        ...

    def _approach(self, arm_name: str, target: GraspTarget) -> bool:
        """移动到抓取接近位姿。"""
        ...

    def _grasp(self, arm_name: str, target: GraspTarget) -> bool:
        """闭合夹爪抓取。"""
        ...

    def _lift(self, arm_name: str, height: float = 0.1) -> bool:
        """抬起物体。"""
        ...

    def _transit(self, arm_name: str, place: PoseStamped) -> bool:
        """转移到放置位姿。"""
        ...

    def _place(self, arm_name: str) -> bool:
        """打开夹爪放置。"""
        ...

    def _retract(self, arm_name: str) -> bool:
        """退回到安全位置。"""
        ...
```

### 4.2 GripperController封装

```python
class GripperController:
    """夹爪控制器封装。"""

    def __init__(self, node: Node, arm_name: str):
        self._client = ActionClient(
            node, GripperCommand,
            f'/{arm_name}/gripper_controller/gripper_cmd'
        )

    def open(self, width: float = 0.08) -> bool:
        """打开夹爪。"""
        return self._command(width, max_effort=50.0)

    def close(self, width: float = 0.0) -> bool:
        """闭合夹爪。"""
        return self._command(width, max_effort=50.0)

    def _command(self, position: float, max_effort: float) -> bool:
        """发送夹爪命令。"""
        goal = GripperCommand.Goal()
        goal.command.position = position
        goal.command.max_effort = max_effort
        # ... 同步/异步执行 ...
```

### 4.3 AllocationStrategy接口与实现

```python
from abc import ABC, abstractmethod

class AllocationStrategy(ABC):
    """任务分配策略抽象基类。"""

    @abstractmethod
    def allocate(self, task: Task,
                 arms: Dict[str, ArmStatus],
                 capabilities: Dict[str, ArmCapability]) -> Optional[str]:
        """返回最适合执行任务的臂名称，无可用臂返回None。"""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        pass


class NearestArmStrategy(AllocationStrategy):
    """选择距离目标最近的空闲臂。"""

    @property
    def name(self) -> str:
        return 'nearest'

    def allocate(self, task, arms, capabilities) -> Optional[str]:
        idle_arms = [n for n, s in arms.items() if s.state == ArmState.IDLE]
        if not idle_arms:
            return None
        # 按到目标Zone距离排序
        return min(idle_arms,
                   key=lambda n: capabilities[n].distance_to.get(task.zone_name, float('inf')))


class LoadBalanceStrategy(AllocationStrategy):
    """选择负载最低的臂。"""

    @property
    def name(self) -> str:
        return 'load_balance'

    def allocate(self, task, arms, capabilities) -> Optional[str]:
        idle_arms = [n for n, s in arms.items() if s.state == ArmState.IDLE]
        if not idle_arms:
            return None
        return min(idle_arms,
                   key=lambda n: capabilities[n].current_load)


class DeadlineStrategy(AllocationStrategy):
    """按截止时间紧急度分配，最紧急的任务优先获得最近的臂。"""

    @property
    def name(self) -> str:
        return 'deadline'

    def allocate(self, task, arms, capabilities) -> Optional[str]:
        idle_arms = [n for n, s in arms.items() if s.state == ArmState.IDLE]
        if not idle_arms:
            return None
        # 综合距离和负载
        return min(idle_arms,
                   key=lambda n: (0.6 * capabilities[n].distance_to.get(task.zone_name, 1.0)
                                + 0.4 * capabilities[n].current_load))


class StrategyFactory:
    """策略工厂。"""

    _strategies = {
        'nearest': NearestArmStrategy,
        'load_balance': LoadBalanceStrategy,
        'deadline': DeadlineStrategy,
    }

    @classmethod
    def create(cls, name: str) -> AllocationStrategy:
        strategy_cls = cls._strategies.get(name)
        if not strategy_cls:
            raise ValueError(f'Unknown strategy: {name}. Available: {list(cls._strategies.keys())}')
        return strategy_cls()

    @classmethod
    def available(cls) -> List[str]:
        return list(cls._strategies.keys())
```

### 4.4 TaskScheduler改造

```python
class TaskScheduler:
    def __init__(self, time_manager, arm_names):
        self.time_manager = time_manager
        self._strategy: AllocationStrategy = NearestArmStrategy()
        # ...

    def set_strategy(self, strategy_name: str) -> bool:
        """动态切换调度策略。"""
        try:
            self._strategy = StrategyFactory.create(strategy_name)
            return True
        except ValueError:
            return False

    def _auto_assign_arm(self, task: Task,
                          arms: Dict[str, ArmStatus],
                          capabilities: Dict[str, ArmCapability]) -> Optional[str]:
        """使用当前策略自动分配臂。"""
        return self._strategy.allocate(task, arms, capabilities)

    @property
    def current_strategy(self) -> str:
        return self._strategy.name
```

---

## 5. 详细流程

### 5.1 Pick-Place状态机

```
IDLE
  │
  ▼ execute(arm, pick, place)
APPROACHING ──(MoveIt2规划到approach位姿)──→ GRASPING
  │ fail                                         │ fail
  ▼                                              ▼
ERROR ←────────────────────────────────────── ERROR
  │                                              │
  │ (timeout)                                    ▼ close gripper
  │                                          LIFTING
  │                                              │
  │                                              ▼ lift 0.1m
  │                                          TRANSITING
  │                                              │
  │                                              ▼ MoveIt2到place位姿
  │                                          PLACING
  │                                              │
  │                                              ▼ open gripper
  │                                          RETRACTING
  │                                              │
  │                                              ▼ retreat to safe pose
  │                                          IDLE
```

### 5.2 动态调度流程

```
1. 任务提交到TaskScheduler
2. TaskScheduler.schedule_all()
3. 对每个待调度任务：
   a. 调用 _auto_assign_arm(task, arms, capabilities)
   b. 策略根据当前臂状态和任务需求选择最佳臂
   c. 检查Zone可用性
   d. 检查时间窗口冲突
   e. 如果可用 → 分配并执行
   f. 如果不可用 → 推迟到下一轮调度
4. 返回调度计划
```

---

## 6. 错误处理与边界情况

| 场景 | 处理 |
|------|------|
| 夹爪闭合后物体滑落 | 力反馈检测stalled→重试一次→标记ERROR |
| 抓取位姿不可达 | MoveIt2规划失败→尝试替代approach方向→回退 |
| 放置时物体卡在夹爪 | 开合3次尝试释放→标记ERROR |
| 所有臂都忙碌 | 任务进入等待队列，有空闲臂时触发 |
| 策略返回None | 任务标记为FAILED，记录原因 |
| 臂动态移除 | 该臂任务重新分配到其他臂 |
| 双臂同时竞争同一任务 | 策略决定优先级，另一臂分配下一个任务 |

---

## 7. 性能与资源估算

| 指标 | 估算值 | 说明 |
|------|--------|------|
| Pick-Place单次耗时 | 8-15s | approach+grasp+lift+transit+place+retract |
| 策略分配延迟 | < 1ms | 纯数值计算 |
| 夹爪动作时间 | 0.5-2s | 开/闭 |
| 抓取成功率 | > 90% | 简单几何物体 |
| 调度器吞吐量 | > 100 tasks/s | 内存中排序 |

---

## 8. 测试要点

### 8.1 单元测试

| 测试 | 验证内容 |
|------|----------|
| test_gripper_open_close | 夹爪开合命令发送与结果 |
| test_nearest_strategy | 最近臂策略选择正确 |
| test_load_balance_strategy | 负载均衡策略选择正确 |
| test_deadline_strategy | 截止时间策略选择正确 |
| test_strategy_factory | 工厂创建正确策略实例 |
| test_strategy_switch | 运行时切换策略 |
| test_no_idle_arm | 所有臂忙碌时返回None |

### 8.2 集成测试

| 测试 | 验证内容 |
|------|----------|
| test_pick_place_full | 完整Pick-Place流程 |
| test_grasp_retry | 抓取失败重试 |
| test_concurrent_tasks | 多任务并发调度 |
| test_arm_removal | 臂移除后任务重新分配 |

### 8.3 E2E测试

| 测试 | 验证内容 |
|------|----------|
| test_production_line | 连续10个Pick-Place任务 |
| test_mixed_strategy | 运行中切换策略后继续执行 |