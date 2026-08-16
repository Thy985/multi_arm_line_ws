# Copyright (c) 2021 Stogl Robotics Consulting UG (haftungsbeschränkt)
# Multi-arm simulation launch file
# 方案: /** 格式 YAML + spawner --param-file
# - simulation_controllers 使用完整 /** 格式 YAML（xacro -> GazeboSimROS2ControlPlugin 初始化 controller_manager）
# - spawner 通过 --param-file 传递同一 YAML（/** 格式让 spawner YAML parser 能正确解析）

from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    IncludeLaunchDescription,
    OpaqueFunction,
    SetEnvironmentVariable,
    TimerAction,
)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import (
    Command,
    FindExecutable,
    LaunchConfiguration,
    PathJoinSubstitution,
    IfElseSubstitution,
)
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
import os


def launch_setup(context, *args, **kwargs):
    ur_type = LaunchConfiguration("ur_type")
    gazebo_gui = LaunchConfiguration("gazebo_gui")
    world_file = LaunchConfiguration("world_file")

    # URDF/XACRO描述文件
    description_file = PathJoinSubstitution(
        [FindPackageShare("ur_simulation_gz"), "urdf", "multi_arm_robot.xacro"]
    )

    # 机械臂配置
    arms = [
        {"name": "left_arm", "prefix": "left_arm_", "pos": ["0", "0", "0"]},
        {"name": "right_arm", "prefix": "right_arm_", "pos": ["1.0", "0", "0"]},
    ]

    nodes_to_start = []

    # ---- Gazebo mesh 资源路径 ----
    # Gazebo 把 package:// 转换为 model:// URI，必须把包 install/share 加入 GZ_SIM_RESOURCE_PATH
    # 否则自定义 STL mesh (torso/head/chassis/pillar) 找不到
    ur_sim_share = PathJoinSubstitution(
        [FindPackageShare("ur_simulation_gz"), "share"]
    ).perform(context)
    nodes_to_start.append(SetEnvironmentVariable(
        name="GZ_SIM_RESOURCE_PATH",
        value=[ur_sim_share, ":", os.environ.get("GZ_SIM_RESOURCE_PATH", "")],
    ))

    # ---- Gazebo ----
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

    # Clock bridge
    gz_sim_bridge = Node(
        package="ros_gz_bridge",
        executable="parameter_bridge",
        arguments=["/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock"],
        output="screen",
    )

    nodes_to_start.append(gz_launch_description)
    nodes_to_start.append(gz_sim_bridge)

    # ---- RViz ----
    rviz_config = PathJoinSubstitution(
        [FindPackageShare("ur_simulation_gz"), "rviz", "view_robot.rviz"]
    )
    rviz_node = Node(
        package="rviz2",
        executable="rviz2",
        arguments=["-d", rviz_config],
        output="screen",
    )
    # ---- RViz（延迟30秒启动，等Gazebo spawner和robot_state_publisher就绪）----
    nodes_to_start.append(TimerAction(period=30.0, actions=[rviz_node]))

    # ---- 为每个机械臂创建节点 ----
    for arm in arms:
        arm_name = arm["name"]
        prefix = arm["prefix"]
        pos = arm["pos"]

        # 完整参数文件（含所有控制器配置），用于 GazeboSimROS2ControlPlugin 初始化
        # spawner 也使用同一个文件（通过 --param-file）
        controllers_config = PathJoinSubstitution(
            [FindPackageShare("ur_simulation_gz"), "config", f"{arm_name}_controllers.yaml"]
        )

        # 生成URDF
        # 使用自定义 joint_limits.yaml（增大 shoulder_lift effort 以避免 Gazebo 物理仿真中的力矩不足）
        joint_limits_file = PathJoinSubstitution(
            [FindPackageShare("ur_simulation_gz"), "config", "joint_limits_custom.yaml"]
        )
        robot_description_content = Command([
            PathJoinSubstitution([FindExecutable(name="xacro")]),
            " ", description_file,
            " joint_limit_params:=", joint_limits_file,
            " safety_limits:=true",
            " safety_pos_margin:=0.15",
            " safety_k_position:=20",
            " name:=ur",
            " ur_type:=", ur_type,
            " tf_prefix:=", prefix,
            " ros_namespace:=", arm_name,
            " simulation_controllers:=", controllers_config,
        ])

        robot_description = {"robot_description": robot_description_content}

        # Robot state publisher
        nodes_to_start.append(Node(
            package="robot_state_publisher",
            executable="robot_state_publisher",
            output="both",
            parameters=[{"use_sim_time": True}, robot_description],
            namespace=arm_name,
        ))

        # Gazebo spawn entity
        nodes_to_start.append(Node(
            package="ros_gz_sim",
            executable="create",
            output="screen",
            arguments=[
                "-string", robot_description_content,
                "-name", arm_name,
                "-allow_renaming", "true",
                "-x", pos[0], "-y", pos[1], "-z", pos[2],
            ],
        ))

    # ============================================================
    # spawner Node（带 --param-file，使用 /** 格式的完整 YAML）
    # ============================================================
    def make_spawner_node(controller_name, arm_name, yaml_path):
        return Node(
            package="controller_manager",
            executable="spawner",
            arguments=[
                controller_name,
                "-c", f"/{arm_name}/controller_manager",
                "--param-file", yaml_path,
            ],
            namespace=arm_name,
            output="screen",
        )

    # 为每个 arm 准备 yaml 路径
    left_arm_yaml = PathJoinSubstitution(
        [FindPackageShare("ur_simulation_gz"), "config", "left_arm_controllers.yaml"]
    ).perform(context)
    right_arm_yaml = PathJoinSubstitution(
        [FindPackageShare("ur_simulation_gz"), "config", "right_arm_controllers.yaml"]
    ).perform(context)

    left_arm_jsb = make_spawner_node("joint_state_broadcaster", "left_arm", left_arm_yaml)
    left_arm_jtc = make_spawner_node("joint_trajectory_controller", "left_arm", left_arm_yaml)
    right_arm_jsb = make_spawner_node("joint_state_broadcaster", "right_arm", right_arm_yaml)
    right_arm_jtc = make_spawner_node("joint_trajectory_controller", "right_arm", right_arm_yaml)

    # 启动顺序：
    # t=30:  left_arm jsb
    # t=35:  left_arm jtc
    # t=50:  right_arm jsb
    # t=55:  right_arm jtc
    nodes_to_start.append(TimerAction(period=30.0, actions=[left_arm_jsb]))
    nodes_to_start.append(TimerAction(period=35.0, actions=[left_arm_jtc]))
    nodes_to_start.append(TimerAction(period=50.0, actions=[right_arm_jsb]))
    nodes_to_start.append(TimerAction(period=55.0, actions=[right_arm_jtc]))

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
            "gazebo_gui", default_value="true", description="Start gazebo with GUI?"
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