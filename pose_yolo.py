#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ROS2 感知 6D 位姿接收 + PoseStamped 运动目标发布 + 手爪 topic 控制。

上游适配 yolo_pose_estimation_ros2 管线，订阅其最终发布给运控端的话题。

yolo 管线最终输出 topic（二选一）：

/perception/detections_in_base  (std_msgs/String, JSON)
   - 由 perception_detections_to_base 节点发布，是 yolo 管线最终给运控端的话题
   - 订阅 /perception_object/detections (Detection2DArray)，转换到 arm_base 系后输出
   - JSON 结构:
     {
       "frame_id": "...",
       "count": N,
       "objects": [
         {
           "arm_base_xyz": [x, y, z],
           "class_name": "...",
           ...
         }
       ]
     }
   - 坐标已在 arm_base 系下，可直接用于运动控制
   - 注：/perception_object/pose_estimates 是 perception_object_pose 包内部中间话题，
     不是给运控端的最终输出

本程序默认订阅 /perception/detections_in_base（string_json 模式），
从 JSON 中提取第一个目标的 x/y/z 坐标，然后执行与 pose.py 完全一致的
运动序列（home → pregrasp → grasp → close → retreat）。

功能流程：
1. 订阅感知模块发布的目标位姿；
2. 从 JSON 中提取目标 x/y/z；
3. 根据 ARM_TYPE 自动选择左臂或右臂目标发布话题；
4. 根据 ARM_TYPE 自动选择左手或右手控制话题；
5. 手爪先打开；
6. 发布 home 位姿；
7. 发布预接近位姿：x + 0.01, y + 0.02, z；
8. 发布目标位姿：x, y, z；
9. 到达目标位姿后关闭手爪；
10. 发布撤离位姿：x + 0.01, y + 0.02, z。

