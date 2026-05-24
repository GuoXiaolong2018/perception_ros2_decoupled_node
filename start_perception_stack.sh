#!/usr/bin/env bash
# 一键启动统一感知流水线（假定相机与 Zenoh 路由已启动）
# 用法:
#   ./start_perception_stack.sh [pose_variant] [options]
#
# pose_variant（默认 object_base，别名 ob）:
#   object_base | ob   — 物体位姿 + 基座系变换（默认）
#   object             — 仅物体位姿
#
# 环境变量 / 选项:
#   PERCEPTION_2D_BACKEND=yoloe|yolo     2D 算法（默认 yoloe）
#   CAMERA_MOUNT=head|breast|left_wrist|right_wrist
#   CAMERA_NAMESPACE=...                 显式覆盖相机命名空间
#   NO_RVIZ=1                            不启动 RViz
#   PUBLISH_BASE_TF=1                    发布 base -> 相机光学系 静态 TF（默认 0，关闭）
#
# 命令行开关:
#   --base-tf                            等同 PUBLISH_BASE_TF=1（供 RViz「Base Frame Detections」）
#   --no-rviz                            等同 NO_RVIZ=1
#
# 示例:
#   CAMERA_MOUNT=head ./start_perception_stack.sh ob
#   CAMERA_MOUNT=head ./start_perception_stack.sh ob --base-tf
#   PUBLISH_BASE_TF=1 ./start_perception_stack.sh ob
#   PERCEPTION_2D_BACKEND=yolo ./start_perception_stack.sh object

set -eo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WS="$ROOT/ros2_ws"
# shellcheck source=/dev/null
source "$ROOT/camera_mount_env.inc.sh"

VARIANT="object_base"
PERCEPTION_2D_BACKEND="${PERCEPTION_2D_BACKEND:-yoloe}"
NO_RVIZ="${NO_RVIZ:-0}"
PUBLISH_BASE_TF="${PUBLISH_BASE_TF:-0}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --base-tf)
      PUBLISH_BASE_TF=1
      ;;
    --no-rviz)
      NO_RVIZ=1
      ;;
    -h | --help)
      sed -n '2,20p' "$0"
      exit 0
      ;;
    object | object_base | ob)
      VARIANT="$1"
      ;;
    *)
      echo "[start_perception_stack] 未知参数: $1（变体: object|object_base|ob；开关: --base-tf|--no-rviz）" >&2
      exit 1
      ;;
  esac
  shift
done

LOG_DIR="$ROOT/log"
RUN_ID="$(date +%Y%m%d_%H%M%S)"
RUN_LOG_DIR="$LOG_DIR/$RUN_ID/perception_${VARIANT}_${PERCEPTION_2D_BACKEND}"
mkdir -p "$RUN_LOG_DIR"

echo "[start_perception_stack] variant=$VARIANT backend=$PERCEPTION_2D_BACKEND publish_base_tf=$PUBLISH_BASE_TF"
echo "[start_perception_stack] CAMERA_NAMESPACE=$CAMERA_NAMESPACE"
echo "[start_perception_stack] log: $RUN_LOG_DIR"

unset LD_LIBRARY_PATH
export RMW_IMPLEMENTATION="${RMW_IMPLEMENTATION:-rmw_zenoh_cpp}"
export CAMERA_NAMESPACE
export PERCEPTION_2D_BACKEND

# 确保工作空间链接
for pkg in yolo_detection yoloe_segmentation perception_2d perception_pose_visualization perception_object_pose perception_detections_to_base; do
  mkdir -p "$WS/src"
  ln -sfn "$ROOT/$pkg" "$WS/src/$pkg"
done

source /opt/ros/jazzy/setup.bash
if [[ ! -f "$WS/install/perception_2d/share/perception_2d/package.xml" ]]; then
  echo "[start_perception_stack] 未找到 install，请先运行: $ROOT/build_perception_stack.sh"
  exit 1
fi
source "$WS/install/setup.bash"

_render_rviz() {
  local src out
  src="$(ros2 pkg prefix perception_2d)/share/perception_2d/rviz/perception_stack_overlay.rviz"
  out="$RUN_LOG_DIR/perception_stack__${CAMERA_NAMESPACE}.rviz"
  sed "s/camera_head/${CAMERA_NAMESPACE}/g" "$src" >"$out"
  echo "$out"
}

