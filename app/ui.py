# -*- coding: utf-8 -*-
"""灰度工坊的 Tkinter 图形界面。"""

from __future__ import annotations

import json
import os
import queue
import sys
import threading
import tkinter as tk
import traceback
import tkinter.font as tkfont
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageTk

from . import __version__, engine
from .standards import (
    DEFAULT_STANDARD_KEY,
    STANDARDS,
    get_standard,
    label_to_key,
)

try:
    from tkinterdnd2 import COPY as DND_COPY
    from tkinterdnd2 import DND_FILES, TkinterDnD

    DND_AVAILABLE = True
except Exception:  # pragma: no cover - 没有拖拽组件时退回普通窗口
    DND_AVAILABLE = False
    DND_COPY = "copy"
    DND_FILES = None
    TkinterDnD = None

BaseTk = tk.Tk


# ---------------------------------------------------------------------------
# 配色与常量
# ---------------------------------------------------------------------------
BG = "#F4F5F7"
CARD = "#FFFFFF"
HEADER_BG = "#171A21"
HEADER_MUTED = "#A6ADBA"
TEXT = "#20242C"
MUTED = "#6F7785"
FAINT = "#99A1AE"
BORDER = "#E3E6EB"
DROP_BG = "#FAFBFC"
DESC_BG = "#F7F9FC"
ACCENT = "#2563EB"
ACCENT_HOVER = "#1D4ED8"
ACCENT_SOFT = "#EAF0FE"
SUCCESS = "#14804A"
SUCCESS_SOFT = "#E8F6EE"
WARNING = "#B45309"
WARNING_SOFT = "#FFF7E6"
ERROR = "#C0392B"
ERROR_SOFT = "#FDECEA"

APP_TITLE = f"灰度工坊  {__version__}"
CONFIG_FILE = Path.home() / ".grayscale_studio.json"

PREVIEW_BOX = (190, 115)


def _load_config() -> dict:
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_config(data: dict) -> None:
    try:
        CONFIG_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass


