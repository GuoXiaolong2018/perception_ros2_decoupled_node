#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
灵巧手控制测试脚本（独立于 pose_yolo.py，不修改其手爪逻辑）。

发布方式与 pose_yolo.py 完全一致：
  同时发布 target_command + target_percent + target_joint_position，
  重复 HAND_COMMAND_REPEAT 次，间隔 HAND_COMMAND_REPEAT_INTERVAL_SECONDS。

修改下方「测试配置」后运行：
  python3 hand_control_test.py
"""

from __future__ import annotations

import copy
import time
from typing import List, Sequence

import rclpy
from rclpy.node import Node
from std_msgs.msg import Float64, Float64MultiArray, Int32


# ============================================================
# 测试配置（改这里即可，无需命令行参数）
# ============================================================

ARM_TYPE = "left_arm"              # "left_arm" / "right_arm"

# 测试模式:
#   "open"         - 仅张开（与 pose_yolo 一致）
#   "close"        - 仅闭合
#   "open_close"   - 先张后闭
#   "thumb_sweep"  - 在基准姿态上扫掠大拇指
#   "joint_sweep"  - 扫掠指定单关节
#   "custom"       - 发 CUSTOM_JOINTS
#   "presets"      - 按 PRESET_TEST_CASES 表依次执行
TEST_MODE = "thumb_sweep"

# thumb_sweep / joint_sweep 用
SWEEP_BASE = "open"                # "open" / "close"
SWEEP_SEMANTIC = "open"            # "open" / "close"；None 表示与 SWEEP_BASE 相同

THUMB_JOINT_INDEX = 0              # 大拇指下标，不对可改为 6
JOINT_SWEEP_INDEX = 0              # joint_sweep 时下标；通常与 THUMB_JOINT_INDEX 相同

THUMB_SWEEP_VALUES = [0.0, 0.25, 0.5, 0.75, 1.0]

# custom 模式
CUSTOM_SEMANTIC = "open"           # "open" / "close"
CUSTOM_JOINTS = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.5]

WAIT_AFTER_STEP_SECONDS = 3.0


# ============================================================
# 与 pose_yolo.py 保持一致的手爪配置
# ============================================================

RIGHT_HAND_COMMAND_TOPIC = "/right_hand_controller/target_command"
LEFT_HAND_COMMAND_TOPIC = "/left_hand_controller/target_command"
RIGHT_HAND_PERCENT_TOPIC = "/right_hand_controller/target_percent"
LEFT_HAND_PERCENT_TOPIC = "/left_hand_controller/target_percent"
RIGHT_HAND_JOINT_TOPIC = "/right_hand_controller/target_joint_position"
LEFT_HAND_JOINT_TOPIC = "/left_hand_controller/target_joint_position"

HAND_CLOSE_VALUE = 0
HAND_OPEN_VALUE = 1
HAND_TARGET_COMMAND_OPEN = 0
HAND_TARGET_COMMAND_CLOSE = 1
HAND_PERCENT_CLOSE = 0.0
HAND_PERCENT_OPEN = 1.0

RIGHT_HAND_OPEN_JOINTS = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
RIGHT_HAND_CLOSE_JOINTS = [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]
LEFT_HAND_OPEN_JOINTS = RIGHT_HAND_OPEN_JOINTS
LEFT_HAND_CLOSE_JOINTS = RIGHT_HAND_CLOSE_JOINTS

HAND_COMMAND_REPEAT = 5
HAND_COMMAND_REPEAT_INTERVAL_SECONDS = 2

NUM_HAND_JOINTS = 7

JOINT_LABELS = [
    "J0(默认大拇指)",
    "J1",
    "J2",
    "J3",
    "J4",
    "J5",
    "J6",
]

PRESET_TEST_CASES = [
    {
        "name": "baseline_open",
        "semantic": "open",
        "joints": None,
        "note": "与 pose_yolo 张开一致",
    },
    {
        "name": "baseline_close",
        "semantic": "close",
        "joints": None,
        "note": "与 pose_yolo 闭合一致",
    },
    {
        "name": "open_thumb_25",
        "semantic": "open",
        "joints": [0.25, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        "note": "张开语义 + 仅 J0=0.25",
    },
    {
        "name": "open_thumb_50",
        "semantic": "open",
        "joints": [0.5, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        "note": "张开语义 + 仅 J0=0.5",
    },
    {
        "name": "open_thumb_75",
        "semantic": "open",
        "joints": [0.75, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        "note": "张开语义 + 仅 J0=0.75",
    },
    {
        "name": "close_thumb_50",
        "semantic": "close",
        "joints": [0.5, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
        "note": "闭合语义 + 仅 J0=0.5，其余指全闭",
    },
    {
        "name": "close_thumb_0",
        "semantic": "close",
        "joints": [0.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
        "note": "闭合语义 + 大拇指张开、四指闭合",
    },
    {
        "name": "custom_all_half",
        "semantic": "open",
        "joints": [0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5],
        "note": "全关节 0.5",
    },
]


class HandControlTestNode(Node):
    """仅测试手爪，发布逻辑与 pose_yolo._publish_hand_action 相同。"""

    def __init__(self, arm_type: str) -> None:
        super().__init__("hand_control_test")
        self.arm_type = arm_type

        self.hand_command_topic = self._resolve_hand_command_topic()
        self.hand_percent_topic = self._resolve_hand_percent_topic()
        self.hand_joint_topic = self._resolve_hand_joint_topic()

        self.hand_command_pub = self.create_publisher(
            Int32, self.hand_command_topic, 10
        )
        self.hand_percent_pub = self.create_publisher(
            Float64, self.hand_percent_topic, 10
        )
        self.hand_joint_pub = self.create_publisher(
            Float64MultiArray, self.hand_joint_topic, 10
        )

        self.get_logger().info(f"机械臂/手: {self.arm_type}")
        self.get_logger().info(f"测试模式: {TEST_MODE}")
        self.get_logger().info(f"target_command: {self.hand_command_topic}")
        self.get_logger().info(f"target_percent: {self.hand_percent_topic}")
        self.get_logger().info(f"target_joint_position: {self.hand_joint_topic}")

        time.sleep(0.5)

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

    def _baseline_open_joints(self) -> List[float]:
        if self.arm_type == "right_arm":
            return list(RIGHT_HAND_OPEN_JOINTS)
        return list(LEFT_HAND_OPEN_JOINTS)

    def _baseline_close_joints(self) -> List[float]:
        if self.arm_type == "right_arm":
            return list(RIGHT_HAND_CLOSE_JOINTS)
        return list(LEFT_HAND_CLOSE_JOINTS)

    @staticmethod
    def _semantic_to_channels(semantic: str) -> tuple:
        if semantic == "open":
            return (
                HAND_OPEN_VALUE,
                HAND_TARGET_COMMAND_OPEN,
                HAND_PERCENT_OPEN,
            )
        if semantic == "close":
            return (
                HAND_CLOSE_VALUE,
                HAND_TARGET_COMMAND_CLOSE,
                HAND_PERCENT_CLOSE,
            )
        raise ValueError(f"semantic 只能是 open / close，收到: {semantic}")

    def publish_hand(
        self,
        *,
        joints: Sequence[float],
        semantic: str,
        command_name: str,
    ) -> None:
        """与 pose_yolo._publish_hand_action 相同的三通道发布。"""
        if len(joints) != NUM_HAND_JOINTS:
            raise ValueError(f"joints 长度应为 {NUM_HAND_JOINTS}，收到 {len(joints)}")

        sem_val, cmd_value, percent = self._semantic_to_channels(semantic)

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

        self.get_logger().info(
            f"[{command_name}] semantic={sem_val} "
            f"target_command={cmd_value} percent={percent} "
            f"joints={[round(v, 3) for v in joints]} repeat={HAND_COMMAND_REPEAT}"
        )

    def publish_open(self, command_name: str = "open") -> None:
        self.publish_hand(
            joints=self._baseline_open_joints(),
            semantic="open",
            command_name=command_name,
        )

    def publish_close(self, command_name: str = "close") -> None:
        self.publish_hand(
            joints=self._baseline_close_joints(),
            semantic="close",
            command_name=command_name,
        )

    def joints_with_thumb(
        self,
        thumb_value: float,
        *,
        base: str,
        thumb_index: int,
    ) -> List[float]:
        if base == "open":
            joints = self._baseline_open_joints()
        elif base == "close":
            joints = self._baseline_close_joints()
        else:
            raise ValueError(f"base 只能是 open / close，收到: {base}")

        out = copy.deepcopy(joints)
        out[thumb_index] = float(thumb_value)
        return out

    def run_open_close(self, wait_s: float) -> None:
        self.publish_open("open")
        time.sleep(wait_s)
        self.publish_close("close")
        time.sleep(wait_s)

    def run_thumb_sweep(
        self,
        *,
        base: str,
        semantic: str,
        thumb_index: int,
        thumb_values: Sequence[float],
        wait_s: float,
    ) -> None:
        label = (
            JOINT_LABELS[thumb_index]
            if thumb_index < len(JOINT_LABELS)
            else f"J{thumb_index}"
        )
        self.get_logger().info(
            f"大拇指扫掠: index={thumb_index} ({label}), base={base}, "
            f"semantic={semantic}, values={list(thumb_values)}"
        )
        for i, tv in enumerate(thumb_values):
            joints = self.joints_with_thumb(
                tv, base=base, thumb_index=thumb_index
            )
            self.publish_hand(
                joints=joints,
                semantic=semantic,
                command_name=f"thumb_sweep_{i:02d}_{tv:.3f}",
            )
            time.sleep(wait_s)

    def run_single_joint_sweep(
        self,
        *,
        joint_index: int,
        base: str,
        semantic: str,
        values: Sequence[float],
        wait_s: float,
    ) -> None:
        if base == "open":
            template = self._baseline_open_joints()
        else:
            template = self._baseline_close_joints()

        label = (
            JOINT_LABELS[joint_index]
            if joint_index < len(JOINT_LABELS)
            else f"J{joint_index}"
        )
        self.get_logger().info(
            f"单关节扫掠: index={joint_index} ({label}), base={base}, "
            f"values={list(values)}"
        )
        for i, v in enumerate(values):
            joints = copy.deepcopy(template)
            joints[joint_index] = float(v)
            self.publish_hand(
                joints=joints,
                semantic=semantic,
                command_name=f"joint{joint_index}_sweep_{i:02d}_{v:.3f}",
            )
            time.sleep(wait_s)

    def _resolve_preset_joints(self, case: dict, thumb_index: int) -> List[float]:
        semantic = case["semantic"]
        raw = case.get("joints")

        if raw is None:
            if semantic == "open":
                return self._baseline_open_joints()
            return self._baseline_close_joints()

        joint_vec = [float(v) for v in raw]
        if "thumb" not in case["name"] or thumb_index == 0:
            return joint_vec

        thumb_value = joint_vec[0]
        base = (
            "open"
            if semantic == "open" or case["name"].startswith("open_")
            else "close"
        )
        out = self.joints_with_thumb(
            thumb_value, base=base, thumb_index=thumb_index
        )
        if semantic == "close" and base == "close":
            close_base = self._baseline_close_joints()
            for j in range(NUM_HAND_JOINTS):
                if j != thumb_index:
                    out[j] = close_base[j]
        return out

    def run_presets(self, wait_s: float, thumb_index: int) -> None:
        for case in PRESET_TEST_CASES:
            name = case["name"]
            semantic = case["semantic"]
            note = case.get("note", "")
            joint_vec = self._resolve_preset_joints(case, thumb_index)

            self.get_logger().info(f"--- 预设 [{name}] {note}")
            self.publish_hand(
                joints=joint_vec,
                semantic=semantic,
                command_name=name,
            )
            time.sleep(wait_s)


def _effective_semantic() -> str:
    if SWEEP_SEMANTIC is not None:
        return str(SWEEP_SEMANTIC)
    return SWEEP_BASE


def _run_test(node: HandControlTestNode) -> None:
    wait_s = WAIT_AFTER_STEP_SECONDS
    semantic = _effective_semantic()

    if TEST_MODE == "open":
        node.publish_open()
    elif TEST_MODE == "close":
        node.publish_close()
    elif TEST_MODE == "open_close":
        node.run_open_close(wait_s)
    elif TEST_MODE == "thumb_sweep":
        node.run_thumb_sweep(
            base=SWEEP_BASE,
            semantic=semantic,
            thumb_index=THUMB_JOINT_INDEX,
            thumb_values=THUMB_SWEEP_VALUES,
            wait_s=wait_s,
        )
    elif TEST_MODE == "joint_sweep":
        node.run_single_joint_sweep(
            joint_index=JOINT_SWEEP_INDEX,
            base=SWEEP_BASE,
            semantic=semantic,
            values=THUMB_SWEEP_VALUES,
            wait_s=wait_s,
        )
    elif TEST_MODE == "custom":
        if len(CUSTOM_JOINTS) != NUM_HAND_JOINTS:
            raise ValueError(
                f"CUSTOM_JOINTS 需要 {NUM_HAND_JOINTS} 个值，当前 {len(CUSTOM_JOINTS)}"
            )
        node.publish_hand(
            joints=CUSTOM_JOINTS,
            semantic=CUSTOM_SEMANTIC,
            command_name="custom",
        )
    elif TEST_MODE == "presets":
        node.run_presets(wait_s, thumb_index=THUMB_JOINT_INDEX)
    else:
        raise ValueError(
            f"未知 TEST_MODE: {TEST_MODE}，可选: open, close, open_close, "
            "thumb_sweep, joint_sweep, custom, presets"
        )


def main() -> None:
    if not (0 <= THUMB_JOINT_INDEX < NUM_HAND_JOINTS):
        raise ValueError(f"THUMB_JOINT_INDEX 必须在 [0, {NUM_HAND_JOINTS - 1}]")
    if not (0 <= JOINT_SWEEP_INDEX < NUM_HAND_JOINTS):
        raise ValueError(f"JOINT_SWEEP_INDEX 必须在 [0, {NUM_HAND_JOINTS - 1}]")

    rclpy.init()
    node = HandControlTestNode(arm_type=ARM_TYPE)

    try:
        _run_test(node)
        node.get_logger().info("测试序列结束。")
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
