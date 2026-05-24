# 感知流水线订阅示例（Python Demo）

本目录提供 **3 个独立示例脚本**，分别对应统一感知流水线的三层输出。它们不实现业务逻辑，只做：

- 订阅对应话题；
- 在终端打印可读摘要；
- 将解析结果写入 **JSONL** 文件（每行一条 JSON：`ts` / `topic` / `payload`），便于对接方对照字段、离线分析。

更完整的架构说明见仓库根目录 [`PERCEPTION_STACK.md`](../PERCEPTION_STACK.md)。

---

## 流水线与脚本对应关系

```
相机 (Orbbec)
  └─► perception_2d          → /perception_2d/*
        └─► perception_object_pose  → /perception_object/*
              └─► perception_detections_to_base → /perception/detections_in_base
```

| 层级 | ROS 包 | 示例脚本 | 典型用途 |
|------|--------|----------|----------|
| 2D 感知 | `perception_2d`（后端 `yolo` / `yoloe`） | `perception_2d_topic_subscriber_demo.py` | 检测框、分割 mask、调试图 |
| 3D 位姿 | `perception_object_pose` | `perception_object_pose_topic_subscriber_demo.py` | 相机系 3D 点、位姿 JSON、RViz Marker |
| 基座输出 | `perception_detections_to_base` | `perception_detections_to_base_topic_subscriber_demo.py` | 机械臂 **base** 系目标点（JSON） |

**选用建议**

- 只做图像检测 / 分割 → 用脚本 1。
- 要相机光学坐标系下的 3D 位置与姿态 → 用脚本 2。
- 要直接给规划 / 抓取用的 **base 系** `[x,y,z]` → 用脚本 3（通常配合 `start_perception_stack.sh ob`）。

---

## 环境与启动（使用前必读）

### 1. 编译

在仓库根目录：

```bash
./build_perception_stack.sh
```

### 2. 启动相机与感知栈

```bash
export RMW_IMPLEMENTATION=rmw_zenoh_cpp
CAMERA_MOUNT=head ./start_camera.sh
CAMERA_MOUNT=head ./start_perception_stack.sh ob    # 或 object
```

- 默认 2D 后端为 **YOLOE**（`PERCEPTION_2D_BACKEND=yoloe`）；改为 YOLO：`PERCEPTION_2D_BACKEND=yolo ./start_perception_stack.sh ob`。
- 脚本 1 中的 `label_map` / `instance_masks` **仅 YOLOE 后端有数据**。

### 3. 运行 Demo（推荐）

在 `demo/` 目录下：

```bash
./run_demo_subscriber.sh <脚本名> --duration 15
```

`run_demo_subscriber.sh` 会自动 `source` ROS Jazzy 与本仓库 `ros2_ws/install/setup.bash`，并使用 `unitree` conda 中的 Python（可通过环境变量 `UNITREE_PYTHON` 覆盖）。

---

## 通用约定

### JSONL 格式

每收到一条（或一帧汇总）消息，写入一行：

```json
{"ts": "14:32:01", "topic": "/perception_2d/detections", "payload": { ... }}
```

默认输出路径（可用 `--jsonl` 覆盖）：

| 脚本 | 默认 JSONL |
|------|------------|
| `perception_2d_topic_subscriber_demo.py` | `demo/perception_2d_events.jsonl` |
| `perception_object_pose_topic_subscriber_demo.py` | `demo/perception_object_pose_events.jsonl` |
| `perception_detections_to_base_topic_subscriber_demo.py` | `demo/perception_detections_in_base_events.jsonl` |

### QoS（与发布端对齐）

| 话题类型 | Reliability | 说明 |
|----------|-------------|------|
| 检测 / 图像 / Marker（2D、3D 检测） | **BEST_EFFORT** | 与相机、感知节点一致 |
| `poses_json` | BEST_EFFORT | 由位姿节点发布 |
| `pose_estimates`、`middlewareMessage_topic`、部分 debug | **RELIABLE** | 桥接或控制类字符串 |
| `detections_in_base` | **RELIABLE** | 基座 JSON 输出 |

订阅端 QoS 与发布端不一致时，可能**永远收不到消息**（`ros2 topic info -v` 可核对）。

### 公共 CLI