def _resource_path(relative: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / relative


class GrayscaleStudioApp(BaseTk):
    def __init__(self) -> None:
        super().__init__(className="GrayscaleStudio")
        self.config_data = _load_config()
        self._dnd_enabled = False
        if DND_AVAILABLE:
            try:
                TkinterDnD.require(self)
                self._dnd_enabled = True
            except Exception:
                self._dnd_enabled = False

        self.title(f"{APP_TITLE} · 图片 / 视频灰度转换")
        self.configure(bg=BG)
        self._set_window_geometry()
        self._setup_fonts()
        self._setup_style()
        self._setup_icon()

        # 队列模型：iid -> {path, kind, size_text, status, output}
        self.items: Dict[str, dict] = {}
        self.order: List[str] = []
        self._next_iid = 1
        self._running = False
        self._cancel_event = threading.Event()
        self._msg_queue: "queue.Queue[tuple]" = queue.Queue()
        self.failed_details: List[str] = []
        self.last_outputs: List[Path] = []

        # 预览模型
        self._preview_serial = 0
        self._preview_path: Optional[Path] = None
        self._preview_data: Optional[engine.PreviewData] = None
        self._preview_source: Optional[Image.Image] = None
        self._preview_alpha: Optional[Image.Image] = None
        self._preview_photo_original: Optional[ImageTk.PhotoImage] = None
        self._preview_photo_gray: Optional[ImageTk.PhotoImage] = None

        self.output_dir_var = tk.StringVar()
        self.standard_var = tk.StringVar()
        self.image_format_var = tk.StringVar()
        self.keep_alpha_var = tk.BooleanVar(value=True)
        self.count_var = tk.StringVar(value="0 个文件")
        self.status_var = tk.StringVar(value="准备就绪")
        self.detail_var = tk.StringVar(
            value="拖入或选择图片 / 视频，选好灰度标准后开始转换。所有处理都在本机完成。"
        )
        self.progress_var = tk.DoubleVar(value=0.0)

        self._build_header()
        self._build_body()
        self._build_footer()

        self._restore_settings()
        self._update_standard_details()
        self._set_preview_empty("等待选择文件", "灰度效果将在这里显示")
        self._bind_shortcuts()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._poll_messages)

    # ------------------------------------------------------------------
    # 初始化辅助
    # ------------------------------------------------------------------
    def _set_window_geometry(self) -> None:
        try:
            screen_w = self.winfo_screenwidth()
            screen_h = self.winfo_screenheight()
            width = min(1180, max(980, screen_w - 80))
            height = min(860, max(680, screen_h - 100))
            x = max(10, (screen_w - width) // 2)
            y = max(10, (screen_h - height) // 2 - 15)
            self.geometry(f"{width}x{height}+{x}+{y}")
            self.minsize(1020, 690)
        except Exception:
            self.geometry("1180x860")

    def _setup_fonts(self) -> None:
        families = set(tkfont.families(self))
        family = "Microsoft YaHei UI"
        for candidate in (
            "Microsoft YaHei UI",
            "Microsoft YaHei",
            "Noto Sans CJK SC",
            "Source Han Sans SC",
            "WenQuanYi Micro Hei",
            "PingFang SC",
            "Segoe UI",
        ):
            if candidate in families:
                family = candidate
                break
        mono = "Consolas"
        for candidate in ("Cascadia Mono", "Consolas", "DejaVu Sans Mono", "Noto Sans Mono", "Courier New"):
            if candidate in families:
                mono = candidate
                break

        self.font_family = family
        self.font_mono = mono
        self.font_ui = (family, 10)
        self.font_small = (family, 9)
        self.font_tiny = (family, 8)
        self.font_bold = (family, 10, "bold")
        self.font_section = (family, 12, "bold")
        self.font_title = (family, 21, "bold")
        self.font_subtitle = (family, 10)
        self.font_formula = (mono, 9)
        self.font_badge = (family, 9, "bold")

        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
            try:
                named = tkfont.nametofont(name)
                named.configure(family=family, size=10)
            except Exception:
                pass

    def _setup_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure(".", font=self.font_ui, background=BG, foreground=TEXT)
        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=CARD)
        style.configure("TLabel", background=CARD, foreground=TEXT)
        style.configure("Muted.TLabel", background=CARD, foreground=MUTED, font=self.font_small)
        style.configure("TButton", font=self.font_ui, padding=(12, 7))
        style.configure(
            "Primary.TButton",
            font=self.font_bold,
            background=ACCENT,
            foreground="#FFFFFF",
            borderwidth=0,
            padding=(18, 9),
        )
        style.map(
            "Primary.TButton",
            background=[("active", ACCENT_HOVER), ("disabled", "#B9C3D3")],
            foreground=[("disabled", "#FFFFFF")],
        )
        style.configure(
            "Secondary.TButton",
            font=self.font_ui,
            background="#F1F3F6",
            foreground=TEXT,
            borderwidth=0,
            padding=(12, 8),
        )
        style.map(
            "Secondary.TButton",
            background=[("active", "#E6EAF0"), ("disabled", "#F5F6F8")],
            foreground=[("disabled", FAINT)],
        )
        style.configure(
            "Stop.TButton",
            font=self.font_ui,
            background="#FBEAEA",
            foreground=ERROR,
            borderwidth=0,
            padding=(12, 8),
        )
        style.map(
            "Stop.TButton",
            background=[("active", "#F6D8D5"), ("disabled", "#F5F6F8")],
            foreground=[("disabled", FAINT)],
        )
        style.configure(
            "TCombobox",
            padding=6,
            fieldbackground=CARD,
            background=CARD,
            foreground=TEXT,
            arrowsize=15,
            bordercolor=BORDER,
            lightcolor=BORDER,
            darkcolor=BORDER,
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", CARD), ("disabled", "#F4F5F7")],
            foreground=[("readonly", TEXT), ("disabled", FAINT)],
            selectbackground=[("readonly", CARD)],
            selectforeground=[("readonly", TEXT)],
            bordercolor=[("focus", ACCENT)],
        )
        style.configure(
            "TEntry",
            padding=7,
            fieldbackground=CARD,
            foreground=TEXT,
            bordercolor=BORDER,
            lightcolor=BORDER,
            darkcolor=BORDER,
        )
        style.map("TEntry", bordercolor=[("focus", ACCENT)])
        style.configure(
            "Treeview",
            background=CARD,
            fieldbackground=CARD,
            foreground=TEXT,
            rowheight=30,
            borderwidth=0,
            font=self.font_ui,
        )
        style.configure(
            "Treeview.Heading",
            background="#F7F8FA",
            foreground=MUTED,
            font=(self.font_family, 9, "bold"),
            relief="flat",
            padding=(7, 7),
        )
        style.map(
            "Treeview",
            background=[("selected", ACCENT_SOFT)],
            foreground=[("selected", TEXT)],
        )
        style.map("Treeview.Heading", background=[("active", "#EEF1F5")])
        style.configure(
            "Horizontal.TProgressbar",
            troughcolor="#E8EBF0",
            background=ACCENT,
            bordercolor="#E8EBF0",
            lightcolor=ACCENT,
            darkcolor=ACCENT,
            thickness=7,
        )
        style.configure(
            "TCheckbutton",
            background=CARD,
            foreground=TEXT,
            font=self.font_small,
            focuscolor=CARD,
        )
        style.map("TCheckbutton", background=[("active", CARD)])
        style.configure("TSeparator", background=BORDER)

    def _setup_icon(self) -> None:
        png = _resource_path("assets/app_logo.png")
        ico = _resource_path("assets/app_icon.ico")
        if png.is_file():
            try:
                logo = Image.open(png).convert("RGBA")
                logo = logo.resize((46, 46), Image.Resampling.LANCZOS)
                self.logo_photo = ImageTk.PhotoImage(logo)
            except Exception:
                self.logo_photo = None
        else:
            self.logo_photo = None
        if os.name == "nt" and ico.is_file():
            try:
                self.iconbitmap(default=str(ico))
            except Exception:
                pass
        elif png.is_file():
            try:
                self.iconphoto(True, tk.PhotoImage(file=str(png)))
            except Exception:
                pass

    def _bind_shortcuts(self) -> None:
        self.bind_all("<Control-o>", lambda _e: self.choose_files())
        self.bind_all("<Control-O>", lambda _e: self.choose_files())
        self.bind_all("<Control-Return>", lambda _e: self.start_conversion())
        self.file_tree.bind("<Delete>", lambda _e: self.remove_selected())

    # ------------------------------------------------------------------
    # 界面搭建
    # ------------------------------------------------------------------
    def _build_header(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = tk.Frame(self, bg=HEADER_BG, height=84)
        header.grid(row=0, column=0, sticky="ew")
        header.pack_propagate(False)

        left = tk.Frame(header, bg=HEADER_BG)
        left.pack(side="left", fill="y", padx=(24, 0))
        if getattr(self, "logo_photo", None) is not None:
            tk.Label(left, image=self.logo_photo, bg=HEADER_BG).pack(
                side="left", pady=17, padx=(0, 14)
            )
        title_box = tk.Frame(left, bg=HEADER_BG)
        title_box.pack(side="left", fill="y", pady=7)
        tk.Label(
            title_box,
            text="灰度工坊",
            bg=HEADER_BG,
            fg="#FFFFFF",
            font=self.font_title,
            anchor="w",
        ).pack(anchor="w")
        tk.Label(
            title_box,
            text="把彩色图像变成可控的灰阶 · 图片 / 视频批量转换",
            bg=HEADER_BG,
            fg=HEADER_MUTED,
            font=self.font_subtitle,
            anchor="w",
        ).pack(anchor="w", pady=(2, 0))

        right = tk.Frame(header, bg=HEADER_BG)
        right.pack(side="right", fill="y", padx=(0, 24))
        tag_frame = tk.Frame(right, bg=HEADER_BG)
        tag_frame.pack(side="right", pady=25)
        self._header_tag(tag_frame, "10 种灰度标准", ACCENT)
        self._header_tag(tag_frame, "本地处理 · 不上传", "#3A404C")

        # 底部灰度渐变细条，呼应“灰度”主题
        strip = tk.Frame(header, bg=HEADER_BG)
        strip.place(relx=0, rely=1.0, relwidth=1.0, height=4, anchor="sw")
        for index in range(12):
            value = 34 + index * 16
            color = f"#{value:02X}{value:02X}{value:02X}"
            tk.Frame(strip, bg=color).pack(side="left", fill="both", expand=True)

    def _header_tag(self, parent: tk.Widget, text: str, color: str) -> None:
        tk.Label(
            parent,
            text=text,
            bg=color,
            fg="#FFFFFF" if color != "#3A404C" else "#D7DBE3",
            font=self.font_small,
            padx=10,
            pady=4,
        ).pack(side="left", padx=(6, 0))

    def _build_body(self) -> None:
        body = tk.Frame(self, bg=BG)
        body.grid(row=1, column=0, sticky="nsew", padx=22, pady=(16, 0))
        body.grid_columnconfigure(0, weight=11, uniform="cards")
        body.grid_columnconfigure(1, weight=9, uniform="cards")
        body.grid_rowconfigure(0, weight=1)

        left_outer, left = self._make_card(body)
        left_outer.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        right_outer = tk.Frame(
            body,
            bg=CARD,
            highlightbackground=BORDER,
            highlightthickness=1,
            bd=0,
        )
        right_outer.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        right_area = tk.Frame(right_outer, bg=CARD)
        right_area.pack(fill="both", expand=True, padx=(17, 8), pady=14)
        self.settings_canvas = tk.Canvas(
            right_area, bg=CARD, highlightthickness=0, bd=0
        )
        self.settings_scroll = ttk.Scrollbar(
            right_area, orient="vertical", command=self.settings_canvas.yview
        )
        self.settings_canvas.configure(yscrollcommand=self.settings_scroll.set)
        self.settings_scroll.pack(side="right", fill="y")
        self.settings_canvas.pack(side="left", fill="both", expand=True)
        settings = tk.Frame(self.settings_canvas, bg=CARD)
        self._settings_window = self.settings_canvas.create_window(
            (0, 0), window=settings, anchor="nw"
        )
        self._settings_content = settings
        settings.bind("<Configure>", self._on_settings_content_configure)
        self.settings_canvas.bind("<Configure>", self._on_settings_canvas_configure)
        self.bind_all("<MouseWheel>", self._on_mousewheel, add="+")
        if sys.platform.startswith("linux"):
            self.bind_all("<Button-4>", self._on_mousewheel, add="+")
            self.bind_all("<Button-5>", self._on_mousewheel, add="+")

        self._build_file_panel(left)
        self._build_settings_panel(settings)

    def _make_card(self, parent: tk.Widget) -> Tuple[tk.Frame, tk.Frame]:
        outer = tk.Frame(
            parent,
            bg=CARD,
            highlightbackground=BORDER,
            highlightthickness=1,
            bd=0,
        )
        inner = tk.Frame(outer, bg=CARD)
        inner.pack(fill="both", expand=True, padx=17, pady=14)
        return outer, inner

    def _section_header(
        self, parent: tk.Widget, number: str, title: str, right_text: str = ""
    ) -> tk.Frame:
        row = tk.Frame(parent, bg=CARD)
        badge = tk.Label(
            row,
            text=number,
            bg=ACCENT_SOFT,
            fg=ACCENT,
            font=self.font_badge,
            padx=7,
            pady=2,
        )
        badge.pack(side="left", padx=(0, 8))
        tk.Label(
            row, text=title, bg=CARD, fg=TEXT, font=self.font_section, anchor="w"
        ).pack(side="left")
        if right_text:
            tk.Label(
                row,
                text=right_text,
                bg=CARD,
                fg=FAINT,
                font=self.font_small,
                anchor="e",
            ).pack(side="right")
        return row

    def _build_file_panel(self, parent: tk.Frame) -> None:
        header = self._section_header(parent, "1", "文件队列")
        header.pack(fill="x")
        self.count_label = tk.Label(
            header, textvariable=self.count_var, bg=CARD, fg=MUTED, font=self.font_small
        )
        self.count_label.pack(side="right")

        # 拖拽 / 选择区
        self.drop_zone = tk.Frame(
            parent,
            bg=DROP_BG,
            highlightbackground="#D8DDE5",
            highlightthickness=1,
            bd=0,
            cursor="hand2",
        )
        self.drop_zone.pack(fill="x", pady=(12, 12), ipady=6)

        plus = tk.Label(
            self.drop_zone,
            text="＋",
            bg=DROP_BG,
            fg="#8D97A5",
            font=(self.font_family, 23),
            cursor="hand2",
        )
        plus.pack(pady=(7, 0))
        hint = tk.Label(
            self.drop_zone,
            text="把图片或视频拖到这里",
            bg=DROP_BG,
            fg=TEXT,
            font=self.font_bold,
            cursor="hand2",
        )
        hint.pack(pady=(0, 2))
        support = tk.Label(
            self.drop_zone,
            text="图片：JPG / PNG / WebP / BMP / TIFF   ·   视频：MP4 / MOV / MKV / AVI 等",
            bg=DROP_BG,
            fg=MUTED,
            font=self.font_tiny,
            cursor="hand2",
        )
        support.pack()
        if not self._dnd_enabled:
            tk.Label(
                self.drop_zone,
                text="当前环境拖拽不可用，请点击下方按钮选择文件",
                bg=DROP_BG,
                fg=WARNING,
                font=self.font_tiny,
            ).pack(pady=(2, 0))

        self.select_files_btn = ttk.Button(
            self.drop_zone,
            text="选择文件",
            style="Secondary.TButton",
            command=self.choose_files,
            cursor="hand2",
        )
        self.select_files_btn.pack(pady=(8, 8))

        for widget in (self.drop_zone, plus, hint, support):
            widget.bind("<Button-1>", lambda _e: self.choose_files())

        # 文件列表
        tree_wrap = tk.Frame(
            parent, bg=CARD, highlightbackground=BORDER, highlightthickness=1
        )
        tree_wrap.pack(fill="both", expand=True)

        columns = ("name", "kind", "size", "status")
        self.file_tree = ttk.Treeview(
            tree_wrap,
            columns=columns,
            show="headings",
            selectmode="browse",
            height=8,
        )
        self.file_tree.heading("name", text="文件", anchor="w")
        self.file_tree.heading("kind", text="类型", anchor="center")
        self.file_tree.heading("size", text="大小", anchor="e")
        self.file_tree.heading("status", text="状态", anchor="center")
        self.file_tree.column("name", width=230, minwidth=150, stretch=True, anchor="w")
        self.file_tree.column("kind", width=58, minwidth=48, stretch=False, anchor="center")
        self.file_tree.column("size", width=78, minwidth=64, stretch=False, anchor="e")
        self.file_tree.column("status", width=84, minwidth=72, stretch=False, anchor="center")
        self.file_tree.tag_configure("running", foreground=ACCENT)
        self.file_tree.tag_configure("done", foreground=SUCCESS)
        self.file_tree.tag_configure("error", foreground=ERROR)
        self.file_tree.tag_configure("cancelled", foreground=FAINT)
        self.file_tree.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(tree_wrap, orient="vertical", command=self.file_tree.yview)
        scrollbar.pack(side="right", fill="y")
        self.file_tree.configure(yscrollcommand=scrollbar.set)
        self.file_tree.bind("<<TreeviewSelect>>", self._on_tree_select)

        # 列表操作
        actions = tk.Frame(parent, bg=CARD)
        actions.pack(fill="x", pady=(10, 0))
        self.remove_btn = ttk.Button(
            actions,
            text="移除所选",
            style="Secondary.TButton",
            command=self.remove_selected,
            cursor="hand2",
        )
        self.remove_btn.pack(side="left")
        self.clear_btn = ttk.Button(
            actions,
            text="清空列表",
            style="Secondary.TButton",
            command=self.clear_files,
            cursor="hand2",
        )
        self.clear_btn.pack(side="left", padx=(8, 0))
        tk.Label(
            actions,
            text="支持一次添加多个文件",
            bg=CARD,
            fg=FAINT,
            font=self.font_tiny,
        ).pack(side="right", pady=(4, 0))

        if self._dnd_enabled:
            self._enable_dnd(self)
            self._enable_dnd(self.drop_zone)
            self._enable_dnd(self.file_tree)

    def _build_settings_panel(self, parent: tk.Frame) -> None:
        header = self._section_header(parent, "2", "灰度标准", "共 10 种算法")
        header.pack(fill="x")

        self.standard_combo = ttk.Combobox(
            parent,
            textvariable=self.standard_var,
            values=[item.label for item in STANDARDS],
            state="readonly",
            font=self.font_ui,
        )
        self.standard_combo.pack(fill="x", pady=(9, 7))
        self.standard_combo.bind("<<ComboboxSelected>>", self._on_standard_changed)

        desc_frame = tk.Frame(
            parent,
            bg=DESC_BG,
            highlightbackground="#E6EBF3",
            highlightthickness=1,
            bd=0,
        )
        desc_frame.pack(fill="x")
        desc_inner = tk.Frame(desc_frame, bg=DESC_BG)
        desc_inner.pack(fill="x", padx=11, pady=8)
        self.formula_label = tk.Label(
            desc_inner,
            text="",
            bg=DESC_BG,
            fg="#334155",
            font=self.font_formula,
            anchor="w",
            justify="left",
            wraplength=390,
        )
        self.formula_label.pack(fill="x", anchor="w")
        self.desc_label = tk.Label(
            desc_inner,
            text="",
            bg=DESC_BG,
            fg=MUTED,
            font=self.font_small,
            anchor="w",
            justify="left",
            wraplength=390,
        )
        self.desc_label.pack(fill="x", anchor="w", pady=(4, 0))
        desc_frame.bind(
            "<Configure>",
            lambda e: (
                self.formula_label.configure(wraplength=max(240, e.width - 26)),
                self.desc_label.configure(wraplength=max(240, e.width - 26)),
            ),
        )

        ttk.Separator(parent, orient="horizontal").pack(fill="x", pady=10)

        header2 = self._section_header(parent, "3", "输出设置")
        header2.pack(fill="x")

        tk.Label(
            parent, text="保存到", bg=CARD, fg=MUTED, font=self.font_tiny, anchor="w"
        ).pack(fill="x", pady=(7, 3))
        path_row = tk.Frame(parent, bg=CARD)
        path_row.pack(fill="x")
        self.output_entry = ttk.Entry(path_row, textvariable=self.output_dir_var, font=self.font_small)
        self.output_entry.pack(side="left", fill="x", expand=True)
        self.browse_btn = ttk.Button(
            path_row,
            text="浏览",
            style="Secondary.TButton",
            command=self.choose_output_dir,
            cursor="hand2",
        )
        self.browse_btn.pack(side="left", padx=(7, 0))

        options = tk.Frame(parent, bg=CARD)
        options.pack(fill="x", pady=(8, 0))
        options.grid_columnconfigure(1, weight=1)
        tk.Label(
            options, text="图片格式", bg=CARD, fg=MUTED, font=self.font_small
        ).grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.image_format_combo = ttk.Combobox(
            options,
            textvariable=self.image_format_var,
            values=[label for _key, label in engine.IMAGE_FORMAT_CHOICES],
            state="readonly",
            width=18,
            font=self.font_small,
        )
        self.image_format_combo.grid(row=0, column=1, sticky="w")
        self.alpha_check = ttk.Checkbutton(
            options,
            text="保留透明通道",
            variable=self.keep_alpha_var,
        )
        self.alpha_check.grid(row=0, column=2, sticky="e", padx=(8, 0))

        self.video_hint = tk.Label(
            parent,
            text="",
            bg=CARD,
            fg=FAINT,
            font=self.font_tiny,
            anchor="w",
        )
        self.video_hint.pack(fill="x", pady=(6, 0))

        ttk.Separator(parent, orient="horizontal").pack(fill="x", pady=10)

        preview_header = tk.Frame(parent, bg=CARD)
        preview_header.pack(fill="x")
        tk.Label(
            preview_header, text="效果预览", bg=CARD, fg=TEXT, font=self.font_bold
        ).pack(side="left")
        self.preview_detail_label = tk.Label(
            preview_header,
            text="",
            bg=CARD,
            fg=FAINT,
            font=self.font_tiny,
            anchor="e",
        )
        self.preview_detail_label.pack(side="right")

        preview_row = tk.Frame(parent, bg=CARD)
        preview_row.pack(fill="x", pady=(7, 0))
        preview_row.grid_columnconfigure(0, weight=1, uniform="preview")
        preview_row.grid_columnconfigure(1, weight=1, uniform="preview")

        original_box = tk.Frame(preview_row, bg=CARD)
        original_box.grid(row=0, column=0, sticky="w")
        tk.Label(
            original_box, text="原始画面", bg=CARD, fg=MUTED, font=self.font_tiny, anchor="w"
        ).pack(fill="x", pady=(0, 3))
        self.preview_original_frame = tk.Frame(
            original_box,
            width=PREVIEW_BOX[0],
            height=PREVIEW_BOX[1],
            bg="#F7F8FA",
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        self.preview_original_frame.pack()
        self.preview_original_frame.pack_propagate(False)
        self.preview_original_label = tk.Label(
            self.preview_original_frame,
            text="等待选择文件",
            bg="#F7F8FA",
            fg=FAINT,
            font=self.font_tiny,
            justify="center",
        )
        self.preview_original_label.pack(fill="both", expand=True)

        gray_box = tk.Frame(preview_row, bg=CARD)
        gray_box.grid(row=0, column=1, sticky="e")
        self.gray_caption = tk.Label(
            gray_box, text="灰度效果", bg=CARD, fg=MUTED, font=self.font_tiny, anchor="w"
        )
        self.gray_caption.pack(fill="x", pady=(0, 3))
        self.preview_gray_frame = tk.Frame(
            gray_box,
            width=PREVIEW_BOX[0],
            height=PREVIEW_BOX[1],
            bg="#F7F8FA",
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        self.preview_gray_frame.pack()
        self.preview_gray_frame.pack_propagate(False)
        self.preview_gray_label = tk.Label(
            self.preview_gray_frame,
            text="灰度效果将在这里显示",
            bg="#F7F8FA",
            fg=FAINT,
            font=self.font_tiny,
            justify="center",
        )
        self.preview_gray_label.pack(fill="both", expand=True)

    def _build_footer(self) -> None:
        outer = tk.Frame(self, bg=BG)
        outer.grid(row=2, column=0, sticky="ew", padx=22, pady=(10, 14))
        card = tk.Frame(
            outer,
            bg=CARD,
            highlightbackground=BORDER,
            highlightthickness=1,
            bd=0,
        )
        card.pack(fill="x")
        inner = tk.Frame(card, bg=CARD)
        inner.pack(fill="x", padx=17, pady=11)
        inner.grid_columnconfigure(0, weight=1)

        left = tk.Frame(inner, bg=CARD)
        left.grid(row=0, column=0, sticky="ew")
        status_row = tk.Frame(left, bg=CARD)
        status_row.pack(fill="x")
        self.status_dot = tk.Canvas(
            status_row, width=12, height=12, bg=CARD, highlightthickness=0
        )
        self.status_dot.pack(side="left", padx=(0, 6))
        self._status_dot = self.status_dot.create_oval(2, 2, 10, 10, fill=FAINT, outline="")
        self.status_label = tk.Label(
            status_row,
            textvariable=self.status_var,
            bg=CARD,
            fg=TEXT,
            font=self.font_bold,
            anchor="w",
        )
        self.status_label.pack(side="left")

        self.detail_label = tk.Label(
            left,
            textvariable=self.detail_var,
            bg=CARD,
            fg=MUTED,
            font=self.font_small,
            anchor="w",
            justify="left",
            wraplength=520,
        )
        self.detail_label.pack(fill="x", pady=(2, 6))
        self.progress = ttk.Progressbar(
            left,
            orient="horizontal",
            mode="determinate",
            maximum=100,
            variable=self.progress_var,
        )
        self.progress.pack(fill="x")

        buttons = tk.Frame(inner, bg=CARD)
        buttons.grid(row=0, column=1, sticky="e", padx=(18, 0))
        self.open_folder_btn = ttk.Button(
            buttons,
            text="打开输出文件夹",
            style="Secondary.TButton",
            command=self.open_output_folder,
            cursor="hand2",
        )
        self.open_folder_btn.pack(side="left")
        self.stop_btn = ttk.Button(
            buttons,
            text="停止",
            style="Stop.TButton",
            command=self.stop_conversion,
            state="disabled",
            cursor="hand2",
        )
        self.stop_btn.pack(side="left", padx=(8, 0))
        self.start_btn = ttk.Button(
            buttons,
            text="开始转换",
            style="Primary.TButton",
            command=self.start_conversion,
            cursor="hand2",
        )
        self.start_btn.pack(side="left", padx=(8, 0))

    # ------------------------------------------------------------------
    # 拖拽与选择
    # ------------------------------------------------------------------
    def _on_settings_content_configure(self, _event=None) -> None:
        self.settings_canvas.configure(scrollregion=self.settings_canvas.bbox("all"))
        self.after_idle(self._update_settings_scrollbar)

    def _on_settings_canvas_configure(self, event) -> None:
        self.settings_canvas.itemconfigure(self._settings_window, width=event.width)
        self.after_idle(self._update_settings_scrollbar)

    def _update_settings_scrollbar(self) -> None:
        try:
            bbox = self.settings_canvas.bbox("all")
            if not bbox:
                return
            content_height = bbox[3] - bbox[1]
            canvas_height = self.settings_canvas.winfo_height()
            needed = content_height > canvas_height + 2
            mapped = bool(self.settings_scroll.winfo_ismapped())
            if needed and not mapped:
                self.settings_scroll.pack(
                    side="right", fill="y", before=self.settings_canvas
                )
            elif not needed and mapped:
                self.settings_scroll.pack_forget()
                self.settings_canvas.yview_moveto(0)
        except Exception:
            pass

    def _on_mousewheel(self, event):
        try:
            widget = self.winfo_containing(event.x_root, event.y_root)
        except Exception:
            widget = None
        target = widget
        while target is not None and target is not self.settings_canvas:
            target = getattr(target, "master", None)
        if target is not self.settings_canvas:
            return None
        if getattr(event, "num", None) == 4:
            units = -3
        elif getattr(event, "num", None) == 5:
            units = 3
        else:
            delta = getattr(event, "delta", 0)
            if not delta:
                return "break"
            units = -3 if delta > 0 else 3
        self.settings_canvas.yview_scroll(units, "units")
        return "break"

    def _enable_dnd(self, widget: tk.Widget) -> None:
        try:
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>", self._on_drop)
            widget.dnd_bind("<<DropEnter>>", self._on_drop_enter)
            widget.dnd_bind("<<DropLeave>>", self._on_drop_leave)
        except Exception:
            pass

    def _dnd_action(self, event) -> str:
        return getattr(event, "action", None) or DND_COPY

    def _on_drop_enter(self, event):
        try:
            self.drop_zone.configure(highlightbackground=ACCENT, highlightthickness=2)
        except Exception:
            pass
        return self._dnd_action(event)

    def _on_drop_leave(self, event):
        try:
            self.drop_zone.configure(highlightbackground="#D8DDE5", highlightthickness=1)
        except Exception:
            pass
        return self._dnd_action(event)

    def _on_drop(self, event):
        try:
            self.drop_zone.configure(highlightbackground="#D8DDE5", highlightthickness=1)
        except Exception:
            pass
        if self._running:
            self._set_status("转换正在进行", "请等待当前任务结束，或点击“停止”。", WARNING)
            return self._dnd_action(event)
        try:
            data = getattr(event, "data", "") or ""
            raw_paths = self.tk.splitlist(data) if data else []
        except Exception:
            raw_paths = []
        paths = []
        for raw in raw_paths:
            text = str(raw).strip()
            if text.startswith("file://"):
                try:
                    from urllib.parse import unquote, urlparse

                    parsed = urlparse(text)
                    text = unquote(parsed.path)
                    if os.name == "nt" and text.startswith("/") and len(text) > 2 and text[2] == ":":
                        text = text[1:]
                except Exception:
                    pass
            if text:
                paths.append(Path(text))
        if paths:
            self._add_paths(paths)
        return self._dnd_action(event)

    def choose_files(self) -> None:
        if self._running:
            return
        patterns = " ".join(
            f"*{suffix}" for suffix in sorted(engine.IMAGE_SUFFIXES | engine.VIDEO_SUFFIXES)
        )
        files = filedialog.askopenfilenames(
            parent=self,
            title="选择图片或视频",
            initialdir=str(engine.desktop_dir()),
            filetypes=[
                ("支持的图片和视频", patterns),
                ("图片", "*.jpg *.jpeg *.png *.webp *.bmp *.tif *.tiff"),
                ("视频", "*.mp4 *.mov *.mkv *.avi *.m4v *.wmv *.flv *.webm"),
                ("所有文件", "*.*"),
            ],
        )
        if files:
            self._add_paths([Path(path) for path in files])

    def _add_paths(self, paths: List[Path]) -> None:
        if self._running:
            return
        added = 0
        rejected: List[str] = []
        existing = {str(item["path"]).casefold() for item in self.items.values()}
        first_added_iid = None

        for raw_path in paths:
            try:
                path = raw_path.expanduser().resolve()
            except Exception:
                path = raw_path
            if not path.is_file():
                rejected.append(f"{path.name}（文件不存在或暂不支持文件夹）")
                continue
            kind = engine.media_kind(path)
            if kind is None:
                rejected.append(f"{path.name}（不支持的格式）")
                continue
            key = str(path).casefold()
            if key in existing:
                continue
            try:
                size_text = engine.human_size(path.stat().st_size)
            except Exception:
                size_text = "—"
            iid = f"item{self._next_iid}"
            self._next_iid += 1
            self.items[iid] = {
                "path": path,
                "kind": kind,
                "size_text": size_text,
                "status": "待转换",
                "output": None,
            }
            self.order.append(iid)
            self.file_tree.insert(
                "",
                "end",
                iid=iid,
                values=(path.name, "图片" if kind == "image" else "视频", size_text, "待转换"),
            )
            existing.add(key)
            added += 1
            if first_added_iid is None:
                first_added_iid = iid

        self._update_count()
        if added:
            self._set_status(
                f"已添加 {added} 个文件",
                "选择灰度标准后点击“开始转换”；也可以继续拖入更多文件。",
                ACCENT,
            )
            if not self.file_tree.selection() and first_added_iid:
                self.file_tree.selection_set(first_added_iid)
                self.file_tree.focus(first_added_iid)
                self.file_tree.see(first_added_iid)
            elif first_added_iid:
                self.file_tree.see(first_added_iid)
        if rejected:
            text = "\n".join(rejected[:8])
            if len(rejected) > 8:
                text += f"\n…以及另外 {len(rejected) - 8} 个文件"
            if added == 0:
                messagebox.showwarning("没有可添加的文件", text, parent=self)
            else:
                self._set_status(
                    f"已添加 {added} 个文件，跳过 {len(rejected)} 个",
                    "跳过的项目：" + "；".join(rejected[:3]),
                    WARNING,
                )

    def remove_selected(self) -> None:
        if self._running:
            return
        selected = self.file_tree.selection()
        if not selected:
            return
        for iid in selected:
            self._drop_item(iid)
        self._update_count()
        self._clear_preview()
        if self.order:
            self._set_status("已移除所选文件", f"队列中还有 {len(self.order)} 个文件。", ACCENT)
        else:
            self._set_status("准备就绪", "队列已清空，继续添加图片或视频即可。", FAINT)

    def clear_files(self) -> None:
        if self._running:
            return
        for iid in list(self.order):
            self._drop_item(iid)
        self._update_count()
        self._clear_preview()
        self._set_status("准备就绪", "队列已清空，继续添加图片或视频即可。", FAINT)

    def _drop_item(self, iid: str) -> None:
        if self.file_tree.exists(iid):
            self.file_tree.delete(iid)
        self.items.pop(iid, None)
        if iid in self.order:
            self.order.remove(iid)

    def _update_count(self) -> None:
        count = len(self.order)
        self.count_var.set(f"{count} 个文件")
        if count == 0:
            self.progress_var.set(0)

    # ------------------------------------------------------------------
    # 设置与预览
    # ------------------------------------------------------------------
    def _restore_settings(self) -> None:
        cfg = self.config_data
        standard_key = cfg.get("standard", DEFAULT_STANDARD_KEY)
        if standard_key not in {item.key for item in STANDARDS}:
            standard_key = DEFAULT_STANDARD_KEY
        self.standard_var.set(get_standard(standard_key).label)

        format_key = cfg.get("image_format", "auto")
        valid_formats = {key for key, _label in engine.IMAGE_FORMAT_CHOICES}
        if format_key not in valid_formats:
            format_key = "auto"
        label = dict(engine.IMAGE_FORMAT_CHOICES)[format_key]
        self.image_format_var.set(label)
        self.keep_alpha_var.set(bool(cfg.get("keep_alpha", True)))

        output_dir = str(cfg.get("output_dir", "") or "").strip()
        self.output_dir_var.set(output_dir or str(engine.default_output_dir()))

        if engine.find_ffmpeg():
            self.video_hint.configure(
                text="视频：输出 MP4，优先使用 H.264，并保留原视频第一条音轨。",
                fg=FAINT,
            )
        else:
            self.video_hint.configure(
                text="视频：未找到 ffmpeg，当前只能转换图片。请使用完整版程序。",
                fg=WARNING,
            )

    def _current_standard_key(self) -> str:
        return label_to_key(self.standard_var.get())

    def _on_standard_changed(self, _event=None) -> None:
        self._update_standard_details()
        self._render_preview()

    def _update_standard_details(self) -> None:
        standard = get_standard(self._current_standard_key())
        self.formula_label.configure(text=standard.formula)
        self.desc_label.configure(text=standard.description)
        self.gray_caption.configure(text=f"灰度预览 · {standard.short}")
        # 更新说明框高度，避免长文案把下方控件挤出窗口
        self.update_idletasks()

    def _on_tree_select(self, _event=None) -> None:
        selected = self.file_tree.selection()
        if not selected:
            return
        iid = selected[0]
        item = self.items.get(iid)
        if not item:
            return
        path = item["path"]
        if self._preview_path == path and self._preview_data is not None:
            return

        self._preview_serial += 1
        serial = self._preview_serial
        self._preview_path = path
        self._preview_data = None
        self._preview_source = None
        self._preview_alpha = None
        self._set_preview_empty("正在读取预览…", "正在读取灰度预览…")
        self.preview_detail_label.configure(text="正在读取…")
        thread = threading.Thread(
            target=self._preview_worker,
            args=(serial, path),
            daemon=True,
        )
        thread.start()

    def _preview_worker(self, serial: int, path: Path) -> None:
        try:
            data = engine.load_preview(path, (440, 300))
            self._msg_queue.put(("preview_ok", (serial, path, data)))
        except Exception as exc:
            self._msg_queue.put(("preview_error", (serial, path, str(exc))))

    def _on_preview_ok(self, serial: int, path: Path, data: engine.PreviewData) -> None:
        if serial != self._preview_serial or path != self._preview_path:
            return
        self._preview_data = data
        self._preview_source = data.image
        self._preview_alpha = data.alpha
        self.preview_detail_label.configure(text=data.detail)
        self._render_preview()

    def _on_preview_error(self, serial: int, path: Path, error: str) -> None:
        if serial != self._preview_serial:
            return
        self._preview_data = None
        self._preview_source = None
        self._preview_alpha = None
        self._set_preview_empty("预览不可用", "无法读取该文件的预览")
        self.preview_detail_label.configure(text="预览读取失败")
        self._set_status("预览读取失败", error[:180], ERROR)

    def _checkerboard(self, size: Tuple[int, int], step: int = 8) -> Image.Image:
        width, height = max(1, size[0]), max(1, size[1])
        image = Image.new("RGB", (width, height), "#FBFBFC")
        draw = ImageDraw.Draw(image)
        for y in range(0, height, step):
            for x in range(0, width, step):
                if ((x // step) + (y // step)) % 2 == 0:
                    draw.rectangle([x, y, x + step - 1, y + step - 1], fill="#F0F2F5")
        return image

    def _compose_preview(
        self, image: Image.Image, alpha: Optional[Image.Image]
    ) -> Image.Image:
        bg = self._checkerboard(PREVIEW_BOX) if alpha is not None else Image.new(
            "RGB", PREVIEW_BOX, "#F7F8FA"
        )
        x = (PREVIEW_BOX[0] - image.width) // 2
        y = (PREVIEW_BOX[1] - image.height) // 2
        bg.paste(image, (x, y), alpha)
        return bg

    def _render_preview(self) -> None:
        if self._preview_source is None:
            return
        source = self._preview_source
        alpha = self._preview_alpha
        scale = min(
            (PREVIEW_BOX[0] - 4) / max(1, source.width),
            (PREVIEW_BOX[1] - 4) / max(1, source.height),
            1.0,
        )
        size = (
            max(1, int(round(source.width * scale))),
            max(1, int(round(source.height * scale))),
        )
        small = source.resize(size, Image.Resampling.LANCZOS)
        alpha_small = (
            alpha.resize(size, Image.Resampling.LANCZOS) if alpha is not None else None
        )
        gray = engine.make_gray_preview(small, self._current_standard_key())

        original_view = self._compose_preview(small, alpha_small)
        gray_view = self._compose_preview(gray, alpha_small)
        self._preview_photo_original = ImageTk.PhotoImage(original_view)
        self._preview_photo_gray = ImageTk.PhotoImage(gray_view)
        self.preview_original_label.configure(
            image=self._preview_photo_original, text="", bg="#F7F8FA"
        )
        self.preview_gray_label.configure(
            image=self._preview_photo_gray, text="", bg="#F7F8FA"
        )
        if self._preview_data:
            self.gray_caption.configure(
                text=f"灰度预览 · {get_standard(self._current_standard_key()).short}"
            )

    def _set_preview_empty(self, original_text: str, gray_text: str) -> None:
        self._preview_photo_original = None
        self._preview_photo_gray = None
        try:
            self.preview_original_label.configure(image="", text=original_text)
            self.preview_gray_label.configure(image="", text=gray_text)
        except Exception:
            pass

    def _clear_preview(self) -> None:
        self._preview_serial += 1
        self._preview_path = None
        self._preview_data = None
        self._preview_source = None
        self._preview_alpha = None
        self.preview_detail_label.configure(text="")
        self._set_preview_empty("等待选择文件", "灰度效果将在这里显示")

    # ------------------------------------------------------------------
    # 输出路径
    # ------------------------------------------------------------------
    def choose_output_dir(self) -> None:
        if self._running:
            return
        current = self.output_dir_var.get().strip()
        initial = current if current and Path(current).is_dir() else str(engine.desktop_dir())
        folder = filedialog.askdirectory(parent=self, title="选择输出文件夹", initialdir=initial)
        if folder:
            self.output_dir_var.set(folder)

    def _resolved_output_dir(self) -> Path:
        text = self.output_dir_var.get().strip()
        if not text:
            return engine.default_output_dir()
        path = Path(os.path.expandvars(os.path.expanduser(text)))
        if not path.is_absolute():
            path = engine.desktop_dir() / path
        return path

    def open_output_folder(self) -> None:
        try:
            folder = self._resolved_output_dir()
            engine.open_folder(folder)
        except Exception as exc:
            messagebox.showerror("无法打开文件夹", str(exc), parent=self)

    # ------------------------------------------------------------------
    # 转换流程
    # ------------------------------------------------------------------
    def start_conversion(self) -> None:
        if self._running:
            return
        if not self.order:
            messagebox.showinfo("还没有文件", "请先添加图片或视频。", parent=self)
            return

        standard_key = self._current_standard_key()
        label = self.image_format_var.get()
        format_key = "auto"
        for key, text in engine.IMAGE_FORMAT_CHOICES:
            if text == label:
                format_key = key
                break

        out_dir = self._resolved_output_dir()
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            probe = out_dir / ".gray_studio_write_test"
            probe.write_bytes(b"")
            probe.unlink()
        except Exception as exc:
            messagebox.showerror(
                "输出位置不可用",
                f"无法写入此文件夹：\n{out_dir}\n\n{exc}",
                parent=self,
            )
            return

        self.config_data.update(
            {
                "standard": standard_key,
                "image_format": format_key,
                "keep_alpha": bool(self.keep_alpha_var.get()),
                "output_dir": str(out_dir),
            }
        )
        _save_config(self.config_data)

        items_snapshot = [
            {
                "iid": iid,
                "path": self.items[iid]["path"],
                "kind": self.items[iid]["kind"],
            }
            for iid in self.order
            if iid in self.items
        ]
        if not items_snapshot:
            return

        self.failed_details = []
        self.last_outputs = []
        for iid in self.order:
            if iid in self.items:
                self._set_item_status(iid, "待转换", None)
        self._running = True
        self._cancel_event.clear()
        self.progress_var.set(0)
        self._set_controls_enabled(False)
        self._set_status(
            "开始转换",
            f"{len(items_snapshot)} 个文件 → {out_dir}",
            ACCENT,
        )
        thread = threading.Thread(
            target=self._conversion_worker,
            args=(
                items_snapshot,
                standard_key,
                out_dir,
                format_key,
                bool(self.keep_alpha_var.get()),
            ),
            daemon=True,
        )
        thread.start()

    def _conversion_worker(
        self,
        items: List[dict],
        standard_key: str,
        out_dir: Path,
        image_format: str,
        keep_alpha: bool,
    ) -> None:
        total = len(items)
        success = 0
        failed = 0
        cancelled = 0
        try:
            for position, item in enumerate(items):
                iid = item["iid"]
                path: Path = item["path"]
                if self._cancel_event.is_set():
                    for rest in items[position:]:
                        self._msg_queue.put(("item_status", (rest["iid"], "已取消", "cancelled")))
                        cancelled += 1
                    break

                self._msg_queue.put(("item_status", (iid, "转换中", "running")))
                self._msg_queue.put(
                    (
                        "progress",
                        (
                            position / total * 100.0,
                            f"正在转换 {position + 1}/{total}：{path.name}",
                            "读取并转换像素…" if item["kind"] == "image" else "开始解码视频…",
                        ),
                    )
                )
                try:
                    if item["kind"] == "image":
                        result = engine.convert_image(
                            path,
                            out_dir,
                            standard_key,
                            output_format=image_format,
                            keep_alpha=keep_alpha,
                        )
                    else:
                        def progress_cb(fraction: float, text: str, _pos=position, _name=path.name) -> None:
                            self._msg_queue.put(
                                (
                                    "progress",
                                    (
                                        (_pos + fraction) / total * 100.0,
                                        f"正在转换 {_pos + 1}/{total}：{_name}",
                                        text,
                                    ),
                                )
                            )

                        result = engine.convert_video(
                            path,
                            out_dir,
                            standard_key,
                            progress_cb=progress_cb,
                            cancel_event=self._cancel_event,
                        )
                except engine.ConversionCancelled:
                    self._msg_queue.put(("item_status", (iid, "已取消", "cancelled")))
                    cancelled += 1
                    for rest in items[position + 1:]:
                        self._msg_queue.put(("item_status", (rest["iid"], "已取消", "cancelled")))
                        cancelled += 1
                    break
                except Exception as exc:
                    failed += 1
                    error_text = str(exc) or exc.__class__.__name__
                    self._msg_queue.put(("item_error", (iid, error_text)))
                    self._msg_queue.put(
                        (
                            "progress",
                            (
                                (position + 1) / total * 100.0,
                                f"第 {position + 1}/{total} 个文件失败：{path.name}",
                                error_text[:180],
                            ),
                        )
                    )
                else:
                    success += 1
                    output = result.outputs[0] if result.outputs else None
                    self._msg_queue.put(
                        (
                            "item_done",
                            (
                                iid,
                                str(output) if output else "",
                                result.note,
                            ),
                        )
                    )
                    self._msg_queue.put(
                        (
                            "progress",
                            (
                                (position + 1) / total * 100.0,
                                f"已完成 {position + 1}/{total}：{path.name}",
                                (str(output) if output else ""),
                            ),
                        )
                    )
        except Exception as exc:
            self._msg_queue.put(("fatal", str(exc)))
            failed += 1
        finally:
            self._msg_queue.put(("finished", (success, failed, cancelled, str(out_dir))))

    def stop_conversion(self) -> None:
        if not self._running:
            return
        self._cancel_event.set()
        self.stop_btn.configure(state="disabled")
        self._set_status(
            "正在停止…",
            "当前帧处理完成后会安全结束，并保留已经转换好的文件。",
            WARNING,
        )

    def _poll_messages(self) -> None:
        try:
            while True:
                try:
                    kind, payload = self._msg_queue.get_nowait()
                except queue.Empty:
                    break
                if kind == "preview_ok":
                    self._on_preview_ok(*payload)
                elif kind == "preview_error":
                    self._on_preview_error(*payload)
                elif kind == "item_status":
                    iid, text, tag = payload
                    self._set_item_status(iid, text, tag)
                elif kind == "item_done":
                    iid, output, note = payload
                    self._set_item_status(iid, "已完成", "done")
                    if iid in self.items:
                        self.items[iid]["status"] = "已完成"
                        self.items[iid]["output"] = output
                    if output:
                        self.last_outputs.append(Path(output))
                elif kind == "item_error":
                    iid, error_text = payload
                    self._set_item_status(iid, "失败", "error")
                    name = self.items.get(iid, {}).get("path", Path("文件")).name
                    self.failed_details.append(f"{name}\n{error_text}")
                elif kind == "progress":
                    percent, status, detail = payload
                    self.progress_var.set(max(0.0, min(100.0, float(percent))))
                    self.status_var.set(status)
                    self.detail_var.set(detail)
                elif kind == "fatal":
                    self.failed_details.append(f"转换线程异常：{payload}")
                elif kind == "finished":
                    self._on_conversion_finished(*payload)
        except Exception:
            self._log_ui_error()
        try:
            self.after(100, self._poll_messages)
        except Exception:
            pass

    def _log_ui_error(self) -> None:
        try:
            log_path = Path.home() / ".grayscale_studio_error.log"
            with log_path.open("a", encoding="utf-8") as fh:
                fh.write(traceback.format_exc() + "\n")
        except Exception:
            pass

    def _on_conversion_finished(
        self, success: int, failed: int, cancelled: int, out_dir: str
    ) -> None:
        self._running = False
        self._set_controls_enabled(True)
        if success + failed + cancelled > 0 and cancelled == 0 and failed == 0:
            self.progress_var.set(100)
        total = success + failed + cancelled
        if cancelled:
            self._set_status(
                "已停止转换",
                f"完成 {success} 个，未处理 {cancelled} 个，失败 {failed} 个。已完成的文件保存在 {out_dir}",
                WARNING,
            )
        elif failed:
            self._set_status(
                "转换结束，有文件失败",
                f"成功 {success} 个，失败 {failed} 个。输出位置：{out_dir}",
                ERROR,
            )
        else:
            self._set_status(
                "转换完成",
                f"{success} 个文件已转换完成，保存在 {out_dir}（共 {total} 个）",
                SUCCESS,
            )
        if self.failed_details:
            details = "\n\n".join(self.failed_details)
            if len(details) > 2200:
                details = details[:2200] + "\n…（错误信息过长，已截断）"
            messagebox.showerror(
                "部分文件转换失败",
                "以下文件没有转换成功：\n\n" + details,
                parent=self,
            )

    def _set_item_status(self, iid: str, text: str, tag: Optional[str]) -> None:
        if not self.file_tree.exists(iid):
            return
        values = list(self.file_tree.item(iid, "values"))
        while len(values) < 4:
            values.append("")
        values[3] = text
        self.file_tree.item(iid, values=values, tags=(tag,) if tag else ())
        if iid in self.items:
            self.items[iid]["status"] = text

    def _set_status(self, status: str, detail: str = "", dot_color: str = FAINT) -> None:
        self.status_var.set(status)
        if detail:
            self.detail_var.set(detail)
        try:
            self.status_dot.itemconfigure(self._status_dot, fill=dot_color)
        except Exception:
            pass

    def _set_controls_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        self.select_files_btn.configure(state=state)
        self.remove_btn.configure(state=state)
        self.clear_btn.configure(state=state)
        self.browse_btn.configure(state=state)
        self.output_entry.configure(state=state)
        self.standard_combo.configure(state="readonly" if enabled else "disabled")
        self.image_format_combo.configure(state="readonly" if enabled else "disabled")
        self.alpha_check.configure(state=state)
        if enabled:
            self.start_btn.configure(text="开始转换", state="normal")
            self.stop_btn.configure(state="disabled")
        else:
            self.start_btn.configure(text="转换中…", state="disabled")
            self.stop_btn.configure(state="normal")

    # ------------------------------------------------------------------
    # 退出
    # ------------------------------------------------------------------
    def _current_format_key(self) -> str:
        label = self.image_format_var.get()
        for key, text in engine.IMAGE_FORMAT_CHOICES:
            if text == label:
                return key
        return "auto"

    def _save_settings(self) -> None:
        self.config_data.update(
            {
                "standard": self._current_standard_key(),
                "image_format": self._current_format_key(),
                "keep_alpha": bool(self.keep_alpha_var.get()),
                "output_dir": self.output_dir_var.get().strip(),
            }
        )
        _save_config(self.config_data)

    def _on_close(self) -> None:
        if self._running:
            if not messagebox.askyesno(
                "转换正在进行",
                "现在退出会停止当前转换。\n已经完成的文件会保留。\n\n确定要退出吗？",
                parent=self,
            ):
                return
            self._cancel_event.set()
        self._save_settings()
        self.destroy()


def run(initial_paths: Optional[List[Path]] = None) -> None:
    app = GrayscaleStudioApp()
    if initial_paths:
        app.after(150, lambda: app._add_paths(list(initial_paths)))
    app.mainloop()
