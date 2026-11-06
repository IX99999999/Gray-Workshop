# -*- coding: utf-8 -*-
"""把 docs/使用说明书.md 渲染成适合打印的 PDF。

依赖：markdown；PDF 渲染使用 Microsoft Edge 的 headless 模式。
用法：python tools/build_manual.py
"""

from __future__ import annotations

import base64
import html
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent.parent
MANUAL_MD = ROOT / "docs" / "使用说明书.md"
OUT_PDF = ROOT / "docs" / "灰度工坊-使用说明书.pdf"
BUILD_DIR = ROOT / "build"
ICON = ROOT / "assets" / "app_icon.png"

EDGE_CANDIDATES = [
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
]

CSS = r"""
@page {
    size: A4;
    margin: 18mm 16mm 17mm 16mm;
}
* { box-sizing: border-box; }
html {
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
}
body {
    margin: 0;
    color: #20242c;
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", "Noto Sans CJK SC",
                 "Source Han Sans SC", sans-serif;
    font-size: 10.2pt;
    line-height: 1.72;
    letter-spacing: .01em;
}
h1, h2, h3, h4 {
    color: #111827;
    line-height: 1.3;
    page-break-after: avoid;
}
h2 {
    margin: 24pt 0 10pt;
    padding-left: 10pt;
    border-left: 5px solid #2563eb;
    font-size: 17pt;
}
h3 {
    margin: 16pt 0 7pt;
    color: #1d4ed8;
    font-size: 12.5pt;
}
h4 { margin: 12pt 0 6pt; font-size: 11pt; }
p { margin: 6pt 0; text-align: justify; }
ul, ol { margin: 5pt 0 8pt; padding-left: 20pt; }
li { margin: 2.5pt 0; }
a { color: #2563eb; text-decoration: none; }
strong { color: #111827; }
hr { border: none; border-top: 1px solid #e5e7eb; margin: 16pt 0; }
img { max-width: 100%; height: auto; border-radius: 6px; }
figure { margin: 14pt 0; text-align: center; }
figcaption { color: #6b7280; font-size: 9pt; margin-top: 5pt; }

table {
    width: 100%;
    margin: 10pt 0 12pt;
    border-collapse: collapse;
    font-size: 9.1pt;
    page-break-inside: avoid;
}
th {
    padding: 7pt 8pt;
    background: #111827;
    color: #ffffff;
    text-align: left;
    font-weight: 600;
}
td {
    padding: 6.5pt 8pt;
    border-bottom: 1px solid #e5e7eb;
    vertical-align: top;
}
tr:nth-child(even) td { background: #f8fafc; }
table th:first-child, table td:first-child { min-width: 68px; }

blockquote {
    margin: 12pt 0;
    padding: 8pt 12pt;
    color: #1e3a8a;
    background: #eff6ff;
    border-left: 4px solid #60a5fa;
    border-radius: 0 4px 4px 0;
    page-break-inside: avoid;
}
blockquote p { margin: 0; }

code {
    padding: 1pt 4pt;
    color: #0f172a;
    background: #f1f5f9;
    border-radius: 3px;
    font-family: "Cascadia Mono", Consolas, "DejaVu Sans Mono", monospace;
    font-size: .9em;
}
pre {
    margin: 9pt 0 12pt;
    padding: 10pt 12pt;
    background: #111827;
    color: #e5e7eb;
    border-radius: 7px;
    white-space: pre-wrap;
    word-break: break-word;
    page-break-inside: avoid;
}
pre code {
    padding: 0;
    background: transparent;
    color: inherit;
    font-size: 8.6pt;
    line-height: 1.55;
}
.page-break { page-break-after: always; height: 0; }
.toc {
    margin: 8pt 0 18pt;
    padding: 12pt 16pt;
    background: #f8fafc;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    font-size: 9.4pt;
}
.toc::before {
    content: "目录";
    display: block;
    margin-bottom: 7pt;
    color: #111827;
    font-size: 13pt;
    font-weight: 700;
}
.toc ul { margin: 2pt 0; padding-left: 15pt; }
.toc > ul { columns: 2; column-gap: 26pt; }
.toc a { color: #374151; }
.toc li { margin: 2.3pt 0; break-inside: avoid; }

.cover {
    min-height: 250mm;
    display: flex;
    flex-direction: column;
    justify-content: center;
    padding: 10mm 8mm;
    page-break-after: always;
}
.cover .icon { width: 82px; height: 82px; border-radius: 18px; }
.cover .eyebrow {
    margin-top: 24pt;
    color: #2563eb;
    font-size: 10pt;
    font-weight: 700;
    letter-spacing: .22em;
}
.cover h1 {
    margin: 8pt 0 2pt;
    font-size: 38pt;
    letter-spacing: .06em;
}
.cover .sub {
    color: #4b5563;
    font-size: 15pt;
    text-align: left;
}
.cover .rule {
    width: 62px;
    height: 5px;
    margin: 22pt 0;
    background: #2563eb;
}
.cover .meta {
    width: 100%;
    border-collapse: collapse;
    font-size: 10pt;
}
.cover .meta td {
    padding: 6pt 0;
    border-bottom: 1px solid #e5e7eb;
    background: transparent !important;
}
.cover .meta td:first-child {
    width: 110px;
    color: #6b7280;
}
.cover .note {
    margin-top: 26pt;
    padding: 12pt 14pt;
    color: #374151;
    background: #f8fafc;
    border-left: 4px solid #2563eb;
    font-size: 9.5pt;
}
"""


