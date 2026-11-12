from __future__ import annotations

import datetime as dt
import os
import threading
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
import tkinter as tk

from PIL import Image, ImageDraw, ImageTk
from reportlab.lib.units import mm

from .gfont import FontInfo, GFont, discover_fonts
from .layout import build_metrics
from .preview import build_preview_geometry
from .renderer import GenerationResult, generate_document


class HandwritingApp:
    def __init__(self, root: tk.Tk, project_root: Path, font_dir: Path):
        self.root = root
        self.project_root = project_root
        self.font_dir = font_dir
        self.font_infos: list[FontInfo] = []
        self.font_by_iid: dict[str, FontInfo] = {}
        self.info_by_path: dict[str, FontInfo] = {}
        self.selected_paths: set[str] = set()
        self.selection_history: list[str] = []
        self._preview_font: GFont | None = None
        self._preview_path: str | None = None
        self._preview_resize_job: str | None = None
        self._preview_guard = False
        self._font_scan_thread: threading.Thread | None = None
        self._worker: threading.Thread | None = None
        self._last_result: GenerationResult | None = None

        self.line_count_var = tk.StringVar(value="52")
        self.seed_var = tk.StringVar()
        self.output_dir_var = tk.StringVar(value=str(project_root / "output"))
        self.base_name_var = tk.StringVar(
            value=f"手写文档_{dt.datetime.now():%Y%m%d_%H%M%S}"
        )
        self.pdf_var = tk.BooleanVar(value=True)
        self.docx_var = tk.BooleanVar(value=True)
        self.search_var = tk.StringVar()
        self.preview_char_var = tk.StringVar(value="中")
        self.preview_font_var = tk.StringVar(value="尚未勾选字体")
        self.character_count_var = tk.StringVar(value="0 字符")
        self.font_summary_var = tk.StringVar(value="正在扫描字体...")
        self.selected_summary_var = tk.StringVar(value="已选 0 种")

        self._configure_window()
        self._build_styles()
        self._build_ui()
        self.preview_char_var.trace_add("write", self._on_preview_char_changed)
        self.root.after(60, self._load_fonts_async)

    def _configure_window(self) -> None:
        self.root.title("A3 随机手写字体文档生成器")
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        width = min(1320, screen_width - 80)
        height = min(920, screen_height - 110)
        self.root.geometry(f"{width}x{height}")
        self.root.minsize(min(1100, width), min(740, height))
        self.root.configure(bg="#f4f2ec")

    def _build_styles(self) -> None:
        self.style = ttk.Style(self.root)
        if "vista" in self.style.theme_names():
            self.style.theme_use("vista")
        self.style.configure(".", font=("Microsoft YaHei UI", 10))
        self.style.configure("Title.TLabel", font=("Microsoft YaHei UI", 24, "bold"))
        self.style.configure("Subtitle.TLabel", foreground="#646054")
        self.style.configure("Section.TLabelframe.Label", font=("Microsoft YaHei UI", 10, "bold"))
        self.style.configure("Primary.TButton", font=("Microsoft YaHei UI", 11, "bold"))
        self.style.configure("Treeview", rowheight=27)
        self.style.configure("Treeview.Heading", font=("Microsoft YaHei UI", 10, "bold"))
        self._checked_icon = self._make_check_icon(checked=True)
        self._unchecked_icon = self._make_check_icon(checked=False)

    @staticmethod
    def _make_check_icon(checked: bool) -> ImageTk.PhotoImage:
        image = Image.new("RGBA", (20, 20), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        if checked:
            draw.rounded_rectangle(
                (1, 1, 18, 18),
                radius=4,
                fill="#168de2",
                outline="#0878c7",
                width=1,
            )
            draw.line((5, 10, 8, 14, 15, 6), fill="white", width=2, joint="curve")
        else:
            draw.rounded_rectangle(
                (1, 1, 18, 18),
                radius=4,
                fill="#ffffff",
                outline="#8b8b8b",
                width=1,
            )
        return ImageTk.PhotoImage(image)

    def _build_ui(self) -> None:
        header = tk.Frame(self.root, bg="#18332f", padx=24, pady=12)
        header.pack(fill="x")
        ttk.Label(
            header,
            text="A3 随机手写字体文档生成器",
            style="Title.TLabel",
            foreground="#f6f1e6",
            background="#18332f",
        ).pack(anchor="w")
        ttk.Label(
            header,
            text="A3 横向 · 双栏 · 逐字随机字体 / ±10° 旋转 / 字高 5% 位移",
            style="Subtitle.TLabel",
            foreground="#c7d6cf",
            background="#18332f",
        ).pack(anchor="w", pady=(4, 0))

        body = tk.Frame(self.root, bg="#f4f2ec", padx=18, pady=10)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=0, minsize=430)
        body.rowconfigure(0, weight=1)

        left = ttk.LabelFrame(body, text=" 待排文字 ", style="Section.TLabelframe")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(1, weight=1)
        ttk.Label(
            left,
            text="粘贴约 15,000 字中文、英文或混合文本。明示换行会保留。",
            foreground="#646054",
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(12, 6))
        text_shell = tk.Frame(left, bg="#ffffff", highlightthickness=1, highlightbackground="#d2cec3")
        text_shell.grid(row=1, column=0, sticky="nsew", padx=12)
        text_shell.columnconfigure(0, weight=1)
        text_shell.rowconfigure(0, weight=1)
        self.text = tk.Text(
            text_shell,
            wrap="word",
            undo=True,
            height=12,
            spacing1=2,
            spacing3=3,
            font=("Microsoft YaHei UI", 11),
            relief="flat",
            padx=12,
            pady=12,
            bg="#fffefa",
            fg="#222222",
            insertbackground="#18332f",
            selectbackground="#b8d1c7",
        )
        text_scroll = ttk.Scrollbar(text_shell, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=text_scroll.set)
        self.text.grid(row=0, column=0, sticky="nsew")
        text_scroll.grid(row=0, column=1, sticky="ns")
        self.text.bind("<<Modified>>", self._on_text_modified)
        left_bottom = tk.Frame(left, bg="#f4f2ec")
        left_bottom.grid(row=2, column=0, sticky="ew", padx=12, pady=(7, 11))
        ttk.Label(left_bottom, textvariable=self.character_count_var).pack(side="left")
        ttk.Button(left_bottom, text="清空", command=self._clear_text).pack(side="right")
        ttk.Button(left_bottom, text="从文件导入", command=self._import_text).pack(side="right", padx=(0, 8))

        right = tk.Frame(body, bg="#f4f2ec")
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)

        settings = ttk.LabelFrame(right, text=" 排版与输出 ", style="Section.TLabelframe")
        settings.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        settings.columnconfigure(1, weight=1)
        ttk.Label(settings, text="每栏行数（常用 46–58）").grid(
            row=0, column=0, sticky="w", padx=12, pady=(10, 5)
        )
        line_box = ttk.Spinbox(
            settings,
            from_=1,
            to=100,
            increment=1,
            width=8,
            textvariable=self.line_count_var,
        )
        line_box.grid(row=0, column=1, sticky="w", pady=(10, 5))
        ttk.Label(settings, text="随机种子").grid(row=0, column=2, sticky="e", padx=(12, 5), pady=(10, 5))
        ttk.Entry(settings, width=15, textvariable=self.seed_var).grid(
            row=0, column=3, sticky="w", padx=(0, 12), pady=(10, 5)
        )
        ttk.Label(settings, text="输出目录").grid(row=1, column=0, sticky="w", padx=12, pady=4)
        ttk.Entry(settings, textvariable=self.output_dir_var).grid(
            row=1, column=1, columnspan=2, sticky="ew", pady=4
        )
        ttk.Button(settings, text="选择", command=self._choose_output_dir).grid(
            row=1, column=3, sticky="ew", padx=(5, 12), pady=4
        )
        ttk.Label(settings, text="文件名").grid(row=2, column=0, sticky="w", padx=12, pady=4)
        ttk.Entry(settings, textvariable=self.base_name_var).grid(
            row=2, column=1, columnspan=3, sticky="ew", padx=(0, 12), pady=4
        )
        format_frame = tk.Frame(settings, bg="#f4f2ec")
        format_frame.grid(row=3, column=0, columnspan=4, sticky="w", padx=12, pady=(5, 10))
        ttk.Checkbutton(format_frame, text="生成 PDF（矢量精确版）", variable=self.pdf_var).pack(side="left")
        ttk.Checkbutton(format_frame, text="同时生成 Word（页面图）", variable=self.docx_var).pack(
            side="left", padx=(16, 0)
        )

        fonts = ttk.LabelFrame(right, text=" 字体选择 ", style="Section.TLabelframe")
        fonts.grid(row=1, column=0, sticky="nsew")
        fonts.columnconfigure(0, weight=1)
        fonts.rowconfigure(3, weight=1)
        search_row = tk.Frame(fonts, bg="#f4f2ec")
        search_row.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))
        search_row.columnconfigure(1, weight=1)
        ttk.Label(search_row, text="搜索文件名").grid(row=0, column=0, padx=(0, 6))
        ttk.Entry(search_row, textvariable=self.search_var).grid(row=0, column=1, sticky="ew")
        ttk.Button(search_row, text="刷新", width=6, command=self._load_fonts_async).grid(
            row=0, column=2, padx=(6, 0)
        )
        self.search_var.trace_add("write", lambda *_: self._refresh_font_tree())
        action_row = tk.Frame(fonts, bg="#f4f2ec")
        action_row.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 5))
        ttk.Label(action_row, textvariable=self.font_summary_var).pack(side="left")
        ttk.Label(action_row, textvariable=self.selected_summary_var).pack(side="right")

        preview_frame = tk.Frame(
            fonts,
            bg="#e9ede8",
            highlightthickness=1,
            highlightbackground="#cbd4cc",
        )
        preview_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=(3, 7))
        preview_frame.columnconfigure(0, weight=1)
        preview_info = tk.Frame(preview_frame, bg="#e9ede8")
        preview_info.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        preview_title = tk.Frame(preview_info, bg="#e9ede8")
        preview_title.pack(fill="x", anchor="w")
        ttk.Label(preview_title, text="单字预览").pack(side="left")
        tk.Entry(
            preview_title,
            textvariable=self.preview_char_var,
            width=3,
            justify="center",
            font=("Microsoft YaHei UI", 16, "bold"),
            relief="solid",
            borderwidth=1,
        ).pack(side="left", padx=7)
        ttk.Label(
            preview_info,
            textvariable=self.preview_font_var,
            foreground="#526158",
            wraplength=250,
            justify="left",
        ).pack(anchor="w", pady=(8, 0))
        self.preview_canvas = tk.Canvas(
            preview_frame,
            width=96,
            height=96,
            bg="#fffefa",
            highlightthickness=0,
        )
        self.preview_canvas.grid(row=0, column=1, sticky="ne", padx=8, pady=8)
        self.preview_canvas.bind("<Configure>", self._schedule_preview_draw)

        tree_shell = tk.Frame(fonts, bg="#ffffff")
        tree_shell.grid(row=3, column=0, sticky="nsew", padx=10)
        tree_shell.columnconfigure(0, weight=1)
        tree_shell.rowconfigure(0, weight=1)
        self.font_tree = ttk.Treeview(
            tree_shell,
            columns=("count", "filename"),
            show="tree headings",
            selectmode="browse",
            height=8,
        )
        self.font_tree.heading("#0", text="选择")
        self.font_tree.heading("count", text="字符数")
        self.font_tree.heading("filename", text="文件名")
        self.font_tree.column("#0", width=54, minwidth=50, anchor="center", stretch=False)
        self.font_tree.column("count", width=70, minwidth=60, anchor="e", stretch=False)
        self.font_tree.column(
            "filename",
            width=270,
            minwidth=180,
            anchor="w",
            stretch=True,
        )
        font_scroll = ttk.Scrollbar(tree_shell, orient="vertical", command=self.font_tree.yview)
        self.font_tree.configure(yscrollcommand=font_scroll.set)
        self.font_tree.grid(row=0, column=0, sticky="nsew")
        font_scroll.grid(row=0, column=1, sticky="ns")
        self.font_tree.bind("<Button-1>", self._on_font_click)
        self.font_tree.bind("<Double-1>", self._on_font_double_click)
        self.font_tree.bind("<space>", self._toggle_focused_font)
        self.font_tree.bind("<Control-a>", self._select_visible_fonts)
        button_row = tk.Frame(fonts, bg="#f4f2ec")
        button_row.grid(row=4, column=0, sticky="ew", padx=10, pady=8)
        ttk.Button(button_row, text="全选当前", command=self._select_visible_fonts).pack(side="left")
        ttk.Button(button_row, text="清空选择", command=self._clear_font_selection).pack(side="left", padx=6)
        ttk.Button(
            button_row,
            text="选前 5 种",
            command=self._select_first_five_fonts,
        ).pack(side="left")

        bottom = tk.Frame(right, bg="#f4f2ec")
        bottom.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        bottom.columnconfigure(0, weight=1)
        self.progress = ttk.Progressbar(bottom, maximum=1.0)
        self.progress.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.generate_button = ttk.Button(
            bottom,
            text="生成 A3 文档",
            style="Primary.TButton",
            command=self._start_generation,
        )
        self.generate_button.grid(row=0, column=1, sticky="e", ipadx=14, ipady=4)
        ttk.Button(bottom, text="打开输出目录", command=self._open_output_dir).grid(
            row=0, column=2, sticky="e", padx=(8, 0)
        )
        self.status = tk.Text(
            bottom,
            height=1,
            wrap="word",
            relief="flat",
            bg="#e9e6dd",
            fg="#4c4a43",
            padx=8,
            pady=6,
            font=("Microsoft YaHei UI", 9),
            state="disabled",
        )
        self.status.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(9, 0))

    def _on_text_modified(self, _event=None) -> None:
        if not self.text.edit_modified():
            return
        count = len(self.text.get("1.0", "end-1c"))
        self.character_count_var.set(f"{count:,} 字符")
        self.text.edit_modified(False)

    def _clear_text(self) -> None:
        self.text.delete("1.0", "end")

    def _import_text(self) -> None:
        path = filedialog.askopenfilename(
            title="选择 UTF-8 文本",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")],
        )
        if not path:
            return
        try:
            content = Path(path).read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            content = Path(path).read_text(encoding="gb18030")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", content)
        self._write_log(f"已导入 {Path(path).name}")

    def _load_fonts_async(self) -> None:
        if self._font_scan_thread and self._font_scan_thread.is_alive():
            return
        self.font_summary_var.set("正在扫描字体素材…")
        self._font_scan_thread = threading.Thread(target=self._scan_fonts, daemon=True)
        self._font_scan_thread.start()

    def _scan_fonts(self) -> None:
        try:
            infos = discover_fonts(self.font_dir)
            self.root.after(0, self._fonts_loaded, infos)
        except Exception as exc:
            self.root.after(0, lambda: self._fonts_failed(str(exc)))

    def _fonts_failed(self, message: str) -> None:
        self.font_summary_var.set("字体扫描失败")
        self._write_log(f"字体扫描失败: {message}")

    def _fonts_loaded(self, infos: list[FontInfo]) -> None:
        valid = [info for info in infos if info.available]
        invalid = [info for info in infos if not info.available]
        self.font_infos = sorted(valid, key=lambda info: info.path.name.casefold())
        self.info_by_path = {str(info.path): info for info in self.font_infos}
        valid_paths = set(self.info_by_path)
        self.selected_paths.intersection_update(valid_paths)
        self.selection_history = [
            path for path in self.selection_history if path in self.selected_paths
        ]
        self.font_summary_var.set(
            f"{len(self.font_infos)} 种可用 · 动态读取"
        )
        self._refresh_font_tree()
        if not self.selected_paths:
            self._select_first_five_fonts()
        else:
            self._refresh_preview_font()
        self._write_log(
            f"已从 {self.font_dir} 动态读取 {len(self.font_infos)} 种可用字体"
        )
        if invalid:
            self._write_log(
                "已排除空/损坏字体：" + "、".join(info.path.name for info in invalid)
            )

    def _refresh_font_tree(self) -> None:
        if not hasattr(self, "font_tree"):
            return
        for iid in self.font_tree.get_children():
            self.font_tree.delete(iid)
        self.font_by_iid.clear()
        query = self.search_var.get().strip().casefold()
        for info in self.font_infos:
            filename = info.path.name
            if query and query not in filename.casefold():
                continue
            iid = str(info.path)
            self.font_by_iid[iid] = info
            self.font_tree.insert(
                "",
                "end",
                iid=iid,
                image=(
                    self._checked_icon
                    if iid in self.selected_paths
                    else self._unchecked_icon
                ),
                values=(f"{info.character_count:,}", filename),
            )
        self._update_selected_summary()

    def _on_font_click(self, event: tk.Event) -> str | None:
        row = self.font_tree.identify_row(event.y)
        column = self.font_tree.identify_column(event.x)
        if row in self.font_by_iid and column == "#0":
            self._toggle_font(row)
            return "break"
        return None

    def _on_font_double_click(self, event: tk.Event) -> str | None:
        row = self.font_tree.identify_row(event.y)
        if row in self.font_by_iid:
            self._toggle_font(row)
            return "break"
        return None

    def _toggle_focused_font(self, _event=None) -> str:
        row = self.font_tree.focus()
        if row in self.font_by_iid:
            self._toggle_font(row)
        return "break"

    def _toggle_font(self, path: str) -> None:
        if path in self.selected_paths:
            self._set_font_checked(path, False)
        else:
            self._set_font_checked(path, True)
        self._update_selected_summary()
        self._refresh_preview_font()

    def _set_font_checked(self, path: str, checked: bool) -> None:
        if checked:
            self.selected_paths.add(path)
            self.selection_history = [
                item for item in self.selection_history if item != path
            ]
            self.selection_history.append(path)
        else:
            self.selected_paths.discard(path)
            self.selection_history = [
                item for item in self.selection_history if item != path
            ]
        if self.font_tree.exists(path):
            self.font_tree.item(
                path,
                image=self._checked_icon if checked else self._unchecked_icon,
            )

    def _update_selected_summary(self) -> None:
        self.selected_summary_var.set(f"已选 {len(self.selected_paths)} 种")

    def _select_visible_fonts(self, _event=None) -> str:
        visible = list(self.font_tree.get_children())
        for path in visible:
            if path in self.font_by_iid:
                self._set_font_checked(path, True)
        self._update_selected_summary()
        self._refresh_preview_font()
        return "break"

    def _clear_font_selection(self) -> None:
        self.selected_paths.clear()
        self.selection_history.clear()
        for path in self.font_tree.get_children():
            if self.font_tree.exists(path):
                self.font_tree.item(path, image=self._unchecked_icon)
        self._update_selected_summary()
        self._refresh_preview_font()

    def _select_first_five_fonts(self) -> None:
        self.selected_paths.clear()
        self.selection_history.clear()
        for info in self.font_infos[:5]:
            self._set_font_checked(str(info.path), True)
        self._update_selected_summary()
        self._refresh_preview_font()

    def _last_selected_font(self) -> FontInfo | None:
        for path in reversed(self.selection_history):
            if path in self.selected_paths and path in self.info_by_path:
                return self.info_by_path[path]
        return None

    def _close_preview_font(self) -> None:
        if self._preview_font is not None:
            self._preview_font.close()
        self._preview_font = None
        self._preview_path = None

    def _refresh_preview_font(self) -> None:
        info = self._last_selected_font()
        self._close_preview_font()
        if info is None:
            self.preview_font_var.set("尚未勾选字体")
            self._draw_preview()
            return
        try:
            self._preview_font = GFont(info.path)
        except Exception as exc:
            self.preview_font_var.set(f"无法读取：{info.path.name}")
            self._write_log(f"字体预览读取失败: {exc}")
            self._draw_preview()
            return
        self._preview_path = str(info.path)
        self.preview_font_var.set(info.path.name)
        self._draw_preview()

    def _on_preview_char_changed(self, *_args) -> None:
        if self._preview_guard:
            return
        value = self.preview_char_var.get().strip()
        normalized = value[:1]
        if normalized != self.preview_char_var.get():
            self._preview_guard = True
            self.preview_char_var.set(normalized)
            self._preview_guard = False
        self._draw_preview()

    def _schedule_preview_draw(self, _event=None) -> None:
        if not hasattr(self, "preview_canvas"):
            return
        if self._preview_resize_job:
            self.root.after_cancel(self._preview_resize_job)
        self._preview_resize_job = self.root.after(60, self._draw_preview)

    def _draw_preview(self) -> None:
        self._preview_resize_job = None
        if not hasattr(self, "preview_canvas"):
            return
        canvas = self.preview_canvas
        canvas.delete("all")
        width = max(80, canvas.winfo_width())
        height = max(80, canvas.winfo_height())
        char = self.preview_char_var.get().strip()
        if not char:
            canvas.create_text(
                width / 2,
                height / 2,
                text="输入一个字符进行预览",
                fill="#777777",
                font=("Microsoft YaHei UI", 10),
            )
            return
        if self._preview_font is None:
            canvas.create_text(
                width / 2,
                height / 2,
                text="请先勾选一种字体",
                fill="#777777",
                font=("Microsoft YaHei UI", 10),
            )
            return
        if not self._preview_font.supports(char):
            canvas.create_text(
                width / 2,
                height / 2,
                text=f"该字体缺少“{char}”",
                fill="#a84a3f",
                font=("Microsoft YaHei UI", 11),
            )
            return
        geometry = build_preview_geometry(
            self._preview_font,
            char,
            width,
            height,
            padding=10,
        )
        try:
            preview_font_size = build_metrics(int(self.line_count_var.get())).font_size
        except (ValueError, TypeError):
            preview_font_size = build_metrics(52).font_size
        target_size = max(1.0, min(width - 20, height - 20) * 0.9)
        preview_stroke = max(
            1.5,
            min(12.0, target_size * (0.5 * mm) / preview_font_size),
        )
        for segment in geometry.segments:
            if len(segment) == 1:
                x, y = segment[0]
                canvas.create_oval(
                    x - preview_stroke / 2,
                    y - preview_stroke / 2,
                    x + preview_stroke / 2,
                    y + preview_stroke / 2,
                    fill="#111111",
                    outline="",
                )
            elif len(segment) >= 2:
                coordinates = [coordinate for point in segment for coordinate in point]
                canvas.create_line(
                    *coordinates,
                    fill="#111111",
                    width=preview_stroke,
                    capstyle=tk.ROUND,
                    joinstyle=tk.ROUND,
                    smooth=True,
                )

    def _choose_output_dir(self) -> None:
        selected = filedialog.askdirectory(
            title="选择输出目录",
            initialdir=self.output_dir_var.get() or str(self.project_root),
        )
        if selected:
            self.output_dir_var.set(selected)

    def _open_output_dir(self) -> None:
        path = Path(self.output_dir_var.get()).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(path)

    def _write_log(self, message: str) -> None:
        stamp = dt.datetime.now().strftime("%H:%M:%S")
        self.status.configure(state="normal")
        self.status.insert("end", f"[{stamp}] {message}\n")
        self.status.see("end")
        self.status.configure(state="disabled")

    def _set_progress(self, fraction: float, message: str) -> None:
        self.progress["value"] = fraction
        if message:
            self._write_log(message)

    def _start_generation(self) -> None:
        if self._worker and self._worker.is_alive():
            return
        text = self.text.get("1.0", "end-1c")
        if not text.strip():
            messagebox.showwarning("缺少文本", "请先粘贴或导入待排文字。")
            return
        selected = sorted(self.selected_paths)
        if not selected:
            messagebox.showwarning("缺少字体", "请至少选择一种手写字体。")
            return
        if not self.pdf_var.get() and not self.docx_var.get():
            messagebox.showwarning("缺少输出格式", "请至少选择 PDF 或 Word。")
            return
        try:
            lines = int(self.line_count_var.get())
        except ValueError:
            messagebox.showwarning("行数无效", "每栏行数必须是 1 到 100 的整数。")
            return
        if not 1 <= lines <= 100:
            messagebox.showwarning("行数无效", "每栏行数必须在 1 到 100 之间。")
            return
        seed_text = self.seed_var.get().strip()
        try:
            seed = int(seed_text) if seed_text else None
        except ValueError:
            messagebox.showwarning("随机种子无效", "随机种子必须是整数。")
            return
        output_dir = Path(self.output_dir_var.get()).expanduser()
        output_dir.mkdir(parents=True, exist_ok=True)
        base_name = self.base_name_var.get().strip() or f"手写文档_{dt.datetime.now():%Y%m%d_%H%M%S}"
        base_name = Path(base_name).stem
        pdf_path = output_dir / f"{base_name}.pdf"
        docx_path = output_dir / f"{base_name}.docx" if self.docx_var.get() else None
        settings = {
            "text": text,
            "font_paths": selected,
            "lines": lines,
            "pdf": pdf_path,
            "docx": docx_path,
            "seed": seed,
        }
        self.generate_button.configure(state="disabled")
        self.progress["value"] = 0
        self._write_log(f"开始生成：{len(selected)} 种字体，每栏 {lines} 行")
        self._worker = threading.Thread(
            target=self._generation_worker,
            args=(settings,),
            daemon=True,
        )
        self._worker.start()

    def _generation_worker(self, settings: dict) -> None:
        def progress(fraction: float, message: str) -> None:
            self.root.after(0, self._set_progress, fraction, message)

        try:
            result = generate_document(
                text=settings["text"],
                font_paths=settings["font_paths"],
                lines_per_column=settings["lines"],
                output_pdf=settings["pdf"],
                output_docx=settings["docx"],
                seed=settings["seed"],
                progress=progress,
            )
            self.root.after(0, self._generation_finished, result)
        except Exception as exc:
            self.root.after(0, self._generation_failed, str(exc))

    def _generation_finished(self, result: GenerationResult) -> None:
        self._last_result = result
        self.generate_button.configure(state="normal")
        self.progress["value"] = 1.0
        self._write_log(
            f"完成：{result.page_count} 页，{result.character_count:,} 字符，"
            f"随机种子 {result.seed}"
        )
        if result.fallback_count:
            self._write_log(
                f"有 {result.fallback_count} 个字符不在所选字体中，已使用系统字体回退。"
            )
        details = (
            f"共 {result.page_count} 页\n"
            f"PDF: {result.pdf_path}\n"
            + (f"Word: {result.docx_path}\n" if result.docx_path else "")
            + f"随机种子: {result.seed}"
        )
        messagebox.showinfo("生成完成", details)

    def _generation_failed(self, message: str) -> None:
        self.generate_button.configure(state="normal")
        self.progress["value"] = 0
        self._write_log(f"生成失败: {message}")
        messagebox.showerror("生成失败", message)


def launch_gui(project_root: Path, font_dir: Path) -> None:
    root = tk.Tk()
    HandwritingApp(root, project_root, font_dir)
    root.mainloop()
