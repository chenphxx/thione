"""接收区与发送区的卡片部件

四个卡片 (串口接收 网络接收 串口发送 网络发送) 由两个类拼出来: ReceivePanel 负责
把收到的字节格式化后追加到只读视图, SendPanel 负责把输入内容按模式解析后交给页面
发送. 两个类都不直接持有会话, 收发动作一律回调给页面

@brief 串口助手的两类数据面板
"""

import logging
import tkinter as tk
from tkinter import ttk

from ... import kit
from ...theme import SIZE_BODY, SIZE_LABEL, mono, sans, tint
from .codec import ParseError, StreamDecoder, format_bytes, parse_payload
from .constants import (
    BYTES_PER_LINE_HINT,
    CONTROL_HINT_WRAP,
    DEFAULT_ENCODING,
    DEFAULT_INTERVAL_MS,
    DEFAULT_SEND_MODE,
    DEFAULT_SUFFIX,
    DISPLAY_MODES,
    ENCODINGS,
    MAX_VIEW_CHARS,
    MIN_INTERVAL_MS,
    RECEIVE_CONTROLS_WIDTH,
    SEND_CONTROLS_WIDTH,
    MODE_COMBO_WIDTH,
    ENCODING_COMBO_WIDTH,
    INTERVAL_ENTRY_WIDTH,
    SUFFIX_COMBO_WIDTH,
    SUFFIX_TEXT_WIDTH,
    TARGET_COMBO_WIDTH,
    SEND_MODES,
    SUFFIX_BYTES,
    SUFFIX_CHOICES,
    SUFFIX_CUSTOM,
)

logger = logging.getLogger(__name__)

#: 视图里的提示文字样式
TAG_SYSTEM = "system"
TAG_ERROR = "error"
TAG_SOURCE = "source"

#: 没有数据时的占位文案
EMPTY_HINT = "还没有收到数据"


def _labels(choices, default_key):
    """下拉框的显示值列表

    @param choices: (键, 显示名) 组成的元组
    @param default_key: 默认键
    @return: (显示值列表, 默认显示值)
    """
    labels = [label for _key, label in choices]
    for key, label in choices:
        if key == default_key:
            return labels, label
    return labels, labels[0]


def _key_of(choices, label):
    """把下拉框显示值换回键

    @param choices: (键, 显示名) 组成的元组
    @param label: 当前显示值
    @return: 键, 找不到时返回第一项的键
    """
    for key, text in choices:
        if text == label:
            return key
    return choices[0][0]


