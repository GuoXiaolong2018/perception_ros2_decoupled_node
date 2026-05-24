#!/usr/bin/env python3.12
"""
订阅 perception_object_pose 管线相关话题（/perception_object/*）。

配套: CAMERA_MOUNT=head ./start_perception_stack.sh object|ob

Usage:
  ./demo/new/run_demo_subscriber.sh perception_object_pose_topic_subscriber_demo.py --duration 15
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
from sensor_msgs.msg import Image
from std_msgs.msg import String
from vision_msgs.msg import Detection2DArray
from visualization_msgs.msg import MarkerArray


def _now_str() -> str:
    return datetime.now().strftime("%H:%M:%S")


class PerceptionObjectPoseTopicSubscriberDemo(Node):
    def __init__(self, jsonl_path: str):
        super().__init__("perception_object_pose_topic_subscriber_demo")

        sensor_qos = QoSProfile(
            depth=10,
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE,
            history=HistoryPolicy.KEEP_LAST,
        )
        reliable_qos = QoSProfile(
            depth=10,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.VOLATILE,
            history=HistoryPolicy.KEEP_LAST,
        )

        self.last_detection_time = None
        self.last_debug_image_time = None
        self.last_marker_time = None
        self.last_middleware_time = None
        self.last_poses_json_time = None
        self.last_pose_estimates_time = None
        self.last_pose_markers_time = None
        self._received_any = False
        self._heartbeat_ticks = 0
        self._counts = {}

        os.makedirs(os.path.dirname(jsonl_path), exist_ok=True)
        self.jsonl_fp = open(jsonl_path, "w", encoding="utf-8", buffering=1)

        self.create_subscription(
            Detection2DArray,
            "/perception_object/detections",
            self.on_detection,
            sensor_qos,
        )
        self.create_subscription(
            Image, "/perception_object/debug_image", self.on_debug_image, reliable_qos
        )
        self.create_subscription(
            MarkerArray, "/perception_object/markers", self.on_marker, sensor_qos
        )
        self.create_subscription(
            String,
            "/perception_object/middlewareMessage_topic",
            self.on_middleware,
            reliable_qos,
        )
        self.create_subscription(
            String, "/perception_object/poses_json", self.on_poses_json, sensor_qos
        )
        self.create_subscription(
            String,
            "/perception_object/pose_estimates",
            self.on_pose_estimates,
            reliable_qos,
        )
        self.create_subscription(
            MarkerArray,
            "/perception_object/pose_markers",
            self.on_pose_markers,
            sensor_qos,
        )
        self.create_timer(3.0, self.print_heartbeat)

        self.get_logger().info("perception_object_pose 话题订阅演示已启动")
        self.get_logger().info("JSONL: " + jsonl_path)
        for t in (
            "/perception_object/detections",
            "/perception_object/debug_image",
            "/perception_object/markers",
            "/perception_object/poses_json",
            "/perception_object/pose_estimates",
            "/perception_object/pose_markers",
            "/perception_object/middlewareMessage_topic",
        ):
            self.get_logger().info(f"  subscribe: {t}")

    def _write_event_jsonl(self, topic: str, payload: dict):
        self._received_any = True
        self._counts[topic] = self._counts.get(topic, 0) + 1
        row = {"ts": _now_str(), "topic": topic, "payload": payload}
        self.jsonl_fp.write(json.dumps(row, ensure_ascii=False) + "\n")

    def on_detection(self, msg: Detection2DArray):
        self.last_detection_time = _now_str()
        detections = []
        for det in msg.detections:
            item = {
                "center_xy": [
                    float(det.bbox.center.position.x),
                    float(det.bbox.center.position.y),
                ],
                "size_wh": [float(det.bbox.size_x), float(det.bbox.size_y)],
            }
            if det.results:
                hyp = det.results[0].hypothesis
                pos = det.results[0].pose.pose.position
                item["class_id"] = hyp.class_id
                item["score"] = float(hyp.score)
                item["xyz"] = [float(pos.x), float(pos.y), float(pos.z)]
            detections.append(item)

        summary = []
        for d in detections[:3]:
            xyz = d.get("xyz") or [0, 0, 0]
            summary.append(
                f"{d.get('class_id')}(s={d.get('score', 0):.2f}) "
                f"xyz=({xyz[0]:.3f},{xyz[1]:.3f},{xyz[2]:.3f})"
            )
        self.get_logger().info(
            f"[detection] count={len(detections)} frame={msg.header.frame_id} top3={summary}"
        )
        self._write_event_jsonl(
            "/perception_object/detections",
            {
                "msg_type": "vision_msgs/Detection2DArray",
                "frame_id": msg.header.frame_id,
                "count": len(detections),
                "detections": detections,
            },
        )

    def on_debug_image(self, msg: Image):
        self.last_debug_image_time = _now_str()
        self.get_logger().info(
            f"[debug_image] {msg.width}x{msg.height} encoding={msg.encoding}"
        )
        self._write_event_jsonl(
            "/perception_object/debug_image",
            {
                "msg_type": "sensor_msgs/Image",
                "width": int(msg.width),
                "height": int(msg.height),
                "encoding": msg.encoding,
                "frame_id": msg.header.frame_id,
            },
        )

    def on_marker(self, msg: MarkerArray):
        self.last_marker_time = _now_str()
        self.get_logger().info(f"[markers] count={len(msg.markers)}")
        self._write_event_jsonl(
            "/perception_object/markers",
            {"msg_type": "visualization_msgs/MarkerArray", "count": len(msg.markers)},
        )

    def on_pose_markers(self, msg: MarkerArray):
        self.last_pose_markers_time = _now_str()
        self.get_logger().info(f"[pose_markers] count={len(msg.markers)}")
        self._write_event_jsonl(
            "/perception_object/pose_markers",
            {"msg_type": "visualization_msgs/MarkerArray", "count": len(msg.markers)},
        )

    def on_middleware(self, msg: String):
        self.last_middleware_time = _now_str()
        text = (msg.data or "").strip()
        if len(text) > 160:
            text = text[:160] + "..."
        self.get_logger().info(f"[middleware] {text}")
        self._write_event_jsonl(
            "/perception_object/middlewareMessage_topic",
            {"msg_type": "std_msgs/String", "text": msg.data},
        )

    def on_poses_json(self, msg: String):
        self.last_poses_json_time = _now_str()
        try:
            data = json.loads(msg.data)
        except json.JSONDecodeError:
            self.get_logger().warn("[poses_json] JSON 解析失败")
            self._write_event_jsonl(
                "/perception_object/poses_json",
                {"error": "json_decode", "raw_preview": (msg.data or "")[:200]},
            )
            return
        n = len(data.get("object_poses", []))
        self.get_logger().info(
            f"[poses_json] frame_id={data.get('frame_id', '')} object_poses={n}"
        )
        self._write_event_jsonl(
            "/perception_object/poses_json",
            {
                "msg_type": "std_msgs/String",
                "json_schema": "object_poses_json",
                "parsed": data,
            },
        )

    def on_pose_estimates(self, msg: String):
        self.last_pose_estimates_time = _now_str()
        try:
            event = json.loads(msg.data)
        except json.JSONDecodeError:
            self.get_logger().warn("[pose_estimates] JSON 解析失败")
            self._write_event_jsonl(
                "/perception_object/pose_estimates",
                {"error": "json_decode", "raw_preview": (msg.data or "")[:200]},
            )
            return
        payload = event.get("payload", event)
        poses = payload.get("poses", [])
        parts = []
        for p in poses[:3]:
            pos = p.get("position_xyz", [0.0, 0.0, 0.0])
            parts.append(
                f"{p.get('class_name', p.get('class_id', ''))} "
                f"pos=({float(pos[0]):.3f},{float(pos[1]):.3f},{float(pos[2]):.3f})"
            )
        self.get_logger().info(
            f"[pose_estimates] n={len(poses)} top3={parts}"
        )
        self._write_event_jsonl(
            "/perception_object/pose_estimates",
            {
                "msg_type": "std_msgs/String",
                "json_schema": "pose_estimates_wrapped",
                "parsed": event,
            },
        )

    def print_heartbeat(self):
        self._heartbeat_ticks += 1
        self.get_logger().info(
            "heartbeat | "
            f"det={self.last_detection_time} dbg={self.last_debug_image_time} "
            f"json={self.last_poses_json_time} counts={self._counts}"
        )
        if not self._received_any and self._heartbeat_ticks >= 2:
            self.get_logger().warning(
                "仍未收到消息。请确认 start_perception_stack.sh object|ob 已运行。"
            )


def main():
    parser = argparse.ArgumentParser(description="订阅 /perception_object/* 并写入 JSONL")
    parser.add_argument(
        "--jsonl",
        default="",
        help="输出 JSONL（默认 demo/new/perception_object_pose_events.jsonl）",
    )
    parser.add_argument("--duration", type=float, default=0.0, help="运行秒数，0=直到 Ctrl+C")
    args = parser.parse_args()

    demo_dir = os.path.dirname(os.path.abspath(__file__))
    jsonl_path = args.jsonl or os.path.join(demo_dir, "perception_object_pose_events.jsonl")

    os.environ.setdefault("RMW_IMPLEMENTATION", "rmw_zenoh_cpp")
    rclpy.init()
    node = PerceptionObjectPoseTopicSubscriberDemo(jsonl_path)
    executor = MultiThreadedExecutor()
    executor.add_node(node)

    try:
        if args.duration > 0:
            import time

            end = time.time() + args.duration
            while rclpy.ok() and time.time() < end:
                executor.spin_once(timeout_sec=0.1)
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
        print(f"[done] jsonl={jsonl_path} counts={node._counts}")


if __name__ == "__main__":
    main()
