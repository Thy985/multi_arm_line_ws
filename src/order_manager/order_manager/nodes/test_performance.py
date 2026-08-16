#!/usr/bin/env python3
"""
性能压力测试
验证系统在高负载下的性能和稳定性
"""

import sys
import time
import threading
import psutil
import os
import rclpy
from rclpy.executors import MultiThreadedExecutor
from order_manager.nodes.multi_arm_coordinator import EnhancedMultiArmCoordinator
from order_manager.nodes.arm_state import ArmState
from order_manager.nodes.task_scheduler import TaskScheduler, Task, TaskPriority
from order_manager.nodes.time_manager import TimeManager

# ============================================================
# Test Framework
# ============================================================

class TestResult:
    def __init__(self, name):
        self.name = name
        self.passed = False
        self.message = ""
        self.metrics = {}

def run_test(name, test_fn, coordinator=None, timeout=30.0):
    """Run a test function with timeout."""
    result = TestResult(name)
    try:
        if coordinator:
            test_fn(coordinator, result, timeout)
        else:
            test_fn(result, timeout)
        result.passed = True
        print(f"  [PASS] {name}")
    except AssertionError as e:
        result.message = str(e)
        print(f"  [FAIL] {name}: {e}")
    except Exception as e:
        result.message = f"Exception: {e}"
        print(f"  [ERROR] {name}: {e}")
    return result

# ============================================================
# Performance Tests
# ============================================================

def test_memory_usage(result, timeout):
    """内存使用监控：无内存泄漏"""
    process = psutil.Process(os.getpid())
    
    # 记录初始内存
    initial_memory = process.memory_info().rss / 1024 / 1024  # MB
    print(f"    初始内存: {initial_memory:.1f} MB")
    
    # 创建多个协调器实例（不重复调用rclpy.init）
    coordinators = []
    
    for i in range(5):
        coord = EnhancedMultiArmCoordinator()
        coordinators.append(coord)
        time.sleep(0.1)
    
    # 记录创建后内存
    after_create_memory = process.memory_info().rss / 1024 / 1024
    print(f"    创建5个协调器后: {after_create_memory:.1f} MB")
    
    # 清理
    for coord in coordinators:
        coord.destroy_node()
    
    # 记录清理后内存
    time.sleep(1)
    after_cleanup_memory = process.memory_info().rss / 1024 / 1024
    print(f"    清理后: {after_cleanup_memory:.1f} MB")
    
    # 检查内存增长
    memory_growth = after_cleanup_memory - initial_memory
    result.metrics['initial_memory_mb'] = initial_memory
    result.metrics['after_create_memory_mb'] = after_create_memory
    result.metrics['after_cleanup_memory_mb'] = after_cleanup_memory
    result.metrics['memory_growth_mb'] = memory_growth
    
    # 允许最多10MB的内存增长
    assert memory_growth < 10.0, f"内存增长过大: {memory_growth:.1f} MB (允许最大10MB)"
    
    print(f"    内存增长: {memory_growth:.1f} MB (可接受)")


