# 第三方组件与许可说明

灰度工坊的源代码采用 MIT License。便携发布包会捆绑以下开源组件；它们各自保留原许可证，本文件不能替代各组件的完整许可证文本。

## 发布包中的主要组件

| 组件 | 用途 | 许可 | 项目主页 / 许可 |
| --- | --- | --- | --- |
| Python | 运行时（Windows 3.11 / Ubuntu 构建环境 3.10） | Python Software Foundation License | https://www.python.org/ |
| Tcl/Tk | 桌面 GUI 运行时 | BSD 风格许可 | https://www.tcl.tk/software/tcltk/license.html |
| Pillow | 图片读写、预览与格式保存 | HPND / CMU 许可 | https://python-pillow.github.io/ |
| NumPy | 像素矩阵计算 | BSD-3-Clause | https://numpy.org/ |
| imageio-ffmpeg | ffmpeg 可执行文件的 Python 封装 | BSD-2-Clause | https://github.com/imageio/imageio-ffmpeg |
| tkinterdnd2 | 文件拖拽支持 | MIT | https://github.com/Eliav2/tkinterdnd2 |
| PyInstaller | 单文件打包工具（含 bootloader） | GPL-2.0-or-later，带 bootloader 例外 | https://pyinstaller.org/ |
| FFmpeg | 视频解码、H.264 编码、音轨保留 | GPL v3（当前内置构建包含 libx264） | https://ffmpeg.org/ |

## 关于 ffmpeg

发布包中捆绑的 ffmpeg 静态构建来自 imageio-ffmpeg / gyan.dev 的发布产物（版本 9.0.2），启用了包括 libx264 在内的 GPL 组件。

- FFmpeg 官方网站：https://ffmpeg.org/
- FFmpeg 源代码：https://ffmpeg.org/download.html
- GPL v3 全文：https://www.gnu.org/licenses/gpl-3.0.html
- gyan.dev Windows 构建：https://www.gyan.dev/ffmpeg/builds/
- imageio-ffmpeg 及其二进制来源：https://github.com/imageio/imageio-ffmpeg

如果你再分发 Windows 或 Ubuntu 安装包，请保留本文件和对应许可证信息。要获得完全由 MIT 源码构成的程序，可自行安装系统 ffmpeg 后从源码运行 `python main.py`；应用会优先使用随包 ffmpeg，也可通过环境变量 `GRAYSCALE_STUDIO_FFMPEG` 指定系统 ffmpeg。

## 免责声明

灰度工坊不是 Adobe、OpenCV、FFmpeg 或任何第三方公司的官方产品。所有商标归其各自所有者。
