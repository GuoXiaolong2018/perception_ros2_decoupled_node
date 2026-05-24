# YOLOE-VP

Reference from https://docs.ultralytics.com/zh/tasks/segment/#models

## 功能说明

YOLOE_VP 是一个支持视觉提示（参考图像）的实例分割模型，支持以下功能：

- **参考图像分割**：输入一张参考图像、及其要分割的物体在图像中的坐标，模型可分割出测试图像中的同类目标，输出二值掩码。
- **批量多目标推理**：支持在参考图像中指定多个类别的物体，然后对多张测试图像进行批量推理，提高推理效率。

## 文件说明

| 文件 | 功能 |
|------|------|
| `yoloe_vp_interface.py` | yoloe_vp的本地推理接口（继承 `BaseInterface`） |
| `yoloe_vp_interface_config.yaml` | 接口配置文件（可选） |
| `test_data` | 测试数据 |
| `ref_template` | 物体的参考图像 |
| `visual_prompt` | 视觉提示的可视化 |
| `weights` | 模型权重 |

**注意**：
- 如果需要标注参考图像中物体的坐标，可以使用 `tools/rect_annotation` 中的矩形标注工具。更多详细信息请参考 `tools/rect_annotation/README.md`。
- `yoloe_vp_interface.py` 已重构为继承 `BaseInterface` 基类，支持统一的配置管理方式（配置文件或配置字典）。

## 安装方法

```bash
# 创建conda环境
conda create -n yoloe_vp python==3.10

# 激活conda环境
conda activate yoloe_vp

# 安装 ultralytics
pip install ultralytics

# 安装OpenCV
pip install opencv-python
```

## 使用方法

### 使用配置文件

首先创建配置文件 `yoloe_vp_interface_config.yaml`：

```yaml
checkpoint_path: "./weights/yoloe-11l-seg.pt"
device: "cuda"  # 或 "cpu"
target_list:
  - target_name: "fg_red_bull"
    ref_image_path: "./ref_template/ref_fg_red_bull.png"
    visual_bbox: [213, 98, 291, 206]
    visual_cls: 0
  # 可以添加多个目标
  # - target_name: "another_target"
  #   ref_image_path: "./ref_template/ref_another.png"
  #   visual_bbox: [100, 100, 200, 200]
  #   visual_cls: 0
```

然后使用配置文件运行：

```bash
cd yoloe_vp
python yoloe_vp_interface.py \
    --config_path yoloe_vp_interface_config.yaml \
    --image ./test_data/test_image_01.jpg \
    --output ./Seg_test_image_01.jpg \
    --target fg_red_bull
```

### 参数说明

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `--image` | str | 是 | 输入测试图像路径 |
| `--config_path` | str | 否 | YAML 配置文件路径 |
| `--output` | str | 是 | 输出二值掩码图像路径 |
| `--target` | str | 否 | 目标类别名称（默认：`fg_red_bull`，必须在配置文件中已注册） |


## 参考图像坐标标注

如果需要为新的参考图像标注物体坐标，可以使用 `tools/rect_annotation` 中的矩形标注工具：

```bash
# 使用矩形标注工具标注参考图像
python tools/rect_annotation/interact.py \
    --input algorithms/yoloe_vp/ref_template/ref_fg_red_bull.png \
    --output_txt algorithms/yoloe_vp/visual_prompt/ref_fg_red_bull_cord.txt \
    --output_image algorithms/yoloe_vp/visual_prompt/ref_fg_red_bull_cord.png
```

标注完成后，将`ref_object_cord.txt`中的坐标信息填入yaml配置文件中visual_bbox字段即可。

## Python API 使用方法

### 方式一：使用配置文件（推荐）

```python
from yoloe_vp_interface import YoloeVPInterface

# 使用配置文件初始化（推荐方式）
segment = YoloeVPInterface(
    config_path="./yoloe_vp_interface_config.yaml"
)

# 执行推理
results = segment.inference("./test_data/test_image_01.jpg", target="fg_red_bull")
# 或使用 inference_segment_one 获取掩码和边界框
mask, bbox = segment.inference_segment_one("./test_data/test_image_01.jpg", target="fg_red_bull")
```

### 方式二：使用配置字典

```python
from yoloe_vp_interface import YoloeVPInterface

# 使用配置字典初始化
config = {
    "checkpoint_path": "./weights/yoloe-11l-seg.pt",
    "device": "cuda",
    "target_list": [
        {
            "target_name": "fg_red_bull",
            "ref_image_path": "./ref_template/ref_fg_red_bull.png",
            "visual_bbox": [213, 98, 291, 206],
            "visual_cls": 0,
        }
    ],
}

segment = YoloeVPInterface(config=config)

# 执行推理
mask, bbox = segment.inference_segment_one("./test_data/test_image_01.jpg", target="fg_red_bull")
```

### 方式三：动态注册参考图像

这种方式允许一个 `YoloeVPInterface` 对象适应多种不同的参考图像和目标物体：

```python
from yoloe_vp_interface import YoloeVPInterface

# 1. 使用配置文件初始化，但 target_list 可以为空
config = {
    "checkpoint_path": "./weights/yoloe-11l-seg.pt",
    "device": "cuda",
    "target_list": [],  # 空列表，不初始化任何目标
}
segment = YoloeVPInterface(config=config)

# 2. 动态注册第一个参考图像和目标
segment.register_target(
    target_name="red_bull",
    ref_image_path="./ref_template/ref_fg_red_bull.png",
    visual_bbox=[213, 98, 291, 206],
    visual_cls=0,
)

# 3. 动态注册第二个参考图像和目标（可以是不同的物体）
segment.register_target(
    target_name="milk",
    ref_image_path="./ref_template/ref_milk.png",
    visual_bbox=[379, 216, 459, 334],
    visual_cls=0,
)

# 4. 使用不同的 target 进行推理
mask1, bbox1 = segment.inference_segment_one("./test_data/test_image_01.jpg", target="red_bull")
mask2, bbox2 = segment.inference_segment_one("./test_data/test_image_02.jpg", target="milk")
```

