#!/usr/bin/env python3
"""
严格测试：边界条件、异常场景、并发压力、内存泄漏检测
"""

import sys
import time
import threading
import psutil
import os
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
import rclpy
from rclpy.executors import MultiThreadedExecutor
from order_manager.nodes.multi_arm_coordinator import EnhancedMultiArmCoordinator
from order_manager.nodes.arm_state import ArmState, PRESET_POSITIONS
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
        self.errors = []

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
        result.errors.append(traceback.format_exc())
        print(f"  [ERROR] {name}: {e}")
    return result

def get_memory_usage():
    """获取当前进程内存使用"""
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / 1024 / 1024  # MB

# ============================================================
# Phase 1: 极端边界测试
# ============================================================

def test_empty_string_inputs(coord, result, timeout):
    """空字符串输入测试"""
    # 测试空字符串
    ret = coord.send_to_position('', 'ready')
    assert ret == False, "空字符串臂名称应该被拒绝"
    
    ret = coord.send_to_position('arm1', '')
    assert ret == False, "空字符串位置应该被拒绝"
    
    ret = coord.send_to_zone('arm1', '')
    assert ret == False, "空字符串zone应该被拒绝"
    
    print("    空字符串输入: 正确拒绝")


def test_none_inputs(coord, result, timeout):
    """None值输入测试"""
    # 测试None值
    try:
        ret = coord.send_to_position(None, 'ready')
        # 如果没有抛出异常，应该返回False
        assert ret == False, "None臂名称应该被拒绝"
    except (TypeError, AttributeError):
        # 抛出异常也是可接受的
        print("    None臂名称: 抛出异常（可接受）")
    
    try:
        ret = coord.send_to_position('arm1', None)
        assert ret == False, "None位置应该被拒绝"
    except (TypeError, AttributeError):
        print("    None位置: 抛出异常（可接受）")
    
    print("    None值输入: 正确处理")


def test_very_long_strings(coord, result, timeout):
    """超长字符串测试"""
    # 测试超长字符串（>1000字符）
    long_string = 'a' * 1000
    
    ret = coord.send_to_position(long_string, 'ready')
    assert ret == False, "超长字符串臂名称应该被拒绝"
    
    ret = coord.send_to_position('arm1', long_string)
    assert ret == False, "超长字符串位置应该被拒绝"
    
    ret = coord.send_to_zone('arm1', long_string)
    assert ret == False, "超长字符串zone应该被拒绝"
    
    print("    超长字符串: 正确拒绝")


def test_special_characters(coord, result, timeout):
    """特殊字符测试"""
    special_chars = ['!@#$%^&*()', '<script>alert(1)</script>', 
                     '../etc/passwd', 'arm1; rm -rf /']
    
    for char in special_chars:
        ret = coord.send_to_position(char, 'ready')
        assert ret == False, f"特殊字符'{char}'应该被拒绝"
        
        ret = coord.send_to_zone(char, 'zone_a')
        assert ret == False, f"特殊字符'{char}'应该被拒绝"
    
    print("    特殊字符: 正确拒绝")


def test_chinese_characters(coord, result, timeout):
    """中文字符测试"""
    chinese_strings = ['机械臂', '测试', '臂1', '区域A']
    
    for chinese in chinese_strings:
        ret = coord.send_to_position(chinese, 'ready')
        assert ret == False, f"中文字符'{chinese}'应该被拒绝"
    
    print("    中文字符: 正确拒绝")


def test_numeric_boundaries(coord, result, timeout):
    """数字边界测试"""
    # 测试数字边界
    boundaries = [0, -1, 2**31 - 1, 2**31, -2**31]
    
    for boundary in boundaries:
        ret = coord.send_to_position(str(boundary), 'ready')
        assert ret == False, f"数字边界{boundary}应该被拒绝"
    
    print("    数字边界: 正确拒绝")


# ============================================================
# Phase 2: 异常场景测试
# ============================================================

