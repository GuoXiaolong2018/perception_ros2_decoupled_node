import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    pkg_share = get_package_share_directory("perception_detections_to_base")
    viz_share = get_package_share_directory("perception_pose_visualization")
    default_params = os.path.join(pkg_share, "config", "detections_to_base_params.yaml")
    default_markers_params = os.path.join(
        viz_share, "config", "detections_to_base_markers_params.yaml"
    )

    params_file_arg = DeclareLaunchArgument(
        "params_file",
        default_value=default_params,
        description="detections_to_base 参数文件",
    )
    bringup_2d_arg = DeclareLaunchArgument(
        "bringup_2d",
        default_value="false",
        description="若为 true，在本 launch 内同时启动 perception_2d。"
        "默认 false：假定已由 perception_object_pose 提供 2D+深度。",
    )
    perception_backend_arg = DeclareLaunchArgument(
        "perception_backend",
        default_value="yoloe",
        description="bringup_2d 为 true 时使用的 2D 后端",
    )
    start_markers_arg = DeclareLaunchArgument(
        "start_markers",
        default_value="true",
        description="启动 JSON→MarkerArray 可视化节点",
    )
    markers_params_arg = DeclareLaunchArgument(
        "markers_params_file",
        default_value=default_markers_params,
        description="Marker 参数文件",
    )
    input_topic_arg = DeclareLaunchArgument(
        "detections_input_topic",
        default_value="/perception_object/detections",
        description="Detection2DArray 输入（默认来自 perception_object_pose）",
    )
    output_topic_arg = DeclareLaunchArgument(
        "detections_output_topic",
        default_value="/perception/detections_in_base",
        description="std_msgs/String JSON 输出",
    )
    markers_json_topic_arg = DeclareLaunchArgument(
        "markers_json_topic",
        default_value="/perception/detections_in_base",
        description="JSON→Marker 订阅话题",
    )
    markers_output_topic_arg = DeclareLaunchArgument(
        "markers_output_topic",
        default_value="/perception/detections_in_base_markers",
        description="MarkerArray 输出",
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

    to_base = Node(
        package="perception_detections_to_base",
        executable="detections_to_base_node.py",
        name="detections_to_base",
        output="screen",
        parameters=[
            LaunchConfiguration("params_file"),
            {
                "input_topic": ParameterValue(
                    LaunchConfiguration("detections_input_topic"), value_type=str
                ),
                "output_topic": ParameterValue(
                    LaunchConfiguration("detections_output_topic"), value_type=str
                ),
            },
        ],
    )

    markers = Node(
        package="perception_pose_visualization",
        executable="detections_to_base_json_to_markers_node.py",
        name="detections_to_base_json_to_markers",
        output="screen",
        parameters=[
            LaunchConfiguration("markers_params_file"),
            {
                "json_topic": ParameterValue(
                    LaunchConfiguration("markers_json_topic"), value_type=str
                ),
                "markers_topic": ParameterValue(
                    LaunchConfiguration("markers_output_topic"), value_type=str
                ),
            },
        ],
        condition=IfCondition(LaunchConfiguration("start_markers")),
    )

    return LaunchDescription(
        [
            params_file_arg,
            bringup_2d_arg,
            perception_backend_arg,
            start_markers_arg,
            markers_params_arg,
            input_topic_arg,
            output_topic_arg,
            markers_json_topic_arg,
            markers_output_topic_arg,
            perception_2d_include,
            to_base,
            markers,
        ]
    )
