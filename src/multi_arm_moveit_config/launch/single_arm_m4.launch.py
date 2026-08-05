"""Launch file for single-arm M4.1 closed-loop validation.

Starts:
1. Single UR5e in Gazebo with ros2_control
2. MoveIt2 move_group for arm1
3. WorldModel node
4. SafetySupervisor node

Validates: Task → Plan → Safety → Motion → Gazebo → JointState → WorldModel
"""

import os
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    IncludeLaunchDescription,
    OpaqueFunction,
    TimerAction,
)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import (
    Command,
    FindExecutable,
    LaunchConfiguration,
    PathJoinSubstitution,
)
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def launch_setup(context, *args, **kwargs):
    ur_type = LaunchConfiguration("ur_type").perform(context)
    gazebo_gui = LaunchConfiguration("gazebo_gui").perform(context)
    launch_rviz = LaunchConfiguration("launch_rviz").perform(context)

    ur_simulation_dir = FindPackageShare("ur_simulation_gz").find("ur_simulation_gz")
    moveit_config_dir = FindPackageShare("multi_arm_moveit_config").find("multi_arm_moveit_config")

    nodes_to_start = []

    # ---- Gazebo + single arm (use upstream ur_sim_control) ----
    gz_sim = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(ur_simulation_dir, "launch", "ur_sim_control.launch.py")
        ),
        launch_arguments={
            "ur_type": ur_type,
            "gazebo_gui": gazebo_gui,
            "launch_rviz": "false",
            "tf_prefix": "arm1_",
            "controllers_file": "arm1_controllers.yaml",
        }.items(),
    )
    nodes_to_start.append(gz_sim)

    # ---- Build robot_description for MoveIt ----
    description_file = os.path.join(ur_simulation_dir, "urdf", "ur_gz.urdf.xacro")
    joint_limits_file = os.path.join(ur_simulation_dir, "config", "joint_limits_custom.yaml")
    arm1_controllers = os.path.join(ur_simulation_dir, "config", "arm1_controllers.yaml")

    robot_description_content = Command([
        FindExecutable(name="xacro"), " ",
        description_file,
        " joint_limit_params:=", joint_limits_file,
        " safety_limits:=true",
        " safety_pos_margin:=0.15",
        " safety_k_position:=20",
        " name:=ur",
        " ur_type:=", ur_type,
        " tf_prefix:=arm1_",
        " ros_namespace:=arm1",
        " simulation_controllers:=", arm1_controllers,
    ])

    # SRDF for single arm (reuse multi_arm.srdf, arm1 group only)
    srdf_file = os.path.join(moveit_config_dir, "config", "multi_arm.srdf")
    with open(srdf_file, "r") as f:
        srdf_content = f.read()

    # MoveIt config files
    ompl_planning = os.path.join(moveit_config_dir, "config", "ompl_planning.yaml")
    kinematics = os.path.join(moveit_config_dir, "config", "kinematics.yaml")
    joint_limits = os.path.join(moveit_config_dir, "config", "joint_limits.yaml")
    moveit_controllers = os.path.join(moveit_config_dir, "config", "moveit_controllers.yaml")
    initial_positions = os.path.join(moveit_config_dir, "config", "initial_positions.yaml")

    # ---- move_group node ----
    move_group_params = {
        "robot_description": robot_description_content,
        "robot_description_semantic": srdf_content,
        "robot_description_kinematics": kinematics,
        "robot_description_planning": joint_limits,
        "use_sim_time": True,
        "publish_robot_description_semantic": True,
        "allow_trajectory_execution": True,
        "publish_planning_scene": True,
        "publish_geometry_updates": True,
        "publish_state_updates": True,
        "publish_transforms_updates": True,
        "planning_pipeline": "ompl",
        "planning_pipelines": ["ompl"],
        "ompl_planning_config": ompl_planning,
        "default_planning_pipeline": "ompl",
        "trajectory_execution": {
            "execution_duration_scaling": 1.2,
            "allowed_execution_duration_scaling": 1.5,
        },
        "moveit_controller_manager": moveit_controllers,
        "initial_positions": initial_positions,
    }

    move_group_node = Node(
        package="moveit_ros_move_group",
        executable="move_group",
        output="screen",
        parameters=[move_group_params],
    )
    nodes_to_start.append(TimerAction(period=20.0, actions=[move_group_node]))

    # ---- WorldModel node ----
    world_model_node = Node(
        package="multi_arm_world_model",
        executable="world_model_node",
        output="screen",
        parameters=[
            {"use_sim_time": True},
            {"arm_names": ["arm1"]},
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
            {"arm_names": ["arm1"]},
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
            parameters=[
                {"use_sim_time": True},
                {"robot_description": robot_description_content},
                {"robot_description_semantic": srdf_content},
                {"robot_description_kinematics": kinematics},
            ],
            output="screen",
        )
        nodes_to_start.append(TimerAction(period=25.0, actions=[rviz_node]))

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
            default_value="true",
            description="Start Gazebo with GUI?",
        )
    )

    declared_arguments.append(
        DeclareLaunchArgument(
            "launch_rviz",
            default_value="true",
            description="Launch RViz?",
        )
    )

    return LaunchDescription(declared_arguments + [OpaqueFunction(function=launch_setup)])