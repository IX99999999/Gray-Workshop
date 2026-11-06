@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [1/4] 创建 Python 虚拟环境...
    py -m venv .venv
    if errorlevel 1 goto :error
)

echo [2/4] 安装 / 检查依赖...
".venv\Scripts\python.exe" -m pip install -q -r requirements.txt pyinstaller
if errorlevel 1 goto :error

echo [3/4] 使用 PyInstaller 打包单文件程序...
".venv\Scripts\python.exe" -m PyInstaller ^
    --noconfirm --clean --onefile --windowed ^
    --hidden-import PIL._tkinter_finder ^
    --name "灰度工坊" ^
    --icon "%CD%\assets\app_icon.ico" ^
    --version-file "%CD%\tools\version_info.txt" ^
    --add-data "%CD%\assets;assets" ^
    --collect-all tkinterdnd2 ^
    --collect-all imageio_ffmpeg ^
    --distpath "发布\Windows" ^
    --workpath "build\pyinstaller-win" ^
    --specpath "build" ^
    main.py
if errorlevel 1 goto :error

if not exist "发布\Windows" mkdir "发布\Windows"
copy /y "docs\分享说明.txt" "发布\Windows\使用说明.txt" >nul
copy /y "README.md" "发布\Windows\README.md" >nul
copy /y "LICENSE" "发布\Windows\LICENSE.txt" >nul
copy /y "THIRD_PARTY_NOTICES.md" "发布\Windows\THIRD_PARTY_NOTICES.md" >nul
if exist "docs\灰度工坊-使用说明书.pdf" copy /y "docs\灰度工坊-使用说明书.pdf" "发布\Windows\灰度工坊-使用说明书.pdf" >nul

echo [4/4] 打包完成：
echo   发布\Windows\灰度工坊.exe
echo.
echo 可直接把 发布\Windows 文件夹中的 exe 分享给别人。
if not defined GRAYSCALE_STUDIO_NO_PAUSE pause
exit /b 0

:error
echo.
echo 构建失败，请查看上方错误信息。
if not defined GRAYSCALE_STUDIO_NO_PAUSE pause
exit /b 1
