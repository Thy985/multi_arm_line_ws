#!/bin/bash
# start_gazebo_headless.sh
# 启动Gazebo headless模式（无GUI）

echo "=========================================="
echo "  启动Gazebo Headless模式"
echo "=========================================="

# 设置环境变量
export GALLIUM_DRIVER=d3d12
export MESA_D3D12_DEFAULT_ADAPTER_NAME=NVIDIA
export QT_QPA_PLATFORM=offscreen
export LIBGL_ALWAYS_SOFTWARE=1

# 清理旧进程
echo "清理旧进程..."
pkill -9 -f "gz sim" 2>/dev/null
pkill -9 -f "parameter_bridge" 2>/dev/null
sleep 2

# 加载ROS环境
echo "加载ROS环境..."
source /opt/ros/jazzy/setup.bash
source ~/multi_arm_line_ws/install/setup.bash

# 启动Gazebo（无GUI）
echo "启动Gazebo（headless模式）..."
cd ~/multi_arm_line_ws
ros2 launch ur_simulation_gz multi_arm_sim.launch.py gazebo_gui:=false &

# 等待启动
echo "等待Gazebo启动..."
sleep 10

# 检查状态
echo "检查启动状态..."
echo "Gazebo进程数: $(ps aux | grep -E 'gz sim' | grep -v grep | wc -l)"
echo "ROS节点数: $(ros2 node list 2>/dev/null | wc -l)"

echo ""
echo "=========================================="
echo "  Gazebo已启动（headless模式）"
echo "=========================================="
echo ""
echo "查看机器人模型，请运行:"
echo "  rviz2 -d ~/multi_arm_line_ws/src/ur_simulation_gz/ur_simulation_gz/rviz/view_robot.rviz"
echo ""
echo "控制机械臂，请运行:"
echo "  python3 /mnt/d/study/机械臂/JX.py"
echo "  然后选择 [15] 交互式控制"
echo ""
