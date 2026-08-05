# 多机械臂系统测试指南

## 系统架构

本系统使用ROS2命名空间隔离实现多机械臂控制：

- 每个机械臂运行在独立的命名空间下（`/arm1`、`/arm2`）
- 每个机械臂有独立的控制器管理器
- 使用不同的TF前缀区分机械臂
- 所有机械臂共享同一个Gazebo仿真世界

## 文件结构

```
src/
├── ur_simulation_gz/
│   ├── launch/
│   │   ├── ur_sim_control.launch.py      # 单机械臂launch文件
│   │   ├── multi_arm_sim.launch.py        # 多机械臂launch文件
│   │   └── test_multi_arm.launch.py       # 测试launch文件
│   └── config/
│       ├── ur_controllers.yaml            # 单机械臂控制器配置
│       └── ur_controllers_multi.yaml      # 多机械臂控制器配置
└── order_manager/
    └── order_manager/
        └── nodes/
            ├── multi_arm_coordinator.py   # 多机械臂协调节点
            └── test_arm_control.py        # 单臂测试脚本
```

## 测试步骤

### 1. 编译工作空间

```bash
cd ~/multi_arm_line_ws
colcon build --packages-select ur_simulation_gz order_manager
source install/setup.bash
```

### 2. 启动多机械臂仿真

```bash
# 启动两个UR5e机械臂
ros2 launch ur_simulation_gz multi_arm_sim.launch.py ur_type:=ur5e
```

这将启动：
- Gazebo仿真环境
- 两个UR5e机械臂（arm1和arm2）
- RViz可视化

### 3. 测试单个机械臂控制

在新的终端中：

```bash
# 测试arm1
ros2 run order_manager test_arm_control arm1

# 测试arm2
ros2 run order_manager test_arm_control arm2
```

### 4. 测试协调控制

```bash
# 启动协调节点
ros2 run order_manager multi_arm_coordinator
```

### 5. 手动发送轨迹命令

使用ros2命令行工具：

```bash
# 查看可用的话题
ros2 topic list | grep joint_trajectory

# 发送轨迹到arm1
ros2 action send_goal /arm1/joint_trajectory_controller/follow_joint_trajectory \
  control_msgs/action/FollowJointTrajectory \
  "{
    trajectory: {
      joint_names: [shoulder_pan_joint, shoulder_lift_joint, elbow_joint, wrist_1_joint, wrist_2_joint, wrist_3_joint],
      points: [
        {
          positions: [0.0, -1.57, 1.57, 0.0, 0.0, 0.0],
          velocities: [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
          accelerations: [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
          time_from_start: {sec: 3, nanosec: 0}
        }
      ]
    }
  }"

# 发送轨迹到arm2
ros2 action send_goal /arm2/joint_trajectory_controller/follow_joint_trajectory \
  control_msgs/action/FollowJointTrajectory \
  "{
    trajectory: {
      joint_names: [shoulder_pan_joint, shoulder_lift_joint, elbow_joint, wrist_1_joint, wrist_2_joint, wrist_3_joint],
      points: [
        {
          positions: [0.0, -1.57, 1.57, 0.0, 0.0, 0.0],
          velocities: [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
          accelerations: [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
          time_from_start: {sec: 3, nanosec: 0}
        }
      ]
    }
  }"
```

## 扩展到更多机械臂

要添加更多机械臂，修改 `multi_arm_sim.launch.py`：

```python
# 在 launch_setup 函数中添加第三个机械臂
arm3_nodes = create_arm_nodes(
    ur_type=ur_type,
    tf_prefix="arm3_",
    controllers_file=controllers_file,
    description_file=description_file,
    world_file=world_file,
    arm_name="arm3",
    initial_position=["2.0", "0.0", "0.0"],  # 不同的位置
)

# 将arm3_nodes添加到nodes_to_start列表
nodes_to_start = [
    gz_launch_description,
    gz_sim_bridge,
    *arm1_nodes,
    *arm2_nodes,
    *arm3_nodes,  # 添加第三个机械臂
    rviz_node,
]
```

## 注意事项

1. **初始位置**：每个机械臂需要不同的初始位置，避免碰撞
2. **TF前缀**：确保每个机械臂的TF前缀唯一
3. **控制器配置**：所有机械臂使用相同的控制器配置，通过TF前缀区分关节
4. **资源占用**：多个机械臂会增加计算负担，确保系统性能足够

## 故障排除

### 问题1：控制器启动失败
检查控制器配置文件中的关节名称是否正确包含TF前缀。

### 问题2：TF冲突
确保每个机械臂的TF前缀唯一，并且URDF/XACRO文件正确使用了tf_prefix参数。

### 问题3：Gazebo性能问题
减少Gazebo渲染频率或关闭GUI以提升性能。

## 下一步

1. 实现更复杂的协调算法（避碰、任务分配）
2. 添加实际的任务场景（抓取、装配）
3. 集成MoveIt2进行运动规划
4. 实现动态添加/移除机械臂