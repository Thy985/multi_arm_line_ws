cmake_minimum_required(VERSION 3.8)
project(multi_arm_moveit_config)

find_package(ament_cmake REQUIRED)

install(
  DIRECTORY config launch rviz scripts
  DESTINATION share/${PROJECT_NAME}
  USE_SOURCE_PERMISSIONS
)

ament_package()