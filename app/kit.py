"""外壳与各工具页面共用的界面零件

@brief 基础界面部件
"""

import inspect
import tkinter as tk
from tkinter import font as tkfont

from .dpi import scale
from .theme import (
    CONTROL_HEIGHT,
    ICON_BOX,
    ICON_CHECK,
    ICON_CHEVRON,
    PANEL_HEAD_HEIGHT,
    SIZE_BODY,
    SIZE_LABEL,
    SIZE_SECTION,
    SIZE_TITLE,
    TABLE_HEAD_HEIGHT,
    TABLE_ROW_HEIGHT,
    color,
    icon,
    mono,
    sans,
    tint,
)

#: 状态栏圆点的直径
DOT_SIZE = scale(7)

#: 弹出列表最多显示多少项, 超出时滚动
LIST_MAX_VISIBLE = 10

#: 弹出列表每项的高度
LIST_ITEM_HEIGHT = scale(28)


def invoke(command, value):
    """调用部件回调, 兼容只接受零个参数的回调

    同一个回调可能被不同部件用不同的约定调用 (有的传取值, 有的不传), 这里按签名
    判断, 少了参数就补上, 免得出现 "takes 1 positional argument but 2 were given"

    @param command: 可调用对象, 允许为 None
    @param value: 需要传给回调的取值
    """
    if command is None:
        return
    try:
        parameters = inspect.signature(command).parameters
    except (TypeError, ValueError):
        command(value)
        return
    required = [item for item in parameters.values()
                if item.kind in (item.POSITIONAL_ONLY,
                                 item.POSITIONAL_OR_KEYWORD)
                and item.default is item.empty]
    if required:
        command(value)
    else:
        command()

#: 表格单元格的左右内边距
CELL_PAD = scale(12)


def hairline(parent, theme, orient="horizontal"):
    """建立一条 1 像素分隔线

    @param parent: 父容器
    @param theme: 主题管理器
    @param orient: horizontal 为横线, vertical 为竖线
    @return: 分隔线控件
    """
    line = tk.Frame(parent, bd=0, highlightthickness=0)
    if orient == "horizontal":
        line.configure(height=1)
    else:
        line.configure(width=1)
    tint(line, bg="hair")
    line.configure(bg=theme.rgb("hair"))
    return line


def text(parent, theme, value="", size=SIZE_BODY, token="text", bold=False,
         mono_font=False, icon_font=False, surface="canvas", anchor="w",
         variable=None, wrap=0):
    """建立一段说明文字

    @param parent: 父容器
    @param theme: 主题管理器
    @param value: 初始文字
    @param size: 字号 (像素)
    @param token: 文字颜色的令牌名
    @param bold: 是否粗体
    @param mono_font: 是否使用等宽字体
    @param icon_font: 是否使用图标字体
    @param surface: 所在表面的令牌名, 决定底色
    @param anchor: 文字对齐方式
    @param variable: 绑定的 StringVar, 传入后忽略 value
    @param wrap: 大于 0 时按该像素宽度换行
    @return: 文字控件
    """
    if icon_font:
        font = icon(size, bold)
    elif mono_font:
        font = mono(size, bold)
    else:
        font = sans(size, bold)
    options = {"anchor": anchor, "bd": 0, "highlightthickness": 0,
               "font": font, "justify": "left" if anchor == "w" else "right",
               "padx": 0, "pady": 0}
    if variable is not None:
        options["textvariable"] = variable
    else:
        options["text"] = value
    if wrap > 0:
        options["wraplength"] = wrap
    label = tk.Label(parent, **options)
    tint(label, bg=surface, fg=token)
    label.configure(bg=theme.rgb(surface), fg=theme.rgb(token))
    return label


class Panel(tk.Frame):
    """面板: 1 像素描边 + 面板底色, 可选 34 像素高的头部

    头部左侧放小节标题, 右侧放补充说明; 需要时用 add_head() 往头部里塞控件
    (分段控件 操作按钮等)
    """

    def __init__(self, master, theme, title=None, right=None, head=True,
                 body_pad=(14, 14)):
        super().__init__(master, bd=0, highlightthickness=1)
        self.theme = theme
        tint(self, bg="panel", hl="hair", hlc="hair")
        self.configure(bg=theme.rgb("panel"),
                       highlightbackground=theme.rgb("hair"),
                       highlightcolor=theme.rgb("hair"))
        self.head = None
        self.title_label = None
        self.right_label = None
        if head:
            self.head = tk.Frame(self, height=PANEL_HEAD_HEIGHT, bd=0,
                                 highlightthickness=0)
            tint(self.head, bg="panel")
            self.head.configure(bg=theme.rgb("panel"))
            self.head.pack(side="top", fill="x")
            self.head.pack_propagate(False)
            # 先放分隔线: 头部左右两侧的文字都是纵向填满, 后放会把线截断
            hairline(self.head, theme).pack(side="bottom", fill="x")
            self.title_label = text(self.head, theme, value=title or "",
                                    size=SIZE_SECTION, token="muted", bold=True,
                                    surface="panel", anchor="w")
            self.title_label.pack(side="left", fill="y",
                                  padx=(scale(14), 0))
            if right is not None:
                self.right_label = text(self.head, theme, value=right,
                                        size=SIZE_LABEL, token="muted",
                                        surface="panel", anchor="e")
                self.right_label.pack(side="right", fill="y",
                                      padx=(0, scale(14)))
        self.body = tk.Frame(self, bd=0, highlightthickness=0)
        tint(self.body, bg="panel")
        self.body.configure(bg=theme.rgb("panel"))
        self.body.pack(side="top", fill="both", expand=True,
                       padx=scale(body_pad[0]), pady=scale(body_pad[1]))

    def add_head(self, widget, side="left", padx=(12, 0)):
        """把控件放进头部

        @param widget: 控件, 需要以 head 为父容器
        @param side: left 或 right
        @param padx: 与相邻控件的间距
        """
        if self.head is None:
            return
        widget.pack(in_=self.head, side=side, fill="y",
                    padx=(scale(padx[0]), scale(padx[1])))

    def set_title(self, value):
        """更新头部左侧的小节标题"""
        if self.title_label is not None:
            self.title_label.configure(text=value)

    def set_right(self, value):
        """更新头部右侧的补充说明"""
        if self.right_label is not None:
            self.right_label.configure(text=value)


