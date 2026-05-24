#!/usr/bin/env bash
# 在新感知流水线下运行 demo/ 订阅脚本（需已 source ROS 且节点在跑）
#
# 用法:
#   cd demo
#   ./run_demo_subscriber.sh perception_2d_topic_subscriber_demo.py --duration 15
#   ./run_demo_subscriber.sh perception_object_pose_topic_subscriber_demo.py --duration 15
#   ./run_demo_subscriber.sh perception_detections_to_base_topic_subscriber_demo.py --duration 15

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PY="${UNITREE_PYTHON:-python3.12}"
WS_SETUP="$ROOT/ros2_ws/install/setup.bash"

if [[ $# -lt 1 ]]; then
  echo "用法: $0 <demo/ 下脚本名> [--duration N] [--jsonl path] [--topic ...]" >&2
  exit 1
fi

unset LD_LIBRARY_PATH
source /opt/ros/jazzy/setup.bash
if [[ ! -f "$WS_SETUP" ]]; then
  echo "错误: 未找到 $WS_SETUP" >&2
  echo "请先在本仓库根目录执行: ./build_perception_stack.sh" >&2
  exit 1
fi
# shellcheck source=/dev/null
source "$WS_SETUP"
export RMW_IMPLEMENTATION="${RMW_IMPLEMENTATION:-rmw_zenoh_cpp}"

exec "$PY" "$SCRIPT_DIR/$1" "${@:2}"