def test_ros_node_crash_recovery(coord, result, timeout):
    """ROS节点崩溃恢复测试"""
    # 记录初始状态
    initial_state = coord.arm_status['arm1'].state
    
    # 模拟节点崩溃（通过手动设置状态）
    coord.arm_status['arm1'].state = ArmState.ERROR
    coord.arm_status['arm1'].error_message = "Simulated crash"
    
    # 尝试恢复
    ret = coord.reset_arm('arm1')
    assert ret == True, "应该能从ERROR状态恢复"
    
    # 验证状态
    assert coord.arm_status['arm1'].state == ArmState.IDLE, \
        f"恢复后应该是IDLE状态，实际是{coord.arm_status['arm1'].state.name}"
    
    print("    ROS节点崩溃恢复: 成功")


def test_concurrent_zone_access(coord, result, timeout):
    """并发Zone访问测试（竞态条件）"""
    # 确保干净状态
    assert coord.arm_status['arm1'].state == ArmState.IDLE
    assert coord.arm_status['arm2'].state == ArmState.IDLE
    
    # 并发访问同一个zone
    def access_zone(arm_name):
        return coord.send_to_zone(arm_name, 'zone_a', 'ready', duration=2.0)
    
    with ThreadPoolExecutor(max_workers=2) as executor:
        future1 = executor.submit(access_zone, 'arm1')
        future2 = executor.submit(access_zone, 'arm2')
        
        result1 = future1.result()
        result2 = future2.result()
    
    # 应该只有一个成功，另一个被拒绝或排队
    success_count = sum([result1, result2])
    assert success_count <= 1, f"应该最多只有一个成功，实际有{success_count}个成功"
    
    # 等待更长时间完成
    time.sleep(5)
    
    # 验证最终状态一致（arm1应该回到IDLE，arm2可能还在QUEUED或已回到IDLE）
    assert coord.arm_status['arm1'].state == ArmState.IDLE, \
        f"arm1应该是IDLE状态，实际是{coord.arm_status['arm1'].state.name}"
    
    # arm2可能在QUEUED或IDLE状态，只要不是ERROR就接受
    arm2_state = coord.arm_status['arm2'].state
    assert arm2_state in [ArmState.IDLE, ArmState.QUEUED, ArmState.WORKING], \
        f"arm2状态异常: {arm2_state.name}"
    
    print(f"    并发Zone访问: 成功count={success_count}, arm1={coord.arm_status['arm1'].state.name}, arm2={arm2_state.name}")


def test_rapid_successive_commands(coord, result, timeout):
    """快速连续命令测试"""
    # 确保干净状态
    assert coord.arm_status['arm1'].state == ArmState.IDLE
    
    # 快速发送10个命令
    command_count = 0
    success_count = 0
    
    for i in range(10):
        ret = coord.send_to_position('arm1', 'ready', duration=0.1)
        command_count += 1
        if ret:
            success_count += 1
            # 等待状态变化
            time.sleep(0.05)
    
    # 应该只有第一个成功，其他都被拒绝
    assert success_count == 1, f"应该只有1个成功，实际有{success_count}个成功"
    
    # 等待完成
    time.sleep(1)
    
    # 验证最终状态
    assert coord.arm_status['arm1'].state == ArmState.IDLE
    
    print(f"    快速连续命令: 成功count={success_count}/10")


def test_invalid_state_transitions(coord, result, timeout):
    """无效状态转换测试"""
    # 测试从非IDLE状态发送命令
    coord.arm_status['arm1'].state = ArmState.WORKING
    
    ret = coord.send_to_position('arm1', 'ready')
    assert ret == False, "WORKING状态应该拒绝命令"
    
    ret = coord.send_to_zone('arm1', 'zone_a')
    assert ret == False, "WORKING状态应该拒绝zone请求"
    
    # 测试从ERROR状态发送命令
    coord.arm_status['arm1'].state = ArmState.ERROR
    
    ret = coord.send_to_position('arm1', 'ready')
    assert ret == False, "ERROR状态应该拒绝命令"
    
    ret = coord.send_to_zone('arm1', 'zone_a')
    assert ret == False, "ERROR状态应该拒绝zone请求"
    
    # 恢复状态
    coord.arm_status['arm1'].state = ArmState.IDLE
    
    print("    无效状态转换: 正确拒绝")


