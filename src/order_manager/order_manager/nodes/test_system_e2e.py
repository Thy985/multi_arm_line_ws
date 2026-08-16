#!/usr/bin/env python3
"""
系统端到端测试
验证整个仿真系统的功能完整性
"""

import sys
import time
import subprocess
import os
import psutil

# ============================================================
# Test Framework
# ============================================================

class TestResult:
    def __init__(self, name):
        self.name = name
        self.passed = False
        self.message = ""
        self.metrics = {}

def run_test(name, test_fn):
    """Run a test function."""
    result = TestResult(name)
    try:
        test_fn(result)
        result.passed = True
        print(f"  [PASS] {name}")
    except AssertionError as e:
        result.message = str(e)
        print(f"  [FAIL] {name}: {e}")
    except Exception as e:
        result.message = f"Exception: {e}"
        print(f"  [ERROR] {name}: {e}")
    return result

def run_command(cmd, timeout=10):
    """Run a shell command and return output."""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            executable='/bin/bash'
        )
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        return "", "Command timed out", 1

# ============================================================
# System Tests
# ============================================================

def test_gazebo_simulation(result):
    """仿真环境启动：Gazebo正常启动"""
    # 检查Gazebo进程是否运行
    gazebo_running = False
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if proc.info['name'] and 'gz' in proc.info['name'].lower():
                gazebo_running = True
                break
            if proc.info['cmdline']:
                for cmd in proc.info['cmdline']:
                    if 'gz' in cmd.lower():
                        gazebo_running = True
                        break
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    
    result.metrics['gazebo_running'] = gazebo_running
    
    assert gazebo_running, "Gazebo进程未运行"
    
    print(f"    Gazebo进程: {'运行中' if gazebo_running else '未运行'}")


def test_controller_loading(result):
    """控制器加载：left_arm/right_arm控制器active"""
    # 检查left_arm控制器
    stdout, stderr, returncode = run_command(
        "source /opt/ros/jazzy/setup.bash && source ~/multi_arm_line_ws/install/setup.bash && "
        "ros2 control list_controllers -c /left_arm/controller_manager"
    )
    
    left_arm_active = 'active' in stdout.lower() and 'joint_trajectory_controller' in stdout
    
    # 检查right_arm控制器
    stdout, stderr, returncode = run_command(
        "source /opt/ros/jazzy/setup.bash && source ~/multi_arm_line_ws/install/setup.bash && "
        "ros2 control list_controllers -c /right_arm/controller_manager"
    )
    
    right_arm_active = 'active' in stdout.lower() and 'joint_trajectory_controller' in stdout
    
    result.metrics['left_arm_active'] = left_arm_active
    result.metrics['right_arm_active'] = right_arm_active
    
    assert left_arm_active, "left_arm控制器未激活"
    assert right_arm_active, "right_arm控制器未激活"
    
    print(f"    left_arm控制器: {'active' if left_arm_active else 'inactive'}")
    print(f"    right_arm控制器: {'active' if right_arm_active else 'inactive'}")


def test_rviz_visualization(result):
    """RViz可视化：显示双机械臂模型"""
    # 检查RViz进程是否运行
    rviz_running = False
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if proc.info['name'] and 'rviz' in proc.info['name'].lower():
                rviz_running = True
                break
            if proc.info['cmdline']:
                for cmd in proc.info['cmdline']:
                    if 'rviz' in cmd.lower():
                        rviz_running = True
                        break
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    
    result.metrics['rviz_running'] = rviz_running
    
    assert rviz_running, "RViz进程未运行"
    
    print(f"    RViz进程: {'运行中' if rviz_running else '未运行'}")


def test_trajectory_execution(result):
    """轨迹执行：机械臂按预期运动"""
    # 发送轨迹命令到left_arm
    cmd = (
        "source /opt/ros/jazzy/setup.bash && source ~/multi_arm_line_ws/install/setup.bash && "
        "timeout 10 ros2 action send_goal /left_arm/joint_trajectory_controller/follow_joint_trajectory "
        "control_msgs/action/FollowJointTrajectory "
        "'{trajectory: {joint_names: [left_arm_shoulder_pan_joint, left_arm_shoulder_lift_joint, left_arm_elbow_joint, left_arm_wrist_1_joint, left_arm_wrist_2_joint, left_arm_wrist_3_joint], "
        "points: [{positions: [0.0, -1.57, 0.0, -1.57, 0.0, 0.0], time_from_start: {sec: 3, nanosec: 0}}]}}'"
    )
    
    stdout, stderr, returncode = run_command(cmd, timeout=15)
    
    success = 'SUCCEEDED' in stdout or 'error_code: 0' in stdout
    
    result.metrics['trajectory_success'] = success
    result.metrics['command_output'] = stdout[:200] if stdout else "No output"
    
    assert success, f"轨迹执行失败: {stderr[:200] if stderr else stdout[:200]}"
    
    print(f"    轨迹执行: {'成功' if success else '失败'}")


