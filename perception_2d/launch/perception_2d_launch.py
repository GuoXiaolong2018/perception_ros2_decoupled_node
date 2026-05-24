"""统一 2D 感知 launch：backend=yolo|yoloe，发布 /perception_2d/*。"""
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def _launch_backend(context, *args, **kwargs):
    backend = LaunchConfiguration("backend").perform(context).strip().lower()
    pkg_share = get_package_share_directory("perception_2d")
    camera_ns = os.environ.get("CAMERA_NAMESPACE", "camera_head")

    if backend == "yolo":
        params_file = os.path.join(pkg_share, "config", "perception_2d_yolo_params.yaml")
        return [
            Node(
                package="yolo_detection",
                executable="yolo_detector_2d_node.py",
                name="yolo_detector_2d",
                output="screen",
                parameters=[params_file, {"camera_namespace": camera_ns}],
                remappings=[
                    ("/middles_yolo_service", "/perception_2d/middles_yolo_service"),
                    ("/middlewareMessage_topic", "/perception_2d/middlewareMessage_topic"),
                ],
            )
        ]

    if backend in ("yoloe", "yolo_e"):
        params_file = os.path.join(pkg_share, "config", "perception_2d_yoloe_params.yaml")
        return [
            Node(
                package="yoloe_segmentation",
                executable="yoloe_segmentation_node.py",
                name="yoloe_segmentation",
                output="screen",
                parameters=[params_file, {"camera_namespace": camera_ns}],
                remappings=[
                    ("/middles_yolo_service", "/perception_2d/middles_yolo_service"),
                    ("/middlewareMessage_topic", "/perception_2d/middlewareMessage_topic"),
                ],
            )
        ]

    raise RuntimeError(f"未知 perception backend: {backend!r}（可选: yolo | yoloe）")


def generate_launch_description():
    backend_arg = DeclareLaunchArgument(
        "backend",
        default_value="yoloe",
        description="2D 感知后端：yolo（闭集检测）| yoloe（少样本分割，默认）",
    )

    return LaunchDescription([backend_arg, OpaqueFunction(function=_launch_backend)])
