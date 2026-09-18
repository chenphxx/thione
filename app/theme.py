"""主题管理。

配色令牌来自 palettes.py (Flat Design 设计系统), 这里只做三件事:

1. 把令牌翻译成 ttk 样式, 并通过 option database 与递归遍历覆盖 tk 原生控件;
2. 维护当前深浅模式, 切换时按帧插值做颜色过渡, 过渡结束后通知监听者;
3. 为外壳与弹窗提供统一的字体与调色板入口。

全应用只有一个 ThemeManager 实例, 由外壳持有; 工具页面不要自己创建。
"""

import logging
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

from .motion import Tween, ease_out_cubic
from .palettes import MODE_NAMES, blend_palette, build_palette

logger = logging.getLogger(__name__)

#: 界面字号基准
FONT_SIZE = 10

#: 字体候选: 取系统里第一个装了的; 中文字形由 Windows 的字体链接回退
SANS_STACK = ("Plus Jakarta Sans", "Inter", "Segoe UI Variable Text",
              "Segoe UI", "Microsoft YaHei UI", "Tahoma")
MONO_STACK = ("Cascadia Code", "Cascadia Mono", "Consolas", "Courier New")

#: 解析后的字体族, 由 _resolve_fonts() 在拿到根窗口后写入
FONT_SANS = "Segoe UI"
FONT_MONO = MONO_STACK[2]

#: 主题过渡时长 (毫秒), 扁平风格的过渡控制在 150-200 毫秒之间
TRANSITION_MS = 180


def _font_tuple(family, size, bold, italic):
    """组装 tk 与 ttk 通用的字体元组。"""
    styles = [name for name, enabled in (("bold", bold), ("italic", italic)) if enabled]
    return (family, size, " ".join(styles)) if styles else (family, size)


def sans(size=FONT_SIZE, bold=False, italic=False):
    """界面正文字体; 中文回退到系统字体。

    @param size: 字号
    @param bold: 是否加粗
    @param italic: 是否斜体
    @return: 字体元组
    """
    return _font_tuple(FONT_SANS, size, bold, italic)


def mono(size=FONT_SIZE, bold=False):
    """等宽字体, 用于路径与序号这类需要对齐的文本。

    @param size: 字号
    @param bold: 是否加粗
    @return: 字体元组
    """
    return _font_tuple(FONT_MONO, size, bold, False)


def _resolve_fonts(root):
    """在系统已装字体里挑选最合适的一项。

    只在第一次创建根窗口时执行; 查询失败时保留模块里的默认值, 不影响启动。
    """
    global FONT_SANS, FONT_MONO
    try:
        available = set(tkfont.families(root))
    except tk.TclError:
        return
    for name in SANS_STACK:
        if name in available:
            FONT_SANS = name
            break
    for name in MONO_STACK:
        if name in available:
            FONT_MONO = name
            break


