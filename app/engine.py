# -*- coding: utf-8 -*-
"""图片 / 视频灰度转换引擎。

图片使用 Pillow + NumPy 精确套用所选灰度公式；
视频使用 ffmpeg 解码为 RGB 原始帧，逐帧套用同一公式，
再用 libx264 编码，并尽量保留原视频的第一条音轨。
"""

from __future__ import annotations

import ctypes
import math
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional, Tuple

import numpy as np
from PIL import Image, ImageOps

from .standards import get_standard, rgb_u8_to_gray_u8

try:
    import imageio_ffmpeg
except Exception:  # pragma: no cover - 仅在依赖损坏时触发
    imageio_ffmpeg = None


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
VIDEO_SUFFIXES = {
    ".mp4", ".mov", ".mkv", ".avi", ".m4v", ".wmv", ".flv", ".webm",
    ".ts", ".mts", ".m2ts", ".3gp", ".mpg", ".mpeg", ".ogv",
}

IMAGE_FORMAT_CHOICES = (
    ("auto", "自动（保持原格式）"),
    ("png", "PNG（无损）"),
    ("jpeg", "JPEG（质量 95）"),
    ("webp", "WebP（无损）"),
    ("tiff", "TIFF（无损）"),
)

_FORMAT_INFO = {
    "png": (".png", "PNG"),
    "jpeg": (".jpg", "JPEG"),
    "webp": (".webp", "WEBP"),
    "tiff": (".tif", "TIFF"),
    "bmp": (".bmp", "BMP"),
}

_AUTO_FORMAT_BY_SUFFIX = {
    ".jpg": "jpeg",
    ".jpeg": "jpeg",
    ".png": "png",
    ".webp": "webp",
    ".bmp": "bmp",
    ".tif": "tiff",
    ".tiff": "tiff",
}

_progress_cb = Callable[[float, str], None]
_cancel_event_type = Optional[threading.Event]

_FFMPEG_LOCK = threading.Lock()
_FFMPEG_PATH: Optional[str] = None
_FFMPEG_CHECKED = False
_ENCODER_LOCK = threading.Lock()
_ENCODER: Optional[str] = None

_CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


class ConversionCancelled(Exception):
    """用户主动停止转换。"""


@dataclass
class ConversionResult:
    src: Path
    outputs: list = field(default_factory=list)
    note: str = ""
    elapsed: float = 0.0


@dataclass
class PreviewData:
    image: Image.Image       # 已缩放好的 RGB 预览图
    source_kind: str         # "image" / "video"
    detail: str = ""
    alpha: Optional[Image.Image] = None  # 透明通道（与 image 同尺寸）


# ---------------------------------------------------------------------------
# 路径与文件工具
# ---------------------------------------------------------------------------

def media_kind(path: Path) -> Optional[str]:
    suffix = path.suffix.lower()
    if suffix in IMAGE_SUFFIXES:
        return "image"
    if suffix in VIDEO_SUFFIXES:
        return "video"
    return None


def human_size(size: int) -> str:
    value = float(max(0, size))
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024.0 or unit == "GB":
            if unit == "B":
                return f"{int(value)} B"
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} GB"


def desktop_dir() -> Path:
    """尽量找到当前用户的“桌面”，兼容中文桌面和 XDG 设置。"""
    if os.name == "nt":
        try:
            buf = ctypes.create_unicode_buffer(1024)
            # CSIDL_DESKTOPDIRECTORY = 0x0010
            if ctypes.windll.shell32.SHGetFolderPathW(None, 0x0010, None, 0, buf) == 0:
                candidate = Path(buf.value)
                if candidate.is_dir():
                    return candidate
        except Exception:
            pass

    home = Path.home()
    # Linux 中文桌面：~/.config/user-dirs.dirs 中通常有 XDG_DESKTOP_DIR="$HOME/桌面"
    user_dirs = home / ".config" / "user-dirs.dirs"
    if user_dirs.is_file():
        try:
            for line in user_dirs.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if line.startswith("XDG_DESKTOP_DIR="):
                    value = line.split("=", 1)[1].strip().strip('"')
                    value = value.replace("$HOME", str(home))
                    candidate = Path(value)
                    if candidate.is_dir():
                        return candidate
        except Exception:
            pass

    for name in ("Desktop", "桌面"):
        candidate = home / name
        if candidate.is_dir():
            return candidate
    return home