def test_cpu_usage(coord, result, timeout):
    """CPU使用监控：CPU使用合理"""
    process = psutil.Process(os.getpid())
    
    # 记录初始CPU使用
    cpu_percent = process.cpu_percent(interval=1)
    print(f"    初始CPU使用: {cpu_percent:.1f}%")
    
    # 执行多个任务
    start_time = time.time()
    tasks = []
    
    for i in range(10):
        task = Task(
            task_id=f'perf_task_{i}',
            zone_name='zone_a',
            position_name='ready',
            priority=TaskPriority.NORMAL,
        )
        tasks.append(task)
    
    # 批量提交任务
    from order_manager.nodes.task_scheduler import TaskScheduler
    tm = TimeManager()
    scheduler = TaskScheduler(tm, ['left_arm', 'right_arm'])
    
    for task in tasks:
        scheduler.submit(task)
    
    # 调度任务
    plan = scheduler.schedule_all()
    
    end_time = time.time()
    scheduling_time = end_time - start_time
    
    # 记录CPU使用
    cpu_percent_after = process.cpu_percent(interval=1)
    print(f"    调度10个任务后CPU使用: {cpu_percent_after:.1f}%")
    print(f"    调度耗时: {scheduling_time:.3f}s")
    
    result.metrics['initial_cpu_percent'] = cpu_percent
    result.metrics['after_cpu_percent'] = cpu_percent_after
    result.metrics['scheduling_time_s'] = scheduling_time
    result.metrics['tasks_scheduled'] = len(plan.scheduled)
    
    # CPU使用应该合理（< 50%）
    assert cpu_percent_after < 50.0, f"CPU使用过高: {cpu_percent_after:.1f}%"
    
    # 调度时间应该合理（< 1秒）
    assert scheduling_time < 1.0, f"调度时间过长: {scheduling_time:.3f}s"
    
    print(f"    调度任务数: {len(plan.scheduled)}/10")


def test_concurrent_response_time(coord, result, timeout):
    """并发任务响应时间：响应时间 < 1秒"""
    # 确保干净状态
    assert coord.arm_status['left_arm'].state == ArmState.IDLE
    assert coord.arm_status['right_arm'].state == ArmState.IDLE
    
    # 并发发送多个命令
    start_time = time.time()
    
    # left_arm -> zone_a
    success1 = coord.send_to_zone('left_arm', 'zone_a', 'ready', duration=2.0)
    
    # right_arm -> zone_b (不同zone，应该立即成功)
    success2 = coord.send_to_zone('right_arm', 'zone_b', 'ready', duration=2.0)
    
    end_time = time.time()
    response_time = end_time - start_time
    
    print(f"    并发命令响应时间: {response_time:.3f}s")
    
    result.metrics['response_time_s'] = response_time
    
    # 响应时间应该 < 1秒
    assert response_time < 1.0, f"响应时间过长: {response_time:.3f}s"
    
    # 验证两个命令都成功
    assert success1, "left_arm命令应该成功"
    assert success2, "right_arm命令应该成功"
    
    # 等待完成
    time.sleep(3)
    
    # 清理
    coord.arm_status['left_arm'].state = ArmState.IDLE
    coord.arm_status['right_arm'].state = ArmState.IDLE


def test_long_running_stability(coord, result, timeout):
    """长时间运行稳定性：运行10秒无崩溃"""
    process = psutil.Process(os.getpid())
    start_time = time.time()
    command_count = 0
    
    print("    开始长时间运行稳定性测试...")
    
    # 运行10秒
    while time.time() - start_time < 10:
        # 交替发送命令到两个臂
        if command_count % 2 == 0:
            arm_name = 'left_arm'
            zone_name = 'zone_a'
        else:
            arm_name = 'right_arm'
            zone_name = 'zone_b'
        
        # 检查臂状态
        if coord.arm_status[arm_name].state == ArmState.IDLE:
            coord.send_to_zone(arm_name, zone_name, 'ready', duration=1.0)
            command_count += 1
        
        time.sleep(0.5)
    
    # 等待所有命令完成
    time.sleep(3)
    
    # 验证系统仍然正常
    assert coord.arm_status['left_arm'].state == ArmState.IDLE, \
        f"left_arm应该是IDLE状态，实际是{coord.arm_status['left_arm'].state.name}"
    assert coord.arm_status['right_arm'].state == ArmState.IDLE, \
        f"right_arm应该是IDLE状态，实际是{coord.arm_status['right_arm'].state.name}"
    
    # 记录指标
    elapsed_time = time.time() - start_time
    result.metrics['elapsed_time_s'] = elapsed_time
    result.metrics['command_count'] = command_count
    result.metrics['commands_per_second'] = command_count / elapsed_time
    
    print(f"    运行时间: {elapsed_time:.1f}s")
    print(f"    命令数量: {command_count}")
    print(f"    命令频率: {command_count / elapsed_time:.2f} 命令/秒")


