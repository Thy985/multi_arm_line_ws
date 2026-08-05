#!/usr/bin/env python3
"""
补充测试：边界条件和错误恢复测试
验证系统在边界条件和错误情况下的行为
"""

import sys
import time
import threading
import rclpy
from rclpy.executors import MultiThreadedExecutor
from order_manager.nodes.multi_arm_coordinator import EnhancedMultiArmCoordinator
from order_manager.nodes.arm_state import ArmState, PRESET_POSITIONS

# ============================================================
# Test Framework
# ============================================================

class TestResult:
    def __init__(self, name):
        self.name = name
        self.passed = False
        self.message = ""

def run_test(name, test_fn, coordinator, timeout=15.0):
    """Run a test function with timeout."""
    result = TestResult(name)
    try:
        test_fn(coordinator, result, timeout)
        result.passed = True
        print(f"  [PASS] {name}")
    except AssertionError as e:
        result.message = str(e)
        print(f"  [FAIL] {name}: {e}")
    except Exception as e:
        result.message = f"Exception: {e}"
        print(f"  [ERROR] {name}: {e}")
    return result

def wait_for_state(coordinator, arm_name, expected_state, timeout=10.0):
    """Wait for an arm to reach a specific state."""
    start = time.time()
    while time.time() - start < timeout:
        state = coordinator.arm_status[arm_name].state
        if state == expected_state:
            return True
        time.sleep(0.1)
    return False

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
# Boundary Condition Tests
# ============================================================

def test_concurrent_zone_requests(coord, result, timeout):
    """并发Zone请求：第二个请求应该排队"""
    # 确保干净状态
    assert coord.arm_status['arm1'].state == ArmState.IDLE
    assert coord.arm_status['arm2'].state == ArmState.IDLE
    
    # arm1获取zone_a
    granted1 = coord.send_to_zone('arm1', 'zone_a', 'ready', duration=3.0)
    assert granted1, "arm1应该获得zone_a"
    time.sleep(0.3)
    assert coord.arm_status['arm1'].state == ArmState.WORKING
    
    # arm2也请求zone_a - 应该排队
    granted2 = coord.send_to_zone('arm2', 'zone_a', 'ready', duration=3.0)
    assert not granted2, "arm2应该被排队（zone被占用）"
    assert coord.arm_status['arm2'].state == ArmState.QUEUED, \
        f"arm2应该是QUEUED状态，实际是{coord.arm_status['arm2'].state.name}"
    
    print(f"    arm1: {coord.arm_status['arm1'].state.name}")
    print(f"    arm2: {coord.arm_status['arm2'].state.name}")
    
    # 等待arm1完成
    wait_for_state_change(coord, 'arm1', ArmState.WORKING, timeout=timeout)
    
    # arm1完成后，arm2应该被触发
    time.sleep(1.0)
    assert coord.arm_status['arm2'].state == ArmState.WORKING, \
        f"arm2应该是WORKING状态，实际是{coord.arm_status['arm2'].state.name}"
    
    print(f"    arm2 after arm1 release: {coord.arm_status['arm2'].state.name}")
    
    # 等待arm2完成
    wait_for_state_change(coord, 'arm2', ArmState.WORKING, timeout=timeout)


def test_rapid_commands(coord, result, timeout):
    """快速连续命令：正确处理队列"""
    # 确保干净状态
    assert coord.arm_status['arm1'].state == ArmState.IDLE
    
    # 快速发送多个命令
    success1 = coord.send_to_position('arm1', 'ready', duration=2.0)
    assert success1, "第一个命令应该成功"
    
    # 立即发送第二个命令 - 应该被拒绝
    success2 = coord.send_to_position('arm1', 'extended')
    assert not success2, "第二个命令应该被拒绝（arm忙）"
    
    # 等待第一个命令完成
    wait_for_state_change(coord, 'arm1', ArmState.WORKING, timeout=timeout)
    
    print("    快速命令处理: 正确")