def default_output_dir() -> Path:
    return desktop_dir() / "灰度输出"


def output_stem(src: Path, standard_key: str) -> str:
    standard = get_standard(standard_key)
    return f"{src.stem}_灰度_{standard.short}"


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    parent = path.parent
    stem = path.stem
    suffix = path.suffix
    index = 2
    while True:
        candidate = parent / f"{stem}-{index}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def _popen_kwargs() -> dict:
    kwargs = {
        "stdin": subprocess.PIPE,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.PIPE,
    }
    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        kwargs["startupinfo"] = startupinfo
        kwargs["creationflags"] = _CREATE_NO_WINDOW
    return kwargs


# ---------------------------------------------------------------------------
# ffmpeg 定位与能力检测
# ---------------------------------------------------------------------------

def find_ffmpeg() -> Optional[str]:
    """优先使用随程序打包的 ffmpeg，其次系统 PATH 中的 ffmpeg。"""
    global _FFMPEG_PATH, _FFMPEG_CHECKED
    with _FFMPEG_LOCK:
        if _FFMPEG_CHECKED:
            return _FFMPEG_PATH
        _FFMPEG_CHECKED = True

        env_path = os.environ.get("GRAYSCALE_STUDIO_FFMPEG", "").strip()
        candidates = []
        if env_path:
            candidates.append(env_path)
        if imageio_ffmpeg is not None:
            try:
                candidates.append(imageio_ffmpeg.get_ffmpeg_exe())
            except Exception:
                pass
        system = shutil.which("ffmpeg")
        if system:
            candidates.append(system)

        for candidate in candidates:
            if candidate and os.path.isfile(candidate):
                _FFMPEG_PATH = candidate
                return _FFMPEG_PATH
        _FFMPEG_PATH = None
        return None


def _detect_video_encoder(ffmpeg: str) -> str:
    """选择 H.264；若打包的 ffmpeg 没有 libx264，则退到 MPEG-4。"""
    global _ENCODER
    with _ENCODER_LOCK:
        if _ENCODER:
            return _ENCODER
        try:
            result = subprocess.run(
                [ffmpeg, "-hide_banner", "-encoders"],
                capture_output=True,
                text=True,
                errors="replace",
                timeout=20,
                **_popen_kwargs_for_run(),
            )
            text = (result.stdout or "") + "\n" + (result.stderr or "")
            _ENCODER = "libx264" if "libx264" in text else "mpeg4"
        except Exception:
            _ENCODER = "mpeg4"
        return _ENCODER


def _popen_kwargs_for_run() -> dict:
    kwargs = {}
    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        kwargs["startupinfo"] = startupinfo
        kwargs["creationflags"] = _CREATE_NO_WINDOW
    return kwargs


# ---------------------------------------------------------------------------
# 图片转换
# ---------------------------------------------------------------------------

def _resolve_image_format(output_format: str, src: Path) -> str:
    if output_format == "auto":
        return _AUTO_FORMAT_BY_SUFFIX.get(src.suffix.lower(), "png")
    if output_format in _FORMAT_INFO:
        return output_format
    return "png"


