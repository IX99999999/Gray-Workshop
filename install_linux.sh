#!/usr/bin/env bash
# 在 Ubuntu 当前用户下安装灰度工坊（无需 sudo），并生成桌面快捷方式和分享包。
set -euo pipefail

cd "$(dirname "$0")"

BIN_SOURCE="发布/Linux/灰度工坊"
if [ ! -f "$BIN_SOURCE" ]; then
    echo "找不到 $BIN_SOURCE，请先运行 ./build_linux.sh"
    exit 1
fi

APP_DIR="$HOME/.local/share/grayscale-studio"
BIN="$APP_DIR/灰度工坊"
ICON_DIR="$HOME/.local/share/icons/hicolor/256x256/apps"
ICON="$ICON_DIR/grayscale-studio.png"
MENU_DIR="$HOME/.local/share/applications"
DESKTOP_DIR=""
if command -v xdg-user-dir >/dev/null 2>&1; then
    DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || true)"
fi
if [ -z "$DESKTOP_DIR" ] || [ "$DESKTOP_DIR" = "$HOME" ]; then
    if [ -d "$HOME/桌面" ]; then
        DESKTOP_DIR="$HOME/桌面"
    else
        DESKTOP_DIR="$HOME/Desktop"
    fi
fi

echo "[1/3] 安装程序文件..."
mkdir -p "$APP_DIR" "$ICON_DIR" "$MENU_DIR" "$DESKTOP_DIR"
cp -f "$BIN_SOURCE" "$BIN"
chmod +x "$BIN"
cp -f "assets/app_icon.png" "$ICON"

cat > "$MENU_DIR/grayscale-studio.desktop" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=灰度工坊
Name[en]=Grayscale Studio
Comment=图片 / 视频灰度转换
Comment[en]=Convert images and videos to grayscale
Exec=$BIN
Icon=$ICON
Terminal=false
Categories=Graphics;Utility;
StartupNotify=true
StartupWMClass=GrayscaleStudio
EOF
chmod +x "$MENU_DIR/grayscale-studio.desktop"

echo "[2/3] 创建桌面快捷方式..."
cp -f "$MENU_DIR/grayscale-studio.desktop" "$DESKTOP_DIR/灰度工坊.desktop"
chmod +x "$DESKTOP_DIR/灰度工坊.desktop"
if command -v gio >/dev/null 2>&1; then
    gio set "$DESKTOP_DIR/灰度工坊.desktop" metadata::trusted true 2>/dev/null || true
fi

echo "[3/3] 生成可分享的 Linux 压缩包..."
STAGE="$(mktemp -d)"
SHARE_DIR="$STAGE/灰度工坊"
mkdir -p "$SHARE_DIR"
cp -f "$BIN" "$SHARE_DIR/灰度工坊"
chmod +x "$SHARE_DIR/灰度工坊"
cp -f "docs/分享说明.txt" "$SHARE_DIR/使用说明.txt"
for f in README.md LICENSE THIRD_PARTY_NOTICES.md; do
    [ -f "$f" ] && cp -f "$f" "$SHARE_DIR/$f"
done
[ -f "docs/灰度工坊-使用说明书.pdf" ] && cp -f "docs/灰度工坊-使用说明书.pdf" "$SHARE_DIR/灰度工坊-使用说明书.pdf"
cp -f "assets/app_icon.png" "$SHARE_DIR/icon.png"
cat > "$SHARE_DIR/安装到桌面.sh" <<'EOS'
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
APP_DIR="$HOME/.local/share/grayscale-studio"
DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || true)"
[ -n "$DESKTOP_DIR" ] || DESKTOP_DIR="$HOME/桌面"
[ -d "$DESKTOP_DIR" ] || DESKTOP_DIR="$HOME/Desktop"
mkdir -p "$APP_DIR" "$DESKTOP_DIR"
cp -f "灰度工坊" "$APP_DIR/灰度工坊"
chmod +x "$APP_DIR/灰度工坊"
cat > "$DESKTOP_DIR/灰度工坊.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=灰度工坊
Exec=$APP_DIR/灰度工坊
Icon=$PWD/icon.png
Terminal=false
Categories=Graphics;Utility;
StartupWMClass=GrayscaleStudio
EOF
chmod +x "$DESKTOP_DIR/灰度工坊.desktop"
gio set "$DESKTOP_DIR/灰度工坊.desktop" metadata::trusted true 2>/dev/null || true
echo "安装完成：$DESKTOP_DIR/灰度工坊.desktop"
EOS
chmod +x "$SHARE_DIR/安装到桌面.sh"
tar -czf "$DESKTOP_DIR/灰度工坊-Linux-x64-1.0.0.tar.gz" -C "$STAGE" "灰度工坊"
rm -rf "$STAGE"

echo
echo "安装完成！"
echo "  程序：$BIN"
echo "  菜单：$MENU_DIR/grayscale-studio.desktop"
echo "  桌面：$DESKTOP_DIR/灰度工坊.desktop"
echo "  分享：$DESKTOP_DIR/灰度工坊-Linux-x64-1.0.0.tar.gz"
