cmake_minimum_required(VERSION 3.8)
project(perception_pose_visualization)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)

execute_process(COMMAND chmod +x "${CMAKE_CURRENT_SOURCE_DIR}/scripts/pose_estimates_to_markers_node.py")
execute_process(COMMAND chmod +x "${CMAKE_CURRENT_SOURCE_DIR}/scripts/detections_to_base_json_to_markers_node.py")

install(PROGRAMS
  scripts/pose_estimates_to_markers_node.py
  scripts/detections_to_base_json_to_markers_node.py
  DESTINATION lib/${PROJECT_NAME}
)

install(DIRECTORY
  config
  DESTINATION share/${PROJECT_NAME}
)

ament_package()