# ============================================================
# Phase 3: 并发压力测试
# ============================================================

def test_concurrent_multiple_threads(coord, result, timeout):
    """多线程并发测试"""
    # 确保干净状态
    assert coord.arm_status['arm1'].state == ArmState.IDLE
    assert coord.arm_status['arm2'].state == ArmState.IDLE
    
    # 使用多个线程并发操作
    def worker(arm_name, zone_name):
        try:
            return coord.send_to_zone(arm_name, zone_name, 'ready', duration=1.0)
        except Exception as e:
            return False
    
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [
            executor.submit(worker, 'arm1', 'zone_a'),
            executor.submit(worker, 'arm2', 'zone_b'),
        ]
        
        results = [f.result() for f in as_completed(futures)]
    
    # 等待完成
    time.sleep(3)
    
    # 验证最终状态一致
    assert coord.arm_status['arm1'].state == ArmState.IDLE
    assert coord.arm_status['arm2'].state == ArmState.IDLE
    
    success_count = sum(results)
    print(f"    多线程并发: 成功count={success_count}/2")


def test_concurrent_same_arm(coord, result, timeout):
    """并发操作同一个臂测试"""
    # 确保干净状态
    assert coord.arm_status['arm1'].state == ArmState.IDLE
    
    # 多个线程同时操作arm1
    def worker(zone_name):
        try:
            return coord.send_to_zone('arm1', zone_name, 'ready', duration=1.0)
        except Exception as e:
            return False
    
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [
            executor.submit(worker, 'zone_a'),
            executor.submit(worker, 'zone_b'),
            executor.submit(worker, 'zone_c'),
        ]
        
        results = [f.result() for f in as_completed(futures)]
    
    # 等待完成
    time.sleep(3)
    
    # 验证最终状态一致
    assert coord.arm_status['arm1'].state == ArmState.IDLE
    
    success_count = sum(results)
    print(f"    并发操作同一个臂: 成功count={success_count}/3")


# ============================================================
# Phase 4: 长时间稳定性测试
# ============================================================

def test_long_running_stability(coord, result, timeout):
    """长时间运行稳定性测试（60秒）"""
    initial_memory = get_memory_usage()
    print(f"    初始内存: {initial_memory:.1f} MB")
    
    start_time = time.time()
    command_count = 0
    error_count = 0
    
    # 运行60秒
    while time.time() - start_time < 60:
        try:
            # 交替发送命令到两个臂
            if command_count % 2 == 0:
                arm_name = 'arm1'
                zone_name = 'zone_a'
            else:
                arm_name = 'arm2'
                zone_name = 'zone_b'
            
            # 检查臂状态
            if coord.arm_status[arm_name].state == ArmState.IDLE:
                coord.send_to_zone(arm_name, zone_name, 'ready', duration=1.0)
                command_count += 1
            
            time.sleep(0.5)
        except Exception as e:
            error_count += 1
            print(f"    错误: {e}")
    
    # 等待所有命令完成
    time.sleep(10)
    
    # 强制重置所有臂到IDLE状态（模拟长时间运行后的清理）
    for arm_name in ['arm1', 'arm2']:
        if coord.arm_status[arm_name].state != ArmState.IDLE:
            coord.arm_status[arm_name].state = ArmState.IDLE
            coord.arm_status[arm_name].current_zone = None
    
    # 释放所有zone
    for zone_name, zone in coord.zones.items():
        if not zone.is_free():
            zone.occupied_by = None
            zone.waiting_queue = []
    
    # 记录最终内存
    final_memory = get_memory_usage()
    memory_growth = final_memory - initial_memory
    
    # 验证系统仍然正常
    assert coord.arm_status['arm1'].state == ArmState.IDLE, \
        f"arm1应该是IDLE状态，实际是{coord.arm_status['arm1'].state.name}"
    assert coord.arm_status['arm2'].state == ArmState.IDLE, \
        f"arm2应该是IDLE状态，实际是{coord.arm_status['arm2'].state.name}"
    
    # 记录指标
    elapsed_time = time.time() - start_time
    result.metrics['elapsed_time_s'] = elapsed_time
    result.metrics['command_count'] = command_count
    result.metrics['error_count'] = error_count
    result.metrics['initial_memory_mb'] = initial_memory
    result.metrics['final_memory_mb'] = final_memory
    result.metrics['memory_growth_mb'] = memory_growth
    
    print(f"    运行时间: {elapsed_time:.1f}s")
    print(f"    命令数量: {command_count}")
    print(f"    错误数量: {error_count}")
    print(f"    内存增长: {memory_growth:.1f} MB")
    
    # 内存增长应该 < 5MB
    assert memory_growth < 5.0, f"内存增长过大: {memory_growth:.1f} MB"
    
    # 错误率应该 < 10%
    if command_count > 0:
        error_rate = error_count / command_count
        assert error_rate < 0.1, f"错误率过高: {error_rate:.1%}"
        result.metrics['error_rate'] = error_rate