def test_batch_task_scheduling(result, timeout):
    """大量任务调度：调度100个任务无错误"""
    tm = TimeManager()
    scheduler = TaskScheduler(tm, ['left_arm', 'right_arm'])
    
    start_time = time.time()
    
    # 创建100个任务
    tasks = []
    zones = ['zone_a', 'zone_b', 'zone_c', 'home']
    positions = ['home', 'ready', 'extended', 'left', 'right']
    
    for i in range(100):
        task = Task(
            task_id=f'batch_task_{i}',
            zone_name=zones[i % len(zones)],
            position_name=positions[i % len(positions)],
            priority=TaskPriority.NORMAL,
            duration=2.0,
        )
        tasks.append(task)
    
    # 批量提交
    ids = scheduler.submit_batch(tasks)
    
    # 调度所有任务
    plan = scheduler.schedule_all()
    
    end_time = time.time()
    scheduling_time = end_time - start_time
    
    print(f"    创建100个任务耗时: {scheduling_time:.3f}s")
    print(f"    成功调度: {len(plan.scheduled)}/100")
    print(f"    调度失败: {len(plan.failed)}")
    
    result.metrics['total_tasks'] = 100
    result.metrics['scheduled_tasks'] = len(plan.scheduled)
    result.metrics['failed_tasks'] = len(plan.failed)
    result.metrics['scheduling_time_s'] = scheduling_time
    
    # 所有任务都应该被调度
    assert len(plan.scheduled) == 100, f"应该调度100个任务，实际调度了{len(plan.scheduled)}"
    assert len(plan.failed) == 0, f"应该没有失败任务，实际有{len(plan.failed)}个失败"
    
    # 调度时间应该合理
    assert scheduling_time < 5.0, f"调度时间过长: {scheduling_time:.3f}s"


# ============================================================
# Main
# ============================================================

def main():
    print("=" * 60)
    print("  Performance Stress Tests")
    print("=" * 60)
    
    rclpy.init()
    
    coordinator = EnhancedMultiArmCoordinator()
    
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(coordinator)
    
    # Spin executor in background
    spin_thread = threading.Thread(target=executor.spin, daemon=True)
    spin_thread.start()
    
    time.sleep(2)  # Let coordinator initialize
    
    print("\n--- Coordinator Status ---")
    coordinator.print_status()
    print()
    
    # Run tests
    results = []
    
    print("[PF-01] Memory usage monitoring")
    results.append(run_test("memory_usage", test_memory_usage))
    
    print("[PF-02] CPU usage monitoring")
    results.append(run_test("cpu_usage", test_cpu_usage, coordinator))
    
    print("[PF-03] Concurrent response time")
    results.append(run_test("concurrent_response_time", test_concurrent_response_time, coordinator))
    
    print("[PF-04] Long running stability")
    results.append(run_test("long_running_stability", test_long_running_stability, coordinator))
    
    print("[PF-05] Batch task scheduling")
    results.append(run_test("batch_task_scheduling", test_batch_task_scheduling))
    
    # Summary
    print("\n" + "=" * 60)
    print("  Test Summary")
    print("=" * 60)
    
    passed = sum(1 for r in results if r.passed)
    total = len(results)
    
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        msg = f" ({r.message})" if r.message else ""
        print(f"  [{status}] {r.name}{msg}")
        if r.metrics:
            for key, value in r.metrics.items():
                print(f"         {key}: {value}")
    
    print(f"\n  Result: {passed}/{total} passed")
    
    # Final status
    print("\n--- Final Coordinator Status ---")
    coordinator.print_status()
    
    # Cleanup
    executor.shutdown()
    coordinator.destroy_node()
    rclpy.shutdown()
    
    return 0 if passed == total else 1


if __name__ == '__main__':
    sys.exit(main())
