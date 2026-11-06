# -*- coding: utf-8 -*-
"""灰度工坊启动入口。"""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path


def _prepare_frozen_ffmpeg() -> None:
    """PyInstaller 打包后，把随包的 ffmpeg 显式告诉 imageio-ffmpeg。"""
    if not getattr(sys, "frozen", False):
        return
    base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    binary_dir = base / "imageio_ffmpeg" / "binaries"
    if not binary_dir.is_dir():
        return
    suffix = ".exe" if os.name == "nt" else ""
    candidates = sorted(binary_dir.glob(f"ffmpeg*{suffix}"))
    for candidate in candidates:
        if candidate.is_file():
            os.environ.setdefault("IMAGEIO_FFMPEG_EXE", str(candidate))
            break


def _set_windows_app_id() -> None:
    if os.name != "nt":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "GrayscaleStudio.App.1"
        )
    except Exception:
        pass


def _initial_paths() -> list:
    """支持把文件拖到 exe 上，或用命令行把文件作为参数打开。"""
    paths = []
    for arg in sys.argv[1:]:
        if arg.startswith("-"):
            continue
        path = Path(arg).expanduser()
        if path.is_file():
            paths.append(path)
    return paths


def main() -> None:
    _set_windows_app_id()
    _prepare_frozen_ffmpeg()
    try:
        from app.ui import run

        run(_initial_paths())
    except Exception:
        details = traceback.format_exc()
        try:
            sys.stderr.write(details + "\n")
        except Exception:
            pass
        try:
            from tkinter import messagebox

            messagebox.showerror(
                "灰度工坊启动失败",
                "程序遇到错误，无法启动。\n\n" + details[-3000:],
            )
        except Exception:
            pass
        raise


if __name__ == "__main__":
    main()
