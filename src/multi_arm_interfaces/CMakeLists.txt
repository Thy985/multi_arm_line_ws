cmake_minimum_required(VERSION 3.8)
project(multi_arm_interfaces)

find_package(rosidl_default_generators REQUIRED)
find_package(ament_cmake REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/TaskDescription.msg"
  "msg/TaskStatus.msg"
  "msg/TaskRequirement.msg"
  "msg/TaskGoal.msg"
  "msg/TaskConstraint.msg"
  "msg/MotionRequest.msg"
  "msg/ObjectPose.msg"
  "msg/CollisionEvent.msg"
  "msg/SystemHealth.msg"
  "msg/ResourceStatus.msg"
  "msg/RecoveryAction.msg"
  "msg/CapabilityInfo.msg"
  "msg/ObjectState.msg"
  "msg/SceneState.msg"
  "msg/TaskState.msg"
  "msg/Relation.msg"
  "msg/RelationGraph.msg"
  "msg/SkillDescription.msg"
  "msg/SkillStatus.msg"
  "srv/SafetyCheck.srv"
  "srv/EmergencyStop.srv"
  "srv/SubmitTask.srv"
  "srv/QueryResources.srv"
  "srv/RecoverFromFailure.srv"
  "srv/GetCapability.srv"
  "srv/QueryWorld.srv"
  "srv/QueryRelation.srv"
  "srv/ControlGripper.srv"
  "srv/ListSkills.srv"
  "srv/ManageSkill.srv"
  "action/PickPlace.action"
  "action/ExecuteTask.action"
  "action/GraspObject.action"
  "action/ExecuteSkill.action"
)

ament_package()