def _prepare_preview(image: Image.Image, max_size: Tuple[int, int]) -> Tuple[Image.Image, Optional[Image.Image]]:
    image = ImageOps.exif_transpose(image)
    has_alpha = image.mode in ("RGBA", "LA") or (
        image.mode == "P" and "transparency" in image.info
    )
    alpha = None
    if has_alpha:
        rgba = image.convert("RGBA")
        rgba.thumbnail(max_size, Image.Resampling.LANCZOS)
        alpha = rgba.getchannel("A")
        result = rgba.convert("RGB")
    else:
        result = image.convert("RGB")
        result.thumbnail(max_size, Image.Resampling.LANCZOS)
    return result, alpha


def load_preview(path: Path, max_size: Tuple[int, int] = (460, 300)) -> PreviewData:
    """读取图片或视频首帧，返回适合预览的 RGB 图像。"""
    kind = media_kind(path)
    if kind == "image":
        with Image.open(path) as image:
            try:
                image.draft("RGB", (max_size[0] * 2, max_size[1] * 2))
            except Exception:
                pass
            prepared, alpha = _prepare_preview(image, max_size)
            detail = f"{image.width} × {image.height} 像素"
        return PreviewData(prepared, "image", detail, alpha)

    if kind == "video":
        if imageio_ffmpeg is None:
            raise RuntimeError("缺少视频解码组件 imageio-ffmpeg")
        reader = imageio_ffmpeg.read_frames(
            str(path), pix_fmt="rgb24", bits_per_pixel=24
        )
        try:
            meta = next(reader)
            raw = next(reader)
        finally:
            try:
                reader.close()
            except Exception:
                pass
        width, height = meta["size"]
        frame = np.frombuffer(raw, dtype=np.uint8).reshape(height, width, 3)
        image = Image.fromarray(frame, "RGB")
        image.thumbnail(max_size, Image.Resampling.LANCZOS)
        fps = meta.get("fps") or 0
        try:
            fps_text = f"{float(fps):.2f} fps"
        except Exception:
            fps_text = "未知帧率"
        detail = f"{width} × {height} 像素 · {fps_text} · 预览为视频首帧"
        return PreviewData(image, "video", detail, None)

    raise ValueError(f"不支持的文件类型：{path.suffix}")


def make_gray_preview(source: Image.Image, standard_key: str) -> Image.Image:
    rgb = np.asarray(source.convert("RGB"), dtype=np.uint8)
    gray = rgb_u8_to_gray_u8(rgb, standard_key)
    return Image.fromarray(gray, "L").convert("RGB")


def convert_image(
    src: Path,
    out_dir: Path,
    standard_key: str,
    output_format: str = "auto",
    keep_alpha: bool = True,
) -> ConversionResult:
    import time

    start = time.time()
    out_dir.mkdir(parents=True, exist_ok=True)

    fmt = _resolve_image_format(output_format, src)
    ext, pillow_format = _FORMAT_INFO[fmt]
    format_supports_alpha = fmt in ("png", "webp", "tiff")
    save_alpha = bool(keep_alpha and format_supports_alpha)
    note = ""

    with Image.open(src) as original:
        image = ImageOps.exif_transpose(original)
        has_alpha = image.mode in ("RGBA", "LA") or (
            image.mode == "P" and "transparency" in image.info
        )
        alpha = None
        if has_alpha:
            rgba = image.convert("RGBA")
            if save_alpha:
                alpha = rgba.getchannel("A")
                rgb = rgba.convert("RGB")
            else:
                # JPEG / BMP 等格式不能保存透明通道。统一铺白底，
                # 避免透明区域在灰度图里变成不可预期的黑色或杂色。
                rgb = Image.new("RGB", rgba.size, (255, 255, 255))
                rgb.paste(rgba, mask=rgba.getchannel("A"))
                if format_supports_alpha:
                    note = "已关闭透明通道，透明区域铺为白色。"
                else:
                    note = "目标格式不支持透明通道，透明区域已铺为白色。"
        else:
            rgb = image.convert("RGB")
        rgb_array = np.asarray(rgb, dtype=np.uint8)
        gray_array = rgb_u8_to_gray_u8(rgb_array, standard_key)
        gray_image = Image.fromarray(gray_array, mode="L")
        if save_alpha and alpha is not None:
            gray_image = Image.merge("LA", (gray_image, alpha))

    out_path = unique_path(out_dir / f"{output_stem(src, standard_key)}{ext}")
    save_kwargs = {}
    if fmt == "png":
        save_kwargs = {"optimize": True}
    elif fmt == "jpeg":
        save_kwargs = {"quality": 95, "subsampling": 0, "optimize": True}
    elif fmt == "webp":
        save_kwargs = {"lossless": True, "quality": 100, "method": 4}
    elif fmt == "tiff":
        save_kwargs = {"compression": "tiff_lzw"}
    gray_image.save(out_path, format=pillow_format, **save_kwargs)

    return ConversionResult(src=src, outputs=[out_path], note=note, elapsed=time.time() - start)