PID_DIR="$ROOT/log"
mkdir -p "$PID_DIR"
ln -sfn "$RUN_LOG_DIR" "$PID_DIR/perception_stack_latest"

_launch_object_pose() {
  local extra="${1:-}"
  nohup bash -c "export RMW_IMPLEMENTATION=\"${RMW_IMPLEMENTATION}\" && export CAMERA_NAMESPACE=\"${CAMERA_NAMESPACE}\" && export PERCEPTION_2D_BACKEND=\"${PERCEPTION_2D_BACKEND}\" && source /opt/ros/jazzy/setup.bash && source \"$WS/install/setup.bash\" && ros2 launch perception_object_pose perception_object_pose_launch.py perception_backend:=${PERCEPTION_2D_BACKEND} ${extra}" >"$RUN_LOG_DIR/object_pose.log" 2>&1 &
  echo $! >"$PID_DIR/perception_object_pose.pid"
}

_start_rviz() {
  local cfg
  cfg="$(_render_rviz)"
  nohup bash -c "export RMW_IMPLEMENTATION=\"${RMW_IMPLEMENTATION}\" && export CAMERA_NAMESPACE=\"${CAMERA_NAMESPACE}\" && source /opt/ros/jazzy/setup.bash && source \"$WS/install/setup.bash\" && rviz2 -d \"$cfg\"" >"$RUN_LOG_DIR/rviz.log" 2>&1 &
  echo $! >"$PID_DIR/perception_stack_rviz.pid"
}

# 与 perception_detections_to_base 中 T_BASE_CAMERA 一致（base <- 相机光学系）
_start_base_tf() {
  local child_frame="${CAMERA_NAMESPACE}_color_optical_frame"
  nohup bash -c "export RMW_IMPLEMENTATION=\"${RMW_IMPLEMENTATION}\" && source /opt/ros/jazzy/setup.bash && ros2 run tf2_ros static_transform_publisher \
    --x 0.1029269369013247063 \
    --y 0.0276960887323011 \
    --z 0.2651688501965433 \
    --roll -2.37680747 \
    --pitch -0.00368669 \
    --yaw -1.56544466 \
    --frame-id base \
    --child-frame-id ${child_frame}" >"$RUN_LOG_DIR/base_tf.log" 2>&1 &
  echo $! >"$PID_DIR/perception_base_tf.pid"
  echo "[start_perception_stack] base TF: base -> ${child_frame}（见 $RUN_LOG_DIR/base_tf.log）"
}

case "$VARIANT" in
  object)
    _launch_object_pose
    sleep 2
    ;;
  object_base | ob)
    _launch_object_pose
    sleep 2
    nohup bash -c "export RMW_IMPLEMENTATION=\"${RMW_IMPLEMENTATION}\" && export CAMERA_NAMESPACE=\"${CAMERA_NAMESPACE}\" && export PERCEPTION_2D_BACKEND=\"${PERCEPTION_2D_BACKEND}\" && source /opt/ros/jazzy/setup.bash && source \"$WS/install/setup.bash\" && ros2 launch perception_detections_to_base perception_detections_to_base_launch.py bringup_2d:=false perception_backend:=${PERCEPTION_2D_BACKEND}" >"$RUN_LOG_DIR/detections_to_base.log" 2>&1 &
    echo $! >"$PID_DIR/perception_detections_to_base.pid"
    ;;
  *)
    echo "未知 pose_variant: $VARIANT（可选: object | object_base | ob）" >&2
    exit 1
    ;;
esac

if [[ "$PUBLISH_BASE_TF" == "1" ]]; then
  _start_base_tf
  sleep 1
fi

if [[ "$NO_RVIZ" != "1" ]]; then
  sleep 1
  _start_rviz
fi

echo "[start_perception_stack] done."
echo "检查: source \"$WS/install/setup.bash\" && ros2 node list | grep -E 'perception|yoloe|yolo_detector'"
echo "停止: $ROOT/stop_perception_stack.sh"
echo "日志: tail -f \"$RUN_LOG_DIR\"/*.log"
