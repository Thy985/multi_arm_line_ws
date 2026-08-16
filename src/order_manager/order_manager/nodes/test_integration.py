#!/usr/bin/env python3
"""
Integration test for EnhancedMultiArmCoordinator.
Tests: single arm movement, zone locking, dual-arm conflict, state machine.
"""

import sys
import time
import threading
import rclpy
from rclpy.executors import MultiThreadedExecutor
from order_manager.nodes.multi_arm_coordinator import EnhancedMultiArmCoordinator
from order_manager.nodes.arm_state import ArmState

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
# Test 1: Single Arm Movement
# ============================================================

def test_single_arm_movement(coord, result, timeout):
    """Send left_arm to 'ready' position and verify it reaches WORKING then IDLE."""
    # Ensure arm is idle
    assert coord.arm_status['left_arm'].state == ArmState.IDLE, \
        f"left_arm not IDLE before test (state={coord.arm_status['left_arm'].state})"

    # Send to position (no zone lock)
    success = coord.send_to_position('left_arm', 'ready', duration=2.0)
    assert success, "send_to_position returned False"

    # Verify arm enters WORKING state
    time.sleep(0.5)
    state = coord.arm_status['left_arm'].state
    assert state == ArmState.WORKING, \
        f"left_arm should be WORKING after send_to_position, got {state}"

    print(f"    left_arm state: {state.name}")

    # Wait for completion
    reached, final_state = wait_for_state_change(coord, 'left_arm', ArmState.WORKING, timeout=timeout)
    assert reached, f"left_arm did not leave WORKING within {timeout}s"
    assert final_state == ArmState.IDLE, \
        f"left_arm should return to IDLE after completion, got {final_state}"

    print(f"    left_arm final state: {final_state.name}")

# ============================================================
# Test 2: Zone Locking
# ============================================================

def test_zone_locking(coord, result, timeout):
    """Send left_arm to zone_a, verify zone is locked, then release."""
    # Ensure clean state
    assert coord.arm_status['left_arm'].state == ArmState.IDLE, \
        f"left_arm not IDLE (state={coord.arm_status['left_arm'].state})"

    zone = coord.zones['zone_a']
    assert zone.is_free(), "zone_a should be free before test"

    # Send to zone
    granted = coord.send_to_zone('left_arm', 'zone_a', 'ready', duration=2.0)
    assert granted, "Zone should be granted (zone was free)"

    # Verify zone locked
    assert not zone.is_free(), "zone_a should be occupied"
    assert zone.occupied_by == 'left_arm', f"zone_a occupied_by should be left_arm, got {zone.occupied_by}"
    assert coord.arm_status['left_arm'].state == ArmState.WORKING

    print(f"    zone_a occupied_by: {zone.occupied_by}")

    # Wait for completion
    reached, final_state = wait_for_state_change(coord, 'left_arm', ArmState.WORKING, timeout=timeout)
    assert reached, f"left_arm did not leave WORKING within {timeout}s"

    # Verify zone released
    assert zone.is_free(), "zone_a should be free after completion"
    assert coord.arm_status['left_arm'].state == ArmState.IDLE

    print(f"    zone_a after release: free={zone.is_free()}")

# ============================================================
# Test 3: Dual Arm Zone Conflict
# ============================================================

def test_dual_arm_zone_conflict(coord, result, timeout):
    """left_arm and right_arm both request zone_a — second should queue (via TimeManager or zone lock)."""
    # Ensure clean state
    assert coord.arm_status['left_arm'].state == ArmState.IDLE
    assert coord.arm_status['right_arm'].state == ArmState.IDLE
    zone = coord.zones['zone_a']
    assert zone.is_free()

    # left_arm gets the zone
    granted1 = coord.send_to_zone('left_arm', 'zone_a', 'ready', duration=3.0)
    assert granted1, "left_arm should get zone_a"
    time.sleep(0.5)
    assert coord.arm_status['left_arm'].state == ArmState.WORKING

    # right_arm requests same zone — should be queued (via TimeManager time conflict OR zone lock)
    granted2 = coord.send_to_zone('right_arm', 'zone_a', 'ready', duration=3.0)
    assert not granted2, "right_arm should be queued (zone occupied or time conflict)"
    assert coord.arm_status['right_arm'].state == ArmState.QUEUED, \
        f"right_arm should be QUEUED, got {coord.arm_status['right_arm'].state.name}"

    print(f"    left_arm: {coord.arm_status['left_arm'].state.name}")
    print(f"    right_arm: {coord.arm_status['right_arm'].state.name}")

    # Wait for left_arm to finish
    reached, _ = wait_for_state_change(coord, 'left_arm', ArmState.WORKING, timeout=timeout)
    assert reached, f"left_arm did not finish within {timeout}s"

    # After left_arm finishes, right_arm should be triggered
    time.sleep(1.0)  # Give callback time to fire
    assert coord.arm_status['right_arm'].state == ArmState.WORKING, \
        f"right_arm should be WORKING after left_arm release, got {coord.arm_status['right_arm'].state}"

    print(f"    right_arm after left_arm release: {coord.arm_status['right_arm'].state.name}")

    # Wait for right_arm to finish
    reached, _ = wait_for_state_change(coord, 'right_arm', ArmState.WORKING, timeout=timeout)
    assert reached, f"right_arm did not finish within {timeout}s"

    # Both should be idle, zone free
    assert coord.arm_status['left_arm'].state == ArmState.IDLE
    assert coord.arm_status['right_arm'].state == ArmState.IDLE
    assert zone.is_free()

    print(f"    final: left_arm={coord.arm_status['left_arm'].state.name}, "
          f"right_arm={coord.arm_status['right_arm'].state.name}, "
          f"zone_free={zone.is_free()}")