# ---------------------------------------------------------------------------
# 视频转换
# ---------------------------------------------------------------------------

def _check_cancel(cancel_event: _cancel_event_type) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise ConversionCancelled()


def _terminate_process(process: subprocess.Popen) -> None:
    try:
        if process.stdin:
            process.stdin.close()
    except Exception:
        pass
    try:
        process.terminate()
        process.wait(timeout=3)
    except Exception:
        try:
            process.kill()
        except Exception:
            pass


def _encode_video(
    ffmpeg: str,
    src: Path,
    out_path: Path,
    reader,
    meta: dict,
    first_frame: np.ndarray,
    standard_key: str,
    progress_cb: _progress_cb,
    cancel_event: _cancel_event_type,
) -> None:
    height, width = first_frame.shape[:2]
    # libx264 的 yuv420p 需要偶数尺寸。遇到奇数尺寸时补一行/一列边缘像素，
    # 比缩放整帧更不容易产生额外模糊。
    pad_right = width % 2
    pad_bottom = height % 2
    out_width = width + pad_right
    out_height = height + pad_bottom

    fps = meta.get("fps") or 0.0
    try:
        fps = float(fps)
    except Exception:
        fps = 0.0
    if not math.isfinite(fps) or fps <= 0.01:
        fps = 30.0
    fps_text = f"{fps:.6f}".rstrip("0").rstrip(".")
    duration = meta.get("duration") or 0.0
    try:
        duration = float(duration)
    except Exception:
        duration = 0.0
    estimated_total = int(duration * fps) if duration > 0 and math.isfinite(duration) else 0

    encoder = _detect_video_encoder(ffmpeg)
    cmd = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel", "error",
        "-i", str(src),
        "-f", "rawvideo",
        "-pix_fmt", "gray",
        "-s", f"{out_width}x{out_height}",
        "-framerate", fps_text,
        "-i", "pipe:0",
        "-map", "1:v:0",
        "-map", "0:a:0?",
        "-c:v", encoder,
    ]
    if encoder == "libx264":
        cmd += ["-preset", "veryfast", "-crf", "18"]
    else:
        cmd += ["-q:v", "2"]
    cmd += [
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        "-movflags", "+faststart",
        str(out_path),
    ]

    error_file = tempfile.TemporaryFile()
    popen_kwargs = _popen_kwargs()
    popen_kwargs["stderr"] = error_file
    process = subprocess.Popen(cmd, **popen_kwargs)

    def write_frame(frame: np.ndarray) -> bool:
        gray = rgb_u8_to_gray_u8(frame, standard_key)
        if pad_right or pad_bottom:
            gray = np.pad(gray, ((0, pad_bottom), (0, pad_right)), mode="edge")
        try:
            process.stdin.write(gray.tobytes())
            return True
        except (BrokenPipeError, OSError):
            return False

    processed = 0
    try:
        frame_index = 0
        # 首帧在打开编码器前已经用于读取尺寸，需要在这里补写。
        if not write_frame(first_frame):
            raise RuntimeError("ffmpeg 编码器启动后立即关闭，无法写入视频帧。")
        processed = 1
        frame_index = 1
        progress_cb(0.02, "正在处理视频帧：1")
        for raw in reader:
            _check_cancel(cancel_event)
            frame = np.frombuffer(raw, dtype=np.uint8).reshape(height, width, 3)
            if not write_frame(frame):
                break
            processed += 1
            frame_index += 1
            if processed % 5 == 0 or processed == 1:
                if estimated_total > 0:
                    fraction = min(0.995, frame_index / estimated_total)
                else:
                    fraction = 0.05
                progress_cb(fraction, f"正在处理视频帧：{frame_index}")
        if process.stdin:
            process.stdin.close()
        return_code = process.wait()
        error_file.seek(0)
        stderr = error_file.read().decode("utf-8", "replace")
        if cancel_event is not None and cancel_event.is_set():
            raise ConversionCancelled()
        if return_code != 0:
            raise RuntimeError(f"ffmpeg 编码失败（退出码 {return_code}）：\n{stderr.strip()[-1200:]}")
    except ConversionCancelled:
        _terminate_process(process)
        raise
    except Exception:
        _terminate_process(process)
        raise
    finally:
        try:
            error_file.close()
        except Exception:
            pass
        try:
            reader.close()
        except Exception:
            pass