三个脚本均支持：

```bash
--duration 15    # 运行 15 秒后退出；省略则 Ctrl+C 结束
--jsonl /path/to/out.jsonl
```

脚本 1 额外支持：

```bash
--save-mask-pixels-once   # 首帧把所有实例 mask 像素写入 JSONL（体积很大，默认关闭）
--detection-topic /perception_2d/detections   # 等话题名均可覆盖
```

脚本 3 额外支持：

```bash
--topic /perception/detections_in_base
```

---

## 脚本 1：`perception_2d_topic_subscriber_demo.py`

### 作用

演示如何消费 **统一 2D 话题前缀** `/perception_2d/*`（由 `perception_2d` 启动 `yolo_detection` 或 `yoloe_segmentation`，话题名在 yaml 中重映射到此前缀）。

### 订阅话题

| 话题 | 消息类型 | 含义 |
|------|----------|------|
| `/perception_2d/detections` | `vision_msgs/Detection2DArray` | 2D 检测：框中心、宽高、类别、分数 |
| `/perception_2d/instance_masks` | `sensor_msgs/Image` | 每个实例一张二值 mask（**YOLOE**） |
| `/perception_2d/label_map` | `sensor_msgs/Image` | 整图实例 ID 图（**YOLOE**，`mono16`） |
| `/perception_2d/label_map_viz` | `sensor_msgs/Image` | 彩色 mask，RViz 用 |
| `/perception_2d/debug_image` | `sensor_msgs/Image` | 叠加框 / mask 的调试图（`bgr8`） |
| `/perception_2d/markers` | `visualization_msgs/MarkerArray` | 2D 可视化 Marker |

### 关键字段说明（`Detection2DArray`）

- `header.frame_id`：相机彩色光学系，如 `camera_head_color_optical_frame`。
- `detections[i].id`：实例编号（字符串 `"1"`, `"2"` …），与 mask、label_map 对齐。
- `detections[i].bbox.center.position`：框中心像素 `(x, y)`。
- `detections[i].bbox.size_x` / `size_y`：框宽高（像素）。
- `detections[i].results[0].hypothesis.class_id`：类别（YOLO 多为数字字符串；YOLOE 多为名称如 `nongfu_spring`）。
- `detections[i].results[0].hypothesis.score`：置信度。

### `instance_masks` 如何用

- 类型：`sensor_msgs/Image`，编码 **`mono8`**，前景 255、背景 0。
- **每个实例单独一条消息**（不是数组）。
- `header.stamp` 与当帧 `detections` 的 `header.stamp` 相同（用于对齐）。
- **`header.frame_id` 存放实例 id**（等于 `detections[i].id`），不是相机坐标系名。

对齐示例（脚本内逻辑）：

1. 收到 `instance_masks` → `CvBridge` 解码为 `numpy` 数组，按 `(stamp_sec, stamp_nsec, instance_id)` 缓存。
2. 收到同 stamp 的 `detections` → 对每条 `det.id` 从缓存取 `mask` 元数据（面积、bbox、质心等）写入 JSONL。

批量解析也可用 **`label_map`**：`mono16` 图像中像素值 `0` 为背景，`1..N` 为实例 id。

### 解析与输出

| 回调 | 解析方式 | JSONL `payload` 要点 |
|------|----------|----------------------|
| `on_instance_mask` | `imgmsg_to_cv2(..., mono8)`，统计面积与 bbox | `instance_id`, `area_pixels`, `mask_bbox_xyxy`, `mask_centroid_xy` |
| `on_detection` | 遍历 `detections`，合并同 stamp 的 mask 缓存 | `detections[]` 含 `bbox_xyxy`, `class_id`, `score`, `mask` |
| `on_label_map` | 解码后 `np.unique` 得 `instance_ids` | `instance_ids`, `instance_count` |
| `on_debug_image` / `on_label_map_viz` | 仅记录尺寸与 encoding | 不写像素 |
| `on_marker` | 统计 Marker 数量与 namespace | `count`, `namespaces` |

### 运行示例

```bash
./run_demo_subscriber.sh perception_2d_topic_subscriber_demo.py --duration 15
```

---

## 脚本 2：`perception_object_pose_topic_subscriber_demo.py`

### 作用

