"""文件格式转换页面: 把选中的音频文件批量转成另一种格式"""

import logging
import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from ... import kit
from ...errors import open_path, show_error
from ...shell.page import ToolPage
from ...theme import SIZE_LABEL, tint
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
    ENGINE_WAIT_TIMEOUT,
    FFMPEG_MISSING,
    FILE_COLUMNS,
    FORMAT_CHOICES,
    FORMAT_CODECS,
    FORMAT_LABELS,
    INPUT_EXTENSIONS,
    LOSSLESS_ONLY_FORMATS,
    LOSSLESS_QUALITY,
    PAGE_HINT,
    PAGE_TITLE,
    PROGRESS_IDLE,
    PROGRESS_RUNNING,
    PROGRESS_STOPPING,
    SUBTITLE,
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
#: 失败原因在状态列里的最大长度, 超出部分截断
REASON_MAX_CHARS = 48

#: 状态列的颜色标记
TAG_RUNNING = "running"
TAG_DONE = "done"
TAG_SKIPPED = "skipped"
TAG_ERROR = "error"

#: 颜色标记与配色令牌的对应关系
TAG_TOKENS = {
    TAG_RUNNING: "accent",
    TAG_DONE: "ok",
    TAG_SKIPPED: "muted",
    TAG_ERROR: "danger",
}


def _status_token(tag):
    """把状态列的颜色标记换成配色令牌

    @param tag: 颜色标记, 空串表示等待转换
    @return: 配色令牌名
    """
    return TAG_TOKENS.get(tag, "muted")