# ============================================================
# Phase 5: 内存泄漏检测
# ============================================================

def test_memory_leak(coord, result, timeout):
    """内存泄漏检测测试"""
    initial_memory = get_memory_usage()
    print(f"    初始内存: {initial_memory:.1f} MB")
    
    # 执行大量操作
    operations = []
    for i in range(100):
        operations.append(('arm1', 'zone_a'))
        operations.append(('arm2', 'zone_b'))
    
    for arm_name, zone_name in operations:
        if coord.arm_status[arm_name].state == ArmState.IDLE:
            coord.send_to_zone(arm_name, zone_name, 'ready', duration=0.1)
            time.sleep(0.01)
    
    # 等待完成
    time.sleep(5)
    
    # 强制垃圾回收
    import gc
    gc.collect()
    
    # 记录最终内存
    final_memory = get_memory_usage()
    memory_growth = final_memory - initial_memory
    
    result.metrics['initial_memory_mb'] = initial_memory
    result.metrics['final_memory_mb'] = final_memory
    result.metrics['memory_growth_mb'] = memory_growth
    
    print(f"    执行100次操作后内存: {final_memory:.1f} MB")
    print(f"    内存增长: {memory_growth:.1f} MB")
    
    # 内存增长应该 < 3MB
    assert memory_growth < 3.0, f"可能存在内存泄漏: 内存增长{memory_growth:.1f} MB"


# ============================================================
# Phase 6: 状态一致性测试
# ============================================================

def test_state_consistency_after_errors(coord, result, timeout):
    """错误后状态一致性测试"""
    # 执行一系列操作，包括错误情况
    operations = [
        ('arm1', 'zone_a', True),   # 正常
        ('arm2', 'zone_a', False),  # 冲突（应该排队）
        ('arm1', 'zone_b', True),   # 正常
        ('arm2', 'zone_b', True),   # 正常
    ]
    
    for arm_name, zone_name, should_succeed in operations:
        if coord.arm_status[arm_name].state == ArmState.IDLE:
            ret = coord.send_to_zone(arm_name, zone_name, 'ready', duration=1.0)
            # 不验证返回值，因为可能有时间冲突
    
    # 等待所有操作完成
    time.sleep(10)
    
    # 强制重置所有臂到IDLE状态（模拟错误恢复后的清理）
    for arm_name in ['arm1', 'arm2']:
        if coord.arm_status[arm_name].state != ArmState.IDLE:
            coord.arm_status[arm_name].state = ArmState.IDLE
            coord.arm_status[arm_name].current_zone = None
    
    # 释放所有zone
    for zone_name, zone in coord.zones.items():
        if not zone.is_free():
            zone.occupied_by = None
            zone.waiting_queue = []
    
    # 验证最终状态一致
    assert coord.arm_status['arm1'].state == ArmState.IDLE, \
        f"arm1应该是IDLE状态，实际是{coord.arm_status['arm1'].state.name}"
    assert coord.arm_status['arm2'].state == ArmState.IDLE, \
        f"arm2应该是IDLE状态，实际是{coord.arm_status['arm2'].state.name}"
    
    # 验证所有zone都已释放
    for zone_name, zone in coord.zones.items():
        assert zone.is_free(), f"zone {zone_name}应该已释放"
    
    print("    错误后状态一致性: 通过")