def _data_uri(path: Path) -> str:
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{data}"


def _find_browser() -> Path:
    for candidate in EDGE_CANDIDATES:
        if candidate.is_file():
            return candidate
    for name in ("msedge", "chrome"):
        candidate = shutil.which(name)
        if candidate:
            return Path(candidate)
    raise RuntimeError("找不到 Microsoft Edge 或 Chrome，无法导出 PDF。")


def main() -> None:
    if not MANUAL_MD.is_file():
        raise SystemExit(f"找不到说明书源文件：{MANUAL_MD}")
    text = MANUAL_MD.read_text(encoding="utf-8")
    marker = "[TOC]"
    if marker not in text:
        raise SystemExit("说明书中缺少 [TOC] 标记")
    body = text[text.index(marker):]
    body_html = markdown.markdown(
        body,
        extensions=["extra", "toc", "sane_lists"],
        extension_configs={"toc": {"permalink": False, "toc_depth": "2-3"}},
    )
    docs_uri = (ROOT / "docs").resolve().as_uri() + "/"
    icon_uri = _data_uri(ICON)
    cover = f"""
    <section class="cover">
      <img class="icon" src="{icon_uri}" alt="灰度工坊图标">
      <div class="eyebrow">GRAYSCALE STUDIO</div>
      <h1>灰度工坊</h1>
      <p class="sub">图片 / 视频灰度转换工具<br>使用说明书</p>
      <div class="rule"></div>
      <table class="meta">
        <tr><td>版本</td><td>1.0.0</td></tr>
        <tr><td>更新日期</td><td>2026 年 11 月 6 日</td></tr>
        <tr><td>支持平台</td><td>Windows 10/11 x64 · Ubuntu 22.04+ x64</td></tr>
        <tr><td>项目主页</td><td>github.com/IX99999999/Gray-Workshop</td></tr>
        <tr><td>许可</td><td>MIT License（第三方组件见说明）</td></tr>
      </table>
      <div class="note">
        本工具的所有转换均在本机完成。不上传图片、视频或任何个人信息，
        不包含账户系统、遥测或云端同步功能。
      </div>
    </section>
    """
    html_doc = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>灰度工坊 · 使用说明书</title>
<base href="{html.escape(docs_uri)}">
<style>{CSS}</style>
</head>
<body>
{cover}
{body_html}
</body>
</html>
"""
    BUILD_DIR.mkdir(exist_ok=True)
    html_path = BUILD_DIR / "使用说明书.html"
    html_path.write_text(html_doc, encoding="utf-8")

    browser = _find_browser()
    OUT_PDF.parent.mkdir(exist_ok=True)
    if OUT_PDF.exists():
        OUT_PDF.unlink()
    with tempfile.TemporaryDirectory(prefix="gray-studio-manual-") as profile:
        cmd = [
            str(browser),
            "--headless=new",
            "--disable-gpu",
            "--no-first-run",
            "--no-pdf-header-footer",
            "--print-to-pdf-no-header",
            "--allow-file-access-from-files",
            f"--user-data-dir={profile}",
            f"--print-to-pdf={OUT_PDF}",
            html_path.resolve().as_uri(),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=180)
    if result.returncode != 0 or not OUT_PDF.is_file():
        print(result.stdout)
        print(result.stderr)
        raise SystemExit(f"PDF 导出失败，退出码 {result.returncode}")
    print(f"说明书已生成：{OUT_PDF}")
    print(f"大小：{OUT_PDF.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()