class DataView(tk.Frame):
    """等宽文本视图: 接收区只读, 发送区可编辑

    外观与设计稿的 .view 一致: fill 底色 + 1 像素描边, 12 像素等宽字体
    """

    def __init__(self, master, theme, editable=False, height=7):
        super().__init__(master, bd=0, highlightthickness=1)
        self.theme = theme
        self.editable = editable
        palette = theme.palette
        tint(self, bg="fill", hl="hair", hlc="hair")
        self.configure(bg=palette["fill"], highlightbackground=palette["hair"],
                       highlightcolor=palette["hair"])
        self.text = tk.Text(
            self, height=height, wrap="char", relief="flat", borderwidth=0,
            highlightthickness=0, background=palette["fill"],
            foreground=palette["text"], insertbackground=palette["text"],
            selectbackground=palette["accent"],
            selectforeground=palette["on_accent"],
            font=mono(SIZE_LABEL), padx=10, pady=10, undo=editable,
            maxundo=200,
        )
        tint(self.text, bg="fill", fg="text", insert="text", sel_bg="accent",
             sel_fg="on_accent")
        self.text.pack(side="left", fill="both", expand=True)
        self.text.tag_configure(TAG_SYSTEM, foreground=palette["muted"])
        self.text.tag_configure(TAG_ERROR, foreground=palette["danger"])
        self.text.tag_configure(TAG_SOURCE, foreground=palette["accent"])
        if not editable:
            self.text.configure(state="disabled")
            # 只读视图仍然要能全选与复制, 因此单独绑定这两个快捷键
            self.text.bind("<Control-a>", self._select_all)
            self.text.bind("<Control-A>", self._select_all)

    def append(self, chunk, tag=None):
        """在末尾追加文本并滚到最新一行

        @param chunk: 文本
        @param tag: 可选的标签
        """
        if not chunk:
            return
        follow = self._at_bottom()
        self._unlock()
        self.text.insert("end", chunk, tag or ())
        self._trim()
        self._relock()
        if follow:
            self.text.see("end")

    def set_content(self, value):
        """覆盖视图内容

        @param value: 新的文本
        """
        self._unlock()
        self.text.delete("1.0", "end")
        self.text.insert("1.0", value)
        self._relock()

    def content(self):
        """取视图里的全部文本

        @return: 文本, 末尾的换行已经去掉
        """
        return self.text.get("1.0", "end-1c")

    def clear(self):
        """清空视图"""
        self._unlock()
        self.text.delete("1.0", "end")
        self._relock()

    def on_theme_changed(self):
        """主题切换后刷新自绘颜色"""
        palette = self.theme.palette
        self.text.configure(
            background=palette["fill"], foreground=palette["text"],
            insertbackground=palette["text"],
            selectbackground=palette["accent"],
            selectforeground=palette["on_accent"], padx=10, pady=10)
        self.text.tag_configure(TAG_SYSTEM, foreground=palette["muted"])
        self.text.tag_configure(TAG_ERROR, foreground=palette["danger"])
        self.text.tag_configure(TAG_SOURCE, foreground=palette["accent"])

    def _unlock(self):
        """只读视图临时切回可写

        Tk 的 Text 处于 disabled 时会忽略 insert 与 delete, 因此清空与覆盖内容
        之前必须先切回 normal

        """
        if not self.editable:
            self.text.configure(state="normal")

    def _relock(self):
        """只读视图恢复只读"""
        if not self.editable:
            self.text.configure(state="disabled")

    def _trim(self):
        """内容超过上限时丢掉最早的部分, 避免长时间运行吃满内存"""
        size = self.text.count("1.0", "end-1c", "chars")
        if not size:
            return
        total = size[0]
        if total > MAX_VIEW_CHARS:
            self.text.delete("1.0", "1.0 + %d chars" % (total - MAX_VIEW_CHARS))

    def _at_bottom(self):
        """视图当前是否停在末尾

        @return: True 表示在末尾
        """
        try:
            return self.text.yview()[1] >= 0.999
        except tk.TclError:
            return True

    def _select_all(self, _event=None):
        self.text.tag_add("sel", "1.0", "end-1c")
        return "break"


