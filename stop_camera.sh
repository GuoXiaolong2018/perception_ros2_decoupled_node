#!/usr/bin/env bash
# 一键停止 Orbbec 相机与 Zenoh 路由（与 start_camera.sh 配对）
# 用法:
#   ./stop_camera.sh
# 说明: 不停止感知栈节点；若需一并停止请再执行 ./stop_perception_stack.sh

set -eo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$ROOT/log"

_kill_pidfile() {
  local name="$1"
  local sig="${2:-INT}"
  local f="$LOG_DIR/$name"
  [[ -f "$f" ]] || return 0
  local pid
  pid=$(cat "$f" 2>/dev/null || true)
  if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
    kill "-$sig" "$pid" 2>/dev/null || true
  fi
  rm -f "$f"
}

echo "[stop_camera] Step 1/3: graceful stop (SIGINT)..."

_kill_pidfile "camera_launch.pid" INT
_kill_pidfile "camera_zenoh.pid" INT

pkill -INT -f "ros2 launch orbbec_camera" 2>/dev/null || true
pkill -INT -f "orbbec_camera" 2>/dev/null || true
pkill -INT -f "component_container" 2>/dev/null || true
pkill -INT -f "rmw_zenohd" 2>/dev/null || true

sleep 2

echo "[stop_camera] Step 2/3: force kill leftovers (SIGKILL)..."

_kill_pidfile "camera_launch.pid" 9
_kill_pidfile "camera_zenoh.pid" 9

pkill -9 -f "ros2 launch orbbec_camera" 2>/dev/null || true
pkill -9 -f "orbbec_camera" 2>/dev/null || true
pkill -9 -f "component_container" 2>/dev/null || true
pkill -9 -f "rmw_zenohd" 2>/dev/null || true

echo "[stop_camera] Step 3/3: check remaining processes..."
PATTERN="[r]mw_zenohd|[o]rbbec_camera|[c]omponent_container"
FILTER_OUT='cursorsandbox|/cursor/resources'
if ps -ef | grep -Ei "$PATTERN" | grep -Ev "$FILTER_OUT" | grep -q .; then
  echo "[stop_camera] Warning: possible leftovers (若 rmw_zenohd 仍在，可尝试: sudo pkill -INT -f rmw_zenohd):"
  ps -ef | grep -Ei "$PATTERN" | grep -Ev "$FILTER_OUT" || true
else
  echo "[stop_camera] OK: no camera / zenoh leftovers."
fi

echo "[stop_camera] Done."