class Field(tk.Frame):
    """控件框: 30 像素高 的 fill 底色方块, 可带右侧箭头

    只负责显示时用它承载一段文字; 需要输入时改用 entry() / area()
    """

    def __init__(self, master, theme, value="", surface="panel",
                 size=SIZE_BODY, token="text", mono_font=True, width=None,
                 height=None, chevron=False, left_pad=9):
        height = CONTROL_HEIGHT if height is None else scale(height)
        width = scale(width) if width is not None else None
        left_pad = scale(left_pad)
        super().__init__(master, bd=0, highlightthickness=1)
        self.theme = theme
        self._surface = surface
        tint(self, bg="fill", hl="hair", hlc="hair")
        self.configure(bg=theme.rgb("fill"), highlightbackground=theme.rgb("hair"),
                       highlightcolor=theme.rgb("hair"))
        self.configure(height=height)
        if width is not None:
            self.configure(width=width)
        self.pack_propagate(False)
        self.grid_propagate(False)
        self._left_pad = left_pad
        self._segments = None
        #: 内容区使用的字体, 可编辑变体与弹出列表都要用同一份
        self._font_spec = mono(size) if mono_font else sans(size)
        #: 可编辑变体才会用到, 由 Dropdown 建立
        self.entry = None

        self.label = text(self, theme, value=value, size=size, token=token,
                          mono_font=mono_font, surface="fill", anchor="w")
        self.label.pack(side="left", fill="both", expand=True,
                        padx=(left_pad, 0))
        if chevron:
            self.chevron = text(self, theme, value=ICON_CHEVRON,
                                size=SIZE_SECTION, token="muted",
                                icon_font=True, surface="fill", anchor="e")
            self.chevron.configure(width=scale(2))
            self.chevron.pack(side="right", fill="y", padx=(0, scale(8)))

    def content_font(self):
        """内容区使用的字体

        @return: Tk 字体配置
        """
        return self._font_spec

    def set(self, value, token=None):
        """更新控件框里的文字

        @param value: 新的文字
        @param token: 新的文字颜色令牌, 省略时保持原色
        """
        self._clear_segments()
        self.label.configure(text=value)
        if token is not None:
            tint(self.label, bg="fill", fg=token)
            self.label.configure(fg=self.theme.rgb(token))

    def get(self):
        """取当前文字"""
        if self._segments is not None:
            return "".join(part.cget("text") for part in self._segments)
        return self.label.cget("text")

    def set_segments(self, segments):
        """用多段不同颜色的文字替换内容

        串口下拉框用它展示 端口 + 占用状态 + 描述, 每一段单独配色

        @param segments: (文本, 颜色令牌, 是否等宽) 序列; 传空序列时退回普通文字
        """
        self._clear_segments()
        if not segments:
            return
        self.label.pack_forget()
        holder = tk.Frame(self, bd=0, highlightthickness=0)
        tint(holder, bg="fill")
        holder.configure(bg=self.theme.rgb("fill"))
        holder.pack(side="left", fill="both", expand=True,
                    padx=(self._left_pad, 0))
        parts = []
        for index, (value, token, mono_font) in enumerate(segments):
            part = text(holder, self.theme, value=value, size=SIZE_BODY,
                        token=token, mono_font=mono_font, surface="fill",
                        anchor="w")
            part._thione_token = token
            part.pack(side="left",
                      padx=(0 if index == 0 else scale(6), 0))
            parts.append(part)
        self._segments = (holder, parts)

    def _clear_segments(self):
        """清掉多段文字, 恢复普通的单段标签"""
        if self._segments is None:
            return
        holder = self._segments[0]
        holder.destroy()
        self._segments = None
        self.label.pack(side="left", fill="both", expand=True,
                        padx=(self._left_pad, 0))

    def set_enabled(self, enabled):
        """启用或禁用控件框

        @param enabled: False 时文字置灰
        """
        token = "text" if enabled else "disabled_text"
        self.label.configure(fg=self.theme.rgb(token))
        tint(self.label, bg="fill", fg=token)
        if self.entry is not None:
            self.entry.configure(
                state="normal" if enabled else "disabled",
                disabledforeground=self.theme.rgb("disabled_text"),
                fg=self.theme.rgb(token))
            tint(self.entry, bg="fill", fg=token, insert="text",
                 sel_bg="accent", sel_fg="on_accent")
        if self._segments is not None:
            for part in self._segments[1]:
                part.configure(fg=self.theme.rgb(token if not enabled
                                                 else getattr(
                                                     part, "_thione_token",
                                                     "text")))


class EntryField(tk.Frame):
    """可编辑的控件框: 外观与 Field 一致, 内部是单行输入框"""

    def __init__(self, master, theme, variable=None, width=150,
                 mono_font=True, size=SIZE_BODY, height=None,
                 align="w"):
        width = scale(width) if width is not None else None
        height = CONTROL_HEIGHT if height is None else scale(height)
        super().__init__(master, bd=0, highlightthickness=1)
        self.theme = theme
        tint(self, bg="fill", hl="hair", hlc="hair")
        self.configure(bg=theme.rgb("fill"),
                       highlightbackground=theme.rgb("hair"),
                       highlightcolor=theme.rgb("hair"), height=height)
        if width is not None:
            self.configure(width=width)
        self.pack_propagate(False)
        self.entry = tk.Entry(self, bd=0, highlightthickness=0, relief="flat",
                              font=mono(size) if mono_font else sans(size),
                              textvariable=variable, justify="left")
        tint(self.entry, bg="fill", fg="text", insert="text", sel_bg="accent",
             sel_fg="on_accent")
        self.entry.configure(bg=theme.rgb("fill"), fg=theme.rgb("text"),
                             insertbackground=theme.rgb("text"),
                             selectbackground=theme.rgb("accent"),
                             selectforeground=theme.rgb("on_accent"))
        self.entry.pack(side="left", fill="both", expand=True,
                        padx=(scale(9), scale(9)))
        if align == "e":
            self.entry.configure(justify="right")

    def get(self):
        """取输入内容"""
        return self.entry.get()

    def set(self, value):
        """覆盖输入内容

        @param value: 新的文本
        """
        self.entry.delete(0, "end")
        self.entry.insert(0, value)

    def focus_set(self):
        """把焦点交给内部输入框"""
        self.entry.focus_set()

    def set_enabled(self, enabled):
        """启用或禁用输入框

        @param enabled: False 时置灰且不可编辑
        """
        token = "text" if enabled else "disabled_text"
        self.entry.configure(
            state="normal" if enabled else "disabled",
            disabledforeground=self.theme.rgb("disabled_text"),
            fg=self.theme.rgb(token))
        tint(self.entry, bg="fill", fg=token, insert="text", sel_bg="accent",
             sel_fg="on_accent")


