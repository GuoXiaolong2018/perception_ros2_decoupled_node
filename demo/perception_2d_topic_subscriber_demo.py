#!/usr/bin/env python3.12
"""
订阅统一 2D 感知话题（/perception_2d/*），含 YOLOE 的 instance_masks / label_map。

配套（默认 YOLOE 后端）:
  CAMERA_MOUNT=head ./start_perception_stack.sh ob|object

Usage:
  ./demo/run_demo_subscriber.sh perception_2d_topic_subscriber_demo.py --duration 15
  ./demo/run_demo_subscriber.sh perception_2d_topic_subscriber_demo.py --duration 15 --save-mask-pixels-once
"""

import argparse
import json
import os
import time
from datetime import datetime

import numpy as np
import rclpy
from cv_bridge import CvBridge
from rclpy._rclpy_pybind11 import RCLError
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy
from sensor_msgs.msg import Image
from vision_msgs.msg import Detection2DArray
from visualization_msgs.msg import MarkerArray


def _now_str() -> str:
    return datetime.now().strftime("%H:%M:%S")


class Perception2dTopicSubscriberDemo(Node):
    def __init__(self, jsonl_path: str, args):
        super().__init__("perception_2d_topic_subscriber_demo")
        self.args = args
        self.bridge = CvBridge()

        sensor_qos = QoSProfile(
            depth=10,
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE,
            history=HistoryPolicy.KEEP_LAST,
        )

        self.detection_topic = args.detection_topic
        self.debug_image_topic = args.debug_image_topic
        self.label_map_topic = args.label_map_topic
        self.label_map_viz_topic = args.label_map_viz_topic
        self.instance_masks_topic = args.instance_masks_topic
        self.marker_topic = args.marker_topic

        self.last_detection_time = None
        self.last_debug_image_time = None
        self.last_label_map_time = None
        self.last_label_map_viz_time = None
        self.last_marker_time = None
        self.last_instance_mask_time = None
        self._received_any = False
        self._heartbeat_ticks = 0
        self._counts = {}
        # (stamp_sec, stamp_nsec) -> {instance_id: mask_metadata}
        self._mask_cache = {}
        # (stamp_sec, stamp_nsec) -> {instance_id: np.ndarray}
        self._mask_array_cache = {}
        self._mask_pixels_frame_saved = False

        os.makedirs(os.path.dirname(jsonl_path) or ".", exist_ok=True)
        self.jsonl_fp = open(jsonl_path, "w", encoding="utf-8", buffering=1)

        self.create_subscription(
            Image, self.instance_masks_topic, self.on_instance_mask, sensor_qos
        )
        self.create_subscription(
            Detection2DArray, self.detection_topic, self.on_detection, sensor_qos
        )
        self.create_subscription(
            Image, self.debug_image_topic, self.on_debug_image, sensor_qos
        )
        self.create_subscription(
            Image, self.label_map_topic, self.on_label_map, sensor_qos
        )
        self.create_subscription(
            Image, self.label_map_viz_topic, self.on_label_map_viz, sensor_qos
        )
        self.create_subscription(
            MarkerArray, self.marker_topic, self.on_marker, sensor_qos
        )
        self.create_timer(3.0, self.print_heartbeat)

        self.get_logger().info("perception_2d 话题订阅演示已启动")
        self.get_logger().info("JSONL: " + jsonl_path)
        for t in (
            self.detection_topic,
            self.instance_masks_topic,
            self.label_map_topic,
            self.label_map_viz_topic,
            self.debug_image_topic,
            self.marker_topic,
        ):
            self.get_logger().info(f"  subscribe: {t}")
        if args.show_format_once:
            self._print_format_hint()
        if args.save_mask_pixels_once:
            self.get_logger().info(
                "首帧完整 mask 像素将写入 JSONL（frame_snapshot=true，体积较大）"
            )

    def _print_format_hint(self):
        self.get_logger().info("Detection2DArray（/perception_2d/detections）：")
        self.get_logger().info("  detections[i].id              # 实例 id，与 mask / label_map 对齐")
        self.get_logger().info("  detections[i].bbox.center     # 像素中心")
        self.get_logger().info("  detections[i].results[0].hypothesis.class_id / score")
        self.get_logger().info(
            f"  {self.instance_masks_topic}  # sensor_msgs/Image mono8；"
            "每实例一条；header.frame_id == detections[i].id（非相机 frame）"
        )
        self.get_logger().info(
            f"  {self.label_map_topic}  # mono16，像素值=实例 id（0=背景）"
        )

    def _write_event_jsonl(self, topic: str, payload: dict):
        self._received_any = True
        self._counts[topic] = self._counts.get(topic, 0) + 1
        row = {"ts": _now_str(), "topic": topic, "payload": payload}
        self.jsonl_fp.write(json.dumps(row, ensure_ascii=False) + "\n")

    def _stamp_key(self, stamp) -> tuple:
        return (int(stamp.sec), int(stamp.nanosec))

    def _mask_metadata_from_array(self, arr: np.ndarray, inst_id: str, stamp) -> dict:
        info = {
            "msg_type": "sensor_msgs/Image",
            "encoding": "mono8",
            "width": int(arr.shape[1]),
            "height": int(arr.shape[0]),
            "frame_id": inst_id,
            "instance_id": inst_id,
            "header_stamp": {"sec": int(stamp.sec), "nanosec": int(stamp.nanosec)},
            "area_pixels": int(np.count_nonzero(arr)),
            "pixel_value_foreground": 255,
            "pixel_value_background": 0,
        }
        ys, xs = np.nonzero(arr > 0)
        if xs.size > 0:
            info["mask_bbox_xyxy"] = [
                int(xs.min()),
                int(ys.min()),
                int(xs.max()),
                int(ys.max()),
            ]
            info["mask_centroid_xy"] = [float(xs.mean()), float(ys.mean())]
        else:
            info["mask_bbox_xyxy"] = None
            info["mask_centroid_xy"] = None
        if not self.args.save_mask_pixels_once or self._mask_pixels_frame_saved:
            info["note"] = (
                "元数据条目；完整 mask_pixels 见 frame_snapshot=true 记录（若已开启）。"
            )
        return info

    def _try_save_one_frame_mask_pixels(
        self, stamp_key: tuple, expected_ids: list | None = None
    ):
        if self._mask_pixels_frame_saved or not self.args.save_mask_pixels_once:
            return
        buf = self._mask_array_cache.get(stamp_key, {})
        if not buf:
            return
        if expected_ids is not None:
            if not all(str(eid) in buf for eid in expected_ids):
                return

        def _sort_id(iid: str):
            return int(iid) if str(iid).isdigit() else 0

        instances = []
        for inst_id in sorted(buf.keys(), key=_sort_id):
            arr = buf[inst_id]
            instances.append(
                {
                    "instance_id": inst_id,
                    "encoding": "mono8",
                    "width": int(arr.shape[1]),
                    "height": int(arr.shape[0]),
                    "mask_pixels": arr.tolist(),
                }
            )

        payload = {
            "frame_snapshot": True,
            "msg_type": "sensor_msgs/Image[]",
            "header_stamp": {"sec": stamp_key[0], "nanosec": stamp_key[1]},
            "instance_count": len(instances),
            "instances": instances,
            "note": (
                "仅保存一帧；mask_pixels 为 [height][width]，取值 0 或 255；"
                "与 detections 通过 instance_id + header_stamp 对齐。"
            ),
        }
        self._write_event_jsonl(self.instance_masks_topic, payload)
        self._mask_pixels_frame_saved = True
        wh = f"{instances[0]['width']}x{instances[0]['height']}" if instances else "?"
        self.get_logger().info(
            f"[instance_masks] 首帧完整像素已写入 JSONL | stamp={stamp_key} | "
            f"instances={len(instances)} | size≈{wh}"
        )

    def on_instance_mask(self, msg: Image):
        self.last_instance_mask_time = _now_str()
        inst_id = msg.header.frame_id
        key = self._stamp_key(msg.header.stamp)
        try:
            arr = self.bridge.imgmsg_to_cv2(msg, desired_encoding="mono8")
        except Exception as exc:
            self.get_logger().error(f"instance_masks 解码失败: {exc}")
            return

        mask_payload = self._mask_metadata_from_array(arr, inst_id, msg.header.stamp)
        self._mask_cache.setdefault(key, {})[inst_id] = mask_payload
        self._mask_array_cache.setdefault(key, {})[inst_id] = arr
        if len(self._mask_cache) > 32:
            oldest = sorted(self._mask_cache.keys())[0]
            del self._mask_cache[oldest]
            self._mask_array_cache.pop(oldest, None)

        self.get_logger().info(
            f"[instance_masks] inst={inst_id} {msg.width}x{msg.height} "
            f"area_px={mask_payload.get('area_pixels', '?')} "
            f"bbox={mask_payload.get('mask_bbox_xyxy')}"
        )
        self._write_event_jsonl(self.instance_masks_topic, mask_payload)

    def _detection_to_dict(self, msg: Detection2DArray) -> dict:
        stamp_key = self._stamp_key(msg.header.stamp)
        masks_for_frame = self._mask_cache.get(stamp_key, {})
        payload = {
            "msg_type": "vision_msgs/Detection2DArray",
            "frame_id": msg.header.frame_id,
            "header_stamp": {"sec": stamp_key[0], "nanosec": stamp_key[1]},
            "count": len(msg.detections),
            "detections": [],
        }
        for det in msg.detections:
            cx = float(det.bbox.center.position.x)
            cy = float(det.bbox.center.position.y)
            sx = float(det.bbox.size_x)
            sy = float(det.bbox.size_y)
            item = {
                "instance_id": det.id,
                "center_xy": [cx, cy],
                "size_wh": [sx, sy],
                "bbox_xyxy": [cx - sx / 2, cy - sy / 2, cx + sx / 2, cy + sy / 2],
                "class_id": None,
                "score": None,
                "mask": masks_for_frame.get(det.id),
            }
            if det.results:
                hyp = det.results[0].hypothesis
                pose = det.results[0].pose.pose.position
                item["class_id"] = hyp.class_id
                item["score"] = float(hyp.score)
                item["pose_xyz"] = [float(pose.x), float(pose.y), float(pose.z)]
            payload["detections"].append(item)
        return payload

    def on_detection(self, msg: Detection2DArray):
        self.last_detection_time = _now_str()
        count = len(msg.detections)
        if count == 0:
            self.get_logger().info("[detection] 空结果")
        else:
            summary = []
            stamp_key = self._stamp_key(msg.header.stamp)
            for det in msg.detections[:5]:
                if not det.results:
                    summary.append(f"inst={det.id},?")
                    continue
                hyp = det.results[0].hypothesis
                cx = det.bbox.center.position.x
                cy = det.bbox.center.position.y
                mask_info = self._mask_cache.get(stamp_key, {}).get(det.id)
                mask_area = str(mask_info.get("area_pixels", "?")) if mask_info else "?"
                summary.append(
                    f"inst={det.id},{hyp.class_id},s={hyp.score:.3f},"
                    f"c=({cx:.0f},{cy:.0f}),mask_px={mask_area}"
                )
            self.get_logger().info(
                f"[detection] count={count} frame={msg.header.frame_id} top5={summary}"
            )
            self._try_save_one_frame_mask_pixels(
                stamp_key, expected_ids=[det.id for det in msg.detections]
            )
        self._write_event_jsonl(self.detection_topic, self._detection_to_dict(msg))

    def _label_map_stats(self, msg: Image) -> dict:
        payload = {
            "msg_type": "sensor_msgs/Image",
            "width": int(msg.width),
            "height": int(msg.height),
            "encoding": msg.encoding,
            "frame_id": msg.header.frame_id,
            "instance_ids": [],
        }
        try:
            arr = self.bridge.imgmsg_to_cv2(msg, desired_encoding="passthrough")
            ids = sorted(int(x) for x in np.unique(arr) if int(x) > 0)
            payload["instance_ids"] = ids
            payload["instance_count"] = len(ids)
        except Exception as exc:
            payload["parse_error"] = str(exc)
        return payload

    def on_label_map(self, msg: Image):
        self.last_label_map_time = _now_str()
        stats = self._label_map_stats(msg)
        self.get_logger().info(
            f"[label_map] {msg.width}x{msg.height} {msg.encoding} "
            f"instances={stats.get('instance_ids', [])}"
        )
        self._write_event_jsonl(self.label_map_topic, stats)

    def on_label_map_viz(self, msg: Image):
        self.last_label_map_viz_time = _now_str()
        self.get_logger().info(
            f"[label_map_viz] {msg.width}x{msg.height} encoding={msg.encoding}"
        )
        self._write_event_jsonl(
            self.label_map_viz_topic,
            {
                "msg_type": "sensor_msgs/Image",
                "width": int(msg.width),
                "height": int(msg.height),
                "encoding": msg.encoding,
                "frame_id": msg.header.frame_id,
            },
        )

    def on_debug_image(self, msg: Image):
        self.last_debug_image_time = _now_str()
        self.get_logger().info(
            f"[debug_image] {msg.width}x{msg.height} encoding={msg.encoding}"
        )
        self._write_event_jsonl(
            self.debug_image_topic,
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
        ns_counts = {}
        for m in msg.markers:
            ns_counts[m.ns] = ns_counts.get(m.ns, 0) + 1
        self.get_logger().info(f"[markers] count={len(msg.markers)} ns={ns_counts}")
        self._write_event_jsonl(
            self.marker_topic,
            {
                "msg_type": "visualization_msgs/MarkerArray",
                "count": len(msg.markers),
                "namespaces": ns_counts,
            },
        )

    def print_heartbeat(self):
        self._heartbeat_ticks += 1
        self.get_logger().info(
            "heartbeat | "
            f"det={self.last_detection_time} masks={self.last_instance_mask_time} "
            f"label_map={self.last_label_map_time} counts={self._counts}"
        )
        if not self._received_any and self._heartbeat_ticks >= 2:
            self.get_logger().warning(
                "仍未收到消息。请确认 start_perception_stack.sh 已运行，"
                "且 PERCEPTION_2D_BACKEND=yoloe（YOLO 后端无 mask/label_map）。"
            )


def main():
    parser = argparse.ArgumentParser(description="订阅 /perception_2d/* 并写入 JSONL")
    parser.add_argument(
        "--detection-topic",
        default="/perception_2d/detections",
        help="vision_msgs/Detection2DArray",
    )
    parser.add_argument(
        "--debug-image-topic",
        default="/perception_2d/debug_image",
        help="sensor_msgs/Image bgr8",
    )
    parser.add_argument(
        "--label-map-topic",
        default="/perception_2d/label_map",
        help="sensor_msgs/Image mono16",
    )
    parser.add_argument(
        "--label-map-viz-topic",
        default="/perception_2d/label_map_viz",
        help="sensor_msgs/Image bgr8",
    )
    parser.add_argument(
        "--instance-masks-topic",
        default="/perception_2d/instance_masks",
        help="sensor_msgs/Image mono8；header.frame_id == Detection2D.id",
    )
    parser.add_argument(
        "--marker-topic",
        default="/perception_2d/markers",
        help="visualization_msgs/MarkerArray",
    )
    parser.add_argument(
        "--jsonl",
        default="",
        help="输出 JSONL（默认 demo/perception_2d_events.jsonl）",
    )
    parser.add_argument("--duration", type=float, default=0.0, help="运行秒数，0=直到 Ctrl+C")
    parser.add_argument("--show-format-once", action="store_true", default=True)
    parser.add_argument(
        "--save-mask-pixels-once",
        action="store_true",
        help="额外把首帧完整 mask 像素写入 JSONL（体积很大，默认关闭）",
    )
    args = parser.parse_args()

    demo_dir = os.path.dirname(os.path.abspath(__file__))
    jsonl_path = args.jsonl or os.path.join(demo_dir, "perception_2d_events.jsonl")

    os.environ.setdefault("RMW_IMPLEMENTATION", "rmw_zenoh_cpp")
    rclpy.init()
    node = Perception2dTopicSubscriberDemo(jsonl_path, args)
    executor = MultiThreadedExecutor()
    executor.add_node(node)

    try:
        if args.duration > 0:
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
