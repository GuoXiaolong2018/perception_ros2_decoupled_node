import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    pkg_share = get_package_share_directory("yoloe_segmentation")
    default_params = os.path.join(pkg_share, "config", "yoloe_segmentation_params.yaml")
    camera_ns = os.environ.get("CAMERA_NAMESPACE", "camera_head")

    params_file_arg = DeclareLaunchArgument(
        "params_file",
        default_value=default_params,
        description="YOLOE 分割节点参数文件",
    )

    segmentation_node = Node(
        package="yoloe_segmentation",
        executable="yoloe_segmentation_node.py",
        name="yoloe_segmentation",
        output="screen",
        parameters=[
            LaunchConfiguration("params_file"),
            {"camera_namespace": camera_ns},
        ],
    )

    return LaunchDescription([params_file_arg, segmentation_node])
