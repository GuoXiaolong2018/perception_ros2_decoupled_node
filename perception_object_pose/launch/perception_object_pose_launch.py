import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    pkg_share = get_package_share_directory("perception_object_pose")
    default_params_file = os.path.join(pkg_share, "config", "object_pose_params.yaml")
    camera_ns = os.environ.get("CAMERA_NAMESPACE", "camera_head")

    params_file_arg = DeclareLaunchArgument(
        "params_file",
        default_value=default_params_file,
        description="物体位姿参数文件",
    )
    bringup_2d_arg = DeclareLaunchArgument(
        "bringup_2d",
        default_value="true",
        description="若为 true，在本 launch 内同时启动 perception_2d；"
        "多段流水线时由 start 脚本传 bringup_2d:=false 避免重复 2D。",
    )
    perception_backend_arg = DeclareLaunchArgument(
        "perception_backend",
        default_value="yoloe",
        description="bringup_2d 为 true 时使用的 2D 后端：yolo | yoloe",
    )

    perception_2d_share = get_package_share_directory("perception_2d")
    perception_2d_launch = os.path.join(
        perception_2d_share, "launch", "perception_2d_launch.py"
    )
    perception_2d_include = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(perception_2d_launch),
        condition=IfCondition(LaunchConfiguration("bringup_2d")),
        launch_arguments=[
            ("backend", LaunchConfiguration("perception_backend")),
        ],
    )

    detector = Node(
        package="perception_object_pose",
        executable="yolo_object_pose_node.py",
        name="perception_object_pose",
        output="screen",
        parameters=[
            LaunchConfiguration("params_file"),
            {"camera_namespace": camera_ns},
        ],
        remappings=[
            ("/middles_yolo_service", "/perception_object/middles_yolo_service"),
            ("/middlewareMessage_topic", "/perception_object/middlewareMessage_topic"),
        ],
    )

    bridge = Node(
        package="perception_object_pose",
        executable="object_pose_json_to_msg_node.py",
        name="object_pose_json_to_msg",
        output="screen",
        parameters=[
            {
                "json_topic": "/perception_object/poses_json",
                "pose_topic": "/perception_object/pose_estimates",
            }
        ],
    )

    viz = Node(
        package="perception_pose_visualization",
        executable="pose_estimates_to_markers_node.py",
        name="object_pose_visualizer",
        output="screen",
        parameters=[
            {
                "input_topic": "/perception_object/pose_estimates",
                "output_topic": "/perception_object/pose_markers",
                "namespace": "perception_object_pose_axes",
                "axis_length_m": 0.08,
                "marker_lifetime_sec": 1.2,
            }
        ],
    )

    return LaunchDescription(
        [
            bringup_2d_arg,
            perception_backend_arg,
            params_file_arg,
            perception_2d_include,
            detector,
            bridge,
            viz,
        ]
    )