### 使用示例

#### 示例1：使用配置文件初始化单个目标

```python
from yoloe_vp_interface import YoloeVPInterface

# 使用配置文件初始化
segment = YoloeVPInterface(config_path="./yoloe_vp_interface_config.yaml")

# 执行推理
mask, bbox = segment.inference_segment_one("./test_data/test_image_01.jpg", target="fg_red_bull")
```

#### 示例2：使用配置字典初始化多个目标

```python
from yoloe_vp_interface import YoloeVPInterface

config = {
    "checkpoint_path": "./weights/yoloe-11l-seg.pt",
    "device": "cuda",
    "target_list": [
        {
            "target_name": "red_bull",
            "ref_image_path": "./ref_template/ref_fg_red_bull.png",
            "visual_bbox": [213, 98, 291, 206],
            "visual_cls": 0,
        },
        {
            "target_name": "milk",
            "ref_image_path": "./ref_template/ref_milk.png",
            "visual_bbox": [379, 216, 459, 334],
            "visual_cls": 0,
        },
    ],
}

segment = YoloeVPInterface(config=config)

# 使用不同的 target 进行推理
for target_name in ["red_bull", "milk"]:
    mask, bbox = segment.inference_segment_one("./test_data/test_image_01.jpg", target=target_name)
```

#### 示例3：动态注册和更新目标

```python
from yoloe_vp_interface import YoloeVPInterface

# 初始化时不注册任何目标
config = {
    "checkpoint_path": "./weights/yoloe-11l-seg.pt",
    "device": "cuda",
    "target_list": [],
}
segment = YoloeVPInterface(config=config)

# 注册第一个目标
segment.register_target(
    target_name="my_target",
    ref_image_path="./ref_template/ref_fg_red_bull.png",
    visual_bbox=[213, 98, 291, 206],
)

# 更新同一个 target 的参考图像和坐标
segment.register_target(
    target_name="my_target",
    ref_image_path="./ref_template/ref_milk.png",
    visual_bbox=[379, 216, 459, 334],
)

# 执行推理
mask, bbox = segment.inference_segment_one("./test_data/test_image_02.jpg", target="my_target")
```

#### 示例4：批量推理多目标（新功能）

该功能允许在参考图像中指定多个类别的物体，然后对多张测试图像进行批量推理：

```python
from yoloe_vp_interface import YoloeVPInterface

# 初始化接口
segment = YoloeVPInterface(config_path="./yoloe_vp_interface_config.yaml")

# 批量推理多目标
# 在参考图像中指定多个物体：cola (类别0) 和 nongfu spring (类别1)
results = segment.inference_batch_multi_targets(
    refer_image="./ref_template/ref_freezer_20251215.png",
    visual_bboxes=[
        [637, 423, 684, 516],  # cola 的边界框
        [785, 398, 845, 527],  # nongfu spring 的边界框
    ],
    visual_cls=[0, 1],  # 对应的类别 id
    test_images=[
        "./test_data/20251215190551739.jpg",
        "./test_data/20251215190918752.jpg",
    ],
)

# 处理每张图像的推理结果
for i, result in enumerate(results):
    result.show()  # 显示结果
    result.save(filename=f"result_{i}.jpg")  # 保存结果
    # 访问详细信息
    boxes = result.boxes  # 边界框信息
    masks = result.masks  # 掩码信息
    confs = result.boxes.conf  # 置信度信息
```

**参数说明：**
- `refer_image`: 参考图像路径，用于定义要检测的物体类别
- `visual_bboxes`: 参考图像中多个物体的边界框列表，格式为 `[[x1, y1, x2, y2], ...]`
- `visual_cls`: 参考图像中每个物体对应的类别 id 列表，长度必须与 `visual_bboxes` 相同
- `test_images`: 测试图像列表，支持批量推理多张图像，可以是路径列表或 np.ndarray 列表

**注意事项：**
- `visual_bboxes` 和 `visual_cls` 的长度必须相同
- 该函数不需要预先注册 target，可以直接使用
- 支持对多张测试图像进行批量推理，提高效率

### 接口说明

#### 初始化参数

`YoloeVPInterface` 继承自 `BaseInterface`，支持以下初始化方式：

- `config_path` (Optional[str]): YAML 配置文件路径
- `config` (Optional[Dict]): 配置字典，会覆盖 `config_path` 中的设置

**配置项说明：**
- `checkpoint_path` (str, 必需): 模型权重文件路径
- `device` (str, 可选): 设备类型，'cuda' 或 'cpu'，默认 'cuda'
- `target_list` (List[Dict], 可选): 目标列表，每个目标包含：
  - `target_name` (str): 目标类别名称
  - `ref_image_path` (str): 参考图像路径
  - `visual_bbox` (List[int]): 参考图像中物体的坐标 [x1,y1,x2,y2]
  - `visual_cls` (int): 参考图像中该物体所属的类别 id，默认 0

#### 主要方法

- `inference(image, target="", **kwargs)`: 执行推理，返回 Results 对象列表
- `inference_segment_one(image, target="")`: 执行推理并解析结果，返回单个 (mask, bbox) 元组
- `register_target(target_name, ref_image_path, visual_bbox, visual_cls=0)`: 动态注册新的参考图像和目标
- `inference_batch_multi_targets(refer_image, visual_bboxes, visual_cls, test_images, **kwargs)`: 批量推理多张测试图像，支持在参考图像中指定多个类别的物体