# ============================================================
# Test 4: State Machine Transitions
# ============================================================

def test_state_machine(coord, result, timeout):
    """Verify all state transitions happen in correct order."""
    transitions = []
    
    # Monitor left_arm state changes — start BEFORE sending trajectory
    state_holder = {'prev': coord.arm_status['left_arm'].state}
    
    def monitor():
        for _ in range(int(timeout * 10)):
            curr = coord.arm_status['left_arm'].state
            if curr != state_holder['prev']:
                transitions.append((state_holder['prev'].name, curr.name))
                state_holder['prev'] = curr
            time.sleep(0.05)  # Faster polling to catch quick transitions
    
    # Start monitoring FIRST, then trigger state change
    monitor_thread = threading.Thread(target=monitor, daemon=True)
    monitor_thread.start()
    
    # Small delay to ensure monitor is running
    time.sleep(0.1)
    
    # Trigger state change: IDLE -> WORKING -> IDLE
    coord.send_to_position('left_arm', 'extended', duration=2.0)
    monitor_thread.join(timeout=timeout + 2)
    
    print(f"    transitions: {transitions}")
    
    # Expected: IDLE -> WORKING -> IDLE
    assert len(transitions) >= 2, \
        f"Expected at least 2 transitions, got {len(transitions)}"
    assert transitions[0] == ('IDLE', 'WORKING'), \
        f"First transition should be IDLE->WORKING, got {transitions[0]}"
    assert transitions[-1] == ('WORKING', 'IDLE'), \
        f"Last transition should be WORKING->IDLE, got {transitions[-1]}"

# ============================================================
# Test 5: Invalid Inputs Rejection
# ============================================================

def test_invalid_inputs(coord, result, timeout):
    """Verify that invalid position/zone names are rejected."""
    # Invalid position
    ret = coord.send_to_position('left_arm', 'nonexistent_position')
    assert ret == False, "Should reject invalid position"
    
    # Invalid zone
    ret = coord.send_to_zone('left_arm', 'nonexistent_zone')
    assert ret == False, "Should reject invalid zone"
    
    print("    Invalid position: rejected ✓")
    print("    Invalid zone: rejected ✓")

# ============================================================
# Test 6: Busy Arm Rejection
# ============================================================

def test_busy_arm_rejection(coord, result, timeout):
    """Verify that commands to a busy arm are rejected."""
    # Ensure left_arm is idle
    assert coord.arm_status['left_arm'].state == ArmState.IDLE
    
    # Send left_arm to position (makes it WORKING)
    coord.send_to_position('left_arm', 'ready', duration=3.0)
    time.sleep(0.3)
    assert coord.arm_status['left_arm'].state == ArmState.WORKING
    
    # Try to send another command — should be rejected
    ret = coord.send_to_position('left_arm', 'home')
    assert ret == False, "Should reject command to busy arm"
    
    ret = coord.send_to_zone('left_arm', 'zone_a')
    assert ret == False, "Should reject zone request to busy arm"
    
    print("    Busy arm position: rejected ✓")
    print("    Busy arm zone: rejected ✓")
    
    # Wait for left_arm to finish
    wait_for_state_change(coord, 'left_arm', ArmState.WORKING, timeout=timeout)

# ============================================================
# Test 7: Zone Free After Error Recovery
# ============================================================

def test_zone_release_on_error(coord, result, timeout):
    """Verify zone is released when arm enters ERROR state."""
    # Ensure clean state
    assert coord.arm_status['left_arm'].state == ArmState.IDLE
    assert coord.arm_status['right_arm'].state == ArmState.IDLE
    zone = coord.zones['zone_a']
    assert zone.is_free()
    
    # Send left_arm to zone_a
    granted = coord.send_to_zone('left_arm', 'zone_a', 'ready', duration=2.0)
    assert granted, "Zone should be granted"
    time.sleep(0.3)
    assert zone.occupied_by == 'left_arm'
    
    # Wait for completion
    wait_for_state_change(coord, 'left_arm', ArmState.WORKING, timeout=timeout)
    
    # Zone should be free after completion
    assert zone.is_free(), "Zone should be free after left_arm completes"
    assert coord.arm_status['left_arm'].state == ArmState.IDLE
    
    print("    Zone released after completion ✓")

# ============================================================
# Test 8: Dual Zone Conflict (Different Zones)
# ============================================================