演示如何消费 **`perception_object_pose`** 的输出：在 2D 检测基础上融合 RGB-D，得到 **相机光学坐标系** 下的 3D 点与物体位姿，并发布 JSON 与 Marker。

输入：默认订阅 `/perception_2d/detections`（在节点参数 `detections_input_topic` 中配置）。  
输出：统一前缀 `/perception_object/*`。

### 订阅话题

| 话题 | 消息类型 | 含义 |
|------|----------|------|
| `/perception_object/detections` | `vision_msgs/Detection2DArray` | 带 **相机系 3D** 的检测（`pose.position` 为米） |
| `/perception_object/poses_json` | `std_msgs/String` | 原始位姿 JSON（字段最全） |
| `/perception_object/pose_estimates` | `std_msgs/String` | 规整后的位姿 JSON（由 `object_pose_json_to_msg_node` 桥接） |
| `/perception_object/debug_image` | `sensor_msgs/Image` | 3D 位姿调试图 |
| `/perception_object/markers` | `visualization_msgs/MarkerArray` | 3D 点球 / 文本 |
| `/perception_object/pose_markers` | `visualization_msgs/MarkerArray` | 由 `pose_estimates` 生成的位姿轴 Marker |
| `/perception_object/middlewareMessage_topic` | `std_msgs/String` | 中间件状态 / 控制反馈字符串 |

### `/perception_object/detections` 解析

脚本从每条 `detection` 提取：

- `bbox.center` → 像素 `center_xy`
- `bbox.size_x/y` → `size_wh`
- `results[0].hypothesis` → `class_id`, `score`
- `results[0].pose.pose.position` → 相机系 **`xyz`（米）**

下游 **`perception_detections_to_base`** 主要使用这里的 **`pose.position`（相机系 3D 点）** 做变换。

### `/perception_object/poses_json` JSON 结构

`msg.data` 为 JSON 字符串，顶层示例：

```json
{
  "stamp": { "sec": 0, "nanosec": 0 },
  "frame_id": "camera_head_color_optical_frame",
  "object_poses": [
    {
      "class_name": "nongfu_spring",
      "class_id": -1,
      "score": 0.95,
      "bbox_xyxy": [x1, y1, x2, y2],
      "center_pixel": [u, v],
      "position": [x, y, z],
      "quaternion_xyzw": [qx, qy, qz, qw],
      "surface_normal": [nx, ny, nz],
      "object_extent_xyz": [ex, ey, ez],
      "object_pose_4x4": [[...], ...],
      "...": "还有点云统计等扩展字段"
    }
  ]
}
```

- 坐标系：`frame_id` 对应的**相机光学系**，单位米。
- 适合需要姿态矩阵、法向量、物体尺寸的应用。

### `/perception_object/pose_estimates` JSON 结构

外层为事件包装（便于与旧版 grasp 话题统一）：

```json
{
  "ts": "14:32:01",
  "topic": "/perception_object/pose_estimates",
  "payload": {
    "msg_type": "std_msgs/String",
    "frame_id": "camera_head_color_optical_frame",
    "count": 2,
    "poses": [
      {
        "variant": "object",
        "class_name": "nongfu_spring",
        "class_id": -1,
        "score": 0.95,
        "center_uv": [u, v],
        "bbox_xyxy": [x1, y1, x2, y2],
        "position_xyz": [x, y, z],
        "quaternion_xyzw": [qx, qy, qz, qw],
        "surface_normal_xyz": [nx, ny, nz],
        "extent_xyz": [ex, ey, ez]
      }
    ]
  }
}
```

脚本解析：`json.loads` → 取 `payload.poses` → 日志打印前 3 个目标的 `position_xyz`。

### 解析与输出

| 回调 | 解析方式 |
|------|----------|
| `on_detection` | 遍历 `Detection2DArray`，提取 2D + 3D 字段 |
| `on_poses_json` | `json.loads`，整包写入 `parsed` |
| `on_pose_estimates` | `json.loads`，读取 `payload.poses` |
| `on_debug_image` / `on_marker` / `on_pose_markers` | 元数据或计数 |
| `on_middleware` | 原始字符串 |

### 运行示例

```bash
./run_demo_subscriber.sh perception_object_pose_topic_subscriber_demo.py --duration 15
```