说明：
- 业务语义：0=关闭、1=打开（日志与常量 HAND_CLOSE_VALUE / HAND_OPEN_VALUE）；
- 灵巧手 target_command 控制器实际：open_config=0、close_config=1，脚本会自动映射；
- 同时发布 target_percent（0 关 / 1 开）与 target_joint_position 以提高闭合成功率；
- 运动目标 topic 类型：geometry_msgs/msg/PoseStamped；
- 默认目标坐标系：arm_base。
"""

import json
import time
import threading
from typing import Any, Dict

import rclpy
from rclpy.node import Node

from geometry_msgs.msg import Pose, PoseStamped
from std_msgs.msg import Float64, Float64MultiArray, Int32, String


# ============================================================
# 基础配置
# ============================================================

ARM_TYPE = "left_arm"                 # 可选: "right_arm" / "left_arm"

# ---- yolo 管线最终发布给运控端的话题 ----
PERCEPTION_POSE_TOPIC = "/perception/detections_in_base"
PERCEPTION_MSG_TYPE = "string_json"    # yolo 管线使用 std_msgs/String 包装 JSON

RIGHT_ARM_TARGET_TOPIC = "/right_target/stamped"
LEFT_ARM_TARGET_TOPIC = "/left_target/stamped"

RIGHT_HAND_COMMAND_TOPIC = "/right_hand_controller/target_command"
LEFT_HAND_COMMAND_TOPIC = "/left_hand_controller/target_command"
RIGHT_HAND_PERCENT_TOPIC = "/right_hand_controller/target_percent"
LEFT_HAND_PERCENT_TOPIC = "/left_hand_controller/target_percent"
RIGHT_HAND_JOINT_TOPIC = "/right_hand_controller/target_joint_position"
LEFT_HAND_JOINT_TOPIC = "/left_hand_controller/target_joint_position"

POSE_FRAME_ID = "arm_base"
PROCESS_ONCE = True


# ============================================================
# 手爪控制配置
# ============================================================

# 业务语义（日志显示）
HAND_CLOSE_VALUE = 0
HAND_OPEN_VALUE = 1

# right_hand_controller 参数 target_command_open_config / close_config
HAND_TARGET_COMMAND_OPEN = 0
HAND_TARGET_COMMAND_CLOSE = 1

# target_percent：0.0 完全闭合，1.0 完全张开
HAND_PERCENT_CLOSE = 0.0
HAND_PERCENT_OPEN = 1.0

# 与控制器 home_1(闭合) / home_2(张开) 一致，7 关节
# RIGHT_HAND_CLOSE_JOINTS = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
RIGHT_HAND_OPEN_JOINTS = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
RIGHT_HAND_CLOSE_JOINTS = [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]
LEFT_HAND_CLOSE_JOINTS = RIGHT_HAND_CLOSE_JOINTS
LEFT_HAND_OPEN_JOINTS = RIGHT_HAND_OPEN_JOINTS

WAIT_AFTER_HAND_COMMAND_SECONDS = 2.5
HAND_COMMAND_REPEAT = 5
HAND_COMMAND_REPEAT_INTERVAL_SECONDS = 2


# ============================================================
# 运动等待时间
# 注意：这里是纯 topic 发布控制，没有读取机器人到位反馈。
# 如果后续有到位反馈 topic，应替换为真实到位判断。
# ============================================================

WAIT_AFTER_HOME_SECONDS = 3.0
WAIT_AFTER_APPROACH_SECONDS = 3.0
WAIT_AFTER_TARGET_SECONDS = 3.0
WAIT_AFTER_RETREAT_SECONDS = 3.0


# ============================================================
# 侧面抓取预接近偏移（arm_base 系，单位 m）
# 右臂：home 在 y 负侧，沿 +Y 靠近目标 → 预抓取在目标「外侧」（y 更小）
# 左臂：沿 -Y 靠近 → 预抓取在目标外侧（y 更大）
# ============================================================
##修改1
APPROACH_OFFSET_X_M = -0.06
APPROACH_OFFSET_Z_M = 0.0

RIGHT_SIDE_APPROACH_OFFSET_Y_M = -0.08
LEFT_SIDE_APPROACH_OFFSET_Y_M = 0.06

# 最终抓取点相对感知目标的偏移（arm_base 系）：x-0, y-0.03, z-0
GRASP_OFFSET_X_M = -0.03
GRASP_OFFSET_Y_M = 0.04
GRASP_OFFSET_Z_M = 0.0


# ============================================================
# Home 位姿
# 这里沿用你原程序中的 right arm home。
# 如果使用 left_arm，需要替换为左臂的 home。
# ============================================================
##修改2
RIGHT_HOME_POSITION = {
    "x": 0.5565265802877374,
    "y": -0.31860213098720186,
    "z": -0.18125616096278593,
}

RIGHT_HOME_ORIENTATION = {
    "x": 0.7167571621514962,
    "y": 9.861487573239968e-05,
    "z": 0.6972945122391361,
    "w": 0.006286810067530681,
}

# 左臂 home 这里先给出占位值，实际使用左臂时必须改成真实安全 home。
LEFT_HOME_POSITION = {
    # "x": 0.45172005986464586,
    # "y": 0.32963833819677746,
    # "z": -0.21422709197187167,
    "x": 0.3022326417106297,
    "y": 0.2796852737351475,
    "z": -0.2266528328182925,
}

LEFT_HOME_ORIENTATION = {
    # "x": 0.7178602779810895,
    # "y": 0.0012361225355033965,
    # "z": 0.6961772220490243,
    # "w": -0.0035169302087745846,
    "x": 0.7267607705458271,
    "y": 0.025808959025820186,
    "z": 0.6859923127779343,
    "w": 0.02381652449917735,

}


# ============================================================
# 目标位姿统一末端姿态
# 这里沿用你原程序中的 TARGET_ORIENTATION。
# ============================================================

RIGHT_TARGET_ORIENTATION = {
    "x": 0.7169629970943424,
    "y": -0.0013946153772783475,
    "z": 0.6970725177688195,
    "w": 0.007212545797867867,
}

# 左臂目标姿态这里先给出镜像占位值，实际使用左臂时建议用标定后的真实四元数。
#修改3
LEFT_TARGET_ORIENTATION = {
    # "x": 0.7150327476070377,
    # "y": -0.0013946153772783475,
    # "z": 0.6990819336239765,
    # "w": -0.0033794333148377,
    "x": 0.7255750767259829,
    "y": -0.043656776281680076,
    "z": 0.6855268378377561,
    "w": -0.041083433680039645,

}


class PoseTopicGraspExecutor(Node):
    """基于 ROS2 topic 的目标位姿执行节点。"""

    def __init__(self):
        super().__init__("pose_topic_grasp_executor")

        self.arm_type = ARM_TYPE
        self.process_once = PROCESS_ONCE

        self._busy = False
        self._finished = False
        self._lock = threading.Lock()

        self.motion_target_topic = self._resolve_motion_target_topic()
        self.hand_command_topic = self._resolve_hand_command_topic()
        self.hand_percent_topic = self._resolve_hand_percent_topic()
        self.hand_joint_topic = self._resolve_hand_joint_topic()

        self.get_logger().info(f"当前使用机械臂: {self.arm_type}")
        self.get_logger().info(f"目标位姿发布 topic: {self.motion_target_topic}")
        self.get_logger().info(f"手爪 target_command: {self.hand_command_topic}")
        self.get_logger().info(f"手爪 target_percent: {self.hand_percent_topic}")
        self.get_logger().info(f"手爪 target_joint_position: {self.hand_joint_topic}")

        self.motion_target_pub = self.create_publisher(
            PoseStamped,
            self.motion_target_topic,
            10,
        )

        self.hand_command_pub = self.create_publisher(
            Int32,
            self.hand_command_topic,
            10,
        )
        self.hand_percent_pub = self.create_publisher(
            Float64,
            self.hand_percent_topic,
            10,
        )
        self.hand_joint_pub = self.create_publisher(
            Float64MultiArray,
            self.hand_joint_topic,
            10,
        )

        self._create_perception_subscription()

        time.sleep(0.5)

        self.get_logger().info(
            f"节点启动完成，等待感知位姿: {PERCEPTION_POSE_TOPIC}, "
            f"消息类型: {PERCEPTION_MSG_TYPE}"
        )

    # ========================================================
    # topic 选择
    # ========================================================

    def _resolve_motion_target_topic(self) -> str:
        """根据当前机械臂选择目标 PoseStamped 发布话题。"""

        if self.arm_type == "right_arm":
            return RIGHT_ARM_TARGET_TOPIC

        if self.arm_type == "left_arm":
            return LEFT_ARM_TARGET_TOPIC

        raise ValueError(f"不支持的 ARM_TYPE: {self.arm_type}")

    def _resolve_hand_command_topic(self) -> str:
        if self.arm_type == "right_arm":
            return RIGHT_HAND_COMMAND_TOPIC
        if self.arm_type == "left_arm":
            return LEFT_HAND_COMMAND_TOPIC
        raise ValueError(f"不支持的 ARM_TYPE: {self.arm_type}")

    def _resolve_hand_percent_topic(self) -> str:
        if self.arm_type == "right_arm":
            return RIGHT_HAND_PERCENT_TOPIC
        if self.arm_type == "left_arm":
            return LEFT_HAND_PERCENT_TOPIC
        raise ValueError(f"不支持的 ARM_TYPE: {self.arm_type}")

    def _resolve_hand_joint_topic(self) -> str:
        if self.arm_type == "right_arm":
            return RIGHT_HAND_JOINT_TOPIC
        if self.arm_type == "left_arm":
            return LEFT_HAND_JOINT_TOPIC
        raise ValueError(f"不支持的 ARM_TYPE: {self.arm_type}")

    def _hand_open_joint_positions(self) -> list:
        if self.arm_type == "right_arm":
            return RIGHT_HAND_OPEN_JOINTS
        return LEFT_HAND_OPEN_JOINTS

    def _hand_close_joint_positions(self) -> list:
        if self.arm_type == "right_arm":
            return RIGHT_HAND_CLOSE_JOINTS
        return LEFT_HAND_CLOSE_JOINTS

    # ========================================================
    # 订阅感知位姿
    # ========================================================

    def _create_perception_subscription(self) -> None:
        """根据 PERCEPTION_MSG_TYPE 创建感知位姿订阅器。

        支持类型:
        - string_json:       std_msgs/String 包装的 JSON(yolo 管线）
        - pose_stamped:      geometry_msgs/PoseStamped
        - pose:              geometry_msgs/Pose
        - float64_multi_array: std_msgs/Float64MultiArray
        """

        if PERCEPTION_MSG_TYPE == "string_json":
            self.perception_sub = self.create_subscription(
                String,
                PERCEPTION_POSE_TOPIC,
                self._perception_pose_callback,
                10,
            )

        elif PERCEPTION_MSG_TYPE == "pose_stamped":
            self.perception_sub = self.create_subscription(
                PoseStamped,
                PERCEPTION_POSE_TOPIC,
                self._perception_pose_callback,
                10,
            )

        elif PERCEPTION_MSG_TYPE == "pose":
            self.perception_sub = self.create_subscription(
                Pose,
                PERCEPTION_POSE_TOPIC,
                self._perception_pose_callback,
                10,
            )

        elif PERCEPTION_MSG_TYPE == "float64_multi_array":
            self.perception_sub = self.create_subscription(
                Float64MultiArray,
                PERCEPTION_POSE_TOPIC,
                self._perception_pose_callback,
                10,
            )

        else:
            raise ValueError(
                "PERCEPTION_MSG_TYPE 仅支持: "
                "string_json / pose_stamped / pose / float64_multi_array"
            )

    def _perception_pose_callback(self, msg: Any) -> None:
        """收到感知位姿后，启动一次动作序列（执行中则静默忽略新消息）。"""

        if self.process_once and self._finished:
            return

        try:
            self._extract_target_position(msg)
        except (ValueError, TypeError):
            return

        with self._lock:
            if self._busy:
                return
            self._busy = True

        worker = threading.Thread(
            target=self._execute_sequence_from_perception,
            args=(msg,),
            daemon=True,
        )
        worker.start()

    # ========================================================
    # 感知位姿解析
    # ========================================================

    @staticmethod
    def _parse_yolo_detections_in_base(data: dict) -> Dict[str, float]:
        """
        解析 /perception/detections_in_base 的 JSON 消息。

        JSON 结构:
        {
          "frame_id": "...",
          "count": N,
          "objects": [
            {
              "arm_base_xyz": [x, y, z],
              "class_name": "...",
              ...
            }
          ]
        }
        """
        objects = data.get("objects", [])
        if not objects:
            raise ValueError("detections_in_base JSON 中 objects 为空，缺少目标")

        arm_base_xyz = objects[0].get("arm_base_xyz")
        if not arm_base_xyz or len(arm_base_xyz) < 3:
            raise ValueError(
                f"无法从 objects[0].arm_base_xyz 提取坐标: {objects[0]}"
            )

        return {
            "x": float(arm_base_xyz[0]),
            "y": float(arm_base_xyz[1]),
            "z": float(arm_base_xyz[2]),
        }

    def _extract_target_position(self, msg: Any) -> Dict[str, float]:
        """
        从感知消息中提取目标位置。

        支持的消息类型:
        - std_msgs/String (JSON): yolo 管线最终输出 (detections_in_base 格式)
        - PoseStamped: msg.pose.position.x/y/z
        - Pose:        msg.position.x/y/z
        - Float64MultiArray: msg.data[0]/[1]/[2]

        注意：
        - 当前运动使用固定 TARGET_ORIENTATION；
        - 感知位姿中的旋转分量暂不参与发布；
        - 如果后续需要使用感知旋转，可在此处扩展四元数转换逻辑。
        """

        # ---- yolo 管线: std_msgs/String 包装 JSON ----
        if isinstance(msg, String):
            raw = msg.data if msg.data else ""
            if not raw.strip():
                raise ValueError("收到空 String 消息")

            try:
                data = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"String 消息 JSON 解析失败: {exc}, raw={raw[:200]}"
                ) from exc

            return self._parse_yolo_detections_in_base(data)

        # ---- 原有兼容: PoseStamped ----
        if isinstance(msg, PoseStamped):
            position = msg.pose.position
            x = float(position.x)
            y = float(position.y)
            z = float(position.z)

        # ---- 原有兼容: Pose ----
        elif isinstance(msg, Pose):
            x = float(msg.position.x)
            y = float(msg.position.y)
            z = float(msg.position.z)

        # ---- 原有兼容: Float64MultiArray ----
        elif isinstance(msg, Float64MultiArray):
            if len(msg.data) < 3:
                raise ValueError("Float64MultiArray 至少需要包含 [x, y, z]")

            x = float(msg.data[0])
            y = float(msg.data[1])
            z = float(msg.data[2])

        else:
            raise TypeError(f"不支持的感知消息类型: {type(msg)}")

        return {
            "x": x,
            "y": y,
            "z": z,
        }

    # ========================================================
    # 位姿构造
    # ========================================================

    def _get_home_position(self) -> Dict[str, float]:
        """返回当前机械臂的 home 位置。"""

        if self.arm_type == "right_arm":
            return RIGHT_HOME_POSITION.copy()

        if self.arm_type == "left_arm":
            return LEFT_HOME_POSITION.copy()

        raise ValueError(f"不支持的 ARM_TYPE: {self.arm_type}")

    def _get_home_orientation(self) -> Dict[str, float]:
        """返回当前机械臂的 home 姿态四元数。"""

        if self.arm_type == "right_arm":
            return RIGHT_HOME_ORIENTATION.copy()

        if self.arm_type == "left_arm":
            return LEFT_HOME_ORIENTATION.copy()

        raise ValueError(f"不支持的 ARM_TYPE: {self.arm_type}")

    def _get_target_orientation(self) -> Dict[str, float]:
        """返回当前机械臂目标运动使用的固定末端姿态。"""

        if self.arm_type == "right_arm":
            return RIGHT_TARGET_ORIENTATION.copy()

        if self.arm_type == "left_arm":
            return LEFT_TARGET_ORIENTATION.copy()

        raise ValueError(f"不支持的 ARM_TYPE: {self.arm_type}")

    def _side_approach_offset_y(self) -> float:
        """侧面抓取：预接近/撤离沿 Y 轴留在目标外侧。"""
        if self.arm_type == "right_arm":
            return RIGHT_SIDE_APPROACH_OFFSET_Y_M
        if self.arm_type == "left_arm":
            return LEFT_SIDE_APPROACH_OFFSET_Y_M
        raise ValueError(f"不支持的 ARM_TYPE: {self.arm_type}")

    def _compute_pregrasp_position(self, target_position: Dict[str, float]) -> Dict[str, float]:
        """
        侧面抓取预接近位姿（在目标外侧沿 Y 留出间隙，再直线靠近抓取）。

        右臂默认：y = target_y - 0.08（在目标 robot 侧多停 8cm）
        """
        offset_y = self._side_approach_offset_y()
        return {
            "x": float(target_position["x"]) + APPROACH_OFFSET_X_M,
            "y": float(target_position["y"]) + offset_y,
            "z": float(target_position["z"]) + APPROACH_OFFSET_Z_M,
        }

    def _compute_grasp_position(self, target_position: Dict[str, float]) -> Dict[str, float]:
        """最终抓取位姿：感知 xyz 经偏移后再发布，再闭合手爪。"""
        return {
            "x": float(target_position["x"]) + GRASP_OFFSET_X_M,
            "y": float(target_position["y"]) + GRASP_OFFSET_Y_M,
            "z": float(target_position["z"]) + GRASP_OFFSET_Z_M,
        }

    def _compute_retreat_position(self, target_position: Dict[str, float]) -> Dict[str, float]:
        """撤离：沿侧面退回预接近外侧点（与 pregrasp 相同偏移）。"""
        return self._compute_pregrasp_position(target_position)

    def _build_pose_stamped(
        self,
        position: Dict[str, float],
        orientation: Dict[str, float],
    ) -> PoseStamped:
        """构造 PoseStamped 消息。"""

        msg = PoseStamped()

        now = self.get_clock().now().to_msg()
        msg.header.stamp = now
        msg.header.frame_id = POSE_FRAME_ID

        msg.pose.position.x = float(position["x"])
        msg.pose.position.y = float(position["y"])
        msg.pose.position.z = float(position["z"])

        msg.pose.orientation.x = float(orientation["x"])
        msg.pose.orientation.y = float(orientation["y"])
        msg.pose.orientation.z = float(orientation["z"])
        msg.pose.orientation.w = float(orientation["w"])

        return msg

    # ========================================================
    # 发布运动目标与手爪命令
    # ========================================================

    def _publish_motion_target(
        self,
        position: Dict[str, float],
        orientation: Dict[str, float],
        motion_name: str,
    ) -> None:
        """发布一个机器人末端目标位姿。"""

        msg = self._build_pose_stamped(position, orientation)
        self.motion_target_pub.publish(msg)

        self.get_logger().info(
            f"发布运动目标 [{motion_name}] -> "
            f"x={position['x']:.6f}, "
            f"y={position['y']:.6f}, "
            f"z={position['z']:.6f}"
        )

    def _publish_hand_action(self, *, open_hand: bool, command_name: str) -> None:
        """
        三通道同时控制灵巧手，避免仅发 target_command 语义值不生效。

        - target_command: 控制器 open_config=0 / close_config=1
        - target_percent: 0.0 关 / 1.0 开
        - target_joint_position: home_1 闭合 / home_2 张开
        """
        if open_hand:
            semantic = HAND_OPEN_VALUE
            cmd_value = HAND_TARGET_COMMAND_OPEN
            percent = HAND_PERCENT_OPEN
            joints = self._hand_open_joint_positions()
        else:
            semantic = HAND_CLOSE_VALUE
            cmd_value = HAND_TARGET_COMMAND_CLOSE
            percent = HAND_PERCENT_CLOSE
            joints = self._hand_close_joint_positions()

        cmd_msg = Int32()
        cmd_msg.data = int(cmd_value)
        percent_msg = Float64()
        percent_msg.data = float(percent)
        joint_msg = Float64MultiArray()
        joint_msg.data = [float(v) for v in joints]

        for i in range(HAND_COMMAND_REPEAT):
            self.hand_command_pub.publish(cmd_msg)
            self.hand_percent_pub.publish(percent_msg)
            self.hand_joint_pub.publish(joint_msg)
            if i + 1 < HAND_COMMAND_REPEAT:
                time.sleep(HAND_COMMAND_REPEAT_INTERVAL_SECONDS)

        action = "打开" if open_hand else "关闭"
        self.get_logger().info(
            f"发布手爪 [{command_name}] ({action}) | "
            f"semantic={semantic}, target_command={cmd_value}, "
            f"percent={percent}, joints={joints}, repeat={HAND_COMMAND_REPEAT}"
        )

    def _open_active_hand(self) -> None:
        self._publish_hand_action(open_hand=True, command_name="open_active_hand")
        time.sleep(WAIT_AFTER_HAND_COMMAND_SECONDS)

    def _close_active_hand(self) -> None:
        self._publish_hand_action(open_hand=False, command_name="close_active_hand")
        time.sleep(WAIT_AFTER_HAND_COMMAND_SECONDS)

    # ========================================================
    # 主运动序列
    # ========================================================

    def _execute_sequence_from_perception(self, msg: Any) -> None:
        """根据感知位姿执行完整动作序列。"""

        try:
            target_position = self._extract_target_position(msg)
            pregrasp_position = self._compute_pregrasp_position(target_position)
            grasp_position = self._compute_grasp_position(target_position)
            retreat_position = self._compute_retreat_position(target_position)

            home_position = self._get_home_position()
            home_orientation = self._get_home_orientation()
            target_orientation = self._get_target_orientation()

            self.get_logger().info(
                "感知目标位姿: "
                f"x={target_position['x']:.6f}, "
                f"y={target_position['y']:.6f}, "
                f"z={target_position['z']:.6f}"
            )
            self.get_logger().info(
                "抓取位姿(偏移后): "
                f"x={grasp_position['x']:.6f}, "
                f"y={grasp_position['y']:.6f}, "
                f"z={grasp_position['z']:.6f} "
                f"(x-{GRASP_OFFSET_X_M}, y-{GRASP_OFFSET_Y_M}, z-{GRASP_OFFSET_Z_M})"
            )

            self.get_logger().info(
                "动作序列(侧面抓取): "
                "open_hand -> home -> pregrasp(外侧) -> grasp(偏移) -> close_hand -> retreat(外侧) | "
                f"pregrasp_offset_y={self._side_approach_offset_y():.3f}m"
            )

            self._open_active_hand()

            self._publish_motion_target(
                position=home_position,
                orientation=home_orientation,
                motion_name="home_pose",
            )
            time.sleep(WAIT_AFTER_HOME_SECONDS)

            self._publish_motion_target(
                position=pregrasp_position,
                orientation=target_orientation,
                motion_name="pregrasp_pose",
            )
            time.sleep(WAIT_AFTER_APPROACH_SECONDS)

            self._publish_motion_target(
                position=grasp_position,
                orientation=target_orientation,
                motion_name="grasp_pose",
            )
            time.sleep(WAIT_AFTER_TARGET_SECONDS)

            self._close_active_hand()

            self._publish_motion_target(
                position=retreat_position,
                orientation=target_orientation,
                motion_name="retreat_pose",
            )
            time.sleep(WAIT_AFTER_RETREAT_SECONDS)

            self.get_logger().info("本轮抓取动作序列执行完成")

            if self.process_once:
                self._finished = True
                self.get_logger().info("PROCESS_ONCE=True，后续感知位姿将不再触发动作")

        except Exception as exc:
            self.get_logger().exception(f"执行动作序列失败: {exc}")

        finally:
            with self._lock:
                self._busy = False


def main(args=None):
    rclpy.init(args=args)

    node = None

    try:
        node = PoseTopicGraspExecutor()
        rclpy.spin(node)

    except KeyboardInterrupt:
        pass

    except Exception as exc:
        print(f"[ERROR] 节点运行失败: {exc}")

    finally:
        if node is not None:
            node.destroy_node()

        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