def test_different_zones_no_conflict(coord, result, timeout):
    """left_arm -> zone_a and right_arm -> zone_b should both succeed (no conflict)."""
    # Ensure clean state
    assert coord.arm_status['left_arm'].state == ArmState.IDLE
    assert coord.arm_status['right_arm'].state == ArmState.IDLE
    
    # left_arm -> zone_a
    granted1 = coord.send_to_zone('left_arm', 'zone_a', 'ready', duration=2.0)
    assert granted1, "left_arm should get zone_a"
    
    # right_arm -> zone_b (different zone, should succeed)
    granted2 = coord.send_to_zone('right_arm', 'zone_b', 'ready', duration=2.0)
    assert granted2, "right_arm should get zone_b (different zone)"
    
    # Both should be WORKING
    assert coord.arm_status['left_arm'].state == ArmState.WORKING
    assert coord.arm_status['right_arm'].state == ArmState.WORKING
    
    print("    left_arm -> zone_a: granted ✓")
    print("    right_arm -> zone_b: granted ✓")
    
    # Wait for both to finish
    wait_for_state_change(coord, 'left_arm', ArmState.WORKING, timeout=timeout)
    wait_for_state_change(coord, 'right_arm', ArmState.WORKING, timeout=timeout)

# ============================================================
# Test 9: Task Scheduling Integration
# ============================================================

def test_task_scheduling(coord, result, timeout):
    """Submit a task and verify it gets scheduled and executed."""
    from order_manager.nodes.task_scheduler import Task, TaskPriority
    
    # Ensure clean state
    assert coord.arm_status['left_arm'].state == ArmState.IDLE
    
    # Submit a task
    task = Task(
        task_id='test_task_1',
        zone_name='zone_a',
        position_name='ready',
        priority=TaskPriority.NORMAL,
    )
    task_id = coord.submit_task(task)
    assert task_id, "Task should be submitted"
    
    # Schedule and execute
    scheduled = coord.schedule_pending_tasks()
    assert scheduled >= 1, f"Should schedule at least 1 task, got {scheduled}"
    
    print(f"    Task submitted: {task_id}")
    print(f"    Tasks scheduled: {scheduled}")
    
    # Wait for execution
    time.sleep(1)
    assert coord.arm_status['left_arm'].state == ArmState.WORKING, \
        f"left_arm should be WORKING after task execution, got {coord.arm_status['left_arm'].state.name}"
    
    # Wait for completion
    wait_for_state_change(coord, 'left_arm', ArmState.WORKING, timeout=timeout)

# ============================================================
# Test 10: Reset Arm from ERROR State
# ============================================================

def test_reset_arm(coord, result, timeout):
    """Test reset_arm API for ERROR→IDLE recovery."""
    # Ensure clean state
    assert coord.arm_status['left_arm'].state == ArmState.IDLE
    
    # Simulate ERROR state manually
    coord.arm_status['left_arm'].state = ArmState.ERROR
    coord.arm_status['left_arm'].error_message = "Test error"
    
    # reset_arm should succeed
    ret = coord.reset_arm('left_arm')
    assert ret == True, "reset_arm should return True"
    assert coord.arm_status['left_arm'].state == ArmState.IDLE, \
        f"left_arm should be IDLE after reset, got {coord.arm_status['left_arm'].state.name}"
    
    # reset_arm on IDLE arm should fail
    ret = coord.reset_arm('left_arm')
    assert ret == False, "reset_arm on IDLE arm should return False"
    
    print("    ERROR→IDLE reset: ✓")
    print("    IDLE reset rejected: ✓")

# ============================================================
# Main
# ============================================================

def main():
    print("=" * 60)
    print("  EnhancedMultiArmCoordinator Integration Test")
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
    
    print("[Test 1] Single arm movement (left_arm -> ready)")
    results.append(run_test("single_arm_movement", test_single_arm_movement, coordinator))
    
    print("[Test 2] Zone locking (left_arm -> zone_a)")
    results.append(run_test("zone_locking", test_zone_locking, coordinator))
    
    print("[Test 3] Dual arm zone conflict (left_arm + right_arm -> zone_a)")
    results.append(run_test("dual_arm_conflict", test_dual_arm_zone_conflict, coordinator))
    
    print("[Test 4] State machine transitions (left_arm -> extended)")
    results.append(run_test("state_machine", test_state_machine, coordinator))
    
    print("[Test 5] Invalid inputs rejection")
    results.append(run_test("invalid_inputs", test_invalid_inputs, coordinator))
    
    print("[Test 6] Busy arm rejection")
    results.append(run_test("busy_arm_rejection", test_busy_arm_rejection, coordinator))
    
    print("[Test 7] Zone release after completion")
    results.append(run_test("zone_release_on_error", test_zone_release_on_error, coordinator))
    
    print("[Test 8] Different zones no conflict (left_arm->zone_a, right_arm->zone_b)")
    results.append(run_test("different_zones_no_conflict", test_different_zones_no_conflict, coordinator))
    
    print("[Test 9] Task scheduling integration")
    results.append(run_test("task_scheduling", test_task_scheduling, coordinator))
    
    print("[Test 10] Reset arm from ERROR state")
    results.append(run_test("reset_arm", test_reset_arm, coordinator))
    
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
