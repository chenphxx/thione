"""文件格式转换页面: 把选中的音频文件批量转成另一种格式。

转换交给 ffmpeg 子进程完成, 页面只负责收集文件 目标格式与输出位置, 并在后台
线程里依次处理; 进度与结果经队列回到主线程刷新列表, 因此后台线程不碰 tkinter
对象。音乐平台的加密容器先还原成常见音频, 已经是目标格式的文件只复制不重新
编码, 因为重新编码只会白白损失音质。转换过程中可以终止, 没写完的输出文件会被
删掉。
"""

import logging
import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from ...errors import open_path, show_error
from ...shell.page import ToolPage
from . import ffmpeg, platforms, tasks
from .constants import (
    AUDIO_FORMATS,
    AUTO_BITRATE,
    BITRATE_LABELS,
    BITRATES,
    CARD_TITLE,
    CONVERT_FAILED,
    COPY_FAILED,
    CUSTOM_DEST_HINT,
    DECRYPT_FAILED,
    DEFAULT_BITRATE,
    DEFAULT_FORMAT,
    DEST_CUSTOM,
    DEST_LABELS,
    DEST_SOURCE,
    DEST_MISSING,
    DEST_SOURCE_HINT,
    EMPTY_HINT,
    EMPTY_TITLE,
    ENGINE_CHOOSE,
    ENGINE_DETECTING,
    ENGINE_LABEL,
    ENGINE_MISSING,
    FFMPEG_MISSING,
    FILE_COLUMNS,
    FORMAT_CHOICES,
    FORMAT_CODECS,
    FORMAT_COMBO_WIDTH,
    FORMAT_LABELS,
    INPUT_EXTENSIONS,
    LOSSLESS_ONLY_FORMATS,
    LOSSLESS_QUALITY,
    PAGE_HINT,
    PAGE_TITLE,
    PROGRESS_IDLE,
    PROGRESS_RUNNING,
    PROGRESS_STOPPING,
    QUALITY_COMBO_WIDTH,
    QUALITY_HINTS,
    RESCAN_LABEL,
    SKIP_SAME_FORMAT,
    TOP_QUALITY,
    STATUS_CANCELLED,
    STATUS_COPIED,
    STATUS_DECODED,
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_RUNNING,
    STATUS_SKIPPED,
    STATUS_WAITING,
    SUMMARY_DONE,
    SUMMARY_SHORT,
    SUMMARY_STOPPED,
)

logger = logging.getLogger(__name__)

#: 后台线程消息的轮询间隔 (毫秒)
POLL_INTERVAL_MS = 120
#: 退出时等待后台线程收尾的时间 (秒)
CLOSE_JOIN_TIMEOUT = 3
#: 表格的默认高度 (行数), 窗口变高时表格会自己撑开
TABLE_HEIGHT = 8
#: 失败原因在状态列里的最大长度, 超出部分截断
REASON_MAX_CHARS = 48
#: 状态列的颜色标记
TAG_RUNNING = "running"
TAG_DONE = "done"
TAG_SKIPPED = "skipped"
TAG_ERROR = "error"


