"""Launch file for multi-arm MoveIt2 with Gazebo simulation.

Starts:
1. Gazebo simulation (via multi_arm_sim.launch.py)
2. MoveIt2 move_group node
3. RViz with MoveIt plugin
4. WorldModel node
5. SafetySupervisor node
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
    headless = LaunchConfiguration("headless").perform(context)

    ur_simulation_dir = FindPackageShare("ur_simulation_gz").find("ur_simulation_gz")
    moveit_config_dir = FindPackageShare("multi_arm_moveit_config").find("multi_arm_moveit_config")

    nodes_to_start = []

    # ---- Gazebo simulation ----
    gz_sim = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(ur_simulation_dir, "launch", "multi_arm_sim.launch.py")
        ),
        launch_arguments={
            "ur_type": ur_type,
            "gazebo_gui": "false" if headless == "true" else gazebo_gui,
        }.items(),
    )
    nodes_to_start.append(gz_sim)

    # ---- Build combined URDF for MoveIt (dual arm) ----
    description_file = os.path.join(ur_simulation_dir, "urdf", "ur_gz.urdf.xacro")
    joint_limits_file = os.path.join(ur_simulation_dir, "config", "joint_limits_custom.yaml")
    left_arm_controllers = os.path.join(ur_simulation_dir, "config", "left_arm_controllers.yaml")

    # Generate left_arm URDF (used as robot_description for MoveIt)
    # MoveIt needs a single robot_description with all joints
    # We use a combined xacro approach
    robot_description_content = Command([
        FindExecutable(name="xacro"), " ",
        description_file,
        " joint_limit_params:=", joint_limits_file,
        " safety_limits:=true",
        " safety_pos_margin:=0.15",
        " safety_k_position:=20",
        " name:=ur",
        " ur_type:=", ur_type,
        " tf_prefix:=left_arm_",
        " ros_namespace:=left_arm",
        " simulation_controllers:=", left_arm_controllers,
    ])

    # For MoveIt, we need a combined robot description with both arms
    # We'll load SRDF that defines both arm groups
    srdf_file = os.path.join(moveit_config_dir, "config", "multi_arm.srdf")

    # MoveIt config files
    ompl_planning = os.path.join(moveit_config_dir, "config", "ompl_planning.yaml")
    kinematics = os.path.join(moveit_config_dir, "config", "kinematics.yaml")
    joint_limits = os.path.join(moveit_config_dir, "config", "joint_limits.yaml")
    moveit_controllers = os.path.join(moveit_config_dir, "config", "moveit_controllers.yaml")
    initial_positions = os.path.join(moveit_config_dir, "config", "initial_positions.yaml")

    # ---- move_group node ----
    # Load SRDF content
    with open(srdf_file, "r") as f:
        srdf_content = f.read()

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

    # Delay move_group until controllers are ready (multi_arm_sim uses 30-55s delays)
    nodes_to_start.append(TimerAction(period=60.0, actions=[move_group_node]))

    # ---- WorldModel node ----
    world_model_node = Node(
        package="multi_arm_world_model",
        executable="world_model_node",
        output="screen",
        parameters=[{"use_sim_time": True}],
    )
    nodes_to_start.append(TimerAction(period=5.0, actions=[world_model_node]))

    # ---- SafetySupervisor node ----
    safety_node = Node(
        package="multi_arm_safety",
        executable="safety_supervisor",
        output="screen",
        parameters=[{"use_sim_time": True}],
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
                {"robot_description_planning": joint_limits},
            ],
            output="screen",
        )
        nodes_to_start.append(TimerAction(period=65.0, actions=[rviz_node]))

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

    declared_arguments.append(
        DeclareLaunchArgument(
            "headless",
            default_value="false",
            description="Run in headless mode (no Gazebo GUI, no display)?",
        )
    )

    return LaunchDescription(declared_arguments + [OpaqueFunction(function=launch_setup)])