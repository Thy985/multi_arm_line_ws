cmake_minimum_required(VERSION 3.8)
project(multi_arm_interfaces)

find_package(rosidl_default_generators REQUIRED)
find_package(ament_cmake REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/TaskDescription.msg"
  "msg/TaskStatus.msg"
  "msg/TaskRequirement.msg"
  "msg/ObjectPose.msg"
  "msg/CollisionEvent.msg"
  "msg/SystemHealth.msg"
  "msg/ResourceStatus.msg"
  "msg/RecoveryAction.msg"
  "srv/SafetyCheck.srv"
  "srv/EmergencyStop.srv"
  "srv/SubmitTask.srv"
  "srv/QueryResources.srv"
  "srv/RecoverFromFailure.srv"
  "action/PickPlace.action"
  "action/ExecuteTask.action"
)

ament_package()