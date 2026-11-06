# -*- coding: utf-8 -*-
"""生成灰度工坊的应用图标（无需外部素材）。"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"


def make_icon(size: int = 1024) -> Image.Image:
    scale = 2
    w = h = size * scale
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    nx = xx / (w - 1)
    ny = yy / (h - 1)

    # 深色圆角背景
    bg = np.zeros((h, w, 4), dtype=np.uint8)
    bg[..., 0] = 23
    bg[..., 1] = 26
    bg[..., 2] = 33
    bg[..., 3] = 255
    bg_img = Image.fromarray(bg, "RGBA")

    # 背景轻微上亮下暗
    shade = (1.0 - ny * 0.22).astype(np.float32)
    arr = np.asarray(bg_img, dtype=np.float32)
    arr[..., :3] *= shade[..., None]
    bg_img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA")

    # 圆形镜头区域外的遮罩
    cx, cy = w * 0.5, h * 0.5
    radius = w * 0.315
    inside = (xx - cx) ** 2 + (yy - cy) ** 2 <= radius ** 2
    edge = np.clip((radius - np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)) / (w * 0.012), 0, 1)

    # 左半：彩色渐变；右半：灰度渐变，中间柔和过渡
    split = nx
    blend = np.clip((split - 0.46) / 0.08, 0, 1)  # 0=彩色 1=灰度
    blend = blend * blend * (3 - 2 * blend)

    # 彩色侧：青蓝到紫红
    top = np.array([34, 211, 238], np.float32)
    bottom = np.array([139, 92, 246], np.float32)
    color_side = top[None, None, :] * (1 - ny[..., None]) + bottom[None, None, :] * ny[..., None]
    # 增加一点横向明暗
    color_side = color_side * (0.88 + 0.25 * (1 - nx[..., None]))

    # 灰度侧：由白到深灰
    g = 245.0 * (1 - ny) + 34.0 * ny
    gray_side = np.dstack([g, g, g])

    lens_rgb = color_side * (1 - blend[..., None]) + gray_side * blend[..., None]
    lens_rgb = np.clip(lens_rgb, 0, 255)

    # 圆内叠到底图上
    base = np.asarray(bg_img, dtype=np.float32)
    mask = (inside * edge)[..., None]
    out_rgb = base[..., :3] * (1 - mask) + lens_rgb * mask
    out = np.dstack([out_rgb, np.full((h, w), 255.0, np.float32)])
    out = np.clip(out, 0, 255).astype(np.uint8)
    icon = Image.fromarray(out, "RGBA")

    # 白色细圆环
    draw = ImageDraw.Draw(icon)
    ring = radius
    ring_width = max(2, int(w * 0.007))
    draw.ellipse(
        [cx - ring, cy - ring, cx + ring, cy + ring],
        outline=(255, 255, 255, 178),
        width=ring_width,
    )

    # 高光弧线
    draw.arc(
        [cx - ring, cy - ring, cx + ring, cy + ring],
        start=196,
        end=326,
        fill=(255, 255, 255, 135),
        width=max(2, int(w * 0.012)),
    )

    icon = icon.resize((size, size), Image.Resampling.LANCZOS)

    # 圆角矩形裁切
    mask = Image.new("L", (size, size), 0)
    mask_draw = ImageDraw.Draw(mask)
    margin = int(size * 0.025)
    radius_px = int(size * 0.22)
    mask_draw.rounded_rectangle(
        [margin, margin, size - margin - 1, size - margin - 1],
        radius=radius_px,
        fill=255,
    )
    icon.putalpha(mask)
    return icon


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    icon = make_icon(1024)
    icon.save(ASSETS / "app_logo.png")
    icon.resize((256, 256), Image.Resampling.LANCZOS).save(ASSETS / "app_icon.png")
    icon.save(
        ASSETS / "app_icon.ico",
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print(f"图标已生成：{ASSETS}")


if __name__ == "__main__":
    main()
