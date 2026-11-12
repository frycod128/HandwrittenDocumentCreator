from __future__ import annotations

import datetime as dt
import os
import threading
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
import tkinter as tk

from .gfont import FontInfo, discover_fonts
from .renderer import GenerationResult, generate_document


class HandwritingApp:
    def __init__(self, root: tk.Tk, project_root: Path, font_dir: Path):
        self.root = root
        self.project_root = project_root
        self.font_dir = font_dir
        self.font_infos: list[FontInfo] = []
        self.font_by_iid: dict[str, FontInfo] = {}
        self.selected_paths: set[str] = set()
        self._restoring_selection = False
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
        self.character_count_var = tk.StringVar(value="0 字符")
        self.font_summary_var = tk.StringVar(value="正在扫描字体...")
        self.selected_summary_var = tk.StringVar(value="已选 0 种")

        self._configure_window()
        self._build_styles()
        self._build_ui()
        self.root.after(60, self._load_fonts_async)

    def _configure_window(self) -> None:
        self.root.title("A3 随机手写字体文档生成器")
        self.root.geometry("1280x860")
        self.root.minsize(1040, 720)
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

    def _build_ui(self) -> None:
        header = tk.Frame(self.root, bg="#18332f", padx=24, pady=18)
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

        body = tk.Frame(self.root, bg="#f4f2ec", padx=18, pady=14)
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
        fonts.rowconfigure(2, weight=1)
        search_row = tk.Frame(fonts, bg="#f4f2ec")
        search_row.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))
        search_row.columnconfigure(0, weight=1)
        ttk.Entry(search_row, textvariable=self.search_var).grid(row=0, column=0, sticky="ew")
        self.search_var.trace_add("write", lambda *_: self._refresh_font_tree())
        action_row = tk.Frame(fonts, bg="#f4f2ec")
        action_row.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 5))
        ttk.Label(action_row, textvariable=self.font_summary_var).pack(side="left")
        ttk.Label(action_row, textvariable=self.selected_summary_var).pack(side="right")
        tree_shell = tk.Frame(fonts, bg="#ffffff")
        tree_shell.grid(row=2, column=0, sticky="nsew", padx=10)
        tree_shell.columnconfigure(0, weight=1)
        tree_shell.rowconfigure(0, weight=1)
        self.font_tree = ttk.Treeview(
            tree_shell,
            columns=("count",),
            show="headings",
            selectmode="extended",
            height=13,
        )
        self.font_tree.heading("#0", text="字体")
        self.font_tree.heading("count", text="字符数")
        self.font_tree.column("#0", width=285, minwidth=180, stretch=True)
        self.font_tree.column("count", width=75, minwidth=60, anchor="e", stretch=False)
        font_scroll = ttk.Scrollbar(tree_shell, orient="vertical", command=self.font_tree.yview)
        self.font_tree.configure(yscrollcommand=font_scroll.set)
        self.font_tree.grid(row=0, column=0, sticky="nsew")
        font_scroll.grid(row=0, column=1, sticky="ns")
        self.font_tree.bind("<<TreeviewSelect>>", self._on_font_selection)
        self.font_tree.bind("<Control-a>", self._select_visible_fonts)
        button_row = tk.Frame(fonts, bg="#f4f2ec")
        button_row.grid(row=3, column=0, sticky="ew", padx=10, pady=8)
        ttk.Button(button_row, text="全选当前", command=self._select_visible_fonts).pack(side="left")
        ttk.Button(button_row, text="清空选择", command=self._clear_font_selection).pack(side="left", padx=6)
        ttk.Button(
            button_row,
            text="恢复推荐字体",
            command=self._select_recommended_fonts,
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
            height=5,
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
        threading.Thread(target=self._scan_fonts, daemon=True).start()

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
        self.font_infos = sorted(valid, key=lambda info: info.name.casefold())
        self.font_summary_var.set(f"{len(self.font_infos)} 种可用")
        self._refresh_font_tree()
        self._select_recommended_fonts()
        self._write_log(
            f"已读取 {self.font_dir.name}：{len(self.font_infos)} 种可用字体"
        )
        if invalid:
            self._write_log(
                "已排除空/损坏字体：" + "、".join(info.name for info in invalid)
            )

    def _refresh_font_tree(self) -> None:
        if not hasattr(self, "font_tree") or not self.font_infos:
            return
        self._capture_visible_selection()
        self._restoring_selection = True
        for iid in self.font_tree.get_children():
            self.font_tree.delete(iid)
        self.font_by_iid.clear()
        query = self.search_var.get().strip().casefold()
        visible_paths: list[str] = []
        for info in self.font_infos:
            if query and query not in info.name.casefold():
                continue
            iid = str(info.path)
            self.font_by_iid[iid] = info
            self.font_tree.insert(
                "",
                "end",
                iid=iid,
                text=info.name,
                values=(f"{info.character_count:,}",),
            )
            visible_paths.append(iid)
        selected = [iid for iid in visible_paths if iid in self.selected_paths]
        if selected:
            self.font_tree.selection_set(selected)
        self._restoring_selection = False
        self._update_selected_summary()

    def _capture_visible_selection(self) -> None:
        if self._restoring_selection or not hasattr(self, "font_tree"):
            return
        visible = set(self.font_tree.get_children())
        self.selected_paths.difference_update(visible)
        self.selected_paths.update(self.font_tree.selection())

    def _on_font_selection(self, _event=None) -> None:
        if self._restoring_selection:
            return
        self._capture_visible_selection()
        self._update_selected_summary()

    def _update_selected_summary(self) -> None:
        self.selected_summary_var.set(f"已选 {len(self.selected_paths)} 种")

    def _select_visible_fonts(self, _event=None) -> str:
        visible = list(self.font_tree.get_children())
        self.selected_paths.update(visible)
        self.font_tree.selection_set(visible)
        self._update_selected_summary()
        return "break"

    def _clear_font_selection(self) -> None:
        self.selected_paths.clear()
        self.font_tree.selection_remove(self.font_tree.selection())
        self._update_selected_summary()

    def _select_recommended_fonts(self) -> None:
        keywords = (
            "常用_kvenjoy_美文",
            "超连笔快写-3500字",
            "手写_kvenjoy_杜磊",
            "楷体_kvenjoy_大孔龙",
            "乐行书_kvenjoy_乐乐",
        )
        chosen: set[str] = set()
        for keyword in keywords:
            match = next(
                (info for info in self.font_infos if keyword.casefold() in info.name.casefold()),
                None,
            )
            if match:
                chosen.add(str(match.path))
        if chosen:
            self.selected_paths = chosen
            visible = [
                iid
                for iid in self.font_tree.get_children()
                if iid in self.selected_paths
            ]
            self._restoring_selection = True
            self.font_tree.selection_set(visible)
            self._restoring_selection = False
            self._update_selected_summary()

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
        self._capture_visible_selection()
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
