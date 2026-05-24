# 统一感知 ROS2 流水线

## 项目简介

面向实体机器人的视觉感知：Orbbec 深度相机提供 RGB-D，`perception_2d` 统一调度 **YOLO**（闭集检测）或 **YOLOE**（少样本分割），`perception_object_pose` 融合深度估计相机系三维位姿，`perception_detections_to_base` 将结果变换到机器人基座系。

- ROS 2 **Jazzy**，默认 **`rmw_zenoh_cpp`**
- 统一 2D 话题前缀：`/perception_2d/*`
- 统一 3D 话题前缀：`/perception_object/*`、`/perception/detections_in_base`

详细架构与话题表见 **[PERCEPTION_STACK.md](PERCEPTION_STACK.md)**。

## 安装

```bash
conda create -n unitree python==3.12
conda activate unitree
pip install ultralytics
```

## 快速开始（推荐顺序）

```bash
cd <项目主目录>

# 1. 编译
./build_perception_stack.sh

# 2. 相机 + Zenoh（单独终端或后台）
export RMW_IMPLEMENTATION=rmw_zenoh_cpp
unset LD_LIBRARY_PATH
CAMERA_MOUNT=head ./start_camera.sh

# 3. 感知栈（默认 YOLOE + object_base）
CAMERA_MOUNT=head PERCEPTION_2D_BACKEND=yoloe ./start_perception_stack.sh ob

# 4. 停止
./stop_perception_stack.sh
./stop_camera.sh
```

### 常用环境变量

| 变量 | 说明 | 默认 |
|------|------|------|
| `CAMERA_MOUNT` | `head` / `breast` / `left_wrist` / `right_wrist` | `head` |
| `CAMERA_SN` | Orbbec 序列号 | 见 `start_camera.sh` |
| `PERCEPTION_2D_BACKEND` | `yoloe` / `yolo` | `yoloe` |
| `PUBLISH_BASE_TF` | 发布 `base`→相机 静态 TF | `0` |
| `NO_RVIZ` | 不启动 RViz | `0` |

命令行开关：`--base-tf`、`--no-rviz`（见 `start_perception_stack.sh --help`）。

## 一键脚本

| 脚本 | 作用 |
|------|------|
| `build_perception_stack.sh` | 编译新流水线全部包 |
| `start_camera.sh` | Zenoh + Orbbec 相机 |
| `stop_camera.sh` | 停止相机与 Zenoh |
| `start_perception_stack.sh [ob\|object]` | 2D + 3D + RViz（需相机已启动） |
| `stop_perception_stack.sh` | 停止感知栈 |

## 数据流（object_base / ob）

默认 `CAMERA_NAMESPACE=camera_head`：

```
相机 RGB-D
  ▼
perception_2d (yoloe|yolo)     → /perception_2d/*
  ▼
perception_object_pose         → /perception_object/*
  ▼
perception_detections_to_base    → /perception/detections_in_base
```

## 活跃 ROS2 包（参与编译）

| 包 | 角色 |
|----|------|
| `yolo_detection` | YOLO 2D 算法后端 |
| `yoloe_segmentation` | YOLOE 2D 算法后端 |
| `perception_2d` | 2D 统一入口（launch + 配置） |
| `perception_object_pose` | 3D 物体位姿 |
| `perception_detections_to_base` | 相机系 → base JSON |
| `perception_pose_visualization` | Marker / 坐标轴可视化 |

`ros2_ws/src/` 仅链接以上包（符号链接到仓库根目录同名目录）。

## 目录结构

```
<项目主目录>/
├── build_perception_stack.sh
├── start_camera.sh / stop_camera.sh
├── start_perception_stack.sh / stop_perception_stack.sh
├── camera_mount_env.inc.sh
├── PERCEPTION_STACK.md
├── ros2_ws/
├── yolo_detection/              # 2D 后端（YOLO）
├── yoloe_segmentation/          # 2D 后端（YOLOE）
├── perception_2d/
├── perception_object_pose/
├── perception_detections_to_base/
├── perception_pose_visualization/
└── demo/
```

## 注意事项

1. 运行节点前：`source /opt/ros/jazzy/setup.bash && source ros2_ws/install/setup.bash`，并 `export RMW_IMPLEMENTATION=rmw_zenoh_cpp`。
2. Conda 可能污染 `LD_LIBRARY_PATH`；启动脚本会 `unset LD_LIBRARY_PATH`，相机异常时请检查。
3. `stop_*` 使用 `pkill`，可能误杀本机同名进程，生产环境慎用。
4. 权重等大文件在 `yolo_detection/models`、`yoloe_segmentation/yoloe_deploy/` 等目录（`.pt` 等大文件默认不纳入 Git，需自行放置）。