class Area(tk.Frame):
    """多行文本块: fill 底色 + 1 像素描边, 用于进制输入与收发区

    内容用 tk.Text 承载, 因此可以换行 滚动与只读
    """

    def __init__(self, master, theme, height=120, surface="panel",
                 size=SIZE_TITLE, token="text", editable=True, wrap="char",
                 pad=10, placeholder=""):
        height = scale(height)
        pad = scale(pad)
        super().__init__(master, bd=0, highlightthickness=1)
        self.theme = theme
        tint(self, bg="fill", hl="hair", hlc="hair")
        self.configure(bg=theme.rgb("fill"),
                       highlightbackground=theme.rgb("hair"),
                       highlightcolor=theme.rgb("hair"), height=height)
        self.pack_propagate(False)
        self.text = tk.Text(self, bd=0, highlightthickness=0, wrap=wrap,
                            font=mono(size), spacing1=0, spacing3=0,
                            cursor="xterm" if editable else "arrow")
        tint(self.text, bg="fill", fg=token, insert="text", sel_bg="accent",
             sel_fg="on_accent")
        self.text.configure(bg=theme.rgb("fill"), fg=theme.rgb(token),
                            insertbackground=theme.rgb("text"),
                            selectbackground=theme.rgb("accent"),
                            selectforeground=theme.rgb("on_accent"),
                            padx=pad, pady=pad)
        self.text.pack(fill="both", expand=True)
        if not editable:
            self.text.configure(state="disabled")
        self._editable = editable
        self._placeholder = placeholder
        self._showing_placeholder = False
        self.text.tag_configure("placeholder", foreground=theme.rgb("muted"))
        if placeholder:
            self.text.bind("<FocusIn>", self._clear_placeholder)
            self.text.bind("<FocusOut>", self._restore_placeholder)
            self._restore_placeholder()

    def set(self, value):
        """替换全部内容

        @param value: 新的文本
        """
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self._showing_placeholder = False
        if value:
            self.text.insert("1.0", value)
        if not self._editable:
            self.text.configure(state="disabled")

    def get(self):
        """取全部内容"""
        if self._showing_placeholder:
            return ""
        return self.text.get("1.0", "end-1c")

    def focus_set(self):
        """把焦点交给文本区"""
        self.text.focus_set()

    def _restore_placeholder(self, _event=None):
        """没有内容时显示占位文案"""
        if not self._placeholder or self.text.get("1.0", "end-1c"):
            return
        self.text.insert("1.0", self._placeholder, "placeholder")
        self._showing_placeholder = True

    def _clear_placeholder(self, _event=None):
        """拿到焦点后清掉占位文案"""
        if not self._showing_placeholder:
            return
        self.text.delete("1.0", "end")
        self._showing_placeholder = False

    @property
    def widget(self):
        """返回内部可编辑的 Text, 便于页面自行插入内容"""
        return self.text

    def _thione_apply(self, palette):
        """主题切换后重画占位文案的颜色

        @param palette: 当前配色
        """
        self.text.tag_configure("placeholder",
                                foreground=color(palette["muted"]))


class Dropdown(Field):
    """下拉选择: 外观与控件框一致, 点击后在下方弹出列表

    弹出列表的宽度与控件框一致, 并沿用同一套方角 细描边样式; 项目较多时列表内部
    滚动, 不会超出屏幕. 传 editable=True 时内容区换成输入框, 既能从列表里选,
    也能直接输入 (串口助手的波特率 数据位 停止位就属于这一类)
    """

    def __init__(self, master, theme, values=(), command=None,
                 surface="panel", size=SIZE_BODY, mono_font=False,
                 width=None, placeholder="", display=None, editable=False,
                 variable=None, align="w"):
        super().__init__(master, theme, value=placeholder, surface=surface,
                         size=size, token="text", mono_font=mono_font,
                         width=width, chevron=True)
        self._values = list(values)
        self._command = command
        self._value = placeholder
        self._enabled = True
        self._display = display
        self._editable = bool(editable)
        self._variable = variable
        self.entry = None
        self._popup_window = None
        if self._editable:
            self._build_entry(align)
        # 点击落在控件框 文字或箭头上都要弹出菜单, 只绑在控件框上会漏掉大部分点击;
        # 可编辑时输入框要让给文字编辑, 只有控件框与箭头弹出列表
        clickable = (self, self.chevron) if self._editable else (
            self, self.label, self.chevron)
        for widget in clickable:
            widget.configure(cursor="hand2")
            widget.bind("<Button-1>", self._popup)

    def _build_entry(self, align="w"):
        """把只读文字换成可编辑输入框, 右侧的箭头保持不变

        @param align: 文字对齐方式, e 表示右对齐
        """
        self.label.pack_forget()
        self.entry = tk.Entry(self, bd=0, highlightthickness=0, relief="flat",
                              font=self._font_spec,
                              textvariable=self._variable,
                              justify="right" if align == "e" else "left")
        tint(self.entry, bg="fill", fg="text", insert="text", sel_bg="accent",
             sel_fg="on_accent")
        self.entry.configure(bg=self.theme.rgb("fill"),
                             fg=self.theme.rgb("text"),
                             insertbackground=self.theme.rgb("text"),
                             selectbackground=self.theme.rgb("accent"),
                             selectforeground=self.theme.rgb("on_accent"))
        self.entry.pack(side="left", fill="both", expand=True,
                        padx=(self._left_pad, 4))
        if self._variable is None and self.label.cget("text"):
            self.entry.insert(0, self.label.cget("text"))

    def set(self, value):
        """直接设置当前值, 不触发回调

        @param value: 新的取值
        """
        self._value = value
        if self._editable:
            self.entry.delete(0, "end")
            self.entry.insert(0, value)
            return
        super().set(value)
        if self._display is not None:
            self.set_segments(self._display(value))

    def value(self):
        """取当前取值"""
        if self._editable:
            return self.entry.get()
        return self._value

    def get(self):
        """取当前文字"""
        return self.value()

    def _popup(self, event=None):
        if not self._enabled:
            return "break"
        self._close_popup()
        self._popup_window = _DropdownPopup(self, self.theme, self._values,
                                            self.value(), self._choose)
        self._popup_window.open()
        return "break"

    def _close_popup(self):
        """收起已经打开的弹出列表"""
        popup, self._popup_window = self._popup_window, None
        if popup is not None:
            popup.close()

    def close_popup(self):
        """收起弹出列表, 供页面在切页或退出时调用"""
        self._close_popup()

    def set_values(self, values):
        """更新可选项, 弹出列表打开着时一并收起

        @param values: 选项文本序列
        """
        self._values = list(values)
        self._close_popup()

    def _choose(self, value):
        self.set(value)
        invoke(self._command, value)

    def set_enabled(self, enabled):
        """启用或禁用下拉框

        @param enabled: False 时置灰且不响应点击
        """
        self._enabled = enabled
        super().set_enabled(enabled)
        cursor = "hand2" if enabled else "arrow"
        for widget in (self, self.label, self.chevron):
            widget.configure(cursor=cursor)
        token = "muted" if enabled else "disabled_text"
        self.chevron.configure(fg=self.theme.rgb(token))
        tint(self.chevron, bg="fill", fg=token)


class Segment(tk.Frame):
    """分段控件: 1 像素描边的方框, 选中项用 accent_soft 底色"""

    def __init__(self, master, theme, options, value=None, command=None,
                 surface="canvas", height=28, size=SIZE_BODY):
        height = scale(height)
        super().__init__(master, bd=0, highlightthickness=1)
        self.theme = theme
        self._surface = surface
        self._size = size
        self._command = command
        self._value = value if value is not None else options[0][0]
        self._items = {}
        tint(self, hl="hair", hlc="hair")
        self.configure(highlightbackground=theme.rgb("hair"),
                       highlightcolor=theme.rgb("hair"))
        for key, label in options:
            cell = tk.Frame(self, height=height, bd=0, highlightthickness=0)
            caption = text(cell, theme, value=label, size=size,
                           surface=surface, anchor="center")
            # 选中项使用粗体, 宽度按粗体测量, 切换时文字才不会被裁掉
            bold_font = tkfont.Font(root=cell, font=sans(size, True))
            cell_width = max(caption.winfo_reqwidth(),
                             bold_font.measure(label)) + scale(24)
            cell.configure(width=cell_width)
            cell.pack_propagate(False)
            cell.pack(side="left", fill="y")
            caption.pack(fill="both", expand=True, padx=scale(12))
            for widget in (cell, caption):
                widget.configure(cursor="hand2")
                widget.bind("<Button-1>", lambda _e, k=key: self.set(k, True))
            self._items[key] = (cell, caption)
        self._paint()

    def _paint(self):
        """按当前选中项刷新配色"""
        for key, (cell, caption) in self._items.items():
            if key == self._value:
                bg, fg, bold = "accent_soft", "accent", True
            else:
                bg, fg, bold = self._surface, "muted", False
            cell.configure(bg=self.theme.rgb(bg))
            caption.configure(bg=self.theme.rgb(bg), fg=self.theme.rgb(fg),
                              font=sans(self._size, bold))
            tint(cell, bg=bg)
            tint(caption, bg=bg, fg=fg)
        self.configure(bg=self.theme.rgb(self._surface))

    def set(self, key, notify=False):
        """切换选中项

        @param key: 选项标识
        @param notify: True 时触发回调
        """
        if key not in self._items or key == self._value:
            return
        self._value = key
        self._paint()
        if notify:
            invoke(self._command, key)

    def value(self):
        """取当前选中项标识"""
        return self._value


class Check(tk.Frame):
    """勾选行: 方框或对勾字形 + 文字, 点击整行切换"""

    def __init__(self, master, theme, value, variable=None, command=None,
                 surface="panel", size=SIZE_BODY, token="text"):
        super().__init__(master, bd=0, highlightthickness=0)
        self.theme = theme
        self._variable = variable if variable is not None else tk.BooleanVar()
        self._command = command
        self._surface = surface
        self._token = token
        self._size = size
        self._enabled = True
        tint(self, bg=surface)
        self.configure(bg=theme.rgb(surface))
        self.mark = text(self, theme, size=size, icon_font=True,
                         surface=surface, anchor="center")
        self.mark.pack(side="left")
        self.label = text(self, theme, value=value, size=size, token=token,
                          surface=surface, anchor="w")
        self.label.pack(side="left", padx=(scale(6), 0))
        self._variable.trace_add("write", lambda *_a: self._paint())
        for widget in (self, self.mark, self.label):
            widget.configure(cursor="hand2")
            widget.bind("<Button-1>", self._toggle)
        self._paint()

    def _toggle(self, _event=None):
        if not self._enabled:
            return
        self._variable.set(not self._variable.get())
        invoke(self._command, self._variable.get())

    def _paint(self):
        """按勾选状态画对勾 or 空方框"""
        checked = bool(self._variable.get())
        self.mark.configure(text=ICON_CHECK if checked else ICON_BOX,
                            fg=self.theme.rgb("accent" if checked else "muted"))
        tint(self.mark, bg=self._surface,
             fg="accent" if checked else "muted")

    def variable(self):
        """返回绑定的 BooleanVar"""
        return self._variable

    def set_enabled(self, enabled):
        """启用或禁用勾选行

        @param enabled: False 时置灰且不响应点击
        """
        self._enabled = enabled
        cursor = "hand2" if enabled else "arrow"
        for widget in (self, self.mark, self.label):
            widget.configure(cursor=cursor)
        token = self._token if enabled else "disabled_text"
        self.label.configure(fg=self.theme.rgb(token))
        tint(self.label, bg=self._surface, fg=token)


def set_enabled(widget, enabled):
    """按控件类型启用或禁用它

    自定义部件走各自的 set_enabled, 原生输入控件直接切状态

    @param widget: 目标控件
    @param enabled: False 表示禁用
    """
    setter = getattr(widget, "set_enabled", None)
    if callable(setter):
        setter(enabled)
        return
    if isinstance(widget, (tk.Entry, tk.Text)):
        widget.configure(state="normal" if enabled else "disabled")


class RadioRow(tk.Frame):
    """单选项行: 对勾/方框字形 + 名称 + 右侧说明"""

    def __init__(self, master, theme, value, label, hint="", variable=None,
                 command=None, surface="panel", height=34):
        height = scale(height)
        super().__init__(master, bd=0, highlightthickness=0, height=height)
        self.theme = theme
        self._surface = surface
        self._value = value
        self._variable = variable if variable is not None else tk.StringVar()
        self._command = command
        tint(self, bg=surface)
        self.configure(bg=theme.rgb(surface))
        self.pack_propagate(False)
        self.mark = text(self, theme, size=SIZE_BODY, icon_font=True,
                         surface=surface, anchor="center")
        self.mark.pack(side="left")
        self.label = text(self, theme, value=label, surface=surface, anchor="w")
        self.label.pack(side="left", padx=(scale(10), 0), fill="x",
                        expand=True)
        self.hint = text(self, theme, value=hint, size=SIZE_LABEL,
                         token="muted", surface=surface, anchor="e")
        self.hint.pack(side="right")
        self._variable.trace_add("write", lambda *_a: self._paint())
        for widget in (self, self.mark, self.label):
            widget.configure(cursor="hand2")
            widget.bind("<Button-1>", self._choose)
        self._paint()

    def _choose(self, _event=None):
        self._variable.set(self._value)
        invoke(self._command, self._value)

    def _paint(self):
        """按选中状态刷新字形与文字配色"""
        checked = self._variable.get() == self._value
        self.mark.configure(text=ICON_CHECK if checked else ICON_BOX,
                            fg=self.theme.rgb("accent" if checked else "muted"))
        tint(self.mark, bg=self._surface,
             fg="accent" if checked else "muted")
        self.label.configure(fg=self.theme.rgb("text"))


