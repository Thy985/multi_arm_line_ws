"""Single-arm M4.1 validation launch with namespace support.

Starts single UR5e in Gazebo with:
- /left_arm namespace for robot_state_publisher
- /left_arm/joint_states (namespaced JSB)
- /left_arm/joint_trajectory_controller (namespaced JTC)
- WorldModel node
- SafetySupervisor node

This matches the multi_arm namespace architecture used by WorldModel and Safety.
"""

import os
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    OpaqueFunction,
    TimerAction,
    RegisterEventHandler,
)
from launch.conditions import IfCondition
from launch.event_handlers import OnProcessExit
from launch.substitutions import (
    Command,
    FindExecutable,
    LaunchConfiguration,
    PathJoinSubstitution,
    IfElseSubstitution,
)
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterFile
from launch_ros.substitutions import FindPackageShare


def launch_setup(context, *args, **kwargs):
    ur_type = LaunchConfiguration("ur_type").perform(context)
    gazebo_gui = LaunchConfiguration("gazebo_gui").perform(context)
    launch_rviz = LaunchConfiguration("launch_rviz").perform(context)

    ur_simulation_dir = FindPackageShare("ur_simulation_gz").find("ur_simulation_gz")
    moveit_config_dir = FindPackageShare("multi_arm_moveit_config").find(
        "multi_arm_moveit_config"
    )

    arm_name = "left_arm"
    prefix = "left_arm_"

    controllers_config = PathJoinSubstitution(
        [FindPackageShare("ur_simulation_gz"), "config", f"{arm_name}_controllers.yaml"]
    )

    description_file = PathJoinSubstitution(
        [FindPackageShare("ur_simulation_gz"), "urdf", "ur_gz.urdf.xacro"]
    )
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

    nodes_to_start = []

    # ---- Gazebo ----
    from launch.actions import IncludeLaunchDescription
    from launch.launch_description_sources import PythonLaunchDescriptionSource

    gz_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            [FindPackageShare("ros_gz_sim"), "/launch/gz_sim.launch.py"]
        ),
        launch_arguments={
            "gz_args": IfElseSubstitution(
                LaunchConfiguration("gazebo_gui"),
                if_value=[" -r -v 4 empty.sdf"],
                else_value=[" -s -r -v 4 empty.sdf"],
            )
        }.items(),
    )
    nodes_to_start.append(gz_launch)

    # Clock bridge
    gz_sim_bridge = Node(
        package="ros_gz_bridge",
        executable="parameter_bridge",
        arguments=["/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock"],
        output="screen",
    )
    nodes_to_start.append(gz_sim_bridge)

    # ---- Robot State Publisher (namespaced) ----
    robot_state_publisher = Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        output="both",
        parameters=[{"use_sim_time": True}, robot_description],
        namespace=arm_name,
    )
    nodes_to_start.append(robot_state_publisher)

    # ---- Spawn entity ----
    gz_spawn_entity = Node(
        package="ros_gz_sim",
        executable="create",
        output="screen",
        arguments=[
            "-string", robot_description_content,
            "-name", arm_name,
            "-allow_renaming", "true",
        ],
    )
    nodes_to_start.append(gz_spawn_entity)

    # ---- Spawners (namespaced controller_manager) ----
    jsb_spawner = Node(
        package="controller_manager",
        executable="spawner",
        arguments=[
            "joint_state_broadcaster",
            "-c", f"/{arm_name}/controller_manager",
        ],
        parameters=[ParameterFile(controllers_config, allow_substs=True)],
        namespace=arm_name,
    )
    nodes_to_start.append(jsb_spawner)

    jtc_spawner = Node(
        package="controller_manager",
        executable="spawner",
        arguments=[
            "joint_trajectory_controller",
            "-c", f"/{arm_name}/controller_manager",
        ],
        parameters=[ParameterFile(controllers_config, allow_substs=True)],
        namespace=arm_name,
    )
    nodes_to_start.append(
        RegisterEventHandler(
            event_handler=OnProcessExit(
                target_action=jsb_spawner,
                on_exit=[jtc_spawner],
            ),
        )
    )

    # ---- WorldModel node ----
    world_model_node = Node(
        package="multi_arm_world_model",
        executable="world_model_node",
        output="screen",
        parameters=[
            {"use_sim_time": True},
            {"arm_names": [arm_name]},
        ],
    )
    nodes_to_start.append(TimerAction(period=5.0, actions=[world_model_node]))

    # ---- SafetySupervisor node ----
    safety_node = Node(
        package="multi_arm_safety",
        executable="safety_supervisor",
        output="screen",
        parameters=[
            {"use_sim_time": True},
            {"arm_names": [arm_name]},
        ],
    )
    nodes_to_start.append(TimerAction(period=5.0, actions=[safety_node]))

    # ---- RViz ----
    if launch_rviz == "true":
        rviz_config = os.path.join(moveit_config_dir, "rviz", "moveit.rviz")
        rviz_node = Node(
            package="rviz2",
            executable="rviz2",
            name="rviz2",
            arguments=["-d", rviz_config] if os.path.exists(rviz_config) else [],
            parameters=[{"use_sim_time": True}, robot_description],
            output="screen",
        )
        nodes_to_start.append(
            RegisterEventHandler(
                event_handler=OnProcessExit(
                    target_action=jtc_spawner,
                    on_exit=[rviz_node],
                ),
            )
        )

    return nodes_to_start


def generate_launch_description():
    declared_arguments = []

    declared_arguments.append(
        DeclareLaunchArgument(
            "ur_type",
            default_value="ur5e",
            description="Type/series of used UR robot.",
        )
    )

    declared_arguments.append(
        DeclareLaunchArgument(
            "gazebo_gui",
            default_value="false",
            description="Start Gazebo with GUI?",
        )
    )

    declared_arguments.append(
        DeclareLaunchArgument(
            "launch_rviz",
            default_value="false",
            description="Launch RViz?",
        )
    )

    return LaunchDescription(
        declared_arguments + [OpaqueFunction(function=launch_setup)]
    )