cmake_minimum_required(VERSION 3.8)
project(yolo_detection)

find_package(ament_cmake REQUIRED)

execute_process(COMMAND chmod +x "${CMAKE_CURRENT_SOURCE_DIR}/scripts/yolo_detector_2d_node.py")

install(PROGRAMS
  scripts/yolo_detector_2d_node.py
  DESTINATION lib/${PROJECT_NAME}
)

install(DIRECTORY
  launch
  rviz
  config
  DESTINATION share/${PROJECT_NAME}
)

install(DIRECTORY
  models
  DESTINATION share/${PROJECT_NAME}
)

ament_package()
