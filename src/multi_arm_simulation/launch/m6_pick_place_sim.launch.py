"""M6 Pick-Place Simulation E2E Launch — full stack closed loop.

Phase 2: Proves the full M6 stack works in Gazebo simulation with objects.

Full chain:
    GazeboGroundTruth → WorldModel → Coordinator → MoveIt2 → JTC → Gazebo
    → JointStates → WorldModel update → ObjectPose → WorldModel update

Components:
    1. Gazebo (m6_test_world.sdf with table + cube + cylinder)
    2. Dual UR5e robot + controllers
    3. ros_gz_bridge (clock + object poses)
    4. GazeboGroundTruthNode (ObjectPose from Gazebo)
    5. WorldModelNode (receives object poses + joint states)
    6. MoveIt2 move_group (motion planning)
    7. SafetySupervisor (safety checks)
    8. CoordinatorNode (task orchestration)
    9. TaskPlannerNode (BT execution)

Unlike m4_6_task_loop.launch.py (empty.sdf, no objects),
this launch has real objects and ground truth perception.
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
from launch_ros.parameter_descriptions import ParameterFile, ParameterValue
from launch_ros.substitutions import FindPackageShare


def load_yaml(file_path):
    """Load YAML file."""
    with open(file_path, "r") as f:
        return yaml.safe_load(f)


def launch_setup(context, *args, **kwargs):
    """Setup launch nodes for full M6 Pick-Place simulation."""
    ur_type = LaunchConfiguration("ur_type").perform(context)
    gazebo_gui = LaunchConfiguration("gazebo_gui").perform(context)

    sim_share = FindPackageShare("multi_arm_simulation").find(
        "multi_arm_simulation"
    )
    moveit_dir = FindPackageShare("multi_arm_moveit_config").find(
        "multi_arm_moveit_config"
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

    robot_description = {"robot_description": ParameterValue(robot_description_content, value_type=str)}

    nodes = []

    # === Gazebo with custom world (objects present) ===
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

    # === Bridge clock + object poses ===
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

    # === Robot state publisher ===
    nodes.append(Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        output="both",
        parameters=[{"use_sim_time": True}, robot_description],
    ))

    # === Spawn robot into Gazebo ===
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

    # === Controllers ===
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

    arm1_gripper_spawner = Node(
        package="controller_manager",
        executable="spawner",
        arguments=[
            "arm1_gripper_controller",
            "-c", "/controller_manager",
        ],
        parameters=[ParameterFile(controllers_config, allow_substs=True)],
    )

    arm2_gripper_spawner = Node(
        package="controller_manager",
        executable="spawner",
        arguments=[
            "arm2_gripper_controller",
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
    nodes.append(RegisterEventHandler(
        OnProcessExit(target_action=arm2_jtc_spawner, on_exit=[arm1_gripper_spawner])
    ))
    nodes.append(RegisterEventHandler(
        OnProcessExit(target_action=arm1_gripper_spawner, on_exit=[arm2_gripper_spawner])
    ))

    # === MoveIt2 move_group ===
    srdf_file = os.path.join(moveit_dir, "config", "multi_arm.srdf")
    with open(srdf_file, "r") as f:
        srdf_content = f.read()

    kinematics_data = load_yaml(os.path.join(moveit_dir, "config", "kinematics.yaml"))
    joint_limits_data = load_yaml(os.path.join(moveit_dir, "config", "joint_limits.yaml"))
    moveit_controllers_data = load_yaml(os.path.join(moveit_dir, "config", "moveit_controllers.yaml"))
    initial_positions_data = load_yaml(os.path.join(moveit_dir, "config", "initial_positions.yaml"))

    move_group_params = {
        "robot_description": ParameterValue(robot_description_content, value_type=str),
        "robot_description_semantic": srdf_content,
        "robot_description_kinematics": kinematics_data,
        "robot_description_planning": joint_limits_data,
        "use_sim_time": True,
        "publish_robot_description_semantic": True,
        "allow_trajectory_execution": True,
        "publish_planning_scene": True,
        "publish_geometry_updates": True,
        "publish_state_updates": True,
        "publish_transforms_updates": True,
        "planning_pipelines": ["ompl"],
        "default_planning_pipeline": "ompl",
        "ompl": {
            "planning_plugins": ["ompl_interface/OMPLPlanner"],
            "request_adapters": [
                "default_planning_request_adapters/ResolveConstraintFrames",
                "default_planning_request_adapters/ValidateWorkspaceBounds",
                "default_planning_request_adapters/CheckStartStateBounds",
                "default_planning_request_adapters/CheckStartStateCollision",
            ],
            "response_adapters": [
                "default_planning_response_adapters/AddTimeOptimalParameterization",
                "default_planning_response_adapters/ValidateSolution",
                "default_planning_response_adapters/DisplayMotionPath",
            ],
            "start_state_max_bounds_error": 0.1,
        },
        "trajectory_execution": {
            "execution_duration_scaling": 1.2,
            "allowed_execution_duration_scaling": 1.5,
        },
        "moveit_controller_manager": moveit_controllers_data.get("moveit_controller_manager", ""),
        "moveit_simple_controller_manager": moveit_controllers_data.get("moveit_simple_controller_manager", {}),
        "moveit_manage_controllers": False,
        "initial_positions": initial_positions_data.get("initial_positions", {}),
    }

    move_group = Node(
        package="moveit_ros_move_group",
        executable="move_group",
        output="screen",
        parameters=[move_group_params],
    )
    nodes.append(RegisterEventHandler(
        OnProcessExit(target_action=arm2_gripper_spawner, on_exit=[move_group])
    ))

    # === Gazebo Ground Truth Node (publishes ObjectPose from Gazebo) ===
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

    # === WorldModel Node (receives object poses + joint states) ===
    world_model_node = Node(
        package="multi_arm_world_model",
        executable="world_model_node",
        output="screen",
        parameters=[{"use_sim_time": True}],
    )
    nodes.append(TimerAction(period=6.0, actions=[world_model_node]))

    # === Safety Supervisor ===
    safety_arm_names = LaunchConfiguration("safety_arm_names").perform(context)
    safety_arm_list = [s.strip() for s in safety_arm_names.split(",") if s.strip()]
    safety_node = Node(
        package="multi_arm_safety",
        executable="safety_supervisor",
        output="screen",
        parameters=[
            {"use_sim_time": True},
            {"arm_names": safety_arm_list},
        ],
    )
    nodes.append(TimerAction(period=6.0, actions=[safety_node]))

    # === Coordinator Node ===
    coordinator_node = Node(
        package="multi_arm_core",
        executable="coordinator_node",
        output="screen",
        parameters=[{"use_sim_time": True}],
    )
    nodes.append(TimerAction(period=8.0, actions=[coordinator_node]))

    # === Task Planner Node ===
    task_planner_node = Node(
        package="multi_arm_task_planner",
        executable="task_planner_node",
        output="screen",
        parameters=[
            {"use_sim_time": True},
            {"use_ros2_plugins": True},
        ],
    )
    nodes.append(TimerAction(period=10.0, actions=[task_planner_node]))

    return nodes


def generate_launch_description():
    """Generate launch description."""
    declared = []
    declared.append(DeclareLaunchArgument("ur_type", default_value="ur5e"))
    declared.append(DeclareLaunchArgument("gazebo_gui", default_value="false"))
    declared.append(DeclareLaunchArgument(
        "safety_arm_names", default_value="arm1,arm2",
        description="Comma-separated arm names for SafetySupervisor to monitor",
    ))
    return LaunchDescription(declared + [OpaqueFunction(function=launch_setup)])