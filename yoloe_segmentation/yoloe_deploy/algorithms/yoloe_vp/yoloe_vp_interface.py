"""YOLOE-VP 推理接口。

支持视觉提示（参考图像）的实例分割模型接口，可以输入一张参考图像及其要分割
的物体在图像中的坐标，模型可分割出测试图像中的同类目标，输出二值掩码。

Authors: guo-xiaolong
Create Date: 2025-12-11
"""

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Optional, Union

import cv2
import numpy as np
from ultralytics import YOLOE
from ultralytics.models.yolo.yoloe import YOLOEVPSegPredictor

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from algorithms.base_interface import BaseInterface


class YoloeVPInterface(BaseInterface):
    """YOLOE-VP 接口类，用于基于参考图像的分割推理。

    支持两种推理模式：
    1. 单目标推理：通过 register_target 注册参考图像和目标坐标，然后使用 inference 或
       inference_segment_one 对单张图像进行推理。
    2. 批量多目标推理：使用 inference_batch_multi_targets 在参考图像中指定多个类别的物体，
       然后对多张测试图像进行批量推理。
    """

    def __init__(
        self,
        *,
        config: Optional[Dict] = None,
        config_path: Optional[str] = None,
    ):
        """初始化 YOLOE-VP 接口。

        参数：
            config (Optional[Dict])：配置字典，会覆盖 config_path 中的设置。
            config_path (Optional[str])：YAML 配置文件的路径。

        配置项说明：
            checkpoint_path (str)：模型权重文件路径（必需）。
            target_list (List[Dict])：目标列表，每个目标包含：
                - target_name (str)：目标类别名称
                - ref_image_path (str)：参考图像路径
                - visual_bbox (List[int])：参考图像中物体的坐标 [x1,y1,x2,y2]
                - visual_cls (int)：参考图像中该物体所属的类别 id，默认 0
            device (str)：设备类型，'cuda' 或 'cpu'，默认 'cuda'。

        异常：
            RuntimeError：当模型加载失败或设备设置失败时触发。
            ValueError：当参数组合不合法时触发。
        """
        # 调用基类初始化，加载配置
        BaseInterface.__init__(self, config=config, config_path=config_path)

        config_data: Dict = dict(self.config)

        # 从配置中读取必需参数
        self.checkpoint_path = config_data.get("checkpoint_path")
        if not self.checkpoint_path:
            raise ValueError(
                "Missing `checkpoint_path` in configuration for YoloeVPInterface initialization."
            )

        # 从配置中读取可选参数
        self.device = config_data.get("device", "cuda")
        target_list_config = config_data.get("target_list", [])

        # 初始化目标列表和查找表
        self.target_list: List[str] = []
        self.ref_imgs_book: Dict[str, str] = {}
        self.visual_prompt_book: Dict[str, Dict[str, np.ndarray]] = {}

        # 加载模型
        try:
            self.yoloe: YOLOE = YOLOE(self.checkpoint_path)
        except Exception as e:
            raise RuntimeError(f"模型加载失败：{self.checkpoint_path}。错误信息：{str(e)}") from e

        # 设置设备
        try:
            self.yoloe.to(self.device)
        except Exception:
            # 如果指定设备不可用，尝试使用 CPU
            try:
                print(f"警告：无法使用设备 {self.device}，切换到 CPU")
                self.device = "cpu"
                self.yoloe.to(self.device)
            except Exception as e2:
                raise RuntimeError(f"设备设置失败。错误信息：{str(e2)}") from e2

        # 从配置中注册目标
        for target_config in target_list_config:
            target_name = target_config.get("target_name")
            ref_image_path = target_config.get("ref_image_path")
            visual_bbox = target_config.get("visual_bbox")
            visual_cls = target_config.get("visual_cls", 0)

            if not target_name or not ref_image_path or not visual_bbox:
                print(f"警告：跳过无效的目标配置：{target_config}")
                continue

            self.register_target(
                target_name=target_name,
                ref_image_path=ref_image_path,
                visual_bbox=visual_bbox,
                visual_cls=visual_cls,
            )

    def _parse_seg_results(self, results):
        """解析 YOLOE 的分割结果，返回一个二值掩码图像。

        参数：
            results：输入 YOLOE 分割结果。

        返回值：
            Tuple[Optional[np.ndarray], Optional[List[float]]]：
                - 第一个元素：二值掩码图像（尺寸与输入图像相同），如果未找到则返回 None。
                - 第二个元素：边界框信息（xyxy 格式），如果未找到则返回 None。
        """
        target_mask: Optional[np.ndarray] = None
        target_box: Optional[List[float]] = None

        for r in results:
            img: np.ndarray = np.copy(r.orig_img)
            boxes: List[List[float]] = r.boxes.xyxy.cpu().tolist()  # 边界框信息，格式为 xyxy
            cls_: List[int] = r.boxes.cls.cpu().tolist()  # 类别信息
            masks = r.masks  # 掩码信息
            confs: List[float] = r.boxes.conf.cpu().tolist()  # 置信度信息

            if masks is None:
                continue

            for b, c, conf, mask in zip(boxes, cls_, confs, masks):
                if conf < 0.5:
                    continue

                try:
                    # 将轮廓贴到画布上
                    b_mask: np.ndarray = np.zeros(img.shape[:2], np.uint8)
                    # 安全访问 mask.xy，避免空列表错误
                    if not mask.xy or len(mask.xy) == 0:
                        continue
                    contour: np.ndarray = mask.xy[0].astype(np.int32).reshape(-1, 1, 2)
                    _ = cv2.drawContours(
                        b_mask, [contour], -1, (255, 255, 255), cv2.FILLED
                    )

                    target_mask = b_mask
                    target_box = b
                except (IndexError, AttributeError, ValueError):
                    # 如果单个掩码解析失败，继续处理下一个
                    continue

        return target_mask, target_box

    def register_target(
        self,
        target_name: str,
        ref_image_path: str,
        visual_bbox: List[int],
        visual_cls: int = 0,
    ):
        """注册一个新的参考图像和目标物体坐标。

        参数：
            target_name (str)：目标类别名称，用于后续推理时指定。
            ref_image_path (str)：参考图像路径。
            visual_bbox (List[int])：参考图像中物体的坐标 [x1, y1, x2, y2]。
            visual_cls (int)：参考图像中该物体所属的类别 id，默认 0。

        异常：
            FileNotFoundError：当参考图像不存在时触发。
            ValueError：当 visual_bbox 格式不正确时触发。
        """
        resolved_ref_image = Path(ref_image_path)

        if not resolved_ref_image.exists():
            raise FileNotFoundError(f"参考图像不存在：{resolved_ref_image}。请检查路径是否正确。")

        if len(visual_bbox) != 4:
            raise ValueError("visual_bbox 必须包含4个元素，格式为 [x1, y1, x2, y2]")

        # 如果 target 已存在，则更新；否则添加新的
        self.ref_imgs_book[target_name] = str(resolved_ref_image)
        self.visual_prompt_book[target_name] = dict(
            bboxes=np.array([visual_bbox], dtype=np.int32),
            cls=np.array([visual_cls], dtype=np.int32),
        )

        # 如果 target_name 不在 target_list 中，则添加
        if target_name not in self.target_list:
            self.target_list.append(target_name)

    def inference(
        self, image: Union[str, Path, np.ndarray], target: str = "", **kwargs
    ):
        """对单张图像进行分割，返回掩码和边界框。

        参数：
            image (Union[str, Path, np.ndarray])：输入图像路径或内存中的图像数组。
            target (str)：目标类别名称，必须在 target_list 中。
            **kwargs：其他可选参数。

        返回值：
            [List]：return a list of Results objects
            示例：
                for result in results:
                    boxes = result.boxes  # Boxes object for bounding box outputs
                    masks = result.masks  # Masks object for segmentation masks outputs
                    keypoints = result.keypoints  # Keypoints object for pose outputs
                    probs = result.probs  # Probs object for classification outputs
                    obb = result.obb  # Oriented boxes object for OBB outputs
                    result.show()  # display to screen
                    result.save(filename="result.jpg")  # save to disk
        异常：
            ValueError：当 target_list 为空或 target 不在 target_list 中时触发。
            RuntimeError：当模型推理失败时触发。
        """
        if not self.target_list:
            raise ValueError(
                "当前没有注册任何 target。请先使用 register_target 方法注册参考图像和目标坐标，"
                "或在配置文件中提供 target_list。"
            )

        if target not in self.target_list:
            raise ValueError(
                f"Target '{target}' 不在已注册的 target_list 中。"
                f"已注册的 targets: {self.target_list}。"
                f"请使用 register_target 方法注册该 target。"
            )

        # 验证输入图像
        source = image
        if isinstance(source, (str, Path)):
            source_path = Path(source) if isinstance(source, str) else source
            if not source_path.exists():
                raise FileNotFoundError(f"输入图像不存在：{source_path}")
            source = str(source_path)

        # 执行推理
        try:
            results = self.yoloe.predict(
                source,  # 支持路径或np.ndarray
                refer_image=self.ref_imgs_book[target],  # 传入参考图像路径
                visual_prompts=self.visual_prompt_book[target],  # 传入参考图像中每个物体的坐标信息
                predictor=YOLOEVPSegPredictor,
                **kwargs,
            )
        except Exception as e:
            raise RuntimeError(f"模型推理失败。错误信息：{str(e)}") from e

        return results

    def inference_segment_one(
        self, image: Union[str, Path, np.ndarray], target: str = ""
    ):
        """对单张图像进行分割，返回掩码和边界框。

        参数：
            image (Union[str, Path, np.ndarray])：输入图像路径或内存中的图像数组。
            target (str)：目标类别名称，必须在 target_list 中。

        返回值：
            Tuple[Optional[np.ndarray], Optional[List[float]]]：
                - 第一个元素：二值掩码图像（尺寸与输入图像相同），如果未找到则返回 None。
                - 第二个元素：边界框信息（xyxy 格式），如果未找到则返回 None。

        异常：
            ValueError：当 target_list 为空或 target 不在 target_list 中时触发。
            RuntimeError：当模型推理失败时触发。
        """
        results = self.inference(image, target)

        # 检查推理结果
        if not results or len(results) == 0:
            return None, None

        if results[0].masks is None:
            return None, None

        # 解析结果
        seg_mask, box = self._parse_seg_results(results)
        return seg_mask, box

    def inference_batch_multi_targets(
        self,
        refer_image: Union[str, Path],
        visual_bboxes: List[List[int]],
        visual_cls: List[int],
        test_images: List[Union[str, Path, np.ndarray]],
        **kwargs,
    ):
        """对多张测试图像进行批量推理，支持在参考图像中指定多个类别的物体。

        该函数允许用户传入一张参考图像，在参考图像中指定多个类别的物体（通过 bboxes 和 cls），
        然后对多张测试图像进行推理，检测并分割出与参考图像中指定物体同类的目标。

        参数：
            refer_image (Union[str, Path])：参考图像路径，用于定义要检测的物体类别。
            visual_bboxes (List[List[int]])：参考图像中多个物体的边界框列表，
                每个边界框格式为 [x1, y1, x2, y2]，长度必须与 visual_cls 相同。
            visual_cls (List[int])：参考图像中每个物体对应的类别 id 列表，
                长度必须与 visual_bboxes 相同。
            test_images (List[Union[str, Path, np.ndarray]])：测试图像列表，
                可以是图像路径列表或内存中的图像数组列表，支持批量推理多张图像。
            **kwargs：其他可选参数，会传递给 model.predict。

        返回值：
            List：返回一个 Results 对象列表，每个元素对应一张测试图像的推理结果。
                示例：
                    results = segment.inference_batch_multi_targets(...)
                    for i, result in enumerate(results):
                        result.show()  # 显示结果
                        result.save(filename=f"result_{i}.jpg")  # 保存结果
                        boxes = result.boxes  # 边界框信息
                        masks = result.masks  # 掩码信息

        异常：
            FileNotFoundError：当参考图像或测试图像不存在时触发。
            ValueError：当参数格式不正确或长度不匹配时触发。
            RuntimeError：当模型推理失败时触发。

        示例：
            >>> segment = YoloeVPInterface(config_path="./config.yaml")
            >>> results = segment.inference_batch_multi_targets(
            ...     refer_image="./ref_template/ref_freezer_cola_can_20251215.png",
            ...     visual_bboxes=[[579, 394, 622, 487], [785, 398, 845, 527]],
            ...     visual_cls=[0, 1],
            ...     test_images=["./test_data/img1.png", "./test_data/img2.png"]
            ... )
            >>> for result in results:
            ...     result.save()
        """
        # 验证参考图像
        refer_image_path = (
            Path(refer_image) if isinstance(refer_image, str) else refer_image
        )
        if not refer_image_path.exists():
            raise FileNotFoundError(f"参考图像不存在：{refer_image_path}")

        # 验证 visual_bboxes 和 visual_cls 的长度和格式
        if len(visual_bboxes) != len(visual_cls):
            raise ValueError(
                f"visual_bboxes 和 visual_cls 的长度必须相同。"
                f"当前 visual_bboxes 长度：{len(visual_bboxes)}，visual_cls 长度：{len(visual_cls)}"
            )

        if len(visual_bboxes) == 0:
            raise ValueError("visual_bboxes 和 visual_cls 不能为空列表")

        # 验证每个 bbox 的格式
        for i, bbox in enumerate(visual_bboxes):
            if len(bbox) != 4:
                raise ValueError(
                    f"visual_bboxes[{i}] 格式不正确，必须包含4个元素 [x1, y1, x2, y2]，"
                    f"当前长度：{len(bbox)}"
                )

        # 验证测试图像列表
        if not test_images or len(test_images) == 0:
            raise ValueError("test_images 不能为空列表")

        # 验证测试图像路径
        validated_test_images = []
        for img in test_images:
            if isinstance(img, (str, Path)):
                img_path = Path(img) if isinstance(img, str) else img
                if not img_path.exists():
                    raise FileNotFoundError(f"测试图像不存在：{img_path}")
                validated_test_images.append(str(img_path))
            else:
                # 如果是 np.ndarray，直接使用
                validated_test_images.append(img)

        # 构建 visual_prompts
        visual_prompts = dict(
            bboxes=np.array(visual_bboxes, dtype=np.int32),
            cls=np.array(visual_cls, dtype=np.int32),
        )

        # 执行批量推理
        try:
            results = self.yoloe.predict(
                validated_test_images,  # 支持多张图像
                refer_image=str(refer_image_path),  # 参考图像路径
                visual_prompts=visual_prompts,  # 多个物体的坐标和类别信息
                predictor=YOLOEVPSegPredictor,
                **kwargs,
            )
        except Exception as e:
            raise RuntimeError(f"模型推理失败。错误信息：{str(e)}") from e

        return results


