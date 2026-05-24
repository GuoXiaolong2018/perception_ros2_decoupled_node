import os
import subprocess

from launch import LaunchDescription
from launch.actions import ExecuteProcess, GroupAction, IncludeLaunchDescription, LogInfo, TimerAction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from ament_index_python.packages import get_package_share_directory


def is_zenohd_running():
    try:
        process_checks = (
            ['pgrep', '-x', 'rmw_zenohd'],
            ['pgrep', '-f', 'rmw_zenoh_cpp rmw_zenohd'],
        )
        for cmd in process_checks:
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if result.returncode == 0:
                return True
    except FileNotFoundError:
        return False
    return False


def generate_launch_description():
    # Include launch files
    package_dir = get_package_share_directory('orbbec_camera')
    launch_file_dir = os.path.join(package_dir, 'launch')
    launch1_include = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(launch_file_dir, 'gemini_330_series_head.launch.py')
        ),
        launch_arguments={
            # 'camera_name': 'camera_head',
            # 'serial_number': 'CPC7B5300068',
            'device_num': '3',
            'manage_rmw_zenohd': 'false',
            'sync_mode': 'standalone',
            'enable_left_ir': 'false',
            'enable_right_ir': 'false',
            'log_level': 'none',
            'log_file_name': 'camera_head.log',
            # 'color_width': '1280',
            # 'color_height': '720',
            # 'color_fps': '30',
            # 'depth_width': '1280',
            # 'depth_height': '720',
            # 'depth_fps': '30',
            # 'uvc_backend': 'v4l2',
            # 'enable_point_cloud': 'false',
            # 'color_format': 'RGB',

        }.items()
    )

    launch2_include = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(launch_file_dir, 'gemini_330_series_left_wrist.launch.py')
        ),
        launch_arguments={
            # 'camera_name': 'camera_breast',
            # 'serial_number': 'CP9365300039',
            'device_num': '3',
            'manage_rmw_zenohd': 'false',
            'sync_mode': 'standalone',
            'enable_left_ir': 'false',
            'enable_right_ir': 'false',
            'log_level': 'none',
            'log_file_name': 'camera_left_wrist.log',
            # 'color_width': '1280',
            # 'color_height': '720',
            # 'color_fps': '30',
            # 'depth_width': '1280',
            # 'depth_height': '720',
            # 'depth_fps': '30',
            # 'uvc_backend': 'v4l2',
            # 'enable_point_cloud': 'false',
            # 'color_format': 'RGB',
        }.items()
    )
    launch3_include = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(launch_file_dir, 'gemini_330_series_right_wrist.launch.py')
        ),
        launch_arguments={
            # 'camera_name': 'camera_3',
            # 'serial_number': 'CP93653000EB',
            'device_num': '3',
            'manage_rmw_zenohd': 'false',
            'sync_mode': 'standalone',
            'enable_left_ir': 'false',
            'enable_right_ir': 'false',
            'log_level': 'none',
            'log_file_name': 'camera_right_wrist.log',
            # 'color_width': '1280',
            # 'color_height': '720',
            # 'color_fps': '30',
            # 'depth_width': '1280',
            # 'depth_height': '720',
            # 'depth_fps': '30',
            # 'uvc_backend': 'v4l2',
            # 'enable_point_cloud': 'false',
            # 'color_format': 'RGB',

        }.items()
    )

    # If you need more cameras, just add more launch_include here, and change the usb_port and device_num

    node_actions = [
        GroupAction([launch1_include]),
        GroupAction([launch2_include]),
        GroupAction([launch3_include]),
    ]

    if os.environ.get('RMW_IMPLEMENTATION', '') != 'rmw_zenoh_cpp':
        return LaunchDescription(node_actions)

    if is_zenohd_running():
        return LaunchDescription([
            LogInfo(msg='Detected running rmw_zenohd, continuing camera launch.'),
            *node_actions,
        ])

    return LaunchDescription([
        LogInfo(msg='rmw_zenohd is not running, starting it before launching the camera.'),
        ExecuteProcess(
            cmd=['ros2', 'run', 'rmw_zenoh_cpp', 'rmw_zenohd'],
            output='screen',
        ),
        TimerAction(
            period=2.0,
            actions=node_actions,
        ),
    ])
