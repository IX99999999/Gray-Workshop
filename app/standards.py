# -*- coding: utf-8 -*-
"""灰度标准的定义与像素换算。

所有公式都直接作用于 sRGB 编码后的 RGB 值（0~255），
只有 sRGB 相对亮度和 CIE Lab L* 会先做线性化。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Tuple

import numpy as np


@dataclass(frozen=True)
class GrayscaleStandard:
    key: str
    label: str           # 下拉列表里显示的文字
    short: str           # 输出文件名中使用的短代码
    formula: str         # 说明面板中的公式
    description: str     # 适用场景说明
    converter: Callable[[np.ndarray], np.ndarray]


def _weighted(weights: Tuple[float, float, float]) -> Callable[[np.ndarray], np.ndarray]:
    w = np.asarray(weights, dtype=np.float32)

    def convert(rgb: np.ndarray) -> np.ndarray:
        return np.tensordot(rgb, w, axes=([-1], [0]))

    return convert


def _srgb_to_linear(rgb: np.ndarray) -> np.ndarray:
    """sRGB 电光转换函数（EOTF），输入 0~1。"""
    return np.where(
        rgb <= 0.04045,
        rgb / 12.92,
        np.power((rgb + 0.055) / 1.055, 2.4),
    ).astype(np.float32)


def _linear_to_srgb(rgb: np.ndarray) -> np.ndarray:
    """sRGB 光电转换函数（OETF），输入 0~1。"""
    return np.where(
        rgb <= 0.0031308,
        rgb * 12.92,
        1.055 * np.power(rgb, 1.0 / 2.4) - 0.055,
    ).astype(np.float32)


def _srgb_luminance(rgb: np.ndarray) -> np.ndarray:
    # 先还原为线性光，按 BT.709 亮度系数得到相对亮度 Y，
    # 再编码回 sRGB，保证输出图在普通屏幕上亮度观感正确。
    linear = _srgb_to_linear(rgb)
    y = np.tensordot(linear, np.asarray([0.2126, 0.7152, 0.0722], np.float32), axes=([-1], [0]))
    return np.clip(_linear_to_srgb(np.clip(y, 0.0, 1.0)), 0.0, 1.0)


def _lab_lightness(rgb: np.ndarray) -> np.ndarray:
    # CIE 1931 相对亮度 Y → CIE Lab 的 L*（D65 白点）
    linear = _srgb_to_linear(rgb)
    y = np.clip(
        np.tensordot(linear, np.asarray([0.2126, 0.7152, 0.0722], np.float32), axes=([-1], [0])),
        0.0,
        1.0,
    )
    epsilon = (6.0 / 29.0) ** 3
    kappa = 3.0 * (6.0 / 29.0) ** 2
    f = np.where(y > epsilon, np.cbrt(y), y / kappa + 4.0 / 29.0)
    lstar = (116.0 * f - 16.0) / 100.0
    return np.clip(lstar, 0.0, 1.0)


def _average(rgb: np.ndarray) -> np.ndarray:
    return np.mean(rgb, axis=-1)


def _hsl_lightness(rgb: np.ndarray) -> np.ndarray:
    return (np.max(rgb, axis=-1) + np.min(rgb, axis=-1)) * 0.5


def _hsv_value(rgb: np.ndarray) -> np.ndarray:
    return np.max(rgb, axis=-1)


def _minimum(rgb: np.ndarray) -> np.ndarray:
    return np.min(rgb, axis=-1)


STANDARDS: Tuple[GrayscaleStandard, ...] = (
    GrayscaleStandard(
        key="bt709",
        label="BT.709 · 高清标准（推荐）",
        short="BT709",
        formula="Y = 0.2126 R + 0.7152 G + 0.0722 B",
        description=(
            "ITU-R BT.709 的高清视频亮度系数，也是 sRGB / 现代显示设备最常用的加权方式。"
            "适合绝大多数照片、1080p 视频和日常分享。"
        ),
        converter=_weighted((0.2126, 0.7152, 0.0722)),
    ),
    GrayscaleStandard(
        key="bt601",
        label="BT.601 · 标清标准",
        short="BT601",
        formula="Y = 0.299 R + 0.587 G + 0.114 B",
        description=(
            "ITU-R BT.601（原 CCIR 601）标清电视标准，也是 OpenCV、MATLAB 等工具"
            "传统灰度转换采用的经典系数。适合兼容老素材和教学演示。"
        ),
        converter=_weighted((0.299, 0.587, 0.114)),
    ),
    GrayscaleStandard(
        key="bt2020",
        label="BT.2020 · 超高清 / HDR 标准",
        short="BT2020",
        formula="Y = 0.2627 R + 0.6780 G + 0.0593 B",
        description=(
            "ITU-R BT.2020 的亮度系数，用于 4K / 8K 超高清和广色域视频。"
            "用普通 sRGB 素材转换时结果会略偏亮、绿色权重更高。"
        ),
        converter=_weighted((0.2627, 0.6780, 0.0593)),
    ),
    GrayscaleStandard(
        key="srgb",
        label="sRGB 感知亮度 · 线性光校正",
        short="sRGB",
        formula="R′G′B′ → 线性光 → 0.2126 R + 0.7152 G + 0.0722 B → sRGB",
        description=(
            "先把 sRGB 颜色还原为线性光，再加权求相对亮度，最后编码回 sRGB。"
            "比直接对屏幕数值加权更接近真实明暗关系，适合合成、蒙版和需要物理亮度的场合。"
        ),
        converter=_srgb_luminance,
    ),
    GrayscaleStandard(
        key="lab_l",
        label="CIE Lab L* · 感知明度",
        short="LabL",
        formula="R′G′B′ → 线性光 Y → L* = 116 f(Y) − 16",
        description=(
            "CIE Lab 的 L* 通道，按人眼感知均匀的方式表示明度。"
            "适合需要保留细节、做感知比较或科学图像分析，观感通常比普通加权更亮。"
        ),
        converter=_lab_lightness,
    ),
    GrayscaleStandard(
        key="average",
        label="算术平均法 · (R+G+B) / 3",
        short="Average",
        formula="Y = (R + G + B) / 3",
        description=(
            "三个颜色通道等权平均。计算最简单，但绿色和蓝色对人类视觉的贡献不同，"
            "因此画面容易显得发灰或对比不足。适合算法实验和特殊效果。"
        ),
        converter=_average,
    ),
    GrayscaleStandard(
        key="hsl",
        label="HSL 明度 · (max + min) / 2",
        short="HSL",
        formula="L = (max(R,G,B) + min(R,G,B)) / 2",
        description=(
            "HSL 色彩空间的 L 分量，也是一种常见的“去饱和”灰度算法。"
            "结果通常比加权法更亮，适合观察色相被拿掉后的明度结构。"
        ),
        converter=_hsl_lightness,
    ),
    GrayscaleStandard(
        key="hsv",
        label="HSV 明度 · 最大值",
        short="HSV",
        formula="V = max(R, G, B)",
        description=(
            "HSV 色彩空间的 V 分量（最大值法）。高饱和的蓝、红色会被提得很亮，"
            "适合做高光提取、阈值分割或灯光效果。"
        ),
        converter=_hsv_value,
    ),
    GrayscaleStandard(
        key="minimum",
        label="最小值法 · min(R,G,B)",
        short="Min",
        formula="Y = min(R, G, B)",
        description=(
            "取三个通道中最小的一个，会压暗大部分彩色区域。"
            "不是常规灰度标准，但在暗通道分析、遮罩和艺术化处理中很有用。"
        ),
        converter=_minimum,
    ),
    GrayscaleStandard(
        key="photoshop",
        label="Photoshop 亮度 · 经典系数",
        short="PS",
        formula="Y = 0.3 R + 0.59 G + 0.11 B",
        description=(
            "早期图像软件常用的近似亮度系数，与 BT.601 非常接近。"
            "适合与旧版 Photoshop 的灰度结果保持视觉一致。"
        ),
        converter=_weighted((0.3, 0.59, 0.11)),
    ),
)

STANDARD_BY_KEY: Dict[str, GrayscaleStandard] = {item.key: item for item in STANDARDS}

DEFAULT_STANDARD_KEY = "bt709"


def get_standard(key: str) -> GrayscaleStandard:
    return STANDARD_BY_KEY.get(key, STANDARD_BY_KEY[DEFAULT_STANDARD_KEY])


def label_to_key(label: str) -> str:
    for standard in STANDARDS:
        if standard.label == label:
            return standard.key
    return DEFAULT_STANDARD_KEY


def rgb_u8_to_gray_u8(rgb: np.ndarray, standard_key: str) -> np.ndarray:
    """把 uint8 / RGB 数组转换成 uint8 灰度数组。

    rgb 的形状为 (H, W, 3)，返回 (H, W)。浮点中间结果用 0~1 表示，
    最后四舍五入回 0~255，避免截断带来的系统偏暗。
    """
    if rgb.ndim != 3 or rgb.shape[-1] < 3:
        raise ValueError("RGB 数组必须是 (H, W, 3) 形状")
    data = np.asarray(rgb[..., :3])
    if data.dtype == np.uint8:
        data = data.astype(np.float32) / 255.0
    elif data.dtype.kind == "f":
        # 允许调用方传入 0~1 的浮点数组
        if data.size and float(np.nanmax(data)) > 1.0001:
            data = data.astype(np.float32) / 255.0
        else:
            data = data.astype(np.float32, copy=False)
    else:
        data = data.astype(np.float32) / 255.0
    data = np.clip(data, 0.0, 1.0)
    gray = get_standard(standard_key).converter(data)
    gray = np.clip(gray, 0.0, 1.0)
    return np.rint(gray * 255.0).astype(np.uint8)