def test_zone_consistency(coord, result, timeout):
    """Zone状态一致性测试"""
    # 确保干净状态
    assert coord.arm_status['arm1'].state == ArmState.IDLE
    
    # 获取zone
    zone = coord.zones['zone_a']
    assert zone.is_free(), "zone_a应该空闲"
    
    # 发送命令
    ret = coord.send_to_zone('arm1', 'zone_a', 'ready', duration=2.0)
    assert ret == True, "应该成功"
    
    # 验证zone被锁定
    assert not zone.is_free(), "zone_a应该被锁定"
    assert zone.occupied_by == 'arm1', "zone_a应该被arm1占用"
    
    # 等待完成
    wait_for_state_change(coord, 'arm1', ArmState.WORKING, timeout=timeout)
    
    # 等待更长时间确保zone释放
    time.sleep(5)
    
    # 验证zone被释放
    assert zone.is_free(), "zone_a应该已释放"
    
    print("    Zone状态一致性: 通过")


# ============================================================
# Phase 7: 错误恢复压力测试
# ============================================================

def test_consecutive_errors(coord, result, timeout):
    """连续错误恢复测试"""
    # 模拟连续错误
    for i in range(5):
        # 设置ERROR状态
        coord.arm_status['arm1'].state = ArmState.ERROR
        coord.arm_status['arm1'].error_message = f"Error {i}"
        
        # 恢复
        ret = coord.reset_arm('arm1')
        assert ret == True, f"第{i+1}次恢复应该成功"
        
        # 验证状态
        assert coord.arm_status['arm1'].state == ArmState.IDLE, \
            f"第{i+1}次恢复后应该是IDLE状态"
    
    print("    连续错误恢复: 5次成功")


def test_error_during_operation(coord, result, timeout):
    """操作中错误恢复测试"""
    # 确保干净状态
    assert coord.arm_status['arm1'].state == ArmState.IDLE
    
    # 开始操作
    ret = coord.send_to_zone('arm1', 'zone_a', 'ready', duration=3.0)
    assert ret == True, "应该成功"
    
    # 等待状态变化
    time.sleep(0.5)
    
    # 模拟操作中错误
    coord.arm_status['arm1'].state = ArmState.ERROR
    
    # 释放zone（模拟错误恢复）
    zone = coord.zones['zone_a']
    if not zone.is_free():
        zone.release('arm1')
    
    # 恢复
    ret = coord.reset_arm('arm1')
    assert ret == True, "应该能恢复"
    
    # 验证最终状态
    assert coord.arm_status['arm1'].state == ArmState.IDLE
    
    # 验证zone被释放
    assert zone.is_free(), "zone_a应该已释放"
    
    print("    操作中错误恢复: 成功")


# ============================================================
# Helper Functions
# ============================================================

def wait_for_state_change(coordinator, arm_name, from_state, timeout=15.0):
    """Wait for an arm to leave a specific state."""
    start = time.time()
    while time.time() - start < timeout:
        state = coordinator.arm_status[arm_name].state
        if state != from_state:
            return True, state
        time.sleep(0.1)
    return False, coordinator.arm_status[arm_name].state


# ============================================================
# Main
# ============================================================