def parse_args():
    """解析命令行参数。

    返回值:
        argparse.Namespace: 解析后的命令行参数。
    """
    parser = argparse.ArgumentParser(description="YOLOE-VP 推理接口，支持视觉提示（参考图像）的实例分割模型")
    parser.add_argument(
        "--image",
        type=str,
        required=True,
        help="输入测试图像路径",
    )
    parser.add_argument(
        "--config_path",
        type=str,
        help="YAML 配置文件路径（推荐使用）",
    )

    parser.add_argument(
        "--output",
        type=str,
        required=True,
        help="输出二值掩码图像路径",
    )
    parser.add_argument(
        "--target",
        type=str,
        default="fg_red_bull",
        help="目标类别名称（默认：fg_red_bull）",
    )

    return parser.parse_args()


def main():
    """主函数。"""
    args = parse_args()

    # 构建配置
    config = {}
    config_path = args.config_path if args.config_path else None

    # 初始化分割器
    try:
        segment = YoloeVPInterface(config=config, config_path=config_path)
    except Exception as e:
        print(f"错误：初始化分割器失败。{str(e)}", file=sys.stderr)
        return 1

    # 执行分割
    try:
        # 解析结果获取掩码
        binary_mask, bbox = segment.inference_segment_one(
            args.image, target=args.target
        )
    except Exception as e:
        print(f"错误：推理失败。{str(e)}", file=sys.stderr)
        return 1

    # 保存结果
    if binary_mask is not None:
        try:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(output_path), binary_mask)
            print(f"[MASK] 二值掩码已保存：{args.output}")
            return 0
        except Exception as e:
            print(f"错误：保存结果失败。{str(e)}", file=sys.stderr)
            return 1
    else:
        print("警告：未找到分割掩码，输出文件未创建。", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