def convert_video(
    src: Path,
    out_dir: Path,
    standard_key: str,
    progress_cb: Optional[_progress_cb] = None,
    cancel_event: _cancel_event_type = None,
) -> ConversionResult:
    import time

    start = time.time()
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise RuntimeError("未找到 ffmpeg，无法转换视频。请重新安装完整版程序。")
    if imageio_ffmpeg is None:
        raise RuntimeError("缺少视频解码组件 imageio-ffmpeg，无法转换视频。")

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = unique_path(out_dir / f"{output_stem(src, standard_key)}.mp4")
    progress_cb = progress_cb or (lambda _fraction, _text: None)

    reader = imageio_ffmpeg.read_frames(str(src), pix_fmt="rgb24", bits_per_pixel=24)
    try:
        _check_cancel(cancel_event)
        meta = next(reader)
        raw = next(reader)
    except StopIteration:
        try:
            reader.close()
        except Exception:
            pass
        raise RuntimeError("视频中没有可读取的画面帧。")
    except Exception:
        try:
            reader.close()
        except Exception:
            pass
        raise

    try:
        width, height = meta["size"]
        first_frame = np.frombuffer(raw, dtype=np.uint8).reshape(height, width, 3)
        progress_cb(0.01, "正在准备视频编码…")
        _encode_video(
            ffmpeg, src, out_path, reader, meta, first_frame, standard_key,
            progress_cb, cancel_event,
        )
        if not out_path.exists() or out_path.stat().st_size == 0:
            raise RuntimeError("转换结束后没有生成有效的视频文件。")
        progress_cb(1.0, "视频转换完成")
        encoder = _detect_video_encoder(ffmpeg)
        note = "已保留原视频的第一条音轨。" if _source_has_audio(ffmpeg, src) else "源视频无音轨。"
        if encoder != "libx264":
            note += " 当前 ffmpeg 不含 libx264，已使用 MPEG-4 编码。"
        return ConversionResult(
            src=src, outputs=[out_path], note=note, elapsed=time.time() - start
        )
    except ConversionCancelled:
        try:
            out_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise
    except Exception:
        try:
            out_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise


def _source_has_audio(ffmpeg: str, src: Path) -> bool:
    """用 ffmpeg -i 的输出判断是否存在音频流；失败时按无音轨处理。"""
    try:
        result = subprocess.run(
            [ffmpeg, "-hide_banner", "-i", str(src)],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=15,
            **_popen_kwargs_for_run(),
        )
        text = (result.stdout or "") + "\n" + (result.stderr or "")
        return "Audio:" in text
    except Exception:
        return False


def open_folder(path: Path) -> None:
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])