class ConvertPage(ToolPage):
    """在常见音频格式之间批量转换的工具页面"""

    key = "convert"
    title = PAGE_TITLE
    icon = "🎵"
    subtitle = "把音频 视频与加密音乐文件批量转换成常见格式"

    def __init__(self, master, shell):
        super().__init__(master, shell)

        self._items = []
        self._folders = []
        self._outputs = set()
        self._dest_dir = ""
        self._ffmpeg_path = ""
        self._engine_checked = False
        self._engine_thread = None
        self._engine_request = 0
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

        self._format = DEFAULT_FORMAT
        self._quality = BITRATE_LABELS[BITRATES.index(DEFAULT_BITRATE)]
        self._dest_source_var = tk.BooleanVar(value=True)
        self._dest_custom_var = tk.BooleanVar(value=False)

        self._build_toolbar()
        self._build_statusbar()
        self._build_list_panel()

        self._sync_quality()
        self._update_counts()
        self._update_empty_state()
        self._update_actions()
        self._poll_job = self.root.after(POLL_INTERVAL_MS, self._poll_messages)

    # ---------------- 界面构建 ----------------
    def _build_toolbar(self):
        """顶栏按钮与两行设置"""
        self.btn_rescan, self.btn_start = self.add_actions((
            (RESCAN_LABEL, None, self._rescan),
            ("开始转换", "Primary.TButton", self._start),
        ))

        source_row = self.add_row(gap=8)
        self.btn_add_files = ttk.Button(source_row, text="添加文件",
                                        style="TButton", command=self._add_files)
        self.btn_add_files.pack(side="left")
        self.btn_add_folder = ttk.Button(source_row, text="添加文件夹",
                                         style="TButton",
                                         command=self._add_folder)
        self.btn_add_folder.pack(side="left", padx=(8, 0))

        kit.text(source_row, self.theme, value="输出格式", size=SIZE_LABEL,
                 token="muted", surface="canvas").pack(side="left",
                                                      padx=(16, 8))
        self.combo_format = kit.Dropdown(source_row, self.theme,
                                         values=list(FORMAT_CHOICES),
                                         command=self._on_format_change,
                                         surface="canvas",
                                         width=104)
        self.combo_format.set(FORMAT_LABELS[DEFAULT_FORMAT])
        self.combo_format.pack(side="left")

        kit.text(source_row, self.theme, value="音质", size=SIZE_LABEL,
                 token="muted", surface="canvas").pack(side="left",
                                                      padx=(14, 8))
        self.combo_quality = kit.Dropdown(source_row, self.theme,
                                          command=self._on_quality_change,
                                          surface="canvas",
                                          width=104)
        self.combo_quality.pack(side="left")
        # 说明音质可选项为什么与别的格式不同: 无损 与 码率 两类
        self.lbl_quality_hint = kit.text(source_row, self.theme, value="",
                                         size=SIZE_LABEL, token="muted",
                                         surface="canvas")
        self.lbl_quality_hint.pack(side="left", padx=(10, 0))

        options_row = self.add_row()
        kit.text(options_row, self.theme, value="输出到", size=SIZE_LABEL,
                 token="muted", surface="canvas").pack(side="left")
        self.check_source = kit.Check(options_row, self.theme,
                                      value=DEST_LABELS[0][1],
                                      variable=self._dest_source_var,
                                      command=lambda _v: self._select_dest(
                                          DEST_SOURCE))
        self.check_source.pack(side="left", padx=(12, 0))
        self.check_custom = kit.Check(options_row, self.theme,
                                      value=DEST_LABELS[1][1],
                                      variable=self._dest_custom_var,
                                      command=lambda _v: self._select_dest(
                                          DEST_CUSTOM))
        self.check_custom.pack(side="left", padx=(12, 0))

        self.btn_clear = ttk.Button(options_row, text="清空列表",
                                    style="TButton",
                                    command=self._clear_items)
        self.btn_clear.pack(side="right")
        self.btn_remove = ttk.Button(options_row, text="移除选中",
                                     style="TButton",
                                     command=self._remove_selected)
        self.btn_remove.pack(side="right", padx=(0, 8))

        # 指定文件夹时在这里显示路径, 点一下可以重新选择输出文件夹
        self.field_dest = kit.Field(options_row, self.theme, mono_font=True,
                                    value=DEST_SOURCE_HINT, token="muted",
                                    width=320)
        self.field_dest.pack(side="left", fill="x", expand=True,
                             padx=(10, 10))
        self.field_dest.configure(cursor="hand2")
        self.field_dest.label.configure(cursor="hand2")
        for widget in (self.field_dest, self.field_dest.label):
            widget.bind("<Button-1>", self._on_dest_click)

    def _build_list_panel(self):
        """待转换文件列表, 没有内容时由空状态占位块顶替"""
        panel = self.add_panel(head=False, body_pad=(0, 0))
        self.list_panel = panel
        self.table = kit.Table(panel.body, self.theme, FILE_COLUMNS,
                               on_select=self._on_row_select, multi=True,
                               empty_text=EMPTY_TITLE, surface="panel")
        self.table.pack(side="top", fill="both", expand=True)
        self.table.body.bind("<Double-1>", self._open_selected)
        self.table.body.bind("<Delete>", lambda _event: self._remove_selected())
        self.table.body.bind("<Button-3>", self._show_menu)

        self.empty_state = self._build_empty_state(panel.body)

        self.menu = tk.Menu(self, tearoff=0)
        self.menu.add_command(label="打开文件", command=self._open_selected)
        self.menu.add_command(label="打开所在文件夹",
                              command=self._open_selected_location)
        self.menu.add_separator()
        self.menu.add_command(label="从列表移除", command=self._remove_selected)

    def _build_empty_state(self, parent):
        """建立列表的空状态占位块

        @param parent: 承载占位块的容器
        @return: 占位块 Frame (默认不显示)
        """
        box = tk.Frame(parent, bd=0, highlightthickness=0)
        tint(box, bg="panel")
        box.configure(bg=self.theme.rgb("panel"))
        inner = tk.Frame(box, bd=0, highlightthickness=0)
        tint(inner, bg="panel")
        inner.configure(bg=self.theme.rgb("panel"))
        inner.place(relx=0.5, rely=0.42, anchor="center")
        kit.text(inner, self.theme, value="\uE8D6", size=34, token="accent",
                 icon_font=True, surface="panel").pack()
        self.empty_title = kit.text(inner, self.theme, value="", size=15,
                                    bold=True, surface="panel")
        self.empty_title.pack(pady=(8, 0))
        self.empty_hint = kit.text(inner, self.theme, value="",
                                   size=SIZE_LABEL, token="muted",
                                   surface="panel", anchor="center")
        self.empty_hint.pack(pady=(6, 0))
        # 说明文案可能较长, 按容器宽度换行, 避免占位块被撑出卡片
        box.bind("<Configure>", lambda event: self._wrap_empty_state(event.width))
        return box

    def _wrap_empty_state(self, width):
        """按容器宽度调整占位块文字的换行宽度

        @param width: 容器的当前宽度 (像素)
        """
        wrap = max(240, width - 80)
        self.empty_title.configure(wraplength=wrap)
        self.empty_hint.configure(wraplength=wrap)

    def _build_statusbar(self):
        """状态栏: 计数 引擎 进度细条与终止按钮, 与设计稿一致"""
        self.status.set_kind("idle")
        self.status.set_text(PAGE_HINT)
        self.counts_metric = kit.text(self.status.tail, self.theme,
                                      size=SIZE_LABEL, mono_font=True,
                                      surface="side")
        self.status.add_tail(self.counts_metric)
        self.engine_metric = kit.text(self.status.tail, self.theme,
                                      size=SIZE_LABEL, mono_font=True,
                                      surface="side")
        self.status.add_tail(self.engine_metric)
        self.btn_engine = ttk.Button(self.status.tail, text=ENGINE_CHOOSE,
                                     style="Ghost.TButton",
                                     command=self._choose_ffmpeg)
        self.status.add_tail(self.btn_engine)
        self.track = kit.Track(self.status.tail, self.theme)
        self.status.add_tail(self.track)
        self.progress_metric = kit.text(self.status.tail, self.theme,
                                        size=SIZE_LABEL, mono_font=True,
                                        surface="side")
        self.status.add_tail(self.progress_metric)
        self.btn_stop = ttk.Button(self.status.actions, text="终止",
                                   style="Danger.TButton",
                                   command=self._stop, state="disabled")
        self.status.add_action(self.btn_stop)

    # ---------------- 文件列表 ----------------
    def _add_files(self):
        """选择若干音频 视频或者加密文件加进列表"""
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
        """选择文件夹并把里面的音频 视频与加密文件一次加进列表"""
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
        """记住加过的文件夹, 供'刷新扫描'重新扫描

        @param folder: 已经加进列表的来源文件夹
        """
        known = {os.path.normcase(path) for path in self._folders}
        if os.path.normcase(folder) not in known:
            self._folders.append(folder)

    def _add_paths(self, paths, skip_outputs=False):
        """把文件加进列表, 已经在列表里的文件会被跳过

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
            added += 1
        if added:
            self._refresh_rows()
            self._update_empty_state()
            self._update_counts()
            self._update_actions()
        return added, skipped

    def _report_added(self, added, skipped=0):
        """把添加结果写到状态栏

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
        """重新扫描来源文件夹与列表里的文件, 与图片查重页的'刷新扫描'一致"""
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
        """把选中的行移出列表, 磁盘上的文件不受影响"""
        selected = set(self.table.selection())
        if not selected:
            return
        self._items = [item for index, item in enumerate(self._items)
                       if index not in selected]
        self.table.clear_selection()
        self._rebuild_rows()
        self.set_status(f"已移除选中项, 还剩 {len(self._items)} 个待转换")

    def _clear_items(self):
        """清空列表, 磁盘上的文件不受影响"""
        if not self._items:
            return
        self._items = []
        self._rebuild_rows()
        self.set_status("列表已清空")

    def _rebuild_rows(self):
        """按当前的文件列表重建表格行, 状态与颜色一并恢复"""
        self.table.set_rows(self._table_rows())
        self._update_empty_state()
        self._update_counts()
        self._update_actions()

    def _table_rows(self):
        """把待转换列表转成表格数据

        @return: 表格数据行
        """
        return [{"data": index, "name": item.name, "format": item.extension,
                 "size": tasks.format_size(item.size),
                 "status": (item.status, _status_token(item.tag))}
                for index, item in enumerate(self._items)]

    def _refresh_rows(self):
        """只重画表格, 保留选中行"""
        self.table.set_rows(self._table_rows(), keep_selection=True)

    def _set_row_status(self, index, status, tag=""):
        """更新一行的状态列与颜色

        @param index: 文件在列表中的序号
        @param status: 状态文字
        @param tag: 颜色标记, 空串表示用默认前景色
        """
        item = self._items[index]
        item.status = status
        item.tag = tag
        self._refresh_rows()

    def _reset_statuses(self):
        """开始新一轮转换前把每一行复位成等待状态"""
        for index in range(len(self._items)):
            self._set_row_status(index, STATUS_WAITING)

    def _selected_index(self):
        """当前选中行对应的序号

        @return: 列表序号; 没有选中任何一行时返回 None
        """
        index = self.table.current_index()
        if index is None or index >= len(self._items):
            return None
        return index

    def _update_empty_state(self):
        """列表为空时显示占位块, 否则显示列表"""
        if self._items:
            self.empty_state.pack_forget()
            self.table.pack(side="top", fill="both", expand=True)
            return
        self.empty_title.configure(text=EMPTY_TITLE)
        self.empty_hint.configure(text=EMPTY_HINT)
        self.table.pack_forget()
        self.empty_state.pack(side="top", fill="both", expand=True)

    def _update_counts(self):
        """刷新状态栏上的文件数与总大小"""
        if not self._items:
            self.counts_metric.configure(text="")
            return
        size = sum(item.size for item in self._items)
        self.counts_metric.configure(
            text=f"{len(self._items)} 个文件 | {tasks.format_size(size)}")

    def _update_actions(self, _event=None):
        """按运行状态与选中项刷新按钮的可用性"""
        busy = self._ongoing
        for button in (self.btn_add_files, self.btn_add_folder, self.btn_clear,
                       self.btn_rescan):
            button.configure(state="disabled" if busy else "normal")
        self.btn_start.configure(state="disabled" if busy else "normal")
        self.btn_stop.configure(state="normal" if busy else "disabled")
        self.btn_remove.configure(
            state="disabled" if busy or not self.table.selection()
            else "normal")

    def _on_row_select(self, _data, _index):
        """表格选中项变化时刷新按钮的可用性

        @param _data: 行携带的序号
        @param _index: 行号
        """
        self._update_actions()

    # ---------------- 右键菜单 ----------------
    def _show_menu(self, event):
        """在右键位置弹出菜单, 先把这一行选中

        @param event: 鼠标事件
        """
        index = self.table.index_at(event.x, event.y)
        if index < 0 or index >= len(self._items):
            return
        self.table.select(index)
        self._update_actions()
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    def _open_selected(self, _event=None):
        """打开选中的文件, 双击一行也会走这里"""
        index = self._selected_index()
        if index is not None:
            open_path(self._items[index].source, parent=self.window)

    def _open_selected_location(self):
        """打开选中文件所在的文件夹并选中它"""
        index = self._selected_index()
        if index is not None:
            open_path(self._items[index].source, parent=self.window,
                      reveal=True)

    # ---------------- 转换设置 ----------------
    def _target_format(self):
        """下拉框当前选中的目标格式

        @return: 扩展名, 不带点
        """
        return self._format

    def _quality_choice(self):
        """音质下拉框当前对应的编码器 码率与额外参数

        @return: (编码器, 码率 kbps, 额外编码参数); 无损与最高音质档的码率见说明
        """
        extension = self._target_format()
        label = self._quality
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
        """按目标格式刷新音质选项与旁边的说明

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
        self.combo_quality.set_values(values)
        if self._quality not in values:
            self._quality = (values[0] if extension in LOSSLESS_ONLY_FORMATS
                             else BITRATE_LABELS[BITRATES.index(DEFAULT_BITRATE)])
        self.combo_quality.set(self._quality)
        self.lbl_quality_hint.configure(text=QUALITY_HINTS.get(extension, ""))

    def _on_format_change(self, label):
        """目标格式变化后刷新音质选项

        @param label: 下拉框里选中的格式名
        """
        for ext, _label, _codec, _by_rate in AUDIO_FORMATS:
            if FORMAT_LABELS[ext] == label:
                self._format = ext
                break
        self._sync_quality()

    def _on_quality_change(self, label):
        """音质变化后记下选择

        @param label: 下拉框里选中的音质名
        """
        self._quality = label

    def _select_dest(self, mode):
        """切换输出位置: 选指定文件夹时挑目录, 取消就保持原来的选择

        @param mode: DEST_SOURCE 或 DEST_CUSTOM
        """
        if mode == DEST_SOURCE:
            self._apply_dest("")
            return
        self._choose_dest_folder()

    def _on_dest_click(self, _event):
        """点输出位置的路径框时重新挑一次输出文件夹"""
        if self._dest_dir:
            self._choose_dest_folder()

    def _choose_dest_folder(self):
        """弹出目录选择框, 选好后写进输出位置一行"""
        folder = filedialog.askdirectory(title="选择输出文件夹",
                                         parent=self.window)
        if folder:
            self._apply_dest(os.path.normpath(folder))
            return
        # 取消时: 还没选过目录就退回源文件夹, 已经选过则保留原来的目录
        if not self._dest_dir:
            self._apply_dest("")

    def _apply_dest(self, folder):
        """把输出目录写进界面状态

        @param folder: 输出目录; 空串表示与源文件同目录
        """
        self._dest_dir = folder
        if folder:
            self._dest_source_var.set(False)
            self._dest_custom_var.set(True)
            self.field_dest.set(folder, token="text")
            return
        self._dest_source_var.set(True)
        self._dest_custom_var.set(False)
        self.field_dest.set(DEST_SOURCE_HINT, token="muted")

    # ---------------- 转换引擎 ----------------
    def _detect_engine(self):
        """在后台线程里找 ffmpeg, 结果经消息队列回到主线程

        随包的 ffmpeg 第一次执行要等系统与杀毒软件读一遍, 在主线程里做会把界面卡住
        数秒; 因此定位与读版本号都放在后台线程, 期间状态栏先显示 正在检测
        """
        self._engine_request += 1
        self.engine_metric.configure(text=ENGINE_DETECTING)
        tint(self.engine_metric, bg="side", fg="muted")
        thread = threading.Thread(
            target=self._detect_engine_worker,
            args=(self._engine_request, self._cached_engine_path()),
            name="convert-engine", daemon=True)
        self._engine_thread = thread
        thread.start()

    def _detect_engine_worker(self, request, cached):
        """后台线程: 定位 ffmpeg 并读一次版本号, 只通过队列与主线程通信

        @param request: 本次检测的序号, 主线程用它丢弃过期结果
        @param cached: 设置里缓存的路径, 交给 find_ffmpeg 优先采用
        """
        path, version = self._locate_engine(cached)
        self._messages.put(("engine", request, path, version))

    @staticmethod
    def _locate_engine(cached):
        """定位 ffmpeg 并读它的版本号, 不碰界面

        @param cached: 上次用过的路径, 可以是空串
        @return: (ffmpeg 路径, 版本号); 找不到时都是空串
        """
        path = ffmpeg.find_ffmpeg(cached)
        if not path:
            return "", ""
        return path, ffmpeg.version(path)

    def _cached_engine_path(self):
        """设置里缓存的 ffmpeg 路径, 文件已经不存在时不再使用

        @return: 可用的缓存路径, 空串表示没有可用缓存
        """
        path = self.shell.settings.ffmpeg_path
        return path if path and os.path.isfile(path) else ""

    def _apply_engine(self, path, version):
        """把检测结果显示在状态栏, 并把路径记进设置

        @param path: ffmpeg 路径, 空串表示没找到
        @param version: 版本号, 读不到时为空串
        """
        self._ffmpeg_path = path
        if not path:
            self.engine_metric.configure(text=ENGINE_MISSING,
                                         fg=self.theme.rgb("danger"))
            tint(self.engine_metric, bg="side", fg="danger")
            return
        self.engine_metric.configure(text=f"ffmpeg {version}".rstrip(),
                                     fg=self.theme.rgb("text"))
        tint(self.engine_metric, bg="side", fg="text")
        self._remember_engine(path)

    def _remember_engine(self, path):
        """记住这次用的 ffmpeg, 下次启动直接采用

        @param path: ffmpeg 可执行文件路径
        """
        settings = self.shell.settings
        if settings.ffmpeg_path == path:
            return
        settings.ffmpeg_path = path
        settings.save()

    def _ensure_engine(self):
        """确认有可用的转换引擎

        首次进入时的后台检测可能还没结束, 这里等它一会儿; 仍然没有结果就同步找一次,
        因为这时用户已经在等转换开始了

        @return: 可以开始转换时为 True, 否则提示用户后返回 False
        """
        if not self._ffmpeg_path:
            thread = self._engine_thread
            if thread is not None and thread.is_alive():
                thread.join(timeout=ENGINE_WAIT_TIMEOUT)
            self._drain_messages()
        if not self._ffmpeg_path:
            self._apply_engine(*self._locate_engine(self._cached_engine_path()))
        if self._ffmpeg_path:
            return True
        show_error(FFMPEG_MISSING, title="找不到 ffmpeg", parent=self.window)
        return False

    def _choose_ffmpeg(self):
        """让用户手动指定 ffmpeg.exe, 选中后先验证一次再采用"""
        path = filedialog.askopenfilename(
            title="选择 ffmpeg.exe",
            filetypes=(("ffmpeg", "ffmpeg.exe"), ("可执行文件", "*.exe"),
                       ("所有文件", "*.*")),
            parent=self.window)
        if not path:
            return
        version = ffmpeg.version(path)
        if not version:
            show_error("这个文件不是可用的 ffmpeg", title="选择 ffmpeg 失败",
                       parent=self.window)
            return
        # 手动选择优先于还在跑的自动检测, 序号加一让它的结果失效
        self._engine_request += 1
        self._apply_engine(os.path.normpath(path), version)
        self.set_status(f"已选择 ffmpeg: {self._ffmpeg_path}")

    # ---------------- 转换流程 ----------------
    def _start(self):
        """开始转换: 快照当前设置后在后台线程里依次处理列表里的文件"""
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
        dest_dir = self._dest_dir
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
        self.status.set_kind("run")

        self._worker = threading.Thread(
            target=self._run,
            args=(jobs, extension, codec, bitrate, extra_args, dest_dir),
            daemon=True)
        self._worker.start()
        self.set_status(f"开始转换 {len(jobs)} 个文件为 {extension.upper()}")

    def _run(self, jobs, extension, codec, bitrate, extra_args, dest_dir):
        """后台线程: 依次转换, 只通过队列与主线程通信

        @param jobs: (序号, 源文件路径) 组成的元组
        @param extension: 目标扩展名, 不带点
        @param codec: 目标格式的音频编码器
        @param bitrate: 码率 (kbps); 无损为 0, 最高音质档为 AUTO_BITRATE
        @param extra_args: 最高音质档附带的编码参数
        @param dest_dir: 指定的输出目录, 空串表示与源文件同目录

        加密容器先还原到临时文件, 用完即删; 视频容器只取其中的音频轨; 加密容器里
        的曲目信息与封面写进输出文件
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

            # 已经是目标格式时只复制; 还原结果本身就是目标格式时直接落盘,
            # 但容器里带出来的曲目信息与封面要用一次流复制写进输出
            if tasks.is_same_format(prepared.extension, extension):
                tags = prepared.tags()
                try:
                    if prepared.temporary and (tags or prepared.cover):
                        # 还原结果里没有容器自己的标签, 用一次流复制把曲目信息
                        # 与封面写进输出, 音频流原样搬运, 不做二次编码
                        ffmpeg.convert(
                            self._ffmpeg_path, prepared.path, target,
                            ffmpeg.COPY_CODEC, 0, tags=tags,
                            cover=prepared.cover,
                            on_start=self._remember_process)
                    elif prepared.temporary:
                        tasks.move_file(prepared.path, target)
                    else:
                        tasks.copy_file(prepared.path, target)
                except ffmpeg.ConvertError as exc:
                    if self._stop_event.is_set():
                        self._messages.put(("stopped",))
                        return
                    logger.warning("写出同格式文件失败: %s: %s", source, exc)
                    self._messages.put(("failed", index, str(exc)))
                except OSError as exc:
                    logger.exception("写出同格式文件失败: %s", source)
                    self._messages.put(
                        ("failed", index, f"{COPY_FAILED}: {exc}"))
                else:
                    self._messages.put(
                        ("decoded" if prepared.temporary else "copied", index,
                         os.path.basename(target), target))
                finally:
                    self._cleanup(prepared)
                continue

            self._messages.put(("start", index))
            try:
                ffmpeg.convert(self._ffmpeg_path, prepared.path, target, codec,
                               bitrate, extra_args, tags=prepared.tags(),
                               cover=prepared.cover,
                               on_progress=self._progress_sender(index),
                               on_start=self._remember_process)
            except ffmpeg.ConvertError as exc:
                if self._stop_event.is_set():
                    self._messages.put(("stopped",))
                    return
                self._messages.put(("failed", index, str(exc)))
                continue
            finally:
                self._cleanup(prepared)
            self._messages.put(("done", index, os.path.basename(target),
                                target))
        self._messages.put(("finished",))

    @staticmethod
    def _cleanup(prepared):
        """删掉这次准备产生的临时文件: 还原出来的音频与封面图

        @param prepared: platforms.prepare() 的返回值
        """
        if prepared.temporary:
            tasks.remove_file(prepared.path)
        if prepared.cover:
            tasks.remove_file(prepared.cover)

    def _progress_sender(self, index):
        """给 ffmpeg 的进度回调绑定当前文件的序号

        @param index: 文件在列表中的序号
        @return: 参数是 0 到 1 的进度回调
        """
        def send(fraction):
            self._messages.put(("progress", index, fraction))
        return send

    def _remember_process(self, process):
        """记住正在运行的 ffmpeg 子进程, 终止时要用它

        @param process: 刚启动的 Popen 对象
        """
        self._process = process

    def _stop(self):
        """终止转换: 通知后台线程并结束正在跑的 ffmpeg 子进程"""
        if not self._ongoing:
            return
        self._stop_event.set()
        process = self._process
        if process is not None and process.poll() is None:
            try:
                process.terminate()
            except OSError:
                logger.warning("结束 ffmpeg 子进程失败", exc_info=True)
        self.progress_metric.configure(text=PROGRESS_STOPPING)
        self.btn_stop.configure(state="disabled")

    def _poll_messages(self):
        """在主线程里消费后台线程的消息"""
        self._drain_messages()
        self._poll_job = self.root.after(POLL_INTERVAL_MS, self._poll_messages)

    def _drain_messages(self):
        """把队列里积压的消息全部处理掉

        除了定时轮询, 等待引擎检测结果时也会调用一次, 否则结果压在队列里要等下一次
        轮询才会生效
        """
        try:
            while True:
                self._handle(self._messages.get_nowait())
        except queue.Empty:
            pass

    def _handle(self, message):
        """处理一条后台消息

        @param message: (类型, ...) 组成的元组, 类型见 _run 与 _detect_engine_worker
                        里的投递
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
            self._advance(message[1], f"{STATUS_DONE} | {message[2]}", TAG_DONE)
        elif kind == "decoded":
            self._ok += 1
            self._outputs.add(os.path.normcase(message[3]))
            self._advance(message[1], f"{STATUS_DECODED} | {message[2]}",
                          TAG_DONE)
        elif kind == "copied":
            self._ok += 1
            self._outputs.add(os.path.normcase(message[3]))
            self._advance(message[1], f"{STATUS_COPIED} | {message[2]}",
                          TAG_DONE)
        elif kind == "skipped":
            self._skipped += 1
            self._advance(message[1], f"{STATUS_SKIPPED} | {message[2]}",
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
        elif kind == "engine":
            # 过期的检测结果直接丢掉: 手动选择或者重新检测已经给出更新的答案
            if message[1] == self._engine_request:
                self._apply_engine(message[2], message[3])

    def _failure_text(self, message):
        """把失败消息压缩成状态列里一行

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
        return f"{STATUS_FAILED} | {reason}"

    def _report_failure(self, index, message):
        """把失败原因写到状态栏与日志

        @param index: 文件在列表中的序号
        @param message: 失败的消息, 已经带有 转换失败 或 复制失败 前缀
        """
        source = self._items[index].source
        logger.warning("文件处理失败: %s: %s", source, message)
        self.set_status(f"{os.path.basename(source)}: {message}")

    def _advance(self, index, status, tag):
        """记下一个文件的结果, 并把整体进度往前推一格

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
        """按已完成数量与当前文件的进度刷新进度条"""
        total = len(self._items)
        if not total:
            self.track.set_fraction(0.0)
            self.progress_metric.configure(text="")
            return
        value = min((self._finished + self._fraction) / total, 1.0)
        self.track.set_fraction(value)
        index = min(self._finished + 1, total)
        self.progress_metric.configure(text=f"{index}/{total}")

    def _finish(self, stopped=False):
        """收尾: 复位进度与按钮, 并把结果写到状态栏

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
        self.track.set_fraction(0.0)
        self.progress_metric.configure(
            text=SUMMARY_SHORT.format(ok=self._ok, skip=self._skipped,
                                      fail=self._failed))
        self._update_actions()
        template = SUMMARY_STOPPED if stopped else SUMMARY_DONE
        self.status.set_kind("idle" if stopped else "ok")
        self.set_status(template.format(ok=self._ok, skip=self._skipped,
                                        fail=self._failed))

    # ---------------- 生命周期 ----------------
    def on_show(self):
        """首次进入本页时才去找 ffmpeg, 而且放在后台线程里, 不卡住界面"""
        if self._engine_checked:
            return
        self._engine_checked = True
        self._detect_engine()

    def on_theme_changed(self):
        """主题切换后重新应用状态列的颜色"""
        self._refresh_rows()
        self._update_empty_state()

    def on_close(self):
        """退出前结束子进程与后台线程, 避免留下没写完的输出文件"""
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
        if self._engine_thread is not None and self._engine_thread.is_alive():
            self._engine_thread.join(timeout=CLOSE_JOIN_TIMEOUT)
        return True