class ConvertPage(ToolPage):
    """在常见音频格式之间批量转换的工具页面。"""

    key = "convert"
    title = PAGE_TITLE
    icon = "🎵"
    subtitle = "把音频 视频与加密音乐文件批量转换成常见格式"

    def __init__(self, master, shell):
        super().__init__(master, shell)

        self._items = []
        self._rows = []
        self._folders = []
        self._outputs = set()
        self._dest_dir = ""
        self._ffmpeg_path = ""
        self._engine_checked = False
        self._messages = queue.Queue()
        self._worker = None
        self._stop_event = None
        self._process = None
        self._poll_job = None
        self._ongoing = False
        self._finished = 0
        self._fraction = 0.0
        self._active_index = None
        self._ok = 0
        self._skipped = 0
        self._failed = 0

        self._format_var = tk.StringVar(value=FORMAT_LABELS[DEFAULT_FORMAT])
        self._quality_var = tk.StringVar(
            value=BITRATE_LABELS[BITRATES.index(DEFAULT_BITRATE)])
        self._quality_hint_var = tk.StringVar()
        self._dest_var = tk.StringVar(value=DEST_SOURCE)
        self._dest_path_var = tk.StringVar(value=DEST_SOURCE_HINT)
        self._hint_var = tk.StringVar(value=PAGE_HINT)
        self._engine_var = tk.StringVar(
            value=f"{ENGINE_LABEL}: {ENGINE_DETECTING}")
        self._counts_var = tk.StringVar()
        self._progress_var = tk.StringVar(value=PROGRESS_IDLE)

        self._build_toolbar()
        self.add_divider()
        # 状态栏先于列表 pack: 高度不够时先压缩列表, 而不是把状态栏挤出可视区
        self._build_statusbar()
        self._build_list_card()

        self._sync_quality()
        self._update_counts()
        self._update_empty_state()
        self._update_actions()
        self._poll_job = self.root.after(POLL_INTERVAL_MS, self._poll_messages)

    # ---------------- 界面构建 ----------------
    def _build_toolbar(self):
        """工具条三行: 标题与主操作 输入与格式 输出位置与列表操作。

        最小窗口宽度下放不下全部控件, 因此设置区拆成两行, 避免控件被 Tk
        挤出可视区。
        """
        bar, head, actions = self.build_toolbar()

        ttk.Label(head, text=PAGE_TITLE,
                  style="PanelHeader.TLabel").pack(side="left")
        ttk.Label(head, textvariable=self._hint_var,
                  style="PanelHint.TLabel").pack(side="left", padx=(12, 0))

        self.btn_start = ttk.Button(actions, text="开始转换",
                                    style="Accent.TButton", command=self._start)
        self.btn_start.pack(side="right")

        # 与图片查重页一致: 刷新扫描放在主操作左边
        self.btn_rescan = ttk.Button(actions, text=RESCAN_LABEL,
                                     style="Secondary.TButton",
                                     command=self._rescan)
        self.btn_rescan.pack(side="right", padx=(0, 8))

        source_row = ttk.Frame(bar, style="Panel.TFrame")
        source_row.pack(side="top", fill="x", pady=(10, 0))

        self.btn_add_files = ttk.Button(source_row, text="添加文件",
                                       style="Secondary.TButton",
                                       command=self._add_files)
        self.btn_add_files.pack(side="left")
        self.btn_add_folder = ttk.Button(source_row, text="添加文件夹",
                                        style="Secondary.TButton",
                                        command=self._add_folder)
        self.btn_add_folder.pack(side="left", padx=(8, 0))

        ttk.Label(source_row, text="输出格式",
                  style="Panel.TLabel").pack(side="left", padx=(16, 6))
        self.combo_format = ttk.Combobox(
            source_row, state="readonly", width=FORMAT_COMBO_WIDTH,
            values=list(FORMAT_CHOICES), textvariable=self._format_var)
        self.combo_format.pack(side="left")
        self.combo_format.bind("<<ComboboxSelected>>",
                               lambda _event: self._sync_quality())

        ttk.Label(source_row, text="音质",
                  style="Panel.TLabel").pack(side="left", padx=(14, 6))
        self.combo_quality = ttk.Combobox(
            source_row, state="readonly", width=QUALITY_COMBO_WIDTH,
            values=list(BITRATE_LABELS), textvariable=self._quality_var)
        self.combo_quality.pack(side="left")
        # 说明音质可选项为什么与别的格式不同: 无损 与 码率 两类
        ttk.Label(source_row, textvariable=self._quality_hint_var,
                  style="PanelHint.TLabel").pack(side="left", padx=(10, 0))

        options_row = ttk.Frame(bar, style="Panel.TFrame")
        options_row.pack(side="top", fill="x", pady=(8, 0))

        # 先 pack 右侧控件, 再 pack 左侧的伸缩项
        self.btn_clear = ttk.Button(options_row, text="清空列表",
                                    style="Secondary.TButton",
                                    command=self._clear_items)
        self.btn_clear.pack(side="right")
        self.btn_remove = ttk.Button(options_row, text="移除选中",
                                     style="Secondary.TButton",
                                     command=self._remove_selected)
        self.btn_remove.pack(side="right", padx=(0, 8))

        ttk.Label(options_row, text="输出到",
                  style="Panel.TLabel").pack(side="left", padx=(0, 6))
        for value, label in DEST_LABELS:
            ttk.Radiobutton(options_row, text=label, value=value,
                            variable=self._dest_var,
                            style="Panel.TRadiobutton",
                            command=self._on_dest_change).pack(side="left",
                                                               padx=(0, 6))

        # 指定文件夹时在这里显示路径, 点一下可以重新选择输出文件夹
        self.entry_dest = ttk.Entry(options_row,
                                    textvariable=self._dest_path_var,
                                    state="disabled")
        self.entry_dest.pack(side="left", fill="x", expand=True, padx=(10, 8))
        self.entry_dest.bind("<Button-1>", self._on_dest_click)

    def _build_list_card(self):
        """待转换文件列表, 没有内容时由空状态占位块顶替。"""
        card = ttk.LabelFrame(self, text=CARD_TITLE, padding=(16, 12))
        card.pack(side="top", fill="both", expand=True, pady=(12, 0))

        box = ttk.Frame(card, style="CardFlat.TFrame")
        box.pack(side="top", fill="both", expand=True)

        self.table_area = ttk.Frame(box, style="CardFlat.TFrame")
        self.table = ttk.Treeview(
            self.table_area, show="headings", height=TABLE_HEIGHT,
            columns=[column[0] for column in FILE_COLUMNS],
            style="Card.Treeview")
        scroll = ttk.Scrollbar(self.table_area, orient="vertical",
                               command=self.table.yview)
        self.table.configure(yscrollcommand=scroll.set)
        # 滚动条先占位: 表格的列宽之和超过面板时, 先 pack 的表格会把宽度用光,
        # 之后 pack 的滚动条拿不到空间会被 Tk 直接隐藏
        scroll.pack(side="right", fill="y")
        self.table.pack(side="left", fill="both", expand=True)
        for key, title, width, anchor in FILE_COLUMNS:
            self.table.heading(key, text=title, anchor="center")
            self.table.column(key, width=width, minwidth=60, anchor=anchor,
                              stretch=key in ("name", "status"))
        self.table.bind("<<TreeviewSelect>>", self._update_actions)
        self.table.bind("<Double-1>", self._open_selected)
        self.table.bind("<Delete>", lambda _event: self._remove_selected())
        self.table.bind("<Button-3>", self._show_menu)
        self._apply_row_tags()

        self.empty_state = self._build_empty_state(box)

        self.menu = tk.Menu(self, tearoff=0)
        self.menu.add_command(label="打开文件", command=self._open_selected)
        self.menu.add_command(label="打开所在文件夹",
                              command=self._open_selected_location)
        self.menu.add_separator()
        self.menu.add_command(label="从列表移除", command=self._remove_selected)

    def _build_empty_state(self, parent):
        """建立列表的空状态占位块。

        @param parent: 承载占位块的容器
        @return: 占位块 Frame (默认不显示)
        """
        box = ttk.Frame(parent, style="CardFlat.TFrame")
        inner = ttk.Frame(box, style="CardFlat.TFrame")
        inner.place(relx=0.5, rely=0.42, anchor="center")
        ttk.Label(inner, text="🎵", style="EmptyIcon.TLabel").pack()
        self.empty_title = ttk.Label(inner, text="", style="EmptyTitle.TLabel")
        self.empty_title.pack(pady=(8, 0))
        self.empty_hint = ttk.Label(inner, text="", style="EmptyHint.TLabel",
                                    justify="center")
        self.empty_hint.pack(pady=(6, 0))
        # 说明文案可能较长, 按容器宽度换行, 避免占位块被撑出卡片
        box.bind("<Configure>", lambda event: self._wrap_empty_state(event.width))
        return box

    def _wrap_empty_state(self, width):
        """按容器宽度调整占位块文字的换行宽度。

        @param width: 容器的当前宽度 (像素)
        """
        wrap = max(240, width - 80)
        self.empty_title.configure(wraplength=wrap)
        self.empty_hint.configure(wraplength=wrap)

    def _build_statusbar(self):
        """底部一行: 引擎 计数 进度与终止按钮。"""
        status = ttk.Frame(self, style="Panel.TFrame", padding=(16, 8))
        status.pack(side="bottom", fill="x")

        self.btn_stop = ttk.Button(status, text="终止", style="Danger.TButton",
                                   command=self._stop, state="disabled")
        self.btn_stop.pack(side="right", padx=(8, 0))

        ttk.Label(status, textvariable=self._counts_var,
                  style="PanelMuted.TLabel").pack(side="left", padx=(0, 12))

        self.lbl_engine = ttk.Label(status, textvariable=self._engine_var,
                                    style="PanelMuted.TLabel")
        self.lbl_engine.pack(side="left", padx=(0, 8))
        ttk.Button(status, text=ENGINE_CHOOSE, style="Secondary.TButton",
                   command=self._choose_ffmpeg).pack(side="left", padx=(0, 12))

        self.progress = ttk.Progressbar(status, orient="horizontal",
                                        mode="determinate", maximum=1.0,
                                        value=0.0)
        self.progress.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ttk.Label(status, textvariable=self._progress_var,
                  style="Panel.TLabel").pack(side="left")

    def _apply_row_tags(self):
        """给状态列配上颜色, 便于一眼看出哪些文件出错。"""
        palette = self.theme.palette
        self.table.tag_configure(TAG_RUNNING, foreground=palette["accent"])
        self.table.tag_configure(TAG_DONE, foreground=palette["ok"])
        self.table.tag_configure(TAG_SKIPPED, foreground=palette["muted"])
        self.table.tag_configure(TAG_ERROR, foreground=palette["danger"])

    # ---------------- 文件列表 ----------------
    def _add_files(self):
        """选择若干音频 视频或者加密文件加进列表。"""
        patterns = " ".join(f"*{ext}" for ext in INPUT_EXTENSIONS)
        paths = filedialog.askopenfilenames(
            title="选择要转换的音频 视频或加密文件",
            filetypes=(("音频 视频与加密文件", patterns), ("所有文件", "*.*")),
            parent=self.window)
        if not paths:
            return
        added, _skipped = self._add_paths(paths)
        self._report_added(added)

    def _add_folder(self):
        """选择文件夹并把里面的音频 视频与加密文件一次加进列表。"""
        folder = filedialog.askdirectory(title="选择包含音频或者视频的文件夹",
                                         parent=self.window)
        if not folder:
            return
        folder = os.path.normpath(folder)
        found = tasks.scan_folder(folder)
        if not found:
            messagebox.showinfo("提示", "这个文件夹里没有可转换的文件",
                                parent=self.window)
            return
        self._remember_folder(folder)
        added, skipped = self._add_paths(found, skip_outputs=True)
        self._report_added(added, skipped)

    def _remember_folder(self, folder):
        """记住加过的文件夹, 供「刷新扫描」重新扫描。

        @param folder: 已经加进列表的来源文件夹
        """
        known = {os.path.normcase(path) for path in self._folders}
        if os.path.normcase(folder) not in known:
            self._folders.append(folder)

    def _add_paths(self, paths, skip_outputs=False):
        """把文件加进列表, 已经在列表里的文件会被跳过。

        @param paths: 文件路径序列
        @param skip_outputs: True 时跳过本次已经转出的文件
        @return: (新增数量, 因为是转出文件而跳过的数量)
        """
        known = {os.path.normcase(item.source) for item in self._items}
        added = skipped = 0
        for path in paths:
            source = os.path.normpath(path)
            key = os.path.normcase(source)
            if key in known:
                continue
            if skip_outputs and key in self._outputs:
                skipped += 1
                continue
            known.add(key)
            item = tasks.ConvertItem(source, tasks.file_size(source))
            self._items.append(item)
            self._rows.append(self._insert_row(item))
            added += 1
        if added:
            self._update_empty_state()
            self._update_counts()
            self._update_actions()
        return added, skipped

    def _report_added(self, added, skipped=0):
        """把添加结果写到状态栏。

        @param added: 新增的文件数量
        @param skipped: 因为是本次转出的文件而跳过的数量
        """
        if not added:
            self.set_status("这些文件已经在列表里了")
            return
        text = f"已添加 {added} 个文件, 共 {len(self._items)} 个待转换"
        if skipped:
            text += f", 跳过 {skipped} 个本次转出的文件"
        self.set_status(text)

    def _rescan(self):
        """重新扫描来源文件夹与列表里的文件, 与图片查重页的「刷新扫描」一致。"""
        if self._ongoing:
            return
        removed = 0
        keep = []
        for item in self._items:
            if os.path.isfile(item.source):
                keep.append(item)
            else:
                removed += 1
        if removed:
            self._items = keep
            self._rebuild_rows()

        added = skipped = 0
        for folder in list(self._folders):
            if not os.path.isdir(folder):
                self._folders.remove(folder)
                continue
            found = tasks.scan_folder(folder)
            new_added, new_skipped = self._add_paths(found, skip_outputs=True)
            added += new_added
            skipped += new_skipped

        if not self._items and not self._folders:
            self.set_status("列表里还没有文件, 先添加文件或者文件夹")
            return
        if not added and not removed:
            text = "刷新完成, 没有发现变化"
            if skipped:
                text = f"刷新完成, 跳过 {skipped} 个本次转出的文件"
            self.set_status(text)
            return
        text = f"刷新完成: 新增 {added} 个, 移除 {removed} 个"
        if skipped:
            text += f", 跳过 {skipped} 个本次转出的文件"
        self.set_status(text)

    def _remove_selected(self):
        """把选中的行移出列表, 磁盘上的文件不受影响。"""
        selected = set(self.table.selection())
        if not selected:
            return
        self._items = [item for item, row in zip(self._items, self._rows)
                       if row not in selected]
        self._rebuild_rows()
        self.set_status(f"已移除选中项, 还剩 {len(self._items)} 个待转换")

    def _clear_items(self):
        """清空列表, 磁盘上的文件不受影响。"""
        if not self._items:
            return
        self._items = []
        self._rebuild_rows()
        self.set_status("列表已清空")

    def _rebuild_rows(self):
        """按当前的文件列表重建表格行, 状态与颜色一并恢复。"""
        self.table.delete(*self.table.get_children())
        self._rows = [self._insert_row(item) for item in self._items]
        self._update_empty_state()
        self._update_counts()
        self._update_actions()

    def _insert_row(self, item):
        """往表格末尾插一行。

        @param item: 这一行对应的记录
        @return: Treeview 的行标识
        """
        return self.table.insert("", "end", values=self._row_values(item),
                                 tags=(item.tag,) if item.tag else ())

    @staticmethod
    def _row_values(item):
        """一行四列的内容: 文件名 格式 大小 状态。"""
        return (item.name, item.extension, tasks.format_size(item.size),
                item.status)

    def _set_row_status(self, index, status, tag=""):
        """更新一行的状态列与颜色。

        @param index: 文件在列表中的序号
        @param status: 状态文字
        @param tag: 颜色标记, 空串表示用默认前景色
        """
        item = self._items[index]
        item.status = status
        item.tag = tag
        self.table.item(self._rows[index], values=self._row_values(item),
                        tags=(tag,) if tag else ())

    def _reset_statuses(self):
        """开始新一轮转换前把每一行复位成等待状态。"""
        for index in range(len(self._items)):
            self._set_row_status(index, STATUS_WAITING)

    def _selected_index(self):
        """当前选中行对应的序号。

        @return: 列表序号; 没有选中任何一行时返回 None
        """
        selection = self.table.selection()
        if not selection:
            return None
        try:
            return self._rows.index(selection[0])
        except ValueError:
            return None

    def _update_empty_state(self):
        """列表为空时显示占位块, 否则显示列表。"""
        if self._items:
            self.empty_state.pack_forget()
            self.table_area.pack(side="top", fill="both", expand=True)
            return
        self.empty_title.configure(text=EMPTY_TITLE)
        self.empty_hint.configure(text=EMPTY_HINT)
        self.table_area.pack_forget()
        self.empty_state.pack(side="top", fill="both", expand=True)

    def _update_counts(self):
        """刷新状态栏上的文件数与总大小。"""
        if not self._items:
            self._counts_var.set("")
            return
        size = sum(item.size for item in self._items)
        self._counts_var.set(f"{len(self._items)} 个文件 · "
                             f"{tasks.format_size(size)}")

    def _update_actions(self, _event=None):
        """按运行状态与选中项刷新按钮的可用性。"""
        busy = self._ongoing
        for button in (self.btn_add_files, self.btn_add_folder, self.btn_clear,
                       self.btn_rescan):
            button.configure(state="disabled" if busy else "normal")
        self.btn_start.configure(state="disabled" if busy else "normal")
        self.btn_stop.configure(state="normal" if busy else "disabled")
        self.btn_remove.configure(
            state="disabled" if busy or not self.table.selection() else "normal")

    # ---------------- 右键菜单 ----------------
    def _show_menu(self, event):
        """在右键位置弹出菜单, 先把这一行选中。

        @param event: 鼠标事件
        """
        row = self.table.identify_row(event.y)
        if not row:
            return
        self.table.selection_set(row)
        self.table.focus(row)
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    def _open_selected(self, _event=None):
        """打开选中的文件, 双击一行也会走这里。"""
        index = self._selected_index()
        if index is not None:
            open_path(self._items[index].source, parent=self.window)

    def _open_selected_location(self):
        """打开选中文件所在的文件夹并选中它。"""
        index = self._selected_index()
        if index is not None:
            open_path(self._items[index].source, parent=self.window,
                      reveal=True)

    # ---------------- 转换设置 ----------------
    def _target_format(self):
        """下拉框当前选中的目标格式。

        @return: 扩展名, 不带点
        """
        label = self._format_var.get()
        for ext, _label, _codec, _by_rate in AUDIO_FORMATS:
            if FORMAT_LABELS[ext] == label:
                return ext
        return DEFAULT_FORMAT

    def _quality_choice(self):
        """音质下拉框当前对应的编码器 码率与额外参数。

        @return: (编码器, 码率 kbps, 额外编码参数); 无损与最高音质档的码率见说明
        """
        extension = self._target_format()
        label = self._quality_var.get()
        lossless = LOSSLESS_QUALITY.get(extension)
        if lossless is not None and label == lossless[0]:
            return lossless[1], 0, ()
        top = TOP_QUALITY.get(extension)
        if top is not None and label == top[0]:
            return (FORMAT_CODECS[extension],
                    AUTO_BITRATE if top[2] else 0, top[1])
        if label in BITRATE_LABELS:
            return (FORMAT_CODECS[extension],
                    BITRATES[BITRATE_LABELS.index(label)], ())
        return FORMAT_CODECS[extension], DEFAULT_BITRATE, ()

    def _sync_quality(self):
        """按目标格式刷新音质选项与旁边的说明。

        容器支持无损编码时把无损排在最前, 有损格式再接最高音质档与共用的
        码率档, 只有 WAV FLAC AIFF 这类没有有损编码的容器才只有无损一项
        """
        extension = self._target_format()
        lossless = LOSSLESS_QUALITY.get(extension)
        values = [lossless[0]] if lossless else []
        top = TOP_QUALITY.get(extension)
        if top is not None:
            values.append(top[0])
        if extension not in LOSSLESS_ONLY_FORMATS:
            values += list(BITRATE_LABELS)
        self.combo_quality.configure(state="readonly", values=values)
        if self._quality_var.get() not in values:
            self._quality_var.set(
                values[0] if extension in LOSSLESS_ONLY_FORMATS
                else BITRATE_LABELS[BITRATES.index(DEFAULT_BITRATE)])
        self._quality_hint_var.set(QUALITY_HINTS.get(extension, ""))

    def _on_dest_change(self):
        """切换输出位置: 选指定文件夹时挑目录, 取消就保持原来的选择。"""
        if self._dest_var.get() == DEST_SOURCE:
            self._apply_dest("")
            return
        self._choose_dest_folder()

    def _on_dest_click(self, _event):
        """点输出位置的路径框时重新挑一次输出文件夹。"""
        if str(self.entry_dest.cget("state")) == "readonly":
            self._choose_dest_folder()

    def _choose_dest_folder(self):
        """弹出目录选择框, 选好后写进输出位置一行。"""
        folder = filedialog.askdirectory(title="选择输出文件夹",
                                         parent=self.window)
        if folder:
            self._apply_dest(os.path.normpath(folder))
            return
        # 取消时: 还没选过目录就退回源文件夹, 已经选过则保留原来的目录
        if not self._dest_dir:
            self._apply_dest("")

    def _apply_dest(self, folder):
        """把输出目录写进界面状态。

        @param folder: 输出目录; 空串表示与源文件同目录
        """
        self._dest_dir = folder
        if folder:
            self._dest_var.set(DEST_CUSTOM)
            self._hint_var.set(CUSTOM_DEST_HINT.format(path=folder))
            self._dest_path_var.set(folder)
            self.entry_dest.configure(state="readonly")
            return
        self._dest_var.set(DEST_SOURCE)
        self._hint_var.set(PAGE_HINT)
        self._dest_path_var.set(DEST_SOURCE_HINT)
        self.entry_dest.configure(state="disabled")

    # ---------------- 转换引擎 ----------------
    def _refresh_engine(self):
        """找一次 ffmpeg, 并把结果显示在状态栏上。"""
        self._engine_checked = True
        self._ffmpeg_path = ffmpeg.find_ffmpeg(self._ffmpeg_path)
        if not self._ffmpeg_path:
            self._engine_var.set(f"{ENGINE_LABEL}: {ENGINE_MISSING}")
            self.lbl_engine.configure(style="PanelError.TLabel")
            return
        version = ffmpeg.version(self._ffmpeg_path)
        self._engine_var.set(f"{ENGINE_LABEL}: ffmpeg {version}".rstrip())
        self.lbl_engine.configure(style="PanelMuted.TLabel")

    def _ensure_engine(self):
        """确认有可用的转换引擎。

        @return: 可以开始转换时为 True, 否则提示用户后返回 False
        """
        if not self._ffmpeg_path:
            self._refresh_engine()
        if self._ffmpeg_path:
            return True
        show_error(FFMPEG_MISSING, title="找不到 ffmpeg", parent=self.window)
        return False

    def _choose_ffmpeg(self):
        """让用户手动指定 ffmpeg.exe, 选中后先验证一次再采用。"""
        path = filedialog.askopenfilename(
            title="选择 ffmpeg.exe",
            filetypes=(("ffmpeg", "ffmpeg.exe"), ("可执行文件", "*.exe"),
                       ("所有文件", "*.*")),
            parent=self.window)
        if not path:
            return
        if not ffmpeg.version(path):
            show_error("这个文件不是可用的 ffmpeg", title="选择 ffmpeg 失败",
                       parent=self.window)
            return
        self._ffmpeg_path = os.path.normpath(path)
        self._refresh_engine()
        self.set_status(f"已选择 ffmpeg: {self._ffmpeg_path}")

    # ---------------- 转换流程 ----------------
    def _start(self):
        """开始转换: 快照当前设置后在后台线程里依次处理列表里的文件。"""
        if self._ongoing:
            return
        if not self._items:
            messagebox.showinfo("提示", "先添加要转换的音频文件",
                                parent=self.window)
            return
        if not self._ensure_engine():
            return

        extension = self._target_format()
        codec, bitrate, extra_args = self._quality_choice()
        dest_dir = self._dest_dir if self._dest_var.get() == DEST_CUSTOM else ""
        if dest_dir and not os.path.isdir(dest_dir):
            messagebox.showwarning("提示", DEST_MISSING, parent=self.window)
            return
        jobs = tuple((index, item.source)
                     for index, item in enumerate(self._items))

        self._reset_statuses()
        self._ongoing = True
        self._finished = 0
        self._fraction = 0.0
        self._active_index = None
        self._ok = self._skipped = self._failed = 0
        self._stop_event = threading.Event()
        self._process = None
        self._update_actions()
        self._update_progress()

        self._worker = threading.Thread(
            target=self._run,
            args=(jobs, extension, codec, bitrate, extra_args, dest_dir),
            daemon=True)
        self._worker.start()
        self.set_status(f"开始转换 {len(jobs)} 个文件为 {extension.upper()}")

    def _run(self, jobs, extension, codec, bitrate, extra_args, dest_dir):
        """后台线程: 依次转换, 只通过队列与主线程通信。

        @param jobs: (序号, 源文件路径) 组成的元组
        @param extension: 目标扩展名, 不带点
        @param codec: 目标格式的音频编码器
        @param bitrate: 码率 (kbps); 无损为 0, 最高音质档为 AUTO_BITRATE
        @param extra_args: 最高音质档附带的编码参数
        @param dest_dir: 指定的输出目录, 空串表示与源文件同目录

        加密容器先还原到临时文件, 用完即删; 视频容器只取其中的音频轨
        """
        for index, source in jobs:
            if self._stop_event.is_set():
                self._messages.put(("stopped",))
                return
            if tasks.is_same_target(source, dest_dir, extension):
                self._messages.put(("skipped", index, SKIP_SAME_FORMAT))
                continue

            try:
                target = tasks.output_path(source, dest_dir, extension)
            except OSError as exc:
                logger.exception("无法规划输出路径: %s", source)
                self._messages.put(("failed", index, str(exc)))
                continue

            # 平台加密容器先还原成常见音频, 普通音频与视频容器原样返回
            try:
                prepared = platforms.prepare(source)
            except platforms.PlatformError as exc:
                logger.warning("无法还原加密容器: %s: %s", source, exc)
                self._messages.put(("failed", index, str(exc)))
                continue

            # 已经是目标格式时只复制; 还原结果本身就是目标格式时直接落盘
            if tasks.is_same_format(prepared.extension, extension):
                try:
                    if prepared.temporary:
                        tasks.move_file(prepared.path, target)
                    else:
                        tasks.copy_file(prepared.path, target)
                except OSError as exc:
                    logger.exception("写出同格式文件失败: %s", source)
                    self._messages.put(
                        ("failed", index, f"{COPY_FAILED}: {exc}"))
                else:
                    self._messages.put(
                        ("decoded" if prepared.temporary else "copied", index,
                         os.path.basename(target), target))
                finally:
                    if prepared.temporary:
                        tasks.remove_file(prepared.path)
                continue

            self._messages.put(("start", index))
            try:
                ffmpeg.convert(self._ffmpeg_path, prepared.path, target, codec,
                               bitrate, extra_args,
                               on_progress=self._progress_sender(index),
                               on_start=self._remember_process)
            except ffmpeg.ConvertError as exc:
                if self._stop_event.is_set():
                    self._messages.put(("stopped",))
                    return
                self._messages.put(("failed", index, str(exc)))
                continue
            finally:
                if prepared.temporary:
                    tasks.remove_file(prepared.path)
            self._messages.put(("done", index, os.path.basename(target),
                                target))
        self._messages.put(("finished",))

    def _progress_sender(self, index):
        """给 ffmpeg 的进度回调绑定当前文件的序号。

        @param index: 文件在列表中的序号
        @return: 参数是 0 到 1 的进度回调
        """
        def send(fraction):
            self._messages.put(("progress", index, fraction))
        return send

    def _remember_process(self, process):
        """记住正在运行的 ffmpeg 子进程, 终止时要用它。

        @param process: 刚启动的 Popen 对象
        """
        self._process = process

    def _stop(self):
        """终止转换: 通知后台线程并结束正在跑的 ffmpeg 子进程。"""
        if not self._ongoing:
            return
        self._stop_event.set()
        process = self._process
        if process is not None and process.poll() is None:
            try:
                process.terminate()
            except OSError:
                logger.warning("结束 ffmpeg 子进程失败", exc_info=True)
        self._progress_var.set(PROGRESS_STOPPING)
        self.btn_stop.configure(state="disabled")

    def _poll_messages(self):
        """在主线程里消费后台线程的消息。"""
        try:
            while True:
                self._handle(self._messages.get_nowait())
        except queue.Empty:
            pass
        self._poll_job = self.root.after(POLL_INTERVAL_MS, self._poll_messages)

    def _handle(self, message):
        """处理一条后台消息。

        @param message: (类型, ...) 组成的元组, 类型见 _run 里的投递
        """
        kind = message[0]
        if kind == "start":
            self._fraction = 0.0
            self._active_index = message[1]
            self._set_row_status(message[1], STATUS_RUNNING, TAG_RUNNING)
            self._update_progress()
        elif kind == "progress":
            self._fraction = message[2]
            self._set_row_status(
                message[1], f"{STATUS_RUNNING} {round(message[2] * 100)}%",
                TAG_RUNNING)
            self._update_progress()
        elif kind == "done":
            self._ok += 1
            self._outputs.add(os.path.normcase(message[3]))
            self._advance(message[1], f"{STATUS_DONE} · {message[2]}", TAG_DONE)
        elif kind == "decoded":
            self._ok += 1
            self._outputs.add(os.path.normcase(message[3]))
            self._advance(message[1], f"{STATUS_DECODED} · {message[2]}",
                          TAG_DONE)
        elif kind == "copied":
            self._ok += 1
            self._outputs.add(os.path.normcase(message[3]))
            self._advance(message[1], f"{STATUS_COPIED} · {message[2]}",
                          TAG_DONE)
        elif kind == "skipped":
            self._skipped += 1
            self._advance(message[1], f"{STATUS_SKIPPED} · {message[2]}",
                          TAG_SKIPPED)
        elif kind == "failed":
            self._failed += 1
            self._advance(message[1], self._failure_text(message[2]),
                          TAG_ERROR)
            self._report_failure(message[1], message[2])
        elif kind == "finished":
            self._finish()
        elif kind == "stopped":
            self._finish(stopped=True)

    def _failure_text(self, message):
        """把失败消息压缩成状态列里一行。

        状态列放不下整段英文报错, 这里只留原因本身; 完整消息写到状态栏与
        日志, 便于排查

        @param message: 转换 复制或解密失败的消息
        @return: 状态列要显示的文字
        """
        reason = message
        for prefix in (f"{CONVERT_FAILED}: ", f"{COPY_FAILED}: ",
                       f"{DECRYPT_FAILED}: "):
            if reason.startswith(prefix):
                reason = reason[len(prefix):]
                break
        reason = reason.strip()
        if len(reason) > REASON_MAX_CHARS:
            reason = reason[:REASON_MAX_CHARS] + "..."
        return f"{STATUS_FAILED} · {reason}"

    def _report_failure(self, index, message):
        """把失败原因写到状态栏与日志。

        @param index: 文件在列表中的序号
        @param message: 失败的消息, 已经带有 转换失败 或 复制失败 前缀
        """
        source = self._items[index].source
        logger.warning("文件处理失败: %s: %s", source, message)
        self.set_status(f"{os.path.basename(source)}: {message}")

    def _advance(self, index, status, tag):
        """记下一个文件的结果, 并把整体进度往前推一格。

        @param index: 文件在列表中的序号
        @param status: 状态列要显示的文字
        @param tag: 状态列的颜色标记
        """
        self._finished += 1
        self._fraction = 0.0
        self._active_index = None
        self._set_row_status(index, status, tag)
        self._update_progress()

    def _update_progress(self):
        """按已完成数量与当前文件的进度刷新进度条。"""
        total = len(self._items)
        if not total:
            self.progress["value"] = 0
            return
        value = min((self._finished + self._fraction) / total, 1.0)
        self.progress["value"] = value
        index = min(self._finished + 1, total)
        self._progress_var.set(PROGRESS_RUNNING.format(index=index, total=total))

    def _finish(self, stopped=False):
        """收尾: 复位进度与按钮, 并把结果写到状态栏。

        @param stopped: True 表示这次是用户终止的
        """
        self._ongoing = False
        self._process = None
        self._worker = None
        # 被终止的文件卡在 转换中 会误导, 这里改成已终止
        if stopped and self._active_index is not None:
            self._set_row_status(self._active_index, STATUS_CANCELLED,
                                 TAG_SKIPPED)
            self._active_index = None
        self.progress["value"] = 0
        self._progress_var.set(
            SUMMARY_SHORT.format(ok=self._ok, skip=self._skipped,
                                 fail=self._failed))
        self._update_actions()
        template = SUMMARY_STOPPED if stopped else SUMMARY_DONE
        self.set_status(template.format(ok=self._ok, skip=self._skipped,
                                        fail=self._failed))

    # ---------------- 生命周期 ----------------
    def on_show(self):
        """首次进入本页时才去找 ffmpeg, 不拖慢程序启动。"""
        if not self._engine_checked:
            self._refresh_engine()

    def on_theme_changed(self):
        """主题切换后重新应用状态列的颜色。"""
        self._apply_row_tags()

    def on_close(self):
        """退出前结束子进程与后台线程, 避免留下没写完的输出文件。"""
        if self._poll_job is not None:
            self.root.after_cancel(self._poll_job)
            self._poll_job = None
        if self._stop_event is not None:
            self._stop_event.set()
        process = self._process
        if process is not None and process.poll() is None:
            try:
                process.terminate()
            except OSError:
                logger.warning("结束 ffmpeg 子进程失败", exc_info=True)
        if self._worker is not None and self._worker.is_alive():
            self._worker.join(timeout=CLOSE_JOIN_TIMEOUT)
        return True
