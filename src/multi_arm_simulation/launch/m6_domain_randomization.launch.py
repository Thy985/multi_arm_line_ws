"""M6 Domain Randomization Benchmark Launch — lightweight stack.

Phase 4: Runs without MoveIt2 to avoid executor thread contention.
Coordinator falls back to direct JTC trajectory execution.

Components:
    1. Gazebo (m6_test_world.sdf with table + cube + cylinder)
    2. Dual UR5e robot + controllers
    3. ros_gz_bridge (clock + object poses)
    4. GazeboGroundTruthNode (ObjectPose from Gazebo)
    5. WorldModelNode (receives object poses + joint states)
    6. SafetySupervisor (safety checks, arm1 only)
    7. CoordinatorNode (task orchestration, JTC direct)
"""

import os
import yaml
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    IncludeLaunchDescription,
    OpaqueFunction,
    TimerAction,
    RegisterEventHandler,
)
from launch.event_handlers import OnProcessExit
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import (
    Command,
    FindExecutable,
    LaunchConfiguration,
    PathJoinSubstitution,
)
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterFile
from launch_ros.substitutions import FindPackageShare


def launch_setup(context, *args, **kwargs):
    """Setup launch nodes for domain randomization benchmark."""
    ur_type = LaunchConfiguration("ur_type").perform(context)
    gazebo_gui = LaunchConfiguration("gazebo_gui").perform(context)

    sim_share = FindPackageShare("multi_arm_simulation").find(
        "multi_arm_simulation"
    )

    world_file = os.path.join(sim_share, "worlds", "m6_test_world.sdf")

    description_file = PathJoinSubstitution(
        [FindPackageShare("ur_simulation_gz"), "urdf", "multi_arm_robot.xacro"]
    )
    controllers_config = PathJoinSubstitution(
        [FindPackageShare("ur_simulation_gz"), "config", "multi_arm_controllers.yaml"]
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
        " name:=multi_arm",
        " ur_type:=", ur_type,
        " simulation_controllers:=", controllers_config,
    ])

    robot_description = {"robot_description": robot_description_content}

    nodes = []

    gz_args = f"-s -r -v 4 {world_file}"
    if gazebo_gui == "true":
        gz_args = f"-r -v 4 {world_file}"

    gz_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            [FindPackageShare("ros_gz_sim"), "/launch/gz_sim.launch.py"]
        ),
        launch_arguments={
            "gz_args": gz_args,
        }.items(),
    )
    nodes.append(gz_launch)

    nodes.append(Node(
        package="ros_gz_bridge",
        executable="parameter_bridge",
        arguments=[
            "/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock",
            "/model/red_cube/pose@geometry_msgs/msg/Pose[gz.msgs.Pose",
            "/model/blue_cylinder/pose@geometry_msgs/msg/Pose[gz.msgs.Pose",
        ],
        output="screen",
    ))

    nodes.append(Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        output="both",
        parameters=[{"use_sim_time": True}, robot_description],
    ))

    nodes.append(Node(
        package="ros_gz_sim",
        executable="create",
        output="screen",
        arguments=[
            "-string", robot_description_content,
            "-name", "multi_arm",
            "-allow_renaming", "true",
        ],
    ))

    jsb_spawner = Node(
        package="controller_manager",
        executable="spawner",
        arguments=[
            "joint_state_broadcaster",
            "-c", "/controller_manager",
        ],
        parameters=[ParameterFile(controllers_config, allow_substs=True)],
    )
    nodes.append(jsb_spawner)

    arm1_jtc_spawner = Node(
        package="controller_manager",
        executable="spawner",
        arguments=[
            "arm1_joint_trajectory_controller",
            "-c", "/controller_manager",
        ],
        parameters=[ParameterFile(controllers_config, allow_substs=True)],
    )

    arm2_jtc_spawner = Node(
        package="controller_manager",
        executable="spawner",
        arguments=[
            "arm2_joint_trajectory_controller",
            "-c", "/controller_manager",
        ],
        parameters=[ParameterFile(controllers_config, allow_substs=True)],
    )

    nodes.append(RegisterEventHandler(
        OnProcessExit(target_action=jsb_spawner, on_exit=[arm1_jtc_spawner])
    ))
    nodes.append(RegisterEventHandler(
        OnProcessExit(target_action=arm1_jtc_spawner, on_exit=[arm2_jtc_spawner])
    ))

    ground_truth_node = Node(
        package="multi_arm_simulation",
        executable="gazebo_ground_truth_node",
        output="screen",
        parameters=[
            {
                "use_sim_time": True,
                "world_name": "m6_test_world",
                "publish_rate": 10.0,
                "object_ids": "red_cube,blue_cylinder",
                "object_types": "cube,cylinder",
            }
        ],
    )
    nodes.append(TimerAction(period=5.0, actions=[ground_truth_node]))

    world_model_node = Node(
        package="multi_arm_world_model",
        executable="world_model_node",
        output="screen",
        parameters=[{"use_sim_time": True}],
    )
    nodes.append(TimerAction(period=6.0, actions=[world_model_node]))

    safety_node = Node(
        package="multi_arm_safety",
        executable="safety_supervisor",
        output="screen",
        parameters=[
            {"use_sim_time": True},
            {"arm_names": ["arm1"]},
        ],
    )
    nodes.append(TimerAction(period=6.0, actions=[safety_node]))

    coordinator_node = Node(
        package="multi_arm_core",
        executable="coordinator_node",
        output="screen",
        parameters=[{"use_sim_time": True}],
    )
    nodes.append(TimerAction(period=8.0, actions=[coordinator_node]))

    return nodes


def generate_launch_description():
    """Generate launch description."""
    declared = []
    declared.append(DeclareLaunchArgument("ur_type", default_value="ur5e"))
    declared.append(DeclareLaunchArgument("gazebo_gui", default_value="false"))
    return LaunchDescription(declared + [OpaqueFunction(function=launch_setup)])