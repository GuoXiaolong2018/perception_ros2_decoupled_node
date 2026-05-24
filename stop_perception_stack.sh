#!/usr/bin/env bash
# 一键停止统一感知流水线（不含相机与 Zenoh 路由）
# 用法: ./stop_perception_stack.sh

set -eo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$ROOT/log"

echo "[stop_perception_stack] Step 1/3: graceful stop..."

for pidfile in perception_object_pose.pid perception_detections_to_base.pid perception_stack_rviz.pid perception_base_tf.pid; do
  if [[ -f "$LOG_DIR/$pidfile" ]]; then
    pid=$(cat "$LOG_DIR/$pidfile" 2>/dev/null || true)
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      kill -INT "$pid" 2>/dev/null || true
    fi
    rm -f "$LOG_DIR/$pidfile"
  fi
done

pkill -INT -f "ros2 launch perception_object_pose " 2>/dev/null || true
pkill -INT -f "ros2 launch perception_detections_to_base " 2>/dev/null || true
pkill -INT -f "ros2 launch perception_2d " 2>/dev/null || true
pkill -INT -f "yolo_object_pose_node.py" 2>/dev/null || true
pkill -INT -f "yolo_object_pose_impl.py" 2>/dev/null || true
pkill -INT -f "object_pose_json_to_msg_node.py" 2>/dev/null || true
pkill -INT -f "detections_to_base_node.py" 2>/dev/null || true
pkill -INT -f "detections_to_base_json_to_markers_node.py" 2>/dev/null || true
pkill -INT -f "pose_estimates_to_markers_node.py" 2>/dev/null || true
pkill -INT -f "yoloe_segmentation_node.py" 2>/dev/null || true
pkill -INT -f "yolo_detector_2d_node.py" 2>/dev/null || true
pkill -INT -f "rviz2 -d .*perception_stack" 2>/dev/null || true
pkill -INT -f "static_transform_publisher.*frame-id base" 2>/dev/null || true
pkill -INT -f "static_transform_publisher --frame-id base" 2>/dev/null || true

sleep 2

echo "[stop_perception_stack] Step 2/3: force kill..."
pkill -9 -f "ros2 launch perception_object_pose " 2>/dev/null || true
pkill -9 -f "ros2 launch perception_detections_to_base " 2>/dev/null || true
pkill -9 -f "ros2 launch perception_2d " 2>/dev/null || true
pkill -9 -f "yolo_object_pose_node.py" 2>/dev/null || true
pkill -9 -f "object_pose_json_to_msg_node.py" 2>/dev/null || true
pkill -9 -f "detections_to_base_node.py" 2>/dev/null || true
pkill -9 -f "detections_to_base_json_to_markers_node.py" 2>/dev/null || true
pkill -9 -f "pose_estimates_to_markers_node.py" 2>/dev/null || true
pkill -9 -f "yoloe_segmentation_node.py" 2>/dev/null || true
pkill -9 -f "yolo_detector_2d_node.py" 2>/dev/null || true
pkill -9 -f "rviz2" 2>/dev/null || true
pkill -9 -f "static_transform_publisher.*frame-id base" 2>/dev/null || true
pkill -9 -f "static_transform_publisher --frame-id base" 2>/dev/null || true

echo "[stop_perception_stack] Step 3/3: check..."
PATTERN="[p]erception_object_pose|[p]erception_2d|[y]oloe_segmentation|[y]olo_detector_2d|[d]etections_to_base|[o]bject_pose_json|[p]ose_estimates_to_markers|[r]viz2.*perception"
FILTER_OUT='cursorsandbox|/cursor/resources'
if ps -ef | grep -Ei "$PATTERN" | grep -Ev "$FILTER_OUT" | grep -q .; then
  echo "[stop_perception_stack] Warning: possible leftovers:"
  ps -ef | grep -Ei "$PATTERN" | grep -Ev "$FILTER_OUT" || true
else
  echo "[stop_perception_stack] OK: no perception stack leftovers."
fi

echo "[stop_perception_stack] Done."