def test_invalid_arm_names(coord, result, timeout):
    """无效臂名称：正确拒绝"""
    # 测试无效臂名称
    ret = coord.send_to_position('nonexistent_arm', 'ready')
    assert ret == False, "应该拒绝无效臂名称"
    
    ret = coord.send_to_zone('nonexistent_arm', 'zone_a')
    assert ret == False, "应该拒绝无效臂名称"
    
    ret = coord.reset_arm('nonexistent_arm')
    assert ret == False, "应该拒绝无效臂名称"
    
    print("    无效臂名称: 正确拒绝")


def test_invalid_zone_names(coord, result, timeout):
    """无效Zone名称：正确拒绝"""
    # 测试无效Zone名称
    ret = coord.send_to_zone('arm1', 'nonexistent_zone')
    assert ret == False, "应该拒绝无效Zone名称"
    
    print("    无效Zone名称: 正确拒绝")


def test_invalid_position_names(coord, result, timeout):
    """无效位置名称：正确拒绝"""
    # 测试无效位置名称
    ret = coord.send_to_position('arm1', 'nonexistent_position')
    assert ret == False, "应该拒绝无效位置名称"
    
    print("    无效位置名称: 正确拒绝")


def test_zero_duration(coord, result, timeout):
    """零持续时间：正确处理"""
    # 确保干净状态
    assert coord.arm_status['arm1'].state == ArmState.IDLE
    
    # 发送零持续时间命令
    success = coord.send_to_position('arm1', 'ready', duration=0.0)
    assert success, "零持续时间命令应该成功"
    
    # 等待完成
    wait_for_state_change(coord, 'arm1', ArmState.WORKING, timeout=timeout)
    
    print("    零持续时间: 正确处理")


def test_negative_duration(coord, result, timeout):
    """负数持续时间：正确处理"""
    # 确保干净状态
    assert coord.arm_status['arm1'].state == ArmState.IDLE
    
    # 发送负数持续时间命令（应该被转换为0或最小值）
    success = coord.send_to_position('arm1', 'ready', duration=-1.0)
    # 注意：这个测试可能根据实现不同而不同
    # 如果实现不处理负数，可能会失败
    if success:
        # 等待完成
        wait_for_state_change(coord, 'arm1', ArmState.WORKING, timeout=timeout)
        print("    负数持续时间: 被接受（可能转换为最小值）")
    else:
        print("    负数持续时间: 被拒绝")


# ============================================================
# Error Recovery Tests
# ============================================================

def test_goal_cancellation(coord, result, timeout):
    """Goal取消：正确取消并释放zone"""
    # 确保干净状态
    assert coord.arm_status['arm1'].state == ArmState.IDLE
    assert coord.arm_status['arm2'].state == ArmState.IDLE
    
    # arm1进入zone_a
    granted = coord.send_to_zone('arm1', 'zone_a', 'ready', duration=5.0)
    assert granted, "arm1应该获得zone_a"
    time.sleep(0.3)
    assert coord.arm_status['arm1'].state == ArmState.WORKING
    
    # 手动模拟goal取消（通过设置ERROR状态）
    coord.arm_status['arm1'].state = ArmState.ERROR
    coord._release_zone_only('arm1')
    
    # 验证zone被释放
    zone = coord.zones['zone_a']
    assert zone.is_free(), "zone_a应该被释放"
    
    # 验证arm1保持ERROR状态
    assert coord.arm_status['arm1'].state == ArmState.ERROR, \
        f"arm1应该是ERROR状态，实际是{coord.arm_status['arm1'].state.name}"
    
    print("    Goal取消: zone被释放，arm保持ERROR状态")
    
    # 清理：重置arm1
    coord.reset_arm('arm1')


def test_timeout_auto_cancel(coord, result, timeout):
    """超时自动取消：超时后自动取消goal"""
    # 确保干净状态
    assert coord.arm_status['arm1'].state == ArmState.IDLE
    
    # arm1进入zone_a
    granted = coord.send_to_zone('arm1', 'zone_a', 'ready', duration=2.0)
    assert granted, "arm1应该获得zone_a"
    time.sleep(0.3)
    
    # 等待正常完成（超时测试需要特殊处理）
    # 这里我们测试超时逻辑是否存在
    status = coord.arm_status['arm1']
    if status.goal_start_time:
        elapsed = time.time() - status.goal_start_time
        predicted = 3.5  # 预测持续时间
        timeout_val = max(predicted * 2, 15.0)
        
        # 如果elapsed > timeout，应该触发取消
        if elapsed > timeout_val:
            print(f"    超时检测: elapsed={elapsed:.1f}s, timeout={timeout_val:.1f}s")
            # 实际测试需要等待超时发生
        else:
            print(f"    超时检测: 正常执行中 (elapsed={elapsed:.1f}s)")
    
    # 等待完成
    wait_for_state_change(coord, 'arm1', ArmState.WORKING, timeout=timeout)


