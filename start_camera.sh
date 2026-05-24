#!/usr/bin/env bash
# 一键启动 Zenoh 路由 + Orbbec 相机（不含 2D/3D 感知节点）
# 用法:
#   CAMERA_MOUNT=head ./start_camera.sh
#   CAMERA_SN=CPC7B53000D9 ./start_camera.sh
# 关闭: ./stop_camera.sh

set -eo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "$ROOT/camera_mount_env.inc.sh"

CAMERA_WS="${CAMERA_WS:-$ROOT/camera_ros2_ws}"
CAMERA_SN="${CAMERA_SN:-CPC7B53000D9}"

LOG_DIR="$ROOT/log"
RUN_ID="$(date +%Y%m%d_%H%M%S)"
RUN_LOG_DIR="$LOG_DIR/$RUN_ID/camera"
mkdir -p "$RUN_LOG_DIR"

echo "[start_camera] CAMERA_MOUNT=$CAMERA_MOUNT CAMERA_NAMESPACE=$CAMERA_NAMESPACE SN=$CAMERA_SN"
echo "[start_camera] log: $RUN_LOG_DIR"

unset LD_LIBRARY_PATH
export RMW_IMPLEMENTATION="${RMW_IMPLEMENTATION:-rmw_zenoh_cpp}"

nohup bash -c "export RMW_IMPLEMENTATION=\"${RMW_IMPLEMENTATION}\" && source /opt/ros/jazzy/setup.bash && ros2 run rmw_zenoh_cpp rmw_zenohd" >"$RUN_LOG_DIR/zenoh.log" 2>&1 &
echo $! >"$LOG_DIR/camera_zenoh.pid"
sleep 1

nohup bash -c "export RMW_IMPLEMENTATION=\"${RMW_IMPLEMENTATION}\" && source /opt/ros/jazzy/setup.bash && source \"$CAMERA_WS/install/setup.bash\" && ros2 launch orbbec_camera ${ORBBEC_CAMERA_LAUNCH} serial_number:=$CAMERA_SN depth_registration:=true enable_colored_point_cloud:=true" >"$RUN_LOG_DIR/camera.log" 2>&1 &
echo $! >"$LOG_DIR/camera_launch.pid"

echo "[start_camera] done. 相机与路由已在后台运行。"
echo "停止: $ROOT/stop_camera.sh"
echo "日志: tail -f \"$RUN_LOG_DIR/camera.log\""