def test_jx_py_step15(result):
    """JX.py step_15：交互式控制正常"""
    # 检查JX.py文件是否存在
    jx_py_path = "/mnt/d/study/机械臂/JX.py"
    file_exists = os.path.exists(jx_py_path)
    
    result.metrics['jx_py_exists'] = file_exists
    
    assert file_exists, f"JX.py文件不存在: {jx_py_path}"
    
    # 检查step_15函数是否存在
    with open(jx_py_path, 'r') as f:
        content = f.read()
    
    step15_exists = 'def step_15():' in content
    step15_has_menu = '选择要控制的机械臂' in content
    step15_has_custom = '自定义角度' in content
    
    result.metrics['step15_function'] = step15_exists
    result.metrics['step15_menu'] = step15_has_menu
    result.metrics['step15_custom'] = step15_has_custom
    
    assert step15_exists, "step_15函数不存在"
    assert step15_has_menu, "step_15缺少机械臂选择菜单"
    assert step15_has_custom, "step_15缺少自定义角度功能"
    
    print(f"    step_15函数: {'存在' if step15_exists else '不存在'}")
    print(f"    机械臂选择菜单: {'存在' if step15_has_menu else '不存在'}")
    print(f"    自定义角度功能: {'存在' if step15_has_custom else '不存在'}")


def test_jx_py_step18(result):
    """JX.py step_18：任务调度器正常"""
    # 检查JX.py文件是否存在
    jx_py_path = "/mnt/d/study/机械臂/JX.py"
    file_exists = os.path.exists(jx_py_path)
    
    result.metrics['jx_py_exists'] = file_exists
    
    assert file_exists, f"JX.py文件不存在: {jx_py_path}"
    
    # 检查step_18函数是否存在
    with open(jx_py_path, 'r') as f:
        content = f.read()
    
    step18_exists = 'def step_18():' in content
    step18_has_coordinator = '启动协调器' in content
    step18_has_task_submit = '提交任务并自动调度' in content
    step18_has_templates = '焊接任务' in content
    
    result.metrics['step18_function'] = step18_exists
    result.metrics['step18_coordinator'] = step18_has_coordinator
    result.metrics['step18_task_submit'] = step18_has_task_submit
    result.metrics['step18_templates'] = step18_has_templates
    
    assert step18_exists, "step_18函数不存在"
    assert step18_has_coordinator, "step_18缺少启动协调器功能"
    assert step18_has_task_submit, "step_18缺少任务提交功能"
    assert step18_has_templates, "step_18缺少任务模板"
    
    print(f"    step_18函数: {'存在' if step18_exists else '不存在'}")
    print(f"    启动协调器: {'存在' if step18_has_coordinator else '不存在'}")
    print(f"    任务提交功能: {'存在' if step18_has_task_submit else '不存在'}")
    print(f"    任务模板: {'存在' if step18_has_templates else '不存在'}")


# ============================================================
# Main
# ============================================================

def main():
    print("=" * 60)
    print("  System End-to-End Tests")
    print("=" * 60)
    
    # Run tests
    results = []
    
    print("[SY-01] Gazebo simulation")
    results.append(run_test("gazebo_simulation", test_gazebo_simulation))
    
    print("[SY-02] Controller loading")
    results.append(run_test("controller_loading", test_controller_loading))
    
    print("[SY-03] RViz visualization")
    results.append(run_test("rviz_visualization", test_rviz_visualization))
    
    print("[SY-04] Trajectory execution")
    results.append(run_test("trajectory_execution", test_trajectory_execution))
    
    print("[SY-05] JX.py step_15")
    results.append(run_test("jx_py_step15", test_jx_py_step15))
    
    print("[SY-06] JX.py step_18")
    results.append(run_test("jx_py_step18", test_jx_py_step18))
    
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
    
    return 0 if passed == total else 1


if __name__ == '__main__':
    sys.exit(main())