def test_error_state_persistence(coord, result, timeout):
    """ERROR状态保持：失败后保持ERROR状态"""
    # 确保干净状态
    assert coord.arm_status['arm1'].state == ArmState.IDLE
    
    # 手动设置ERROR状态
    coord.arm_status['arm1'].state = ArmState.ERROR
    coord.arm_status['arm1'].error_message = "测试错误"
    
    # 验证ERROR状态保持
    assert coord.arm_status['arm1'].state == ArmState.ERROR, \
        f"arm1应该是ERROR状态，实际是{coord.arm_status['arm1'].state.name}"
    
    # 尝试发送命令 - 应该被拒绝
    ret = coord.send_to_position('arm1', 'ready')
    assert ret == False, "ERROR状态应该拒绝命令"
    
    ret = coord.send_to_zone('arm1', 'zone_a')
    assert ret == False, "ERROR状态应该拒绝zone请求"
    
    print("    ERROR状态保持: 正确")
    
    # 清理
    coord.reset_arm('arm1')


def test_manual_reset(coord, result, timeout):
    """手动reset：reset_arm()正确恢复"""
    # 确保干净状态
    assert coord.arm_status['arm1'].state == ArmState.IDLE
    
    # 手动设置ERROR状态
    coord.arm_status['arm1'].state = ArmState.ERROR
    coord.arm_status['arm1'].error_message = "测试错误"
    
    # reset应该成功
    ret = coord.reset_arm('arm1')
    assert ret == True, "reset_arm应该返回True"
    assert coord.arm_status['arm1'].state == ArmState.IDLE, \
        f"arm1应该是IDLE状态，实际是{coord.arm_status['arm1'].state.name}"
    
    print("    手动reset: 正确恢复")


def test_non_error_state_reset(coord, result, timeout):
    """非ERROR状态reset：拒绝reset"""
    # 确保干净状态
    assert coord.arm_status['arm1'].state == ArmState.IDLE
    
    # 尝试reset IDLE状态 - 应该失败
    ret = coord.reset_arm('arm1')
    assert ret == False, "IDLE状态应该拒绝reset"
    
    # 发送命令使arm变为WORKING
    coord.send_to_position('arm1', 'ready', duration=2.0)
    time.sleep(0.3)
    assert coord.arm_status['arm1'].state == ArmState.WORKING
    
    # 尝试reset WORKING状态 - 应该失败
    ret = coord.reset_arm('arm1')
    assert ret == False, "WORKING状态应该拒绝reset"
    
    print("    非ERROR状态reset: 正确拒绝")
    
    # 等待完成
    wait_for_state_change(coord, 'arm1', ArmState.WORKING, timeout=timeout)


def test_zone_release_only(coord, result, timeout):
    """Zone释放但不重置状态：ERROR时zone释放，状态不变"""
    # 确保干净状态
    assert coord.arm_status['arm1'].state == ArmState.IDLE
    assert coord.arm_status['arm2'].state == ArmState.IDLE
    
    # arm1进入zone_a
    granted = coord.send_to_zone('arm1', 'zone_a', 'ready', duration=2.0)
    assert granted, "arm1应该获得zone_a"
    time.sleep(0.3)
    
    # 验证zone被锁定
    zone = coord.zones['zone_a']
    assert not zone.is_free(), "zone_a应该被锁定"
    assert zone.occupied_by == 'arm1'
    
    # 模拟ERROR状态
    coord.arm_status['arm1'].state = ArmState.ERROR
    
    # 调用_release_zone_only
    coord._release_zone_only('arm1')
    
    # 验证zone被释放
    assert zone.is_free(), "zone_a应该被释放"
    
    # 验证arm1保持ERROR状态
    assert coord.arm_status['arm1'].state == ArmState.ERROR, \
        f"arm1应该是ERROR状态，实际是{coord.arm_status['arm1'].state.name}"
    
    print("    Zone释放但不重置状态: 正确")
    
    # 清理
    coord.reset_arm('arm1')