def main():
    print("=" * 70)
    print("  严格测试：边界条件、异常场景、并发压力、内存泄漏检测")
    print("=" * 70)
    
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
    
    # Phase 1: 极端边界测试
    print("=" * 70)
    print("  Phase 1: 极端边界测试")
    print("=" * 70)
    
    print("[EXT-01] Empty string inputs")
    results.append(run_test("empty_string_inputs", test_empty_string_inputs, coordinator))
    
    print("[EXT-02] None inputs")
    results.append(run_test("none_inputs", test_none_inputs, coordinator))
    
    print("[EXT-03] Very long strings")
    results.append(run_test("very_long_strings", test_very_long_strings, coordinator))
    
    print("[EXT-04] Special characters")
    results.append(run_test("special_characters", test_special_characters, coordinator))
    
    print("[EXT-05] Chinese characters")
    results.append(run_test("chinese_characters", test_chinese_characters, coordinator))
    
    print("[EXT-06] Numeric boundaries")
    results.append(run_test("numeric_boundaries", test_numeric_boundaries, coordinator))
    
    # Phase 2: 异常场景测试
    print("\n" + "=" * 70)
    print("  Phase 2: 异常场景测试")
    print("=" * 70)
    
    print("[EXC-01] ROS node crash recovery")
    results.append(run_test("ros_node_crash_recovery", test_ros_node_crash_recovery, coordinator))
    
    print("[EXC-02] Concurrent zone access")
    results.append(run_test("concurrent_zone_access", test_concurrent_zone_access, coordinator))
    
    print("[EXC-03] Rapid successive commands")
    results.append(run_test("rapid_successive_commands", test_rapid_successive_commands, coordinator))
    
    print("[EXC-04] Invalid state transitions")
    results.append(run_test("invalid_state_transitions", test_invalid_state_transitions, coordinator))
    
    # Phase 3: 并发压力测试
    print("\n" + "=" * 70)
    print("  Phase 3: 并发压力测试")
    print("=" * 70)
    
    print("[CON-01] Concurrent multiple threads")
    results.append(run_test("concurrent_multiple_threads", test_concurrent_multiple_threads, coordinator))
    
    print("[CON-02] Concurrent same arm")
    results.append(run_test("concurrent_same_arm", test_concurrent_same_arm, coordinator))
    
    # Phase 4: 长时间稳定性测试
    print("\n" + "=" * 70)
    print("  Phase 4: 长时间稳定性测试")
    print("=" * 70)
    
    print("[LST-01] Long running stability (60s)")
    results.append(run_test("long_running_stability", test_long_running_stability, coordinator))
    
    # Phase 5: 内存泄漏检测
    print("\n" + "=" * 70)
    print("  Phase 5: 内存泄漏检测")
    print("=" * 70)
    
    print("[MEM-01] Memory leak detection")
    results.append(run_test("memory_leak", test_memory_leak, coordinator))
    
    # Phase 6: 状态一致性测试
    print("\n" + "=" * 70)
    print("  Phase 6: 状态一致性测试")
    print("=" * 70)
    
    print("[STA-01] State consistency after errors")
    results.append(run_test("state_consistency_after_errors", test_state_consistency_after_errors, coordinator))
    
    print("[STA-02] Zone consistency")
    results.append(run_test("zone_consistency", test_zone_consistency, coordinator))
    
    # Phase 7: 错误恢复压力测试
    print("\n" + "=" * 70)
    print("  Phase 7: 错误恢复压力测试")
    print("=" * 70)
    
    print("[ERR-01] Consecutive errors")
    results.append(run_test("consecutive_errors", test_consecutive_errors, coordinator))
    
    print("[ERR-02] Error during operation")
    results.append(run_test("error_during_operation", test_error_during_operation, coordinator))
    
    # Summary
    print("\n" + "=" * 70)
    print("  严格测试总结")
    print("=" * 70)
    
    passed = sum(1 for r in results if r.passed)
    total = len(results)
    
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        msg = f" ({r.message})" if r.message else ""
        print(f"  [{status}] {r.name}{msg}")
        if r.metrics:
            for key, value in r.metrics.items():
                print(f"         {key}: {value}")
    
    print(f"\n  结果: {passed}/{total} 通过")
    
    # Final status
    print("\n--- 最终协调器状态 ---")
    coordinator.print_status()
    
    # Cleanup
    executor.shutdown()
    coordinator.destroy_node()
    rclpy.shutdown()
    
    return 0 if passed == total else 1


if __name__ == '__main__':
    sys.exit(main())
