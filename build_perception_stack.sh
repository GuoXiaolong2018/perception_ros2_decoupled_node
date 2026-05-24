#!/usr/bin/env bash
# 一键编译统一感知流水线相关 ROS2 包
# 用法: ./build_perception_stack.sh

set -eo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WS="$ROOT/ros2_ws"
PY_EXEC="/usr/bin/python3.12"

_prune_missing_ws_install_paths() {
  local var="$1"
  local val="${!var:-}"
  [[ -z "$val" ]] && return 0
  local out="" p
  while IFS= read -r -d '' p; do
    [[ -z "$p" ]] && continue
    if [[ "$p" == "$WS/install/"* ]] && [[ ! -d "$p" ]]; then
      continue
    fi
    out="${out:+$out:}$p"
  done < <(printf '%s\0' "${val//:/$'\0'}")
  export "${var}=${out}"
}
_prune_missing_ws_install_paths AMENT_PREFIX_PATH
_prune_missing_ws_install_paths CMAKE_PREFIX_PATH

ensure_link() {
  local pkg="$1"
  mkdir -p "$WS/src"
  ln -sfn "$ROOT/$pkg" "$WS/src/$pkg"
}

for pkg in \
  yolo_detection \
  yoloe_segmentation \
  perception_2d \
  perception_pose_visualization \
  perception_object_pose \
  perception_detections_to_base; do
  ensure_link "$pkg"
done

source /opt/ros/jazzy/setup.bash
cd "$WS"

colcon build \
  --packages-select \
    yolo_detection \
    yoloe_segmentation \
    perception_2d \
    perception_pose_visualization \
    perception_object_pose \
    perception_detections_to_base \
  --symlink-install \
  --cmake-args -DPython3_EXECUTABLE="$PY_EXEC"

echo "[build_perception_stack] done."