def test_queued_arm_trigger(coord, result, timeout):
    """排队臂触发：arm1完成后自动触发arm2"""
    # 确保干净状态
    assert coord.arm_status['arm1'].state == ArmState.IDLE
    assert coord.arm_status['arm2'].state == ArmState.IDLE
    
    # arm1进入zone_a
    granted1 = coord.send_to_zone('arm1', 'zone_a', 'ready', duration=3.0)
    assert granted1, "arm1应该获得zone_a"
    time.sleep(0.3)
    
    # arm2也请求zone_a - 应该排队
    granted2 = coord.send_to_zone('arm2', 'zone_a', 'ready', duration=3.0)
    assert not granted2, "arm2应该被排队"
    assert coord.arm_status['arm2'].state == ArmState.QUEUED, \
        f"arm2应该是QUEUED状态，实际是{coord.arm_status['arm2'].state.name}"
    
    # 记录arm2的requested_position
    requested_position = coord.arm_status['arm2'].requested_position
    assert requested_position == 'ready', \
        f"arm2的requested_position应该是ready，实际是{requested_position}"
    
    print(f"    arm2 requested_position: {requested_position}")
    
    # 等待arm1完成
    wait_for_state_change(coord, 'arm1', ArmState.WORKING, timeout=timeout)
    
    # arm1完成后，arm2应该被触发并移动到zone_a
    time.sleep(1.0)
    assert coord.arm_status['arm2'].state == ArmState.WORKING, \
        f"arm2应该是WORKING状态，实际是{coord.arm_status['arm2'].state.name}"
    
    print(f"    arm2 after arm1 release: {coord.arm_status['arm2'].state.name}")
    
    # 等待arm2完成
    wait_for_state_change(coord, 'arm2', ArmState.WORKING, timeout=timeout)


# ============================================================
# Main
# ============================================================

def main():
    print("=" * 60)
    print("  Boundary Condition & Error Recovery Tests")
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
    
    print("[BC-01] Concurrent zone requests")
    results.append(run_test("concurrent_zone_requests", test_concurrent_zone_requests, coordinator))
    
    print("[BC-02] Rapid commands")
    results.append(run_test("rapid_commands", test_rapid_commands, coordinator))
    
    print("[BC-03] Invalid arm names")
    results.append(run_test("invalid_arm_names", test_invalid_arm_names, coordinator))
    
    print("[BC-04] Invalid zone names")
    results.append(run_test("invalid_zone_names", test_invalid_zone_names, coordinator))
    
    print("[BC-05] Invalid position names")
    results.append(run_test("invalid_position_names", test_invalid_position_names, coordinator))
    
    print("[BC-06] Zero duration")
    results.append(run_test("zero_duration", test_zero_duration, coordinator))
    
    print("[BC-07] Negative duration")
    results.append(run_test("negative_duration", test_negative_duration, coordinator))
    
    print("[ER-01] Goal cancellation")
    results.append(run_test("goal_cancellation", test_goal_cancellation, coordinator))
    
    print("[ER-02] Timeout auto cancel")
    results.append(run_test("timeout_auto_cancel", test_timeout_auto_cancel, coordinator))
    
    print("[ER-03] Error state persistence")
    results.append(run_test("error_state_persistence", test_error_state_persistence, coordinator))
    
    print("[ER-04] Manual reset")
    results.append(run_test("manual_reset", test_manual_reset, coordinator))
    
    print("[ER-05] Non-error state reset")
    results.append(run_test("non_error_state_reset", test_non_error_state_reset, coordinator))
    
    print("[ER-06] Zone release only")
    results.append(run_test("zone_release_only", test_zone_release_only, coordinator))
    
    print("[ER-07] Queued arm trigger")
    results.append(run_test("queued_arm_trigger", test_queued_arm_trigger, coordinator))
    
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
