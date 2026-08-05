# LLD - 抓取操作、调度与恢复模块详细设计

| 字段 | 内容 |
|------|------|
| 版本 | v2.1 |
| 作者 | Thy985 |
| 日期 | 2026-08-05 |
| 状态 | Draft |
| 关联架构 | Architecture-MultiArm-202608051018.md v2.1 |

---

## 1. 模块概述

Pick-Place抓取操作（BT.CPP驱动）+ ResourceManager/CapabilityMatcher + Recovery故障恢复。

---

## 2. Pick-Place（BehaviorTree.CPP驱动）

### 2.1 BT XML定义

```xml
<BehaviorTree ID="PickPlace">
  <Sequence>
    <Selector name="grasp_strategy">
      <Sequence><MoveTo goal="{approach_top}"/><Grasp approach="top"/></Sequence>
      <Sequence><MoveTo goal="{approach_side}"/><Grasp approach="side"/></Sequence>
    </Selector>
    <Lift height="0.1"/>
    <MoveTo goal="{place_approach}"/>
    <Place/>
    <Retract/>
  </Sequence>
</BehaviorTree>
```

### 2.2 BT Python插件

```python
class MoveToNode(py_trees.behaviour.Behaviour):
    """调用MoveIt2规划到目标位姿。"""
    def update(self):
        plan = self.moveit_planner.plan_to_pose(self.arm, self.target_pose)
        if plan.success: return py_trees.common.Status.SUCCESS
        return py_trees.common.Status.FAILURE

class GraspNode(py_trees.behaviour.Behaviour):
    """闭合夹爪，检测力反馈。"""
    def update(self):
        success = self.gripper.close()
        if success: return py_trees.common.Status.SUCCESS
        return py_trees.common.Status.FAILURE

class CheckSafetyNode(py_trees.behaviour.Behaviour):
    """查询Safety Plane。"""
    def update(self):
        approved, _ = self.safety_interface.check(self.arm, self.trajectory)
        return py_trees.common.Status.SUCCESS if approved else py_trees.common.Status.FAILURE

class RecoverNode(py_trees.behaviour.Behaviour):
    """调用Recovery层。"""
    def update(self):
        result = self.recovery_client.recover(self.failure_type, self.task_id)
        return py_trees.common.Status.SUCCESS if result.success else py_trees.common.Status.FAILURE
```

### 2.3 GripperController封装

```python
class GripperController:
    def __init__(self, node, arm_name): ...
    def open(self, width=0.08) -> bool: ...
    def close(self, width=0.0) -> bool: ...
```

---

## 3. ResourceManager + CapabilityMatcher

### 3.1 Resource

```python
class ResourceType(Enum):
    ROBOT = auto()    ZONE = auto()    TOOL = auto()    SENSOR = auto()    FIXTURE = auto()

class Resource:
    name: str
    resource_type: ResourceType
    state: ResourceState  # FREE | ALLOCATED | RESERVED | ERROR
    allocated_to: Optional[str]
    capabilities: Dict[str, Any]

class ResourceManager:
    def allocate(task_id, resources) -> AllocateResult
    def release(task_id) -> List[str]
    def query_available(resource_type) -> List[Resource]
```

### 3.2 CapabilityMatcher

```python
class CapabilityMatcher:
    """匹配任务需求与资源能力。"""
    def match(self, requirement: TaskRequirement, resources: List[Resource]) -> List[Resource]:
        """返回满足需求的资源，按匹配度排序。"""
        # requirement.capability_constraints: ["precision<0.05mm", "payload>2kg"]
        # resource.capabilities: {"precision_mm": 0.02, "payload_kg": 5.0}
```

### 3.3 AllocationStrategy（可插拔）

```python
class AllocationStrategy(ABC):
    @abstractmethod
    def allocate(self, task, arms, capabilities) -> Optional[str]: ...

class NearestArmStrategy(AllocationStrategy): ...
class LoadBalanceStrategy(AllocationStrategy): ...
class DeadlineStrategy(AllocationStrategy): ...

class StrategyFactory:
    _strategies = {'nearest': NearestArmStrategy, 'load_balance': LoadBalanceStrategy, 'deadline': DeadlineStrategy}
    @classmethod
    def create(cls, name) -> AllocationStrategy: ...
```

---

## 4. Recovery故障恢复

### 4.1 RecoveryManager

```python
class RecoveryManager(Node):
    """故障检测与策略恢复。Safety≠Recovery。"""
    def __init__(self):
        self.create_subscription(CollisionEvent, '/safety/collision_events', ...)
        self.create_service(RecoverFromFailure, '/recovery/recover', self._on_recover)
        self._strategies = {
            'grasp_failed': GraspRetry(),
            'planning_failed': ReplanMotion(),
            'comm_timeout': CommunicationReset(),
            'collision': CollisionRecovery(),
        }

    def _on_recover(self, request, response):
        strategy = self._strategies.get(request.failure_type)
        if strategy:
            result = strategy.execute(request.task_id)
            response.success = result.success
            response.recovery_strategy_used = strategy.name
        return response
```

### 4.2 恢复策略

```python
class GraspRetry:
    """抓取失败→换approach方向重试，3次失败→AbortTask。"""
    max_retries = 3
    approaches = ['top', 'side', 'angled']
    def execute(self, task_id) -> RecoveryResult: ...

class ReplanMotion:
    """规划失败→放宽约束重规划。"""
    def execute(self, task_id) -> RecoveryResult: ...

class CommunicationReset:
    """通信超时→重连action server。"""
    def execute(self, task_id) -> RecoveryResult: ...

class CollisionRecovery:
    """碰撞→退回安全位→更新WorldModel→重规划。"""
    def execute(self, task_id) -> RecoveryResult: ...
```

---

## 5. 测试要点

| 测试 | 验证 |
|------|------|
| test_bt_pick_place | BT完整Pick-Place流程 |
| test_grasp_retry | 抓取失败自动重试 |
| test_capability_match | 能力匹配正确 |
| test_resource_allocate | 资源分配与释放 |
| test_strategy_switch | 运行时切换调度策略 |
| test_recovery_grasp | GraspRetry恢复 |
| test_recovery_collision | CollisionRecovery恢复 |
| test_recovery_abort | 3次失败→AbortTask |