class ThemeManager:
    """管理全局样式与调色板, 并在深浅模式之间平滑切换。

    参数:
        root: tkinter 根窗口
        mode: 初始模式, "light" 或 "dark"; 非法值回落到深色
    """

    def __init__(self, root, mode="dark"):
        self.root = root
        self.style = ttk.Style(root)
        self.style.theme_use("clam")
        self._windows = [root]
        self._listeners = []
        self._frame_listeners = []
        self._transition = None
        self._target = None
        self._target_mode = None

        _resolve_fonts(root)
        # 供 option database 引用的具名字体; 每次切换都重建会不断占用 Tcl 字体资源
        self._default_font = tkfont.Font(root=root, family=FONT_SANS, size=FONT_SIZE)

        self.mode = mode if mode in MODE_NAMES else "dark"
        self.palette = build_palette(self.mode)
        self._apply_palette(self.palette)

    # ------------------------------------------------------------------
    # 窗口登记与监听
    # ------------------------------------------------------------------
    def register(self, window):
        """登记新建的 Toplevel 窗口, 切换主题时一并刷新。"""
        if window not in self._windows:
            self._windows.append(window)

    def add_listener(self, callback):
        """登记「主题稳定后」的回调。

        过渡动画期间不会调用, 只在颜色最终落定时调用一次; 页面用它刷新那些把
        颜色写进了数据而不只是控件选项的内容 (行标签色, 已渲染的缩略图)。
        """
        if callback not in self._listeners:
            self._listeners.append(callback)

    def remove_listener(self, callback):
        """注销回调, 重复注销不会报错。"""
        if callback in self._listeners:
            self._listeners.remove(callback)

    def add_frame_listener(self, callback):
        """登记「每一帧都调用」的回调, 用于自绘控件跟着过渡一起变色。"""
        if callback not in self._frame_listeners:
            self._frame_listeners.append(callback)

    def remove_frame_listener(self, callback):
        """注销逐帧回调。"""
        if callback in self._frame_listeners:
            self._frame_listeners.remove(callback)

    def _notify(self):
        for callback in list(self._listeners):
            try:
                callback()
            except Exception:
                logger.exception("主题回调执行失败")

    def _notify_frame(self):
        for callback in list(self._frame_listeners):
            try:
                callback()
            except Exception:
                logger.exception("主题逐帧回调执行失败")

    # ------------------------------------------------------------------
    # 模式切换
    # ------------------------------------------------------------------
    @property
    def is_dark(self):
        """当前是否为深色模式。"""
        return self.mode == "dark"

    def set_mode(self, mode, animate=True):
        """切换到指定模式, 返回最终的模式名。

        @param mode: "light" 或 "dark"
        @param animate: 是否播放颜色过渡
        @return: 切换后的模式名
        @throws ValueError: 模式不存在
        """
        if mode not in MODE_NAMES:
            raise ValueError("未知模式: %s" % mode)
        if mode == self.mode and self._transition is None:
            return self.mode
        self.mode = mode
        self._start_transition(build_palette(mode), animate)
        return self.mode

    def toggle(self, animate=True):
        """在深色与浅色之间切换, 返回切换后的模式名。

        @param animate: 是否播放颜色过渡
        @return: 切换后的模式名
        """
        return self.set_mode("light" if self.is_dark else "dark", animate=animate)

    def _start_transition(self, target, animate):
        """开始一次调色板过渡; 新的切换会取消尚未结束的旧过渡。"""
        self._cancel_transition()
        if not animate:
            self._settle(target)
            return
        start = self.palette
        self._target = target
        self._target_mode = self.mode
        self._transition = Tween(
            self.root,
            TRANSITION_MS,
            on_frame=lambda progress: self._apply_palette(
                blend_palette(start, target, progress)
            ),
            on_done=self._finish_transition,
            easing=ease_out_cubic,
        ).start()

    def _finish_transition(self):
        """过渡结束: 补一次精确取色, 再通知监听者。"""
        self._transition = None
        target, self._target = self._target, None
        if target is None:
            target = build_palette(self.mode)
        self._settle(target)

    def _settle(self, palette):
        """把调色板落定到控件上, 并通知「稳定后」的监听者。"""
        self._apply_palette(palette)
        self._notify()

    def _cancel_transition(self):
        if self._transition is not None:
            self._transition.cancel()
            self._transition = None

    def _apply_palette(self, palette):
        """把调色板写进样式与所有已登记的窗口, 并通知逐帧监听的控件。"""
        self.palette = palette
        self._configure_styles(palette)
        self._apply_option_db(palette)
        self.apply_theme()
        self._notify_frame()

    # ------------------------------------------------------------------
    # 应用与遍历
    # ------------------------------------------------------------------
    def apply_theme(self, widget=None):
        """把当前主题应用到指定控件树; 缺省时应用到所有登记的窗口。"""
        targets = [widget] if widget is not None else list(self._windows)
        for window in targets:
            try:
                if window.winfo_exists():
                    self._walk(window)
            except tk.TclError:
                pass

    def _walk(self, widget):
        """递归刷新 tk 原生控件; ttk 控件由样式负责, 这里不碰。

        控件可以用 _thione_surface 属性声明自己所在的表面层 (panel / card / bg),
        缺省按页面底色处理; 自绘的画布需要它来拿到正确的底色。
        """
        p = self.palette
        surface = getattr(widget, "_thione_surface", None)
        base = p.get(surface, p["bg"]) if surface else p["bg"]
        cls = widget.winfo_class()
        try:
            if cls == "Canvas":
                widget.configure(bg=base, highlightbackground=p["border"],
                                 highlightthickness=0)
            elif cls == "Label":
                widget.configure(bg=base, fg=p["text"])
            elif cls == "Frame":
                widget.configure(bg=base)
            elif cls == "Menu":
                widget.configure(bg=p["panel"], fg=p["text"],
                                 activebackground=p["hover"],
                                 activeforeground=p["text"],
                                 borderwidth=0, relief="flat")
        except tk.TclError:
            pass
        for child in widget.winfo_children():
            self._walk(child)

    # ------------------------------------------------------------------
    # 样式表
    # ------------------------------------------------------------------
    def _configure_styles(self, p):
        """把调色板写进 ttk 样式。

        约定: 页面底用 bg, 侧栏与工具条用 panel, 卡片用 card。整体是扁平风格,
        只用 1 像素描边和留白分层, 不画渐变与阴影; lightcolor/darkcolor 必须
        跟着背景色一起映射, 否则 clam 会画出立体高光。

        按控件族拆成若干段, 改动某一类控件时只需看对应的方法。
        """
        s = self.style
        s.configure(
            ".",
            background=p["bg"],
            foreground=p["text"],
            fieldbackground=p["input"],
            bordercolor=p["border"],
            troughcolor=p["trough"],
            selectbackground=p["accent"],
            selectforeground=p["on_accent"],
            font=sans(),
        )
        self._style_surfaces(p)
        self._style_labels(p)
        self._style_buttons(p)
        self._style_checkbuttons(p)
        self._style_inputs(p)
        self._style_treeviews(p)
        self._style_scrollbars(p)
        self._style_labelframes(p)

    def _style_surfaces(self, p):
        """表面与分隔: 页面底用 bg, 侧栏与工具条用 panel, 卡片用 card。"""
        s = self.style
        s.configure("TFrame", background=p["bg"])
        s.configure("Panel.TFrame", background=p["panel"])
        s.configure("Card.TFrame", background=p["card"])
        s.configure("Divider.TFrame", background=p["border"])
        s.configure("Drag.TFrame", background=p["border"])
        s.configure("DragHover.TFrame", background=p["accent"])
        s.configure("TPanedwindow", background=p["border"], sashwidth=6,
                    sashrelief="flat")
        s.configure("TSeparator", background=p["border"])

    def _style_labels(self, p):
        """文字与空状态占位块的标签。"""
        s = self.style
        s.configure("TLabel", background=p["bg"], foreground=p["text"])
        s.configure("Panel.TLabel", background=p["panel"], foreground=p["text"])
        s.configure("Muted.TLabel", background=p["bg"], foreground=p["muted"])
        s.configure("PanelMuted.TLabel", background=p["panel"],
                    foreground=p["muted"])
        s.configure("Card.TLabel", background=p["card"], foreground=p["text"])
        s.configure("CardMuted.TLabel", background=p["card"], foreground=p["muted"])
        s.configure("Header.TLabel", background=p["bg"], foreground=p["header"],
                    font=sans(15, bold=True))
        s.configure("PanelHeader.TLabel", background=p["panel"],
                    foreground=p["header"], font=sans(15, bold=True))
        s.configure("PanelHint.TLabel", background=p["panel"],
                    foreground=p["muted"], font=sans(10))
        s.configure("CardTitle.TLabel", background=p["card"],
                    foreground=p["header"], font=sans(11, bold=True))
        s.configure("SidebarMuted.TLabel", background=p["panel"],
                    foreground=p["muted"], font=sans(9))

        # 空状态: 一个符号加一句引导, 避免出现整块白屏
        s.configure("EmptyIcon.TLabel", background=p["card"],
                    foreground=p["muted"], font=sans(26))
        s.configure("EmptyTitle.TLabel", background=p["card"],
                    foreground=p["text"], font=sans(12, bold=True))
        s.configure("EmptyHint.TLabel", background=p["card"],
                    foreground=p["muted"], font=sans(10))

    def _style_buttons(self, p):
        """按钮: 默认次级 白底加 1 像素描边, 悬停与按下只改底色。"""
        s = self.style
        s.configure("TButton", background=p["card"], foreground=p["text"],
                    bordercolor=p["border_strong"], lightcolor=p["card"],
                    darkcolor=p["card"], borderwidth=1, relief="solid",
                    padding=(14, 7), focusthickness=0, font=sans())
        s.map("TButton",
              background=[("disabled", p["input"]), ("pressed", p["active"]),
                          ("active", p["hover"])],
              lightcolor=[("disabled", p["input"]), ("pressed", p["active"]),
                          ("active", p["hover"])],
              darkcolor=[("disabled", p["input"]), ("pressed", p["active"]),
                         ("active", p["hover"])],
              bordercolor=[("focus", p["ring"]), ("pressed", p["accent"]),
                           ("active", p["accent"])],
              foreground=[("disabled", p["muted"])])

        # 次级按钮与 TButton 同款, 单独命名是为了调用处语义清晰
        s.configure("Secondary.TButton", background=p["card"],
                    foreground=p["text"], bordercolor=p["border_strong"],
                    lightcolor=p["card"], darkcolor=p["card"], borderwidth=1,
                    relief="solid", padding=(14, 7), focusthickness=0, font=sans())
        s.map("Secondary.TButton",
              background=[("disabled", p["input"]), ("pressed", p["active"]),
                          ("active", p["hover"])],
              lightcolor=[("disabled", p["input"]), ("pressed", p["active"]),
                          ("active", p["hover"])],
              darkcolor=[("disabled", p["input"]), ("pressed", p["active"]),
                         ("active", p["hover"])],
              bordercolor=[("focus", p["ring"]), ("active", p["accent"])],
              foreground=[("disabled", p["muted"])])

        # 主操作: 实心主色, 每页只出现一个
        s.configure("Accent.TButton", background=p["accent"],
                    foreground=p["on_accent"], bordercolor=p["accent"],
                    lightcolor=p["accent"], darkcolor=p["accent"], borderwidth=1,
                    relief="solid", padding=(16, 8), focusthickness=0,
                    font=sans(bold=True))
        s.map("Accent.TButton",
              background=[("disabled", p["input"]),
                          ("pressed", p["accent_hover"]),
                          ("active", p["accent_hover"])],
              lightcolor=[("disabled", p["input"]),
                          ("pressed", p["accent_hover"]),
                          ("active", p["accent_hover"])],
              darkcolor=[("disabled", p["input"]),
                         ("pressed", p["accent_hover"]),
                         ("active", p["accent_hover"])],
              bordercolor=[("focus", p["ring"]),
                           ("disabled", p["input"]),
                           ("pressed", p["accent_hover"]),
                           ("active", p["accent_hover"])],
              foreground=[("disabled", p["muted"])])

        # 危险操作用描边而不是实心红: 两套模式下都不需要另配前景色
        s.configure("Danger.TButton", background=p["card"],
                    foreground=p["danger"], bordercolor=p["danger"],
                    lightcolor=p["card"], darkcolor=p["card"], borderwidth=1,
                    relief="solid", padding=(14, 7), focusthickness=0, font=sans())
        s.map("Danger.TButton",
              background=[("disabled", p["input"]), ("pressed", p["active"]),
                          ("active", p["hover"])],
              lightcolor=[("disabled", p["input"]), ("pressed", p["active"]),
                          ("active", p["hover"])],
              darkcolor=[("disabled", p["input"]), ("pressed", p["active"]),
                         ("active", p["hover"])],
              bordercolor=[("focus", p["ring"]), ("disabled", p["border"])],
              foreground=[("disabled", p["muted"])])

        # 视图控件: 缩略图档位与窗格开关。打开态只改底色与描边,
        # 字体与内边距与 Secondary.TButton 一致, 切换时按钮尺寸不会跳
        s.configure("SegmentOn.TButton", background=p["accent_weak"],
                    foreground=p["link"], bordercolor=p["accent"],
                    lightcolor=p["accent_weak"], darkcolor=p["accent_weak"],
                    borderwidth=1, relief="solid", padding=(14, 7),
                    focusthickness=0, font=sans())
        s.map("SegmentOn.TButton",
              background=[("pressed", p["active"]), ("active", p["hover"])],
              lightcolor=[("pressed", p["active"]), ("active", p["hover"])],
              darkcolor=[("pressed", p["active"]), ("active", p["hover"])],
              bordercolor=[("focus", p["ring"])],
              foreground=[("disabled", p["muted"])])

        # 侧栏底部的主题按钮
        s.configure("Chip.TButton", background=p["panel"], foreground=p["text"],
                    bordercolor=p["border"], lightcolor=p["panel"],
                    darkcolor=p["panel"], borderwidth=1, relief="solid",
                    anchor="w", padding=(12, 7), focusthickness=0, font=sans())
        s.map("Chip.TButton",
              background=[("pressed", p["active"]), ("active", p["hover"])],
              lightcolor=[("pressed", p["active"]), ("active", p["hover"])],
              darkcolor=[("pressed", p["active"]), ("active", p["hover"])],
              bordercolor=[("focus", p["ring"]), ("active", p["accent"])])

    def _style_checkbuttons(self, p):
        """勾选框。"""
        s = self.style
        s.configure("TCheckbutton", background=p["bg"], foreground=p["text"],
                    focuscolor=p["bg"], indicatorbackground=p["input"],
                    indicatorforeground=p["on_accent"], padding=(4, 2),
                    font=sans())
        s.map("TCheckbutton",
              background=[("active", p["hover"])],
              indicatorbackground=[("selected", p["accent"]),
                                   ("pressed", p["active"])],
              foreground=[("disabled", p["muted"])])
        s.configure("Card.TCheckbutton", background=p["card"],
                    foreground=p["text"], focuscolor=p["card"],
                    indicatorbackground=p["input"],
                    indicatorforeground=p["on_accent"], padding=(4, 2),
                    font=sans())
        s.map("Card.TCheckbutton",
              background=[("active", p["hover"])],
              indicatorbackground=[("selected", p["accent"]),
                                   ("pressed", p["active"])],
              foreground=[("disabled", p["muted"])])

    def _style_inputs(self, p):
        """输入框与下拉框。"""
        s = self.style
        s.configure("TEntry", fieldbackground=p["input"], foreground=p["text"],
                    insertcolor=p["text"], bordercolor=p["border_strong"],
                    lightcolor=p["border_strong"], darkcolor=p["border_strong"],
                    borderwidth=1, relief="flat", padding=(9, 6))
        s.map("TEntry",
              bordercolor=[("focus", p["accent"])],
              lightcolor=[("focus", p["accent"])],
              darkcolor=[("focus", p["accent"])])

        s.configure("TCombobox", fieldbackground=p["input"], background=p["input"],
                    foreground=p["text"], arrowcolor=p["muted"],
                    bordercolor=p["border_strong"], lightcolor=p["border_strong"],
                    darkcolor=p["border_strong"], padding=(9, 6), arrowsize=13,
                    font=sans())
        s.map("TCombobox",
              fieldbackground=[("readonly", p["input"])],
              background=[("readonly", p["input"]), ("active", p["hover"])],
              lightcolor=[("readonly", p["input"])],
              darkcolor=[("readonly", p["input"])],
              selectbackground=[("readonly", p["input"])],
              selectforeground=[("readonly", p["text"])],
              bordercolor=[("focus", p["accent"])],
              arrowcolor=[("active", p["text"])])

    def _style_treeviews(self, p):
        """树形列表: 选中态用主色的浅底配主色文字, 比整行实心更轻。"""
        s = self.style
        s.configure("Treeview", background=p["bg"], fieldbackground=p["bg"],
                    foreground=p["text"], bordercolor=p["border"], borderwidth=0,
                    relief="flat", rowheight=28, font=sans())
        s.map("Treeview",
              background=[("selected", p["accent_weak"])],
              foreground=[("selected", p["link"])])
        s.configure("Treeview.Heading", background=p["panel"],
                    foreground=p["muted"], bordercolor=p["border"],
                    borderwidth=0, relief="flat", padding=(10, 8),
                    font=sans(bold=True))
        s.map("Treeview.Heading",
              background=[("active", p["hover"]), ("pressed", p["active"])],
              foreground=[("active", p["text"])])

        # 卡片内的列表: 底色与卡片一致, 免得卡片里凹出一块另一种底色
        s.configure("Card.Treeview", background=p["card"],
                    fieldbackground=p["card"], foreground=p["text"],
                    bordercolor=p["border"], borderwidth=0, relief="flat",
                    rowheight=28, font=sans())
        s.map("Card.Treeview",
              background=[("selected", p["accent_weak"])],
              foreground=[("selected", p["link"])])

    def _style_scrollbars(self, p):
        """滚动条与进度条 进度用琥珀色, 和主色形成一冷一暖的层次。"""
        s = self.style
        for orient in ("Vertical", "Horizontal"):
            name = "%s.TScrollbar" % orient
            s.configure(name, background=p["scroll"], troughcolor=p["trough"],
                        bordercolor=p["trough"], lightcolor=p["scroll"],
                        darkcolor=p["scroll"], borderwidth=0, relief="flat",
                        arrowcolor=p["muted"], arrowsize=13)
            s.map(name, background=[("active", p["border_strong"])],
                  arrowcolor=[("active", p["text"])])
        s.configure("Horizontal.TProgressbar", background=p["accent_alt"],
                    troughcolor=p["input"], bordercolor=p["input"],
                    lightcolor=p["accent_alt"], darkcolor=p["accent_alt"],
                    borderwidth=0, thickness=6)

    def _style_labelframes(self, p):
        """分组卡片 TLabelframe。"""
        s = self.style
        s.configure("TLabelframe", background=p["card"],
                    bordercolor=p["border"], lightcolor=p["card"],
                    darkcolor=p["card"], borderwidth=1, relief="solid")
        s.configure("TLabelframe.Label", background=p["card"],
                    foreground=p["muted"], font=sans(bold=True))

    def _apply_option_db(self, p):
        """为之后创建的 tk 原生控件提供默认颜色。

        option database 只影响之后创建的控件, 因此每次切换都要重放一遍,
        否则新弹出的窗口会拿到上一套颜色。
        """
        root = self.root
        try:
            root.option_clear()
        except tk.TclError:
            return
        root.option_add("*background", p["bg"])
        root.option_add("*foreground", p["text"])
        root.option_add("*Font", self._default_font.name)
        root.option_add("*selectBackground", p["accent"])
        root.option_add("*selectForeground", p["on_accent"])
        root.option_add("*highlightBackground", p["border"])
        root.option_add("*highlightColor", p["accent"])
        root.option_add("*highlightThickness", 0)
        root.option_add("*Button.activeBackground", p["hover"])
        root.option_add("*Button.activeForeground", p["text"])
        root.option_add("*Menu.background", p["panel"])
        root.option_add("*Menu.foreground", p["text"])
        root.option_add("*Menu.activeBackground", p["hover"])
        root.option_add("*Menu.activeForeground", p["text"])
        root.option_add("*Menu.borderWidth", 0)
        root.option_add("*Text.background", p["preview"])
        root.option_add("*Text.foreground", p["text"])
        root.option_add("*Text.insertBackground", p["text"])
        root.option_add("*Text.selectBackground", p["accent"])
        root.option_add("*Text.selectForeground", p["on_accent"])
        root.option_add("*Listbox.background", p["input"])
        root.option_add("*Listbox.foreground", p["text"])
        root.option_add("*TCombobox*Listbox.background", p["input"])
        root.option_add("*TCombobox*Listbox.foreground", p["text"])
        root.option_add("*TCombobox*Listbox.selectBackground", p["accent"])
        root.option_add("*TCombobox*Listbox.selectForeground", p["on_accent"])