class ReceivePanel(tk.Frame):
    """接收卡片: 展示模式 编码 自动换行 保存 开始暂停 清屏 与接收计数"""

    def __init__(self, master, theme, page, title, default_mode, show_source=False):
        super().__init__(master, bd=0, highlightthickness=0)
        self.theme = theme
        self.page = page
        self.show_source = show_source
        self._capturing = True
        self._paused_bytes = 0
        self._total = 0
        self._placeholder = False
        self._line_start = False
        self._last_source = ""
        self._decoder = StreamDecoder(default_mode, DEFAULT_ENCODING)

        display_labels, display_default = _labels(DISPLAY_MODES, default_mode)
        self.mode_var = tk.StringVar(value=display_default)
        self.encoding_var = tk.StringVar(value=DEFAULT_ENCODING)
        self.wrap_var = tk.BooleanVar(value=True)
        self.count_var = tk.StringVar(value=self._count_text())

        self.panel = kit.Panel(self, theme, title=title, right=display_default,
                               body_pad=(14, 14))
        self.panel.pack(fill="both", expand=True)
        self.panel.body.columnconfigure(0, weight=1)
        self.panel.body.rowconfigure(0, weight=1)
        # 面板头部右侧依次是接收字节数与展示模式
        self.lbl_count = kit.text(self.panel.head, theme, size=SIZE_LABEL,
                                  mono_font=True, token="muted",
                                  surface="panel", anchor="e")
        self.panel.add_head(self.lbl_count, side="right", padx=(0, 10))

        # 配置列先占住右侧, 剩下的宽度全部留给数据视图
        self.controls = tk.Frame(self.panel.body, bd=0, highlightthickness=0,
                                 width=RECEIVE_CONTROLS_WIDTH)
        tint(self.controls, bg="panel")
        self.controls.configure(bg=theme.rgb("panel"))
        self.controls.grid(row=0, column=1, sticky="nsew", padx=(14, 0))
        # 配置列的宽度由面板的列最小值固定, 高度仍然跟着内容走
        self.panel.body.columnconfigure(1, minsize=RECEIVE_CONTROLS_WIDTH)
        self._build_controls(display_labels)
        self.view = DataView(self.panel.body, theme, editable=False)
        # 间距算在视图这一列, 配置列的宽度因此等于控件的实际宽度
        self.view.grid(row=0, column=0, sticky="nsew")
        self._show_placeholder()
        self._refresh_count()

    # ---------------- 界面 ----------------
    def _build_controls(self, display_labels):
        """右侧配置列: 展示模式 编码 自动换行 保存 开始暂停 清屏 与接收计数

        参数排在上面, 动作与计数贴着列底, 中间的空档由列自己吸收, 因此接收
        与发送两边的动作按钮排在同一个高度

        @param display_labels: 展示模式的显示值列表
        """
        bar = self.controls
        bar.columnconfigure(0, weight=1)
        self._setting(bar, 0, "展示", display_labels, self.mode_var,
                      self._on_mode_change)
        self._setting(bar, 1, "编码", list(ENCODINGS), self.encoding_var,
                      self._on_encoding_change)
        self.check_wrap = kit.Check(bar, self.theme, value="自动换行",
                                    variable=self.wrap_var, surface="panel")
        self.check_wrap.grid(row=2, column=0, sticky="w", pady=(12, 0))
        kit.text(bar, self.theme, value=BYTES_PER_LINE_HINT,
                 size=SIZE_LABEL, token="muted",
                 surface="panel").grid(row=3, column=0, sticky="w",
                                       pady=(6, 0))

        actions = tk.Frame(bar, bd=0, highlightthickness=0)
        tint(actions, bg="panel")
        actions.configure(bg=self.theme.rgb("panel"))
        actions.grid(row=5, column=0, sticky="ew")
        for column in range(3):
            actions.columnconfigure(column, weight=1, uniform="recv_action")
        ttk.Button(actions, text="保存为 txt", style="TButton",
                   command=self._save).grid(row=0, column=0, sticky="ew")
        self.btn_capture = ttk.Button(actions, text="暂停接收",
                                      style="TButton",
                                      command=self._toggle_capture)
        self.btn_capture.grid(row=0, column=1, sticky="ew", padx=(8, 0))
        ttk.Button(actions, text="清屏", style="TButton",
                   command=self.clear).grid(row=0, column=2, sticky="ew",
                                            padx=(8, 0))

        kit.text(bar, self.theme, variable=self.count_var, size=SIZE_LABEL,
                 token="muted", surface="panel").grid(row=6, column=0,
                                                      sticky="w",
                                                      pady=(6, 0))
        # 中间的空档吸收多余高度, 动作按钮因此贴着列底
        bar.rowconfigure(4, weight=1)

    def _setting(self, parent, row, caption, values, variable, command):
        """建立一列下拉设置: 标签在上, 控件框样式的下拉在下

        @param parent: 父容器
        @param row: 行号
        @param caption: 标签文字
        @param values: 可选项
        @param variable: 绑定的 StringVar
        @param command: 选中后的回调
        @return: 建立好的下拉控件
        """
        holder = tk.Frame(parent, bd=0, highlightthickness=0)
        tint(holder, bg="panel")
        holder.configure(bg=self.theme.rgb("panel"))
        holder.grid(row=row, column=0, sticky="ew",
                    pady=(0 if row == 0 else 10, 0))
        kit.text(holder, self.theme, value=caption, size=SIZE_LABEL,
                 token="muted", surface="panel").pack(anchor="w",
                                                      pady=(0, 5))
        combo = kit.Dropdown(holder, self.theme, values=values,
                             surface="panel",
                             command=lambda label: self._on_setting(
                                 variable, label, command))
        combo.set(variable.get())
        combo.pack(fill="x")
        return combo

    @staticmethod
    def _on_setting(variable, label, command):
        """下拉框选中后先同步变量, 再调用页面回调

        @param variable: 绑定的 StringVar
        @param label: 新选中的显示值
        @param command: 页面回调, 接收 tkinter 事件或者无参
        """
        variable.set(label)
        if command is not None:
            command(None)

    def set_controls_width(self, width):
        """固定配置列的宽度, 让接收与发送两边的数据视图左右对齐

        @param width: 配置列宽度 (像素)
        """
        self.panel.body.columnconfigure(1, minsize=width)

    def _show_placeholder(self):
        """空视图里给一句引导"""
        self.view.append(EMPTY_HINT, TAG_SYSTEM)
        self._placeholder = True

    # ---------------- 数据 ----------------
    def feed(self, data, source=""):
        """收到一段数据

        @param data: 字节串
        @param source: 数据来源, 例如 "192.168.1.5:8080"
        """
        if not data:
            return
        if not self._capturing:
            self._paused_bytes += len(data)
            self._refresh_count()
            return
        self._total += len(data)
        if self._placeholder:
            # 占位文案很快会被清掉, 第一条数据直接从行首开始
            break_line = False
            self._decoder.reset_line()
        else:
            # 自动换行: 每收到一条消息就另起一行, 行内排版也从行首重新开始
            break_line = self.wrap_var.get() and not self._line_start
            if break_line:
                self._decoder.reset_line()
        text = self._decoder.feed(data)
        if not text:
            # 文本模式下多字节字符还没有收全, 等下一个数据包补齐
            self._refresh_count()
            return
        if self._placeholder:
            self.view.clear()
            self._placeholder = False
        prefix = self._source_prefix(source)
        parts = ["\n"] if break_line else []
        if prefix:
            parts.append(prefix)
            self._decoder.reset_line()
        parts.append(text)
        self.view.append("".join(parts))
        self._line_start = text.endswith("\n")
        self._refresh_count()

    def note(self, text, error=False):
        """在视图里写一条提示

        @param text: 提示内容
        @param error: True 用错误色
        """
        tag = TAG_ERROR if error else TAG_SYSTEM
        if self._placeholder:
            self.view.clear()
            self._placeholder = False
            self._line_start = True
        if not self._line_start:
            self.view.append("\n", tag)
        self.view.append(text, tag)
        self._line_start = False
        self._decoder.reset_line()

    def set_capturing(self, capturing):
        """切换接收与暂停

        @param capturing: True 表示正在接收
        """
        self._capturing = capturing
        self.btn_capture.configure(text="暂停接收" if capturing else "开始接收")
        if capturing and self._paused_bytes:
            self.note("已继续接收, 暂停期间收到 %d 字节" % self._paused_bytes)
            self._paused_bytes = 0
        self._refresh_count()

    def is_capturing(self):
        """当前是否正在接收"""
        return self._capturing

    def clear(self):
        """清空视图与计数"""
        self.view.clear()
        self._decoder.reset()
        self._total = 0
        self._paused_bytes = 0
        self._last_source = ""
        self._placeholder = False
        self._line_start = True
        self._refresh_count()

    def save(self, path):
        """把当前视图内容写到文本文件

        @param path: 目标文件
        @throws OSError: 写不进去时
        """
        with open(path, "w", encoding="utf-8", newline="\r\n") as handle:
            handle.write(self.view.content())
            handle.write("\r\n")

    def view_text(self):
        """当前视图里的文本"""
        return self.view.content()

    def total_bytes(self):
        """本次接收到的字节数

        @return: 字节数
        """
        return self._total

    def on_theme_changed(self):
        """主题切换后刷新视图颜色"""
        self.view.on_theme_changed()

    # ---------------- 内部 ----------------
    def _source_prefix(self, source):
        """来源变化时给出一个前缀

        @param source: 数据来源
        @return: 需要写进视图的前缀, 不需要时为空串
        """
        if not self.show_source or not source or source == self._last_source:
            return ""
        self._last_source = source
        return "[%s] " % source

    def _count_text(self):
        """计数行的文本

        @return: 展示文本
        """
        text = "本次接收 %d 字节" % self._total
        if self._paused_bytes:
            text += " | 暂停期间 %d 字节" % self._paused_bytes
        return text

    def _refresh_count(self):
        self.count_var.set(self._count_text())
        self.lbl_count.configure(text="RX %d B" % self._total)

    def _on_mode_change(self, _event=None):
        mode = _key_of(DISPLAY_MODES, self.mode_var.get())
        self.panel.set_right(self.mode_var.get())
        leftover = self._decoder.set_mode(mode)
        if leftover:
            self.view.append(leftover)
            self._line_start = leftover.endswith("\n")

    def _on_encoding_change(self, _event=None):
        leftover = self._decoder.set_encoding(self.encoding_var.get())
        if leftover:
            self.view.append(leftover)
            self._line_start = leftover.endswith("\n")

    def _toggle_capture(self):
        self.page.toggle_receive(self)

    def _save(self):
        self.page.save_receive(self)


