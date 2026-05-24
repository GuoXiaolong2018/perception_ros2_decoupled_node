#!/usr/bin/env python3.12
"""
订阅 perception_detections_to_base 节点发布的基座系检测 JSON。

默认话题: /perception/detections_in_base（std_msgs/String）
消息体: {"frame_id": str, "count": int, "objects": [{"arm_base_xyz": [x,y,z], ...}, ...]}

Usage:
  source /opt/ros/jazzy/setup.bash
  source <项目>/ros2_ws/install/setup.bash
  export RMW_IMPLEMENTATION=rmw_zenoh_cpp
  python3.12 \\
    demo/new/perception_detections_to_base_topic_subscriber_demo.py

或: ./demo/new/run_demo_subscriber.sh perception_detections_to_base_topic_subscriber_demo.py --duration 15
"""

import argparse
import json
import os
from datetime import datetime

import rclpy
from rclpy._rclpy_pybind11 import RCLError
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy
from std_msgs.msg import String


def _now_str() -> str:
    return datetime.now().strftime("%H:%M:%S")


class PerceptionDetectionsToBaseSubscriberDemo(Node):
    def __init__(self, jsonl_path: str, topic: str):
        super().__init__("perception_detections_to_base_topic_subscriber_demo")

        reliable_qos = QoSProfile(
            depth=10,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.VOLATILE,
            history=HistoryPolicy.KEEP_LAST,
        )

        self._topic = topic
        self.last_msg_time = None
        self.msg_count = 0
        self._received_any = False
        self._heartbeat_ticks = 0

        os.makedirs(os.path.dirname(jsonl_path), exist_ok=True)
        self.jsonl_fp = open(jsonl_path, "w", encoding="utf-8", buffering=1)

        self.create_subscription(String, topic, self.on_detections_in_base, reliable_qos)
        self.create_timer(3.0, self.print_heartbeat)

        self.get_logger().info("perception_detections_to_base 订阅演示已启动")
        self.get_logger().info(f"订阅话题: {topic}")
        self.get_logger().info(f"JSONL: {jsonl_path}")
        self.get_logger().info(
            f"RMW={os.environ.get('RMW_IMPLEMENTATION', '')} "
            f"ROS_DOMAIN_ID={os.environ.get('ROS_DOMAIN_ID', '<unset>')}"
        )

    def _write_event_jsonl(self, payload: dict):
        self._received_any = True
        row = {"ts": _now_str(), "topic": self._topic, "payload": payload}
        self.jsonl_fp.write(json.dumps(row, ensure_ascii=False) + "\n")

    def on_detections_in_base(self, msg: String):
        self.last_msg_time = _now_str()
        self.msg_count += 1
        raw = msg.data if msg.data else ""
        if not raw.strip():
            self.get_logger().warn("[detections_in_base] 空字符串")
            self._write_event_jsonl({"error": "empty_data"})
            return

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            self.get_logger().error(f"[detections_in_base] JSON 解析失败: {exc}")
            self._write_event_jsonl({"error": "json_decode", "raw_preview": raw[:200]})
            return

        count = data.get("count")
        objects = data.get("objects")
        if not isinstance(count, int) or not isinstance(objects, list):
            self.get_logger().error(f"[detections_in_base] schema 异常 keys={list(data.keys())}")
            self._write_event_jsonl({"error": "schema", "parsed": data})
            return

        preview = []
        for obj in objects[:5]:
            if isinstance(obj, dict):
                xyz = obj.get("arm_base_xyz")
                if isinstance(xyz, (list, tuple)) and len(xyz) >= 3:
                    preview.append(
                        f"xyz=({float(xyz[0]):.3f},{float(xyz[1]):.3f},{float(xyz[2]):.3f})"
                    )
                    continue
            preview.append(str(obj)[:80])

        self.get_logger().info(
            f"[detections_in_base] #{self.msg_count} count={count} preview={preview}"
        )
        self._write_event_jsonl(
            {
                "msg_type": "std_msgs/String",
                "json_schema": "perception_detections_in_base",
                "frame_id": data.get("frame_id"),
                "count": count,
                "objects": objects,
            }
        )

    def print_heartbeat(self):
        self._heartbeat_ticks += 1
        self.get_logger().info(
            f"heartbeat | topic={self._topic} last={self.last_msg_time} total={self.msg_count}"
        )
        if not self._received_any and self._heartbeat_ticks >= 2:
            self.get_logger().warning(
                f"仍未收到消息。请确认已运行 start_perception_stack.sh ob，"
                f"且话题为 {self._topic}；Zenoh 与 rmw_zenohd 已启动。"
            )


def main():
    parser = argparse.ArgumentParser(description="订阅 /perception/detections_in_base 并写入 JSONL")
    parser.add_argument(
        "--topic",
        default="/perception/detections_in_base",
        help="std_msgs/String JSON 话题",
    )
    parser.add_argument(
        "--jsonl",
        default="",
        help="输出 JSONL 路径（默认 demo/new/perception_detections_in_base_events.jsonl）",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=0.0,
        help="运行秒数，0 表示一直运行直到 Ctrl+C",
    )
    args = parser.parse_args()

    demo_dir = os.path.dirname(os.path.abspath(__file__))
    jsonl_path = args.jsonl or os.path.join(demo_dir, "perception_detections_in_base_events.jsonl")

    os.environ.setdefault("RMW_IMPLEMENTATION", "rmw_zenoh_cpp")
    rclpy.init()
    node = PerceptionDetectionsToBaseSubscriberDemo(jsonl_path, args.topic)
    executor = MultiThreadedExecutor()
    executor.add_node(node)

    def _spin_once():
        executor.spin_once(timeout_sec=0.1)

    try:
        if args.duration > 0:
            import time

            end = time.time() + args.duration
            while rclpy.ok() and time.time() < end:
                _spin_once()
        else:
            executor.spin()
    except (KeyboardInterrupt, rclpy.executors.ExternalShutdownException, RCLError):
        pass
    finally:
        executor.shutdown()
        node.jsonl_fp.close()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
        print(f"[done] received={node.msg_count} jsonl={jsonl_path}")


if __name__ == "__main__":
    main()
