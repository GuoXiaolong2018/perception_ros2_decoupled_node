cmake_minimum_required(VERSION 3.8)
project(perception_object_pose)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)

execute_process(COMMAND chmod +x "${CMAKE_CURRENT_SOURCE_DIR}/scripts/object_pose_json_to_msg_node.py")
execute_process(COMMAND chmod +x "${CMAKE_CURRENT_SOURCE_DIR}/scripts/yolo_object_pose_node.py")
execute_process(COMMAND chmod +x "${CMAKE_CURRENT_SOURCE_DIR}/scripts/yolo_object_pose_impl.py")

install(PROGRAMS
  scripts/yolo_object_pose_node.py
  scripts/yolo_object_pose_impl.py
  scripts/object_pose_json_to_msg_node.py
  DESTINATION lib/${PROJECT_NAME}
)

install(DIRECTORY
  launch
  rviz
  config
  DESTINATION share/${PROJECT_NAME}
)

ament_package()
