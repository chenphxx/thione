"""Markdown 改造页面: 生成博客导入 ZIP 或原目录文档"""

import logging
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from ... import kit
from ...errors import open_path, show_error
from ...shell.page import ToolPage
from ...theme import BODY_GAP, SIZE_LABEL, tint
from .archiver import (
    ArchiveResult,
    build_archive,
    build_documents,
    collect_markdown_inputs,
    default_output,
    document_output_path,
    normalize_image_folder,
)
from .constants import (
    ALLOW_MISSING_HINT,
    DEFAULT_IMAGE_FOLDER,
    DOCUMENT_FORCE_HINT,
    DOCUMENT_IMAGE_FOLDER_HINT,
    DOCUMENT_OUTPUT_HINT,
    EMPTY_TEXT,
    FILE_COLUMNS,
    GENERATE_ZIP_HINT,
    PAGE_TITLE,
    STATUS_IDLE,
    SUBTITLE,
    ZIP_FORCE_HINT,
    ZIP_IMAGE_FOLDER_HINT,
    ZIP_OUTPUT_HINT,
)

logger = logging.getLogger(__name__)

POLL_INTERVAL_MS = 120


class MarkdownPage(ToolPage):
    """把 Markdown 与图片打包或输出到原目录的工具页面"""

    key = "markdown"
    title = PAGE_TITLE
    icon = "\uE8A5"
    subtitle = SUBTITLE

    def __init__(self, master, shell):
        super().__init__(master, shell)

        self._sources: list[Path] = []
        self._messages = queue.Queue()
        self._worker = None
        self._poll_job = None
        self._busy = False
        self._last_output = None
        self._output_auto = True
        self._allow_missing_var = tk.BooleanVar(value=False)
        self._force_var = tk.BooleanVar(value=False)
        self._generate_zip_var = tk.BooleanVar(value=True)
        self._output_var = tk.StringVar(value="")
        self._image_folder_var = tk.StringVar(value=DEFAULT_IMAGE_FOLDER)

        self._build_toolbar()
        self._build_output_panel()
        self._build_file_panel()
        self._build_statusbar()
        self._refresh_files()
        self.status.set_kind("idle")
        self.status.set_text(STATUS_IDLE)

    # ---------------- 界面构建 ----------------
    def _build_toolbar(self):
        """添加输入文件并启动处理的主操作区"""
        row = self.add_row(gap=8)
        self.btn_add_files = ttk.Button(
            row,
            text="添加文件",
            style="TButton",
            command=self._add_files,
        )
        self.btn_add_files.pack(side="left")
        self.btn_add_folder = ttk.Button(
            row,
            text="添加文件夹",
            style="TButton",
            command=self._add_folder,
        )
        self.btn_add_folder.pack(side="left", padx=(8, 0))
        self.btn_remove = ttk.Button(
            row,
            text="移除选中",
            style="TButton",
            command=self._remove_selected,
        )
        self.btn_remove.pack(side="left", padx=(8, 0))
        self.btn_clear = ttk.Button(
            row,
            text="清空列表",
            style="TButton",
            command=self._clear_files,
        )
        self.btn_clear.pack(side="right")
        self.btn_start = ttk.Button(
            row,
            text="开始改造",
            style="Primary.TButton",
            command=self._start,
        )
        self.btn_start.pack(side="right", padx=(0, 8))

    def _build_output_panel(self):
        """压缩模式, 输出路径, 图片目录与处理选项"""
        panel = self.add_panel(title="输出设置", grow=False)
        mode_row = tk.Frame(panel.body, bd=0, highlightthickness=0)
        tint(mode_row, bg="panel")
        mode_row.configure(bg=self.theme.rgb("panel"))
        mode_row.pack(side="top", fill="x")
        self.check_generate_zip = kit.Check(
            mode_row,
            self.theme,
            value=GENERATE_ZIP_HINT,
            variable=self._generate_zip_var,
            command=self._on_generate_zip_changed,
            surface="panel",
        )
        self.check_generate_zip.pack(side="left")
        self.output_hint_label = kit.text(
            mode_row,
            self.theme,
            value=ZIP_OUTPUT_HINT,
            size=SIZE_LABEL,
            token="muted",
            surface="panel",
        )
        self.output_hint_label.pack(side="right")

        output_row = tk.Frame(panel.body, bd=0, highlightthickness=0)
        tint(output_row, bg="panel")
        output_row.configure(bg=self.theme.rgb("panel"))
        output_row.pack(side="top", fill="x", pady=(BODY_GAP, 0))
        self.output_label = kit.text(
            output_row,
            self.theme,
            value="输出 ZIP",
            size=SIZE_LABEL,
            token="muted",
            surface="panel",
        )
        self.output_label.pack(side="left", padx=(0, 10))
        self.output_field = kit.EntryField(
            output_row,
            self.theme,
            variable=self._output_var,
            width=520,
        )
        self.output_field.pack(side="left", fill="x", expand=True)
        self.output_field.entry.bind(
            "<KeyRelease>",
            lambda _event: setattr(self, "_output_auto", False),
        )
        self.btn_output = ttk.Button(
            output_row,
            text="选择位置",
            style="TButton",
            command=self._choose_output,
        )
        self.btn_output.pack(side="left", padx=(8, 0))

        image_row = tk.Frame(panel.body, bd=0, highlightthickness=0)
        tint(image_row, bg="panel")
        image_row.configure(bg=self.theme.rgb("panel"))
        image_row.pack(side="top", fill="x", pady=(BODY_GAP, 0))
        kit.text(
            image_row,
            self.theme,
            value="图片目录",
            size=SIZE_LABEL,
            token="muted",
            surface="panel",
        ).pack(side="left", padx=(0, 10))
        self.image_folder_field = kit.EntryField(
            image_row,
            self.theme,
            variable=self._image_folder_var,
            width=520,
        )
        self.image_folder_field.pack(side="left", fill="x", expand=True)
        self.image_hint_label = kit.text(
            image_row,
            self.theme,
            value=ZIP_IMAGE_FOLDER_HINT,
            size=SIZE_LABEL,
            token="muted",
            surface="panel",
        )
        self.image_hint_label.pack(side="left", padx=(10, 0))

        options = tk.Frame(panel.body, bd=0, highlightthickness=0)
        tint(options, bg="panel")
        options.configure(bg=self.theme.rgb("panel"))
        options.pack(side="top", fill="x", pady=(BODY_GAP, 0))
        self.check_missing = kit.Check(
            options,
            self.theme,
            value=ALLOW_MISSING_HINT,
            variable=self._allow_missing_var,
            surface="panel",
        )
        self.check_missing.pack(side="left")
        self.check_force = kit.Check(
            options,
            self.theme,
            value=ZIP_FORCE_HINT,
            variable=self._force_var,
            surface="panel",
        )
        self.check_force.pack(side="left", padx=(18, 0))
        self._sync_output_mode()

    def _on_generate_zip_changed(self, _enabled):
        """切换压缩包与本地文档输出模式"""
        self._sync_output_mode()

    def _sync_output_mode(self):
        """按当前模式更新输出控件和说明文字"""
        generate_zip = self._generate_zip_var.get()
        output_enabled = generate_zip and not self._busy
        self.output_field.set_enabled(output_enabled)
        self.btn_output.configure(
            state="normal" if output_enabled else "disabled"
        )
        self.output_hint_label.configure(
            text=ZIP_OUTPUT_HINT if generate_zip else DOCUMENT_OUTPUT_HINT
        )
        self.image_hint_label.configure(
            text=(
                ZIP_IMAGE_FOLDER_HINT
                if generate_zip
                else DOCUMENT_IMAGE_FOLDER_HINT
            )
        )
        self.check_force.label.configure(
            text=ZIP_FORCE_HINT if generate_zip else DOCUMENT_FORCE_HINT
        )

    def _build_file_panel(self):
        """待处理的 Markdown 文件列表"""
        self.file_panel = self.add_panel(
            title="Markdown 文件",
            right="0 个文件",
            body_pad=(0, 0),
        )
        self.table = kit.Table(
            self.file_panel.body,
            self.theme,
            FILE_COLUMNS,
            empty_text=EMPTY_TEXT,
            surface="panel",
        )
        self.table.pack(side="top", fill="both", expand=True)
        self.table.body.bind("<Double-1>", self._open_selected)
        self.table.body.bind("<Delete>", lambda _event: self._remove_selected())

    def _build_statusbar(self):
        """状态栏显示文件数量并提供打开输出目录的入口"""
        self.status.set_kind("idle")
        self.status.set_text(STATUS_IDLE)
        self.btn_open_output = ttk.Button(
            self.status.actions,
            text="打开输出目录",
            style="TButton",
            command=self._open_output_folder,
            state="disabled",
        )
        self.status.add_action(self.btn_open_output)

    # ---------------- 文件选择 ----------------
    def _add_files(self):
        """选择一个或多个 Markdown 文件"""
        if self._busy:
            return
        paths = filedialog.askopenfilenames(
            parent=self.window,
            title="选择 Markdown 文件",
            filetypes=[("Markdown", "*.md"), ("所有文件", "*.*")],
        )
        self._add_paths(paths)

    def _add_folder(self):
        """递归添加文件夹中的 Markdown 文件"""
        if self._busy:
            return
        folder = filedialog.askdirectory(
            parent=self.window,
            title="选择包含 Markdown 的文件夹",
        )
        if not folder:
            return
        sources = collect_markdown_inputs([folder])
        if not sources:
            messagebox.showinfo(
                "提示",
                "这个文件夹里没有 Markdown 文件",
                parent=self.window,
            )
            return
        self._add_sources(sources)

    def _add_paths(self, paths):
        """把文件对话框返回的路径加入列表"""
        if not paths:
            return
        self._add_sources(collect_markdown_inputs(list(paths)))

    def _add_sources(self, sources):
        """去重后加入源文件列表并刷新默认输出路径"""
        known = {source.resolve() for source in self._sources}
        added = 0
        for source in sources:
            resolved = source.resolve()
            if resolved not in known:
                known.add(resolved)
                self._sources.append(resolved)
                added += 1
        self._sources.sort(key=lambda item: str(item).lower())
        if added:
            self._refresh_files()
            self.status.set_kind("idle")
            self.status.set_text(f"已添加 {added} 个 Markdown 文件")

    def _remove_selected(self):
        """移除列表里选中的 Markdown"""
        if self._busy:
            return
        selected = self.table.selection()
        if not selected:
            return
        for index in reversed(selected):
            del self._sources[index]
        self._refresh_files()

    def _clear_files(self):
        """清空源文件与自动输出路径"""
        if self._busy:
            return
        self._sources.clear()
        self._last_output = None
        self._output_auto = True
        self.btn_open_output.configure(state="disabled")
        self._refresh_files()

    def _refresh_files(self):
        """同步文件表格、数量和默认输出路径"""
        rows = []
        for source in self._sources:
            rows.append(
                {
                    "name": source.name,
                    "folder": str(source.parent),
                    "data": source,
                }
            )
        self.table.set_rows(rows)
        self.file_panel.set_right(f"{len(rows)} 个文件")
        if self._output_auto:
            self._output_var.set(
                str(default_output(self._sources)) if self._sources else ""
            )
        self.status.set_text(
            f"已选择 {len(rows)} 个 Markdown 文件"
            if rows else STATUS_IDLE
        )

    def _open_selected(self, _event=None):
        """用系统默认程序打开选中的 Markdown"""
        selected = self.table.selection()
        if selected:
            open_path(self._sources[selected[0]], parent=self.window)

    # ---------------- 输出设置 ----------------
    def _choose_output(self):
        """选择 ZIP 输出位置"""
        current = self._output_var.get().strip()
        initial_dir = str(Path(current).parent) if current else ""
        initial_file = Path(current).name if current else "markdown-blog-import.zip"
        path = filedialog.asksaveasfilename(
            parent=self.window,
            title="保存博客导入包",
            defaultextension=".zip",
            filetypes=[("ZIP 压缩包", "*.zip")],
            initialdir=initial_dir or None,
            initialfile=initial_file,
        )
        if path:
            self._output_var.set(path)
            self._output_auto = False

    def _open_output_folder(self):
        """打开最近一次输出的所在目录"""
        if self._last_output is not None:
            open_path(self._last_output.parent, parent=self.window)

    # ---------------- 后台处理 ----------------
    def _start(self):
        """校验输入并启动后台改造"""
        if self._busy:
            return
        if not self._sources:
            messagebox.showwarning(
                "提示",
                "先添加要处理的 Markdown 文件",
                parent=self.window,
            )
            return
        generate_zip = self._generate_zip_var.get()
        output = None
        if generate_zip:
            output_text = self._output_var.get().strip()
            if not output_text:
                messagebox.showwarning(
                    "提示",
                    "请选择输出 ZIP 的位置",
                    parent=self.window,
                )
                return
            output = Path(output_text).expanduser()
            if output.suffix.lower() != ".zip":
                output = output.with_suffix(".zip")
                self._output_var.set(str(output))
            output = output.resolve()

        force = self._force_var.get()
        try:
            image_folder = normalize_image_folder(
                self._image_folder_var.get()
            )
        except ValueError as exc:
            messagebox.showwarning(
                "提示",
                str(exc),
                parent=self.window,
            )
            return
        self._image_folder_var.set(image_folder)
        if generate_zip:
            if output.exists() and not force:
                overwrite = messagebox.askyesno(
                    "覆盖文件",
                    f"输出文件已存在, 是否覆盖?\n\n{output}",
                    parent=self.window,
                )
                if not overwrite:
                    return
                force = True
        else:
            existing = [
                document_output_path(source)
                for source in self._sources
                if document_output_path(source).exists()
            ]
            if existing and not force:
                paths = "\n".join(str(path) for path in existing)
                overwrite = messagebox.askyesno(
                    "覆盖文件",
                    f"以下改造文档已存在, 是否覆盖?\n\n{paths}",
                    parent=self.window,
                )
                if not overwrite:
                    return
                force = True

        self._set_busy(True)
        self.status.set_kind("run")
        self.status.set_text("正在整理 Markdown 和图片...")
        self._messages = queue.Queue()
        self._worker = threading.Thread(
            target=self._run_conversion,
            args=(
                list(self._sources),
                output,
                self._allow_missing_var.get(),
                force,
                image_folder,
                generate_zip,
            ),
            name="markdown-conversion",
            daemon=True,
        )
        self._worker.start()
        self._poll_job = self.root.after(POLL_INTERVAL_MS, self._poll_messages)

    def _run_conversion(
        self,
        sources,
        output,
        allow_missing,
        force,
        image_folder,
        generate_zip,
    ):
        """后台线程: 只处理文件, 不接触 Tk 控件"""
        try:
            if generate_zip:
                result = build_archive(
                    sources,
                    output,
                    allow_missing=allow_missing,
                    force=force,
                    image_folder=image_folder,
                )
            else:
                result = build_documents(
                    sources,
                    allow_missing=allow_missing,
                    force=force,
                    image_folder=image_folder,
                )
        except Exception as exc:
            logger.exception("Markdown 改造失败")
            self._messages.put(("error", exc))
        else:
            self._messages.put(("done", result))

    def _poll_messages(self):
        """主线程轮询后台结果并刷新界面"""
        self._poll_job = None
        try:
            message = self._messages.get_nowait()
        except queue.Empty:
            if self._worker is not None and self._worker.is_alive():
                self._poll_job = self.root.after(
                    POLL_INTERVAL_MS,
                    self._poll_messages,
                )
            else:
                self._set_busy(False)
                self.status.set_kind("fail")
                self.status.set_text("处理线程意外结束, 详情见日志")
            return

        self._worker = None
        self._set_busy(False)
        if message[0] == "done":
            _, result = message
            self._conversion_finished(result)
        else:
            self._conversion_failed(message[1])

    def _conversion_finished(self, result: ArchiveResult):
        """展示成功统计并保留打开输出目录的入口"""
        self._last_output = result.outputs[0] if result.outputs else None
        self.btn_open_output.configure(state="normal")
        self.status.set_kind("ok")
        if result.mode == "document":
            summary = (
                f"已生成 {result.markdown_count} 个改造文档, "
                f"图片 {result.image_count} 张"
            )
        else:
            name = result.outputs[0].name if result.outputs else "ZIP"
            summary = (
                f"已生成 {name}: "
                f"Markdown {result.markdown_count} 个, "
                f"图片 {result.image_count} 张"
            )
        if result.skipped_images:
            summary += f", 已忽略 {result.skipped_images} 张缺失图片"
        self.status.set_text(summary)

    def _conversion_failed(self, exc):
        """展示改造错误并恢复操作"""
        self.status.set_kind("fail")
        self.status.set_text("生成失败, 详情见提示窗口")
        show_error(
            str(exc),
            title="Markdown改造失败",
            parent=self.window,
        )

    def _set_busy(self, busy):
        """处理中禁用会改变输入的操作"""
        self._busy = busy
        state = "disabled" if busy else "normal"
        self.btn_add_files.configure(state=state)
        self.btn_add_folder.configure(state=state)
        self.btn_remove.configure(state=state)
        self.btn_start.configure(state=state)
        self.btn_clear.configure(state=state)
        self.check_generate_zip.set_enabled(not busy)
        self._sync_output_mode()
        self.image_folder_field.set_enabled(not busy)
        self.check_missing.set_enabled(not busy)
        self.check_force.set_enabled(not busy)

    def on_close(self):
        """退出前停止界面轮询"""
        if self._poll_job is not None:
            self.root.after_cancel(self._poll_job)
            self._poll_job = None
        return True
