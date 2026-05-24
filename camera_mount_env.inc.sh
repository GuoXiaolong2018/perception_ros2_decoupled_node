#!/usr/bin/env bash
# 由 start_camera.sh、start_perception_stack.sh 等 source（旧脚本见 scripts/legacy/）。
# 切换安装位置时只需设置 CAMERA_MOUNT（或显式设置 CAMERA_NAMESPACE / ORBBEC_CAMERA_LAUNCH）。
#
# CAMERA_MOUNT: head | breast | left_wrist | right_wrist
# CAMERA_SN:     Orbbec 序列号（不同机身可能不同，自行 export）
# CAMERA_WS:     相机功能包所在 colcon 工作空间（默认 <项目根>/camera_ros2_ws）

CAMERA_MOUNT="${CAMERA_MOUNT:-head}"
case "${CAMERA_MOUNT}" in
  head)
    : "${CAMERA_NAMESPACE:=camera_head}"
    : "${ORBBEC_CAMERA_LAUNCH:=gemini_330_series_head.launch.py}"
    ;;
  breast)
    : "${CAMERA_NAMESPACE:=camera_breast}"
    : "${ORBBEC_CAMERA_LAUNCH:=gemini_330_series_breast.launch.py}"
    ;;
  left_wrist)
    : "${CAMERA_NAMESPACE:=camera_left_wrist}"
    : "${ORBBEC_CAMERA_LAUNCH:=gemini_330_series_left_wrist.launch.py}"
    ;;
  right_wrist)
    : "${CAMERA_NAMESPACE:=camera_right_wrist}"
    : "${ORBBEC_CAMERA_LAUNCH:=gemini_330_series_right_wrist.launch.py}"
    ;;
  *)
    echo "[camera_mount_env] 未知 CAMERA_MOUNT=${CAMERA_MOUNT}（可选: head|breast|left_wrist|right_wrist）" >&2
    exit 1
    ;;
esac
export CAMERA_NAMESPACE ORBBEC_CAMERA_LAUNCH