---

## 脚本 3：`perception_detections_to_base_topic_subscriber_demo.py`

### 作用

演示如何消费 **`perception_detections_to_base`** 的最终输出：将 `/perception_object/detections` 中每个目标的相机系 3D 点，用固定外参矩阵变换到 **`base` 坐标系**，以 **JSON 字符串** 发布，便于非 ROS 模块或机械臂接口直接读取。

### 订阅话题

| 话题 | 消息类型 | 含义 |
|------|----------|------|
| `/perception/detections_in_base` | `std_msgs/String` | 基座系目标列表 JSON（**本脚本唯一订阅**） |

> 另有 `/perception/detections_in_base_markers`（`MarkerArray`）供 RViz 显示，本 demo 未订阅；需要可视化可自行订阅。

### JSON 结构（`msg.data`）

```json
{
  "frame_id": "camera_head_color_optical_frame",
  "count": 2,
  "objects": [
    {
      "arm_base_xyz": [x, y, z],
      "class_id": 39,
      "class_name": "bottle",
      "score": 0.87
    }
  ]
}
```

| 字段 | 说明 |
|------|------|
| `frame_id` | 来源检测消息的坐标系名（变换前相机系） |
| `count` | `objects` 数组长度 |
| `objects[].arm_base_xyz` | **base 系** 目标点 `[x, y, z]`（米），下游最常用的字段 |
| `objects[].class_id` | 整数（COCO）或字符串（YOLOE 类名） |
| `objects[].class_name` | 人类可读类别名 |
| `objects[].score` | 置信度 |

变换使用节点内常量 `T_BASE_CAMERA`（与 `./start_perception_stack.sh ob --base-tf` 发布的静态 TF 一致）。可选参数 `base_x_offset` 会对 base 的 x 做偏移。

### 解析流程

1. `on_detections_in_base` 读取 `std_msgs/String.data`。
2. `json.loads`；校验 `count` 为 int、`objects` 为 list。
3. 日志打印前 5 个目标的 `arm_base_xyz`。
4. 整包写入 JSONL（`json_schema`: `perception_detections_in_base`）。

### 运行示例

```bash
./run_demo_subscriber.sh perception_detections_to_base_topic_subscriber_demo.py --duration 15
```

需已运行 **`start_perception_stack.sh ob`**（或 `object` + 对应 launch 链），否则无数据。

---

## 快速自检

```bash
# 话题是否存在、是否有发布者
ros2 topic list | grep perception
ros2 topic hz /perception_2d/detections
ros2 topic hz /perception_object/pose_estimates
ros2 topic hz /perception/detections_in_base

# QoS 是否匹配
ros2 topic info /perception_2d/detections -v
```

Demo 运行约 15 s 后终端应打印 `[done] jsonl=... counts={...}`，且 `counts` 中各话题计数大于 0。

---

## 对接方最小集成示例（Python）

仅订阅基座 JSON（与脚本 3 相同逻辑）：

```python
import json
from rclpy.node import Node
from std_msgs.msg import String

class MyConsumer(Node):
    def __init__(self):
        super().__init__("my_consumer")
        self.create_subscription(
            String, "/perception/detections_in_base", self.on_base, 10
        )

    def on_base(self, msg: String):
        data = json.loads(msg.data)
        for obj in data["objects"]:
            x, y, z = obj["arm_base_xyz"]
            name = obj.get("class_name", "")
            # 交给规划 / 抓取模块 ...
```

需要 **mask** 时订阅脚本 1 中的 `/perception_2d/instance_masks`，并用 `detections[i].id` 与 `header.stamp` 对齐（见上文）。

---

## 文件一览

| 文件 | 说明 |
|------|------|
| `perception_2d_topic_subscriber_demo.py` | 2D + 分割 mask |
| `perception_object_pose_topic_subscriber_demo.py` | 3D 位姿与 JSON |
| `perception_detections_to_base_topic_subscriber_demo.py` | base 系 JSON |
| `run_demo_subscriber.sh` | 统一启动（ROS + workspace + Python） |

如有新后端接入，只要继续发布相同结构的 `/perception_2d/detections`，脚本 2、3 通常**无需修改**；脚本 1 可增加对新话题名的参数覆盖。
