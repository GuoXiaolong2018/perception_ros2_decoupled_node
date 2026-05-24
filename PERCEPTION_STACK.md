# 统一感知流水线（重构版）

## 架构概览

```
相机 Orbbec
  └─► perception_2d（backend=yolo|yoloe）
        发布 /perception_2d/*
      └─► perception_object_pose
            发布 /perception_object/*
          └─► perception_detections_to_base（object_base / ob）
                发布 /perception/detections_in_base*
```

## 包命名

| 角色 | 包名 | 说明 |
|------|------|------|
| 2D 感知入口 | `perception_2d` | 按 `backend` 启动 YOLO 或 YOLOE，统一话题前缀 |
| 3D 物体位姿 | `perception_object_pose` | RGB-D + 2D 检测 |
| 基座变换 | `perception_detections_to_base` | 相机系 → base |
| 可视化工具 | `perception_pose_visualization` | Marker / 坐标轴 |
| 算法后端 | `yolo_detection`, `yoloe_segmentation` | 不合并实现，由 perception_2d 调度 |

## 统一话题（默认）

### 2D：`/perception_2d/`

- `detections` — `vision_msgs/Detection2DArray`
- `debug_image` — `sensor_msgs/Image`
- `label_map`, `label_map_viz`, `instance_masks` — YOLOE 有数据，YOLO 无
- `markers` — `visualization_msgs/MarkerArray`（YOLOE）
- `middlewareMessage_topic`, `middles_yolo_service`

### 3D 物体：`/perception_object/`

- `detections`, `debug_image`, `markers`, `poses_json`, `pose_estimates`, `pose_markers`

### 基座：`/perception/`

- `detections_in_base` — JSON `std_msgs/String`
- `detections_in_base_markers` — `MarkerArray`

## 脚本

| 脚本 | 作用 |
|------|------|
| `./build_perception_stack.sh` | 编译全部相关包 |
| `./start_camera.sh` | Zenoh + Orbbec（可选，与感知分离） |
| `./stop_camera.sh` | 停止相机与 Zenoh 路由 |
| `./start_perception_stack.sh [ob\|object]` | 启动 2D+3D+RViz（**假定相机已开**） |
| `./stop_perception_stack.sh` | 停止感知栈（不含相机） |

### 常用命令

```bash
# 1. 编译
./build_perception_stack.sh

# 2. 相机（若未启动）
export RMW_IMPLEMENTATION=rmw_zenoh_cpp
CAMERA_MOUNT=head ./start_camera.sh

# 3. 感知栈（默认 YOLOE + object_base）
CAMERA_MOUNT=head PERCEPTION_2D_BACKEND=yoloe ./start_perception_stack.sh ob

# 4. 停止感知（保留相机）
./stop_perception_stack.sh

# 5. 停止相机
./stop_camera.sh
```

环境变量 `PERCEPTION_2D_BACKEND`：`yoloe`（默认）| `yolo`。

**基座 TF（可选，默认关闭）**：RViz 中「Base Frame Detections」需要 TF 树存在 `base` 坐标系。

```bash
# 方式 1：命令行开关
./start_perception_stack.sh ob --base-tf

# 方式 2：环境变量
PUBLISH_BASE_TF=1 ./start_perception_stack.sh ob
```

外参与 `perception_detections_to_base` 节点内 `T_BASE_CAMERA` 一致；子坐标系随 `CAMERA_NAMESPACE` 自动变为 `{CAMERA_NAMESPACE}_color_optical_frame`。

## 扩展新 2D 算法

1. 在仓库新增算法包（如 `foo_detection`）。
2. 在 `perception_2d/config/` 增加 `perception_2d_foo_params.yaml`（话题指向 `/perception_2d/*`）。
3. 在 `perception_2d/launch/perception_2d_launch.py` 增加 `backend==foo` 分支。
4. `build_perception_stack.sh` 的 `packages-select` 中加入新包。

下游 `perception_object_pose` 无需修改，只要新后端发布相同结构的 `Detection2DArray`。