class Dot(tk.Canvas):
    """状态栏上的 7 像素圆点"""

    def __init__(self, master, theme, kind="idle", surface="side"):
        super().__init__(master, width=DOT_SIZE, height=DOT_SIZE, bd=0,
                         highlightthickness=0)
        self.theme = theme
        self._kind = kind
        self._surface = surface
        tint(self, bg=surface)
        self.bind("<Expose>", lambda _e: self.redraw())
        self.redraw()

    def set_kind(self, kind):
        """切换圆点颜色

        @param kind: ok / run / idle / warn / fail
        """
        if kind == self._kind:
            return
        self._kind = kind
        self.redraw()

    def redraw(self):
        """按当前状态重画圆点"""
        self.configure(bg=self.theme.rgb(self._surface))
        self.delete("all")
        self.create_oval(0, 0, DOT_SIZE - 1, DOT_SIZE - 1, outline="",
                         fill=self.theme.rgb(self._color_token()))

    def _color_token(self):
        return {"ok": "ok", "run": "accent", "warn": "warn",
                "fail": "danger"}.get(self._kind, "muted")

    def _thione_apply(self, _palette):
        """主题切换后重画"""
        self.redraw()


class Splitter(tk.Frame):
    """两个面板之间的拖拽分隔条

    平时与页面底色一致 (看不见), 指针进入或者拖动时用强调色; 拖动量交给调用方,
    由调用方按自己的范围夹紧
    """

    def __init__(self, master, theme, orient="vertical", size=5,
                 on_drag=None, on_start=None, on_end=None):
        size = scale(size)
        super().__init__(master, bd=0, highlightthickness=0)
        self.theme = theme
        self.orient = orient
        self._on_drag = on_drag
        self._on_start = on_start
        self._on_end = on_end
        self._origin = None
        tint(self, bg="canvas")
        self.configure(bg=theme.rgb("canvas"))
        self.configure(cursor="sb_h_double_arrow" if orient == "vertical"
                       else "sb_v_double_arrow")
        if orient == "vertical":
            self.configure(width=size)
        else:
            self.configure(height=size)
        self.bind("<Button-1>", self._press)
        self.bind("<B1-Motion>", self._drag)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<Enter>", lambda _e: self._hover(True))
        self.bind("<Leave>", lambda _e: self._hover(False))

    # ---------------- 拖拽 ----------------
    def _press(self, event):
        """记下拖动起点

        @param event: 鼠标按下事件
        """
        self._origin = event.x_root if self.orient == "vertical" else event.y_root
        self.configure(bg=self.theme.rgb("accent"))
        if self._on_start is not None:
            self._on_start()

    def _drag(self, event):
        """把拖动量交给调用方

        拖动量始终相对按下时的位置, 调用方据此在自己的起始尺寸上做偏移, 这样
        分隔条才会跟住指针, 不会越拖越偏

        @param event: 鼠标拖动事件
        """
        if self._origin is None or self._on_drag is None:
            return
        current = event.x_root if self.orient == "vertical" else event.y_root
        self._on_drag(current - self._origin)

    def _release(self, _event):
        """结束拖动, 回到平时的颜色"""
        self._origin = None
        self.configure(bg=self.theme.rgb("canvas"))
        if self._on_end is not None:
            self._on_end()

    def _hover(self, hovering):
        """指针进入与离开时换色

        @param hovering: 指针是否在分隔条上
        """
        if self._origin is not None:
            return
        self.configure(bg=self.theme.rgb("accent" if hovering else "canvas"))


