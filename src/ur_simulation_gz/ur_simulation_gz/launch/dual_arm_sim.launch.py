# Copyright (c) 2026 multi-arm-line project
# 单 Robot + 双 Arm + 单 ControllerManager 架构的 launch 文件
#
# 架构：
#   - 单一 Gazebo robot entity（dual_arm_robot.xacro）
#   - 一个 gz_ros2_control plugin 实例
#   - 一个 /controller_manager（不是 /arm1/cm 或 /arm2/cm）
#   - joint_state_broadcaster + left_arm_controller + right_arm_controller

from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    IncludeLaunchDescription,
    OpaqueFunction,
    TimerAction,
    RegisterEventHandler,
    EmitEvent,
)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import (
    Command,
    FindExecutable,
    LaunchConfiguration,
    PathJoinSubstitution,
    IfElseSubstitution,
)
from launch.events import OnProcessStart
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
import os


def launch_setup(context, *args, **kwargs):
    ur_type = LaunchConfiguration("ur_type").perform(context)
    gazebo_gui = LaunchConfiguration("gazebo_gui")
    world_file = LaunchConfiguration("world_file")

    # URDF/xacro 描述文件
    description_file = PathJoinSubstitution(
        [FindPackageShare("ur_simulation_gz"), "urdf", "dual_arm_robot.xacro"]
    ).perform(context)

    # 控制器 YAML（单一文件，包含全部控制器配置）
    controllers_config = PathJoinSubstitution(
        [FindPackageShare("ur_simulation_gz"), "config", "dual_arm_controllers.yaml"]
    ).perform(context)

    # 生成 robot_description（调用 xacro）
    robot_description_content = Command([
        PathJoinSubstitution([FindExecutable(name="xacro")]),
        " ", description_file,
        " name:=dual_arm",
        " ur_type:=", ur_type,
        " left_origin:=0 0.5 0 0 0 0",
        " right_origin:=0 -0.5 0 0 0 0",
        " simulation_controllers:=", controllers_config,
    ])

    robot_description = {"robot_description": robot_description_content}

    nodes_to_start = []

    # ============================================================
    # Gazebo 启动
    # ============================================================
    gz_launch_description = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            [FindPackageShare("ros_gz_sim"), "/launch/gz_sim.launch.py"]
        ),
        launch_arguments={
            "gz_args": IfElseSubstitution(
                gazebo_gui,
                if_value=[" -r -v 4 ", world_file],
                else_value=[" -s -r -v 4 ", world_file],
            )
        }.items(),
    )

    # Clock bridge（/clock 用于仿真时间同步）
    clock_bridge = Node(
        package="ros_gz_bridge",
        executable="parameter_bridge",
        arguments=["/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock"],
        output="screen",
    )

    nodes_to_start.append(gz_launch_description)
    nodes_to_start.append(clock_bridge)

    # ============================================================
    # Robot State Publisher（单次，因为是单一 robot entity）
    # ============================================================
    rsp_node = Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        output="both",
        parameters=[
            {"use_sim_time": True},
            {"robot_description": robot_description_content},
        ],
    )
    nodes_to_start.append(rsp_node)

    # ============================================================
    # Gazebo Spawn Entity（单次，生成单一 robot entity）
    # ============================================================
    spawn_entity_node = Node(
        package="ros_gz_sim",
        executable="create",
        output="screen",
        arguments=[
            "-string", robot_description_content,
            "-name", "dual_arm",
            "-allow_renaming", "true",
        ],
    )
    nodes_to_start.append(spawn_entity_node)

    # ============================================================
    # Controller Manager Spawner（单一，指向 /controller_manager）
    # ============================================================
    # 注意：-c 参数是 /controller_manager，不是 /arm1/controller_manager
    # 所有控制器（JSB + left + right）通过同一个 --param-file 加载
    cm_spawner = Node(
        package="controller_manager",
        executable="spawner",
        arguments=[
            "joint_state_broadcaster",
            "left_arm_controller",
            "right_arm_controller",
            "-c", "/controller_manager",
            "--param-file", controllers_config,
        ],
        output="screen",
    )

    # 延迟启动：等 Gazebo spawn 完成 + robot_state_publisher 就绪
    # Gazebo spawn 约 5-10s，RSP 就绪约 2s，留 15s 缓冲
    nodes_to_start.append(TimerAction(period=15.0, actions=[cm_spawner]))

    # ============================================================
    # RViz（延迟启动，等 CM spawner 就绪）
    # ============================================================
    rviz_config = PathJoinSubstitution(
        [FindPackageShare("ur_simulation_gz"), "rviz", "view_robot.rviz"]
    ).perform(context)

    rviz_node = Node(
        package="rviz2",
        executable="rviz2",
        arguments=["-d", rviz_config],
        output="screen",
    )
    nodes_to_start.append(TimerAction(period=25.0, actions=[rviz_node]))

    return nodes_to_start


def generate_launch_description():
    declared_arguments = []

    declared_arguments.append(
        DeclareLaunchArgument(
            "ur_type",
            description="Type/series of used UR robot.",
            choices=[
                "ur3", "ur5", "ur10",
                "ur3e", "ur5e", "ur7e", "ur10e", "ur12e", "ur16e",
                "ur8long", "ur15", "ur18", "ur20", "ur30",
            ],
            default_value="ur5e",
        )
    )

    declared_arguments.append(
        DeclareLaunchArgument(
            "gazebo_gui",
            default_value="true",
            description="Start gazebo with GUI?",
        )
    )

    declared_arguments.append(
        DeclareLaunchArgument(
            "world_file",
            default_value="empty.sdf",
            description="Gazebo world file.",
        )
    )

    return LaunchDescription(declared_arguments + [OpaqueFunction(function=launch_setup)])