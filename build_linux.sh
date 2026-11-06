#!/usr/bin/env bash
# 在 Ubuntu 22.04+ 内构建可分享的单文件程序。
set -euo pipefail

cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
    echo "未找到 python3，请先安装：sudo apt install python3 python3-venv python3-tk"
    exit 1
fi

if [ ! -x ".venv-linux/bin/python" ]; then
    echo "[1/4] 创建 Python 虚拟环境..."
    python3 -m venv .venv-linux
fi

echo "[2/4] 安装 / 检查依赖..."
.venv-linux/bin/python -m pip install -q -r requirements.txt pyinstaller

echo "[3/4] 使用 PyInstaller 打包单文件程序..."
.venv-linux/bin/python -m PyInstaller \
    --noconfirm --clean --onefile --windowed \
    --hidden-import PIL._tkinter_finder \
    --name "灰度工坊" \
    --add-data "$(pwd)/assets:assets" \
    --collect-all tkinterdnd2 \
    --collect-all imageio_ffmpeg \
    --distpath "发布/Linux" \
    --workpath "build/pyinstaller-linux" \
    --specpath "build" \
    main.py

mkdir -p "发布/Linux"
cp -f "docs/分享说明.txt" "发布/Linux/使用说明.txt" 2>/dev/null || true
chmod +x "发布/Linux/灰度工坊"

echo "[4/4] 打包完成：发布/Linux/灰度工坊"
echo "接下来可以运行 ./install_linux.sh 安装到桌面和开始菜单，并生成分享包。"