class SendPanel(tk.Frame):
    """发送卡片: 发送模式 编码 载入文本 后缀 循环发送 开始暂停 清屏 与发送计数"""

    def __init__(self, master, theme, page, title, kind="serial", with_targets=False,
                 targets_parent=None):
        super().__init__(master, bd=0, highlightthickness=0)
        self.theme = theme
        self.page = page
        self.kind = kind
        self.with_targets = with_targets
        # 发送对象默认排在输入框上方, 页面也可以指定别的容器
        self.targets_parent = targets_parent
        self._loop_job = None
        self._sent_total = 0
        self._targets = []
        self._multi_targets = None

        send_labels, send_default = _labels(SEND_MODES, DEFAULT_SEND_MODE)
        suffix_labels, suffix_default = _labels(SUFFIX_CHOICES, DEFAULT_SUFFIX)
        self.mode_var = tk.StringVar(value=send_default)
        self.encoding_var = tk.StringVar(value=DEFAULT_ENCODING)
        self.suffix_var = tk.StringVar(value=suffix_default)
        self.suffix_text_var = tk.StringVar()
        self.loop_var = tk.BooleanVar(value=False)
        self.interval_var = tk.StringVar(value=str(DEFAULT_INTERVAL_MS))
        self.target_var = tk.StringVar(value="全部设备")
        self.count_var = tk.StringVar(value="本次发送 0 字节")
        self.hint_var = tk.StringVar()

        self.panel = kit.Panel(self, theme, title=title, right="TX 0 B",
                               body_pad=(14, 14))
        self.panel.pack(fill="both", expand=True)
        # 行 0 吸收多余高度, 数据视图才会跟着发送区一起长高
        self.panel.body.columnconfigure(0, weight=1)
        self.panel.body.rowconfigure(0, weight=1)

        # 配置列先占住右侧, 剩下的宽度全部留给输入视图
        self.controls = tk.Frame(self.panel.body, bd=0, highlightthickness=0,
                                 width=SEND_CONTROLS_WIDTH)
        tint(self.controls, bg="panel")
        self.controls.configure(bg=theme.rgb("panel"))
        self.controls.grid(row=0, column=1, sticky="nsew", padx=(14, 0))
        # 配置列的宽度由面板的列最小值固定, 高度仍然跟着内容走
        self.panel.body.columnconfigure(1, minsize=SEND_CONTROLS_WIDTH)
        # 左列: 发送对象排在输入框上方, 其余情况只有输入框
        self.view_box = tk.Frame(self.panel.body, bd=0, highlightthickness=0)
        tint(self.view_box, bg="panel")
        self.view_box.configure(bg=theme.rgb("panel"))
        # 间距算在视图这一列, 配置列的宽度因此等于控件的实际宽度
        self.view_box.grid(row=0, column=0, sticky="nsew")
        self._build_controls(send_labels, suffix_labels)
        self.view = DataView(self.view_box, theme, editable=True, height=4)
        self.view.pack(side="top", fill="both", expand=True)

    # ---------------- 界面 ----------------
    def _build_controls(self, send_labels, suffix_labels):
        """右侧配置列: 发送 后缀 编码 循环发送 载入 动作 提示与计数

        参数排在上面, 动作与提示贴着列底, 中间的空档由列自己吸收, 因此接收与
        发送两边的动作按钮排在同一个高度, 发送区被拖高时也不会散开

        @param send_labels: 发送模式的显示值列表
        @param suffix_labels: 后缀的显示值列表
        """
        bar = self.controls
        bar.columnconfigure(0, weight=1)
        row1 = tk.Frame(bar, bd=0, highlightthickness=0)
        tint(row1, bg="panel")
        row1.configure(bg=self.theme.rgb("panel"))
        row1.grid(row=0, column=0, sticky="ew")
        for column in range(3):
            row1.columnconfigure(column, weight=1, uniform="send_pair")
        self.combo_mode = self._pair_setting(
            row1, 0, "发送", send_labels, self.mode_var)
        self.combo_suffix = self._pair_setting(
            row1, 1, "后缀", suffix_labels, self.suffix_var,
            self._on_suffix_change)
        self.combo_encoding = self._pair_setting(
            row1, 2, "编码", list(ENCODINGS), self.encoding_var)

        # 只有选了 自定义 后缀才需要输入框, 平时把这一行收起来
        self.row_suffix_text = tk.Frame(bar, bd=0, highlightthickness=0)
        tint(self.row_suffix_text, bg="panel")
        self.row_suffix_text.configure(bg=self.theme.rgb("panel"))
        self.entry_suffix = kit.EntryField(
            self.row_suffix_text, self.theme, variable=self.suffix_text_var,
            width=120, mono_font=False)
        self.entry_suffix.pack(side="left", fill="x", expand=True)
        self.row_suffix_text.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self.row_suffix_text.grid_remove()

        row2 = tk.Frame(bar, bd=0, highlightthickness=0)
        tint(row2, bg="panel")
        row2.configure(bg=self.theme.rgb("panel"))
        row2.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        self.check_loop = kit.Check(row2, self.theme, value="循环发送",
                                    variable=self.loop_var, surface="panel")
        self.check_loop.pack(side="left")
        self.entry_interval = kit.EntryField(row2, self.theme,
                                             variable=self.interval_var,
                                             width=64, height=24,
                                             size=SIZE_LABEL)
        self.entry_interval.pack(side="left", padx=(8, 6))
        kit.text(row2, self.theme, value="毫秒", size=SIZE_LABEL,
                 token="muted", surface="panel").pack(side="left")
        self._on_suffix_change()

        actions = tk.Frame(bar, bd=0, highlightthickness=0)
        tint(actions, bg="panel")
        actions.configure(bg=self.theme.rgb("panel"))
        actions.grid(row=4, column=0, sticky="ew")
        for column in range(3):
            actions.columnconfigure(column, weight=1, uniform="send_action")
        ttk.Button(actions, text="载入文本", style="TButton",
                   command=self._load_text).grid(row=0, column=0, sticky="ew")
        self.btn_send = ttk.Button(actions, text="开始发送",
                                   style="Primary.TButton",
                                   command=self._toggle_send)
        self.btn_send.grid(row=0, column=1, sticky="ew", padx=(8, 0))
        ttk.Button(actions, text="清屏", style="TButton",
                   command=self.view_clear).grid(row=0, column=2, sticky="ew",
                                                 padx=(8, 0))

        # 提示与计数贴着列底, 提示按剩余宽度折行
        row4 = tk.Frame(bar, bd=0, highlightthickness=0)
        tint(row4, bg="panel")
        row4.configure(bg=self.theme.rgb("panel"))
        row4.grid(row=5, column=0, sticky="ew", pady=(6, 0))
        self.lbl_hint = kit.text(row4, self.theme, variable=self.hint_var,
                                 size=SIZE_LABEL, token="muted",
                                 surface="panel", wrap=CONTROL_HINT_WRAP)
        self.lbl_hint.pack(side="left", fill="x", expand=True)
        kit.text(row4, self.theme, variable=self.count_var, size=SIZE_LABEL,
                 token="muted", surface="panel").pack(side="right",
                                                      padx=(8, 0))
        # 参数与动作之间的空档吸收多余高度, 动作按钮因此和接收区一样贴着列底
        bar.rowconfigure(3, weight=1)

        if self.with_targets:
            place = {"side": "left"} if self.targets_parent is not None else {
                "side": "top", "fill": "x", "pady": (0, 6)}
            row = ttk.Frame(self.targets_parent or self.view_box,
                            style="CardFlat.TFrame")
            ttk.Label(row, text="对象", style="CardMuted.TLabel").pack(side="left")
            self.combo_target = ttk.Combobox(row, state="readonly",
                                             width=TARGET_COMBO_WIDTH,
                                             values=["全部设备"],
                                             textvariable=self.target_var)
            self.combo_target.pack(side="left", padx=(4, 0))
            self.btn_targets = ttk.Button(row, text="多选",
                                          style="Secondary.TButton",
                                          command=self._choose_targets)
            self.btn_targets.pack(side="left", padx=(6, 0))
            self.row_targets = row
            self._target_place = place
            row.pack(**place)

    def _pair_setting(self, parent, column, caption, values, variable,
                      extra=None):
        """在上半部分排一列 标签 + 下拉框

        @param parent: 父容器
        @param column: 列号
        @param caption: 标签文字
        @param values: 可选项
        @param variable: 绑定的 StringVar
        @param extra: 选中后的额外回调
        @return: 建立好的下拉控件
        """
        holder = tk.Frame(parent, bd=0, highlightthickness=0)
        tint(holder, bg="panel")
        holder.configure(bg=self.theme.rgb("panel"))
        holder.grid(row=0, column=column, sticky="ew",
                    padx=(0, 10) if column == 0 else (0, 0))
        kit.text(holder, self.theme, value=caption, size=SIZE_LABEL,
                 token="muted", surface="panel").pack(anchor="w",
                                                      pady=(0, 5))

        def choose(label):
            variable.set(label)
            if extra is not None:
                extra(None)

        combo = kit.Dropdown(holder, self.theme, values=values,
                             surface="panel", command=choose)
        combo.set(variable.get())
        combo.pack(fill="x")
        return combo

    def set_controls_width(self, width):
        """固定配置列的宽度

        @param width: 配置列宽度 (像素)
        """
        self.panel.body.columnconfigure(1, minsize=width)


    # ---------------- 发送 ----------------
    def payload(self):
        """按当前设置解析要发送的字节

        @return: 字节串, 后缀已经拼好
        @throws ParseError: 输入内容与模式不匹配时
        """
        mode = self.mode()
        content = self.view.content()
        body = parse_payload(content, mode, self.encoding())
        suffix = self.suffix_bytes()
        if not body and not suffix:
            raise ParseError("没有可发送的内容")
        return body + suffix

    def mode(self):
        """当前发送模式"""
        return _key_of(SEND_MODES, self.mode_var.get())

    def encoding(self):
        """当前编码名"""
        return self.encoding_var.get()

    def suffix_bytes(self):
        """当前后缀对应的字节

        @return: 字节串
        @throws ParseError: 自定义后缀与模式不匹配时
        """
        key = _key_of(SUFFIX_CHOICES, self.suffix_var.get())
        if key != SUFFIX_CUSTOM:
            return SUFFIX_BYTES.get(key, b"")
        text = self.suffix_text_var.get()
        if not text:
            return b""
        return parse_payload(text, self.mode(), self.encoding())

    def interval_ms(self):
        """循环发送的间隔, 不合法或者过小时取默认值

        @return: 间隔毫秒数
        """
        try:
            value = int(self.interval_var.get().strip())
        except ValueError:
            return DEFAULT_INTERVAL_MS
        if value < MIN_INTERVAL_MS:
            return MIN_INTERVAL_MS
        return value

    def note_sent(self, size):
        """记录一次成功的发送

        @param size: 字节数
        """
        self._sent_total += size
        self.count_var.set("本次发送 %d 字节" % self._sent_total)
        self.panel.set_right("TX %d B" % self._sent_total)

    def reset_count(self):
        """清空发送计数"""
        self._sent_total = 0
        self.count_var.set("本次发送 0 字节")
        self.panel.set_right("TX 0 B")

    def sent_total(self):
        """本次发送的字节数

        @return: 字节数
        """
        return self._sent_total

    def view_clear(self):
        """清空输入区"""
        self.view.clear()

    def set_content(self, value):
        """覆盖输入区的内容, 用于载入文本文件

        @param value: 新的文本
        """
        self.view.set_content(value)

    def set_hint(self, text, error=False):
        """更新卡片下方的说明

        @param text: 说明文本
        @param error: True 用错误色
        """
        self.hint_var.set(text)
        style = "CardError.TLabel" if error else "CardMuted.TLabel"
        if self.lbl_hint.cget("style") != style:
            self.lbl_hint.configure(style=style)

    def set_targets(self, addresses):
        """刷新 TCP Server 的发送对象下拉框

        @param addresses: 当前在线的客户端地址列表
        """
        if not self.with_targets:
            return
        self._targets = list(addresses)
        if self._multi_targets is not None:
            self._multi_targets = [addr for addr in self._multi_targets
                                   if addr in self._targets]
            if not self._multi_targets:
                self._multi_targets = None
        values = ["全部设备"] + self._targets
        if self._multi_targets:
            values = ["已选 %d 个设备" % len(self._multi_targets)] + values
        current = self.target_var.get()
        if current not in values:
            self.target_var.set("全部设备")
        self.combo_target.configure(values=values)

    def set_multi_targets(self, addresses):
        """记录多选对话框的结果

        @param addresses: 选中的地址列表; 为空表示改回全部设备
        """
        if not self.with_targets:
            return
        if not addresses:
            self._multi_targets = None
            self.target_var.set("全部设备")
            return
        self._multi_targets = list(addresses)
        value = "已选 %d 个设备" % len(self._multi_targets)
        self.combo_target.configure(values=[value] + ["全部设备"] + self._targets)
        self.target_var.set(value)

    def target_addresses(self):
        """当前在线的客户端地址"""
        return list(self._targets)

    def selected_targets(self):
        """当前选中的发送对象

        @return: 地址列表; None 表示全部设备
        """
        if not self.with_targets:
            return None
        value = self.target_var.get()
        if value == "全部设备":
            return None
        if value.startswith("已选"):
            return list(self._multi_targets or []) or None
        return [value]

    def show_target_controls(self, visible):
        """按协议显示或者隐藏发送对象那一行

        @param visible: True 显示, False 隐藏
        """
        if not self.with_targets:
            return
        if visible:
            if self.row_targets.master is self.view.master:
                # 与输入框同一列时要排在它前面, 否则重新显示会掉到输入框下面
                self.row_targets.pack(before=self.view, **self._target_place)
            else:
                self.row_targets.pack(**self._target_place)
        else:
            self.row_targets.pack_forget()

    def is_looping(self):
        """是否正在循环发送"""
        return self._loop_job is not None

    def start_loop(self):
        """启动循环发送"""
        if self._loop_job is not None:
            return
        self.btn_send.configure(text="暂停发送")
        self._schedule_loop()

    def stop_loop(self):
        """停止循环发送"""
        if self._loop_job is not None:
            self.root_after_cancel(self._loop_job)
            self._loop_job = None
        self.btn_send.configure(text="开始发送")

    def on_theme_changed(self):
        """主题切换后刷新视图颜色"""
        self.view.on_theme_changed()

    def _schedule_loop(self):
        """安排下一次循环发送"""
        delay = self.interval_ms()
        self._loop_job = self.winfo_toplevel().after(delay, self._tick)

    def root_after_cancel(self, job):
        """取消定时器, 窗口已经销毁时忽略错误"""
        try:
            self.winfo_toplevel().after_cancel(job)
        except tk.TclError:
            pass

    def _tick(self):
        """循环发送的一拍"""
        self._loop_job = None
        if not self.loop_var.get():
            self.btn_send.configure(text="开始发送")
            return
        keep = self.page.send_from(self)
        if keep and self.loop_var.get():
            self._schedule_loop()
        else:
            self.loop_var.set(False)
            self.btn_send.configure(text="开始发送")

    def _toggle_send(self):
        self.page.toggle_send(self)

    def _load_text(self):
        self.page.load_send_text(self)

    def _on_suffix_change(self, _event=None):
        """选了自定义后缀才允许输入"""
        custom = _key_of(SUFFIX_CHOICES, self.suffix_var.get()) == SUFFIX_CUSTOM
        if custom:
            self.row_suffix_text.grid()
        else:
            self.row_suffix_text.grid_remove()

    def _choose_targets(self):
        self.page.choose_targets(self)

    def close(self):
        """退出前停掉定时器"""
        self.stop_loop()
