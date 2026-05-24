cmake_minimum_required(VERSION 3.8)
project(yoloe_segmentation)

find_package(ament_cmake REQUIRED)

execute_process(COMMAND chmod +x "${CMAKE_CURRENT_SOURCE_DIR}/scripts/yoloe_segmentation_node.py")

install(PROGRAMS
  scripts/yoloe_segmentation_node.py
  DESTINATION lib/${PROJECT_NAME}
)

install(DIRECTORY
  launch
  rviz
  config
  DESTINATION share/${PROJECT_NAME}
)

install(DIRECTORY
  yoloe_deploy
  DESTINATION share/${PROJECT_NAME}
)

ament_package()
