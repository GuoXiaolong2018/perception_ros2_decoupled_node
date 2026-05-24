import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    pkg_share = get_package_share_directory("yolo_detection")
    default_params = os.path.join(pkg_share, "config", "yolo_params.yaml")
    camera_ns = os.environ.get("CAMERA_NAMESPACE", "camera_head")

    params_file_arg = DeclareLaunchArgument(
        "params_file",
        default_value=default_params,
        description="YOLO 2D 参数文件",
    )

    detector = Node(
        package="yolo_detection",
        executable="yolo_detector_2d_node.py",
        name="yolo_detector_2d",
        output="screen",
        parameters=[
            LaunchConfiguration("params_file"),
            {"camera_namespace": camera_ns},
        ],
        remappings=[
            ("/middles_yolo_service", "/yolo_detector/middles_yolo_service"),
            ("/middlewareMessage_topic", "/yolo_detector/middlewareMessage_topic"),
        ],
    )

    return LaunchDescription([params_file_arg, detector])