class _DropdownPopup:
    """下拉框的弹出列表

    宽度与控件框一致, 样式沿用同一套方角与细描边; 项目较多时列表内部滚动,
    点击列表之外的地方或者按 Esc 收起
    """

    def __init__(self, field, theme, values, current, on_choose):
        self.field = field
        self.theme = theme
        self.values = list(values)
        self.current = current
        self.on_choose = on_choose
        self.window = None
        self._rows = []

    # ---------------- 打开与收起 ----------------
    def open(self):
        """在控件框正下方弹出列表, 下方放不下时翻到上方"""
        field = self.field
        field.update_idletasks()
        if not self.values:
            return
        width = max(field.winfo_width(), scale(80))
        row_count = max(1, min(len(self.values), LIST_MAX_VISIBLE))
        height = row_count * LIST_ITEM_HEIGHT

        self.window = tk.Toplevel(field)
        self.window.withdraw()
        self.window.overrideredirect(True)
        self.window.transient(field.winfo_toplevel())
        # 外框底色当描边用, 里面再铺一层面板底色, 得到 1 像素方角边框
        self.window.configure(bg=self.theme.rgb("hair"))
        inner = tk.Frame(self.window, bd=0, highlightthickness=0)
        tint(inner, bg="panel")
        inner.configure(bg=self.theme.rgb("panel"))
        inner.pack(fill="both", expand=True, padx=1, pady=1)
        self.canvas = tk.Canvas(inner, bd=0, highlightthickness=0,
                                width=width, height=height)
        tint(self.canvas, bg="panel")
        self.canvas.configure(bg=self.theme.rgb("panel"))
        self.canvas.pack(side="left", fill="both", expand=True)
        # 项目多到一屏放不下时给一条细滚动条, 让用户知道下面还有内容
        self.scroll = None
        if len(self.values) > LIST_MAX_VISIBLE:
            from tkinter import ttk

            self.scroll = ttk.Scrollbar(
                inner, orient="vertical", command=self.canvas.yview,
                style="Thin.Vertical.TScrollbar")
            self.canvas.configure(yscrollcommand=self.scroll.set)
            self.scroll.pack(side="right", fill="y", padx=(0, 1), pady=1)
        self.items = tk.Frame(self.canvas, bd=0, highlightthickness=0)
        tint(self.items, bg="panel")
        self.items.configure(bg=self.theme.rgb("panel"))
        self.canvas.create_window((0, 0), window=self.items, anchor="nw",
                                  width=width)
        self._build_items()
        self.items.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

        x = field.winfo_rootx()
        y = field.winfo_rooty() + field.winfo_height()
        screen_height = field.winfo_screenheight()
        margin = scale(8)
        if y + height > screen_height - margin:
            above = field.winfo_rooty() - height - scale(2)
            y = above if above > margin else max(
                margin, screen_height - height - margin)
        self.window.geometry("%dx%d+%d+%d" % (width + 2, height + 2, x, y))
        self.window.deiconify()
        self.window.lift()
        try:
            # 主窗口可能是置顶的, 列表也要置顶才不会被盖住
            self.window.attributes("-topmost", True)
        except tk.TclError:
            pass
        self.window.grab_set()
        # 点列表之外的地方收起; 列表项自己会先处理点击
        for widget in (self.window, self.canvas, self.items):
            widget.bind("<Button-1>", lambda _e: self.close())
        self.window.bind("<Escape>", lambda _e: self.close())
        # 滚轮要绑在列表 列表项与窗口上: 指针多半停在某一项上, 只绑画布收不到
        for widget in [self.window, self.canvas, self.items] + [
                item for pair in self._rows for item in pair[:2]]:
            widget.bind("<MouseWheel>", self._wheel)

    def close(self):
        """收起列表"""
        window, self.window = self.window, None
        if window is None:
            return
        try:
            window.grab_release()
            window.destroy()
        except tk.TclError:
            pass
        if self.field._popup_window is self:
            self.field._popup_window = None

    # ---------------- 列表项 ----------------
    def _build_items(self):
        """按取值建立列表项, 当前值用选中色标出"""
        for index, value in enumerate(self.values):
            row = tk.Frame(self.items, height=LIST_ITEM_HEIGHT, bd=0,
                           highlightthickness=0)
            row.pack(side="top", fill="x")
            row.pack_propagate(False)
            selected = value == self.current
            token = "accent" if selected else "text"
            bg = "accent_soft" if selected else "panel"
            tint(row, bg=bg)
            row.configure(bg=self.theme.rgb(bg))
            label = text(row, self.theme, value=value, size=SIZE_BODY,
                         token=token, surface=bg, anchor="w")
            label.pack(fill="both", expand=True, padx=scale(9))
            label.configure(font=self.field.content_font())
            for widget in (row, label):
                widget.configure(cursor="hand2")
                widget.bind("<Button-1>",
                            lambda _e, v=value: self._choose(v))
                widget.bind("<Enter>", lambda _e, r=row, l=label:
                            self._hover_row(r, l, True))
                widget.bind("<Leave>", lambda _e, r=row, l=label:
                            self._hover_row(r, l, False))
            self._rows.append((row, label, value))

    def _hover_row(self, row, label, hovering):
        """指针移到某项上时换底色

        @param row: 列表项容器
        @param label: 列表项文字
        @param hovering: 指针是否在该项上
        """
        selected = label.cget("text") == self.current
        if selected:
            return
        bg = "fill" if hovering else "panel"
        row.configure(bg=self.theme.rgb(bg))
        label.configure(bg=self.theme.rgb(bg))
        tint(row, bg=bg)
        tint(label, bg=bg, fg="text")

    def _choose(self, value):
        """选中一项后收起列表

        @param value: 选项文本
        """
        self.close()
        self.on_choose(value)

    def _wheel(self, event):
        """列表内部滚动

        @param event: 滚轮事件
        """
        bbox = self.canvas.bbox("all")
        if bbox is None or (bbox[3] - bbox[1]) <= self.canvas.winfo_height():
            return
        self.canvas.yview_scroll(-int(event.delta // 120), "units")
        return "break"


def value_grid(master, theme, fields, surface="panel", label_width=None,
               value_mono=True, value_size=SIZE_BODY, wrap_width=0):
    """建立两列的键值网格

    @param master: 父容器
    @param theme: 主题管理器
    @param fields: (键, 初始值) 序列
    @param surface: 所在表面的令牌名
    @param label_width: 键列的像素宽度, 省略时按内容
    @param value_mono: 值是否使用等宽字体
    @param value_size: 值的字号
    @param wrap_width: 大于 0 时值按该像素宽度换行
    @return: (容器, 值字典, 设置函数)
    """
    frame = tk.Frame(master, bd=0, highlightthickness=0)
    tint(frame, bg=surface)
    frame.configure(bg=theme.rgb(surface))
    values = {}
    holders = {}
    if label_width is not None:
        frame.columnconfigure(0, minsize=label_width)
    frame.columnconfigure(1, weight=1)
    for index, (key, caption) in enumerate(fields):
        caption_label = text(frame, theme, value=caption, size=SIZE_LABEL,
                             token="muted", surface=surface, anchor="w")
        caption_label.grid(row=index, column=0, sticky="nw",
                           pady=(0, scale(7)))
        holder = tk.Frame(frame, bd=0, highlightthickness=0)
        tint(holder, bg=surface)
        holder.configure(bg=theme.rgb(surface))
        holder.grid(row=index, column=1, sticky="ew",
                    padx=(scale(10), 0), pady=(0, scale(7)))
        label = text(holder, theme, value="-", size=value_size,
                     mono_font=value_mono, surface=surface, anchor="w",
                     wrap=wrap_width > 0)
        label.pack(fill="x")
        values[key] = label
        holders[key] = holder

    def apply(mapping):
        for key, label in values.items():
            if key not in mapping:
                continue
            item = mapping[key]
            token = "text"
            if isinstance(item, tuple):
                item, token = item
            label.configure(text=item, fg=theme.rgb(token))
            tint(label, bg=surface, fg=token)
            if wrap_width > 0:
                label.configure(wraplength=max(
                    wrap_width, holders[key].winfo_width() or wrap_width))

    return frame, values, apply


class Table(tk.Frame):
    """设计稿风格的表格

    表头一行 (11 像素字号 下方 1 像素分隔线), 数据行 31 像素高 行间 1 像素
    分隔线; 选中行使用 fill_hi 底色 左端画 2 像素强调条 首列文字改用强调色
    """

    def __init__(self, master, theme, columns, on_select=None, empty_text="",
                 surface="panel", row_height=TABLE_ROW_HEIGHT, padding=0,
                 multi=False):
        super().__init__(master, bd=0, highlightthickness=0)
        self.theme = theme
        self._columns = list(columns)
        self._on_select = on_select
        self._empty_text = empty_text
        self._surface = surface
        self.row_height = row_height
        self.padding = scale(padding)
        self._rows = []
        self._selected = None
        #: 允许多选时记录所有被勾选的行号
        self._checked = set()
        self.multi = bool(multi)
        self._layout = []
        tint(self, bg=surface)
        self.configure(bg=theme.rgb(surface))

        self.header = tk.Canvas(self, height=TABLE_HEAD_HEIGHT, bd=0,
                                highlightthickness=0)
        tint(self.header, bg=surface)
        self.header.configure(bg=theme.rgb(surface))
        self.header.pack(side="top", fill="x")

        self.body = tk.Canvas(self, bd=0, highlightthickness=0)
        tint(self.body, bg=surface)
        self.body.configure(bg=theme.rgb(surface))
        self.scroll = tk.Scrollbar(self, orient="vertical",
                                   command=self.body.yview, width=scale(8),
                                   bd=0, highlightthickness=0,
                                   troughcolor=theme.rgb(surface),
                                   activebackground=theme.rgb("muted"),
                                   bg=theme.rgb("muted"),
                                   relief="flat")
        tint(self.scroll, bg="muted", trough=surface)
        self.body.configure(yscrollcommand=self.scroll.set)
        self.body.pack(side="left", fill="both", expand=True)
        self._scroll_visible = False
        self.body.bind("<Configure>", self._on_body_configure)
        self.body.bind("<Button-1>", self._on_click)
        self.body.bind("<MouseWheel>", self._on_wheel)

    # ---------------- 数据 ----------------
    def set_rows(self, rows, keep_selection=False):
        """替换全部数据行

        @param rows: 行序列, 每行是 {key: 文本} 或 {key: (文本, 颜色令牌)},
                     额外可用 data 键携带业务数据
        @param keep_selection: True 时尽量保留原来的选中行号
        """
        self._rows = list(rows)
        if not keep_selection or self._selected is None \
                or self._selected >= len(self._rows):
            self._selected = None
        self._checked = {index for index in self._checked
                         if index < len(self._rows)}
        self._redraw()

    def selection(self):
        """当前选中的行号

        @return: 行号列表, 单选时最多一个
        """
        if self.multi:
            return sorted(self._checked)
        return [] if self._selected is None else [self._selected]

    def clear_selection(self):
        """清空选中"""
        changed = bool(self._checked) or self._selected is not None
        self._checked.clear()
        self._selected = None
        if changed:
            self._redraw()
            if self._on_select is not None:
                self._on_select(None, None)

    def set_columns(self, columns):
        """替换列定义, 数据行不受影响

        @param columns: 列定义序列
        """
        self._columns = list(columns)
        self._compute_layout()
        self._redraw()

    def select(self, index, notify=False):
        """选中某一行, index 为 None 时清空选中

        @param index: 行号
        @param notify: True 时触发选中回调
        """
        if self.multi:
            self._checked = set() if index is None else {index}
            self._selected = index
            self._redraw()
            if notify and self._on_select is not None:
                data = None if index is None else self._rows[index].get("data")
                self._on_select(data, index)
            return
        if index == self._selected:
            return
        self._selected = index
        self._redraw()
        if notify and index is not None and self._on_select is not None:
            self._on_select(self._rows[index].get("data"), index)

    def selected_index(self):
        """取当前选中行号"""
        return self._selected

    def set_empty_text(self, value):
        """设置没有数据时显示的说明

        @param value: 说明文字
        """
        self._empty_text = value
        if not self._rows:
            self._redraw()

    # ---------------- 绘制 ----------------
    def _on_body_configure(self, _event=None):
        self._redraw()

    def _compute_layout(self):
        """按画布宽度算出各列的起点与宽度"""
        width = max(self.body.winfo_width(), 1) - self.padding * 2
        weights = [max(float(col.get("weight", 1)), 0.01)
                   for col in self._columns]
        total = sum(weights)
        layout = []
        x = self.padding
        for col, weight in zip(self._columns, weights):
            column_width = int(width * weight / total)
            layout.append((col, x, column_width))
            x += column_width
        self._layout = layout

    def _redraw(self):
        """重画表头与全部数据行"""
        if not self._layout or self.body.winfo_width() <= 1:
            self._compute_layout()
        self._compute_layout()
        self._draw_header()
        self._draw_body()

    def _draw_header(self):
        canvas = self.header
        canvas.delete("all")
        width = max(self.body.winfo_width(), 1)
        canvas.configure(width=width)
        for col, x, col_width in self._layout:
            anchor, offset = self._cell_anchor(col, x, col_width)
            canvas.create_text(offset, 0, anchor="n" if anchor == "center"
                               else anchor.replace("w", "nw").replace("e", "ne"),
                               text=col.get("title", ""),
                               font=sans(SIZE_SECTION, True),
                               fill=self.theme.rgb("muted"))
        canvas.create_line(self.padding, TABLE_HEAD_HEIGHT - 0.5,
                           max(width - self.padding, self.padding),
                           TABLE_HEAD_HEIGHT - 0.5,
                           fill=self.theme.rgb("hair"))

    def _draw_body(self):
        canvas = self.body
        canvas.delete("all")
        width = max(self.body.winfo_width(), 1)
        if not self._rows:
            canvas.create_text(width / 2, self.row_height,
                               text=self._empty_text, anchor="n",
                               font=sans(), fill=self.theme.rgb("muted"))
            canvas.configure(scrollregion=(0, 0, width, self.row_height * 3))
            self._update_scroll(False)
            return
        for index, row in enumerate(self._rows):
            top = index * self.row_height
            self._draw_row(canvas, row, index, top, width)
            canvas.create_line(self.padding, top + self.row_height - 0.5,
                               max(width - self.padding, self.padding),
                               top + self.row_height - 0.5,
                               fill=self.theme.rgb("hair"))
        canvas.configure(scrollregion=(0, 0, width,
                                       len(self._rows) * self.row_height))
        self._update_scroll(len(self._rows) * self.row_height
                            > canvas.winfo_height())

    def _draw_row(self, canvas, row, index, top, width):
        """画一行数据

        @param canvas: 数据区画布
        @param row: 行数据
        @param index: 行号
        @param top: 行的上边距
        @param width: 画布宽度
        """
        selected = (index in self._checked if self.multi
                    else index == self._selected)
        row_bg = row.get("row_bg")
        if selected:
            canvas.create_rectangle(0, top, width, top + self.row_height,
                                    outline="", fill=self.theme.rgb("fill_hi"))
            canvas.create_rectangle(0, top, 2, top + self.row_height,
                                    outline="", fill=self.theme.rgb("accent"))
        elif row_bg:
            canvas.create_rectangle(0, top, width, top + self.row_height,
                                    outline="", fill=self.theme.rgb(row_bg))
        for position, (col, x, col_width) in enumerate(self._layout):
            key = col.get("key")
            cell = row.get(key, "")
            token = col.get("color", "text")
            if isinstance(cell, tuple):
                cell, token = cell
            if selected and position == 0:
                token = "accent"
            anchor, offset = self._cell_anchor(col, x, col_width)
            font = mono() if col.get("mono") else sans()
            canvas.create_text(offset, top + self.row_height / 2, text=cell,
                               anchor=anchor, font=font,
                               fill=self.theme.rgb(token))

    def _cell_anchor(self, col, x, col_width):
        """算出某一列文字的锚点与横坐标

        @param col: 列定义
        @param x: 列的左边界
        @param col_width: 列的宽度
        @return: (锚点, 横坐标)
        """
        anchor = col.get("anchor", "w")
        if anchor == "e":
            return "e", x + col_width - CELL_PAD
        if anchor == "center":
            return "center", x + col_width / 2
        return "w", x + CELL_PAD

    # ---------------- 交互 ----------------
    def _update_scroll(self, visible):
        """内容超出可视区时才显示滚动条

        @param visible: 是否需要滚动条
        """
        if visible == self._scroll_visible:
            return
        self._scroll_visible = visible
        if visible:
            self.scroll.pack(side="right", fill="y")
        else:
            self.scroll.pack_forget()

    def _on_wheel(self, event):
        canvas = self.body
        bbox = canvas.bbox("all")
        if bbox is None or (bbox[3] - bbox[1]) <= canvas.winfo_height():
            return
        canvas.yview_scroll(-int(event.delta // 120), "units")

    def _on_click(self, event):
        index = self.index_at(event.x, event.y)
        if index < 0 or index >= len(self._rows):
            if not self.multi:
                self.select(None)
            return
        if self.multi:
            if index in self._checked:
                self._checked.discard(index)
            else:
                self._checked.add(index)
            self._selected = index
            self._redraw()
            if self._on_select is not None:
                self._on_select(self._rows[index].get("data"), index)
            return
        self.select(index, notify=True)

    def current_index(self):
        """最后一次被点击的行号, 多选时用它定位右键与双击的目标

        @return: 行号或 None
        """
        return self._selected

    def index_at(self, x, y):
        """把画布坐标换算成行号

        @param x: 相对控件的横坐标
        @param y: 相对控件的纵坐标
        @return: 行号, 不在任何行上时返回 -1
        """
        del x
        offset = self.body.canvasy(0)
        return int((y + offset) // self.row_height)

    def _thione_apply(self, palette):
        """主题切换后重画"""
        self.configure(bg=color(palette[self._surface]))
        self.header.configure(bg=color(palette[self._surface]))
        self.body.configure(bg=color(palette[self._surface]))
        self.scroll.configure(troughcolor=color(palette[self._surface]),
                              bg=color(palette["muted"]))
        self._redraw()


class StatusRow:
    """页面在底座状态栏上的内容

    左侧依次是圆点与说明文字, 之后用 add_tail() 追加指标 进度条或次要按钮;
    右侧用 add_action() 放指标与操作按钮, 按加入顺序从左到右排列; 页面切换时
    由外壳调用 show() / hide() 决定是否显示
    """

    def __init__(self, host_left, host_right, theme, kind="idle"):
        self.theme = theme
        self.frame = tk.Frame(host_left, bd=0, highlightthickness=0)
        tint(self.frame, bg="side")
        self.frame.configure(bg=theme.rgb("side"))
        self.dot = Dot(self.frame, theme, kind=kind, surface="side")
        self.dot.pack(side="left")
        self.text = text(self.frame, theme, size=SIZE_LABEL, token="muted",
                         surface="side")
        self.text.pack(side="left", padx=(scale(12), 0))
        self.tail = tk.Frame(self.frame, bd=0, highlightthickness=0)
        tint(self.tail, bg="side")
        self.tail.configure(bg=theme.rgb("side"))
        self.actions = tk.Frame(host_right, bd=0, highlightthickness=0)
        tint(self.actions, bg="side")
        self.actions.configure(bg=theme.rgb("side"))
        self._tail_count = 0
        self._action_count = 0

    def set_text(self, value):
        """设置主要说明"""
        self.text.configure(text=value)

    def set_kind(self, kind):
        """设置圆点状态"""
        self.dot.set_kind(kind)

    def add_tail(self, widget):
        """把一个控件接在说明文字后面 (指标 进度条或次要按钮)

        @param widget: 以 self.tail 为父容器的控件
        """
        if self._tail_count == 0:
            self.tail.pack(side="left", padx=(scale(12), 0))
        widget.pack(in_=self.tail, side="left",
                    padx=(scale(12), 0) if self._tail_count else (0, 0))
        self._tail_count += 1

    def add_action(self, widget):
        """把一个控件放进右侧操作区, 按加入顺序从左到右排列

        @param widget: 以 self.actions 为父容器的控件
        """
        widget.pack(in_=self.actions, side="left",
                    padx=(scale(10), 0) if self._action_count else (0, 0))
        self._action_count += 1

    def show(self):
        """页面切到前台时显示状态栏内容"""
        self.frame.pack(side="left")
        self.actions.pack(side="right")

    def hide(self):
        """页面切到后台时收起状态栏内容"""
        self.frame.pack_forget()
        self.actions.pack_forget()


class Track(tk.Canvas):
    """进度条: 150 x 4 像素的细条, 前景用强调色"""

    def __init__(self, master, theme, width=150, height=4, surface="side"):
        width = scale(width)
        height = scale(height)
        super().__init__(master, width=width, height=height, bd=0,
                         highlightthickness=0)
        self.theme = theme
        self._width = width
        self._height = height
        self._surface = surface
        self._fraction = 0.0
        tint(self, bg=surface)
        self.after(0, self.redraw)

    def set_fraction(self, fraction):
        """设置进度

        @param fraction: 0 到 1 之间的比例
        """
        fraction = max(0.0, min(float(fraction), 1.0))
        if abs(fraction - self._fraction) < 0.005:
            return
        self._fraction = fraction
        self.redraw()

    def redraw(self):
        """重画进度条"""
        self.configure(bg=self.theme.rgb(self._surface))
        self.delete("all")
        if self._fraction <= 0:
            return
        self.create_rectangle(0, 0, self._fraction * self._width,
                              self._height, outline="",
                              fill=self.theme.rgb("accent"))

    def _thione_apply(self, _palette):
        """主题切换后重画"""
        self.redraw()
