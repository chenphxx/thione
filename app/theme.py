"""统一管理界面外观的配色令牌与 ttk 控件样式

界面按设计稿实现: 全部方角, 只用 1 像素描边与色块分层, 不出现渐变与圆角
配色令牌的名字与设计稿里的 CSS 变量一一对应 (canvas / side / panel / fill /
fill_hi / text / muted / hair / accent / on_accent / accent_soft / ok /
danger / warn), 便于与设计稿逐项对照

字号统一用像素值 (tkinter 里负数字号表示像素高度), 与设计稿的 px 一致

@brief 设计令牌, 字体与控件样式
"""

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

# ---------------- 字号 (像素) ----------------
SIZE_BRAND = 14
SIZE_TITLE = 15
SIZE_VALUE = 14
SIZE_BODY = 13
SIZE_LABEL = 12
SIZE_SECTION = 11
SIZE_EMPTY = 34

# ---------------- 尺寸 (像素) ----------------
SIDEBAR_WIDTH = 208
TOPBAR_HEIGHT = 62
STATUSBAR_HEIGHT = 32
PANEL_HEAD_HEIGHT = 34
CONTROL_HEIGHT = 30
BUTTON_HEIGHT = 30
MINI_BUTTON_HEIGHT = 26
TABLE_ROW_HEIGHT = 31
#: 表头高度: 24 像素文字行与下边距 + 1 像素分隔线
TABLE_HEAD_HEIGHT = 25
BODY_PAD_X = 20
BODY_PAD_TOP = 18
BODY_GAP = 12

# 字体族, 由 ThemeManager 启动时按系统可用字体改写
FONT_SANS = "Segoe UI"
FONT_MONO = "Consolas"
FONT_ICON = "Segoe MDL2 Assets"

#: 设计稿里用到的图标字形 (Segoe Fluent Icons / Segoe MDL2 Assets 同码位)
ICON_BRAND = "\uE950"
ICON_BACK = "\uE72B"
ICON_CHEVRON = "\uE70D"
ICON_SWAP = "\uE8AB"
ICON_CHECK = "\uE73E"
ICON_ARROW = "\uE72A"
ICON_BOX = "\u25A1"
ICON_PANE_DETAILS = "\uE7C4"
ICON_PANE_PREVIEW = "\uE773"
ICON_EMPTY = "\uE7C5"

# ---------------- 配色令牌 ----------------
PALETTE = {
    # 设计稿令牌
    "canvas": "#F3F5F8",
    "side": "#EBEEF3",
    "panel": "#FFFFFF",
    "fill": "#F5F6F8",
    "fill_hi": "#E4F1EF",
    "text": "#141A21",
    "muted": "#6B7482",
    "hair": "#E5E8EC",
    "accent": "#0E8C7F",
    "on_accent": "#FFFFFF",
    "accent_soft": "#E4F3F1",
    "icon": "#6B7482",
    "ok": "#0F7A54",
    "danger": "#B92B2E",
    "warn": "#B45309",
    "ph1": "#D8DFE9",
    "ph2": "#AAB8CA",
    "back": "#DFE2E8",
    # 派生令牌: 设计稿没有直接给出, 但控件需要
    "disabled": "#F5F6F8",
    "disabled_text": "#A9B0BB",
    "thumb_edge": "#EFF1F4",
    "placeholder": (216, 223, 233),
    "mode": "light",
    "mode_name": "浅色",
    "is_dark": False,
}

DARK_PALETTE = {
    "canvas": "#0F1216",
    "side": "#14171C",
    "panel": "#161A20",
    "fill": "#1B2129",
    "fill_hi": "#1E2A33",
    "text": "#E8ECF2",
    "muted": "#8A94A4",
    "hair": "#242A33",
    "accent": "#2DD4BF",
    "on_accent": "#06231F",
    "accent_soft": "#12312E",
    "icon": "#8A94A4",
    "ok": "#34D399",
    "danger": "#F87171",
    "warn": "#F59E0B",
    "ph1": "#2A323D",
    "ph2": "#1E242D",
    "back": "#0A0C0F",
    "disabled": "#1B2129",
    "disabled_text": "#5C6472",
    "thumb_edge": "#20262E",
    "placeholder": (42, 50, 61),
    "mode": "dark",
    "mode_name": "深色",
    "is_dark": True,
}

PALETTES = {"light": PALETTE, "dark": DARK_PALETTE}

#: 控件属性 -> 令牌名, 供部件在主题切换时重绘色彩
ROLE_ATTRS = {
    "bg": "background",
    "fg": "foreground",
    "hl": "highlightbackground",
    "hlc": "highlightcolor",
    "insert": "insertbackground",
    "sel_bg": "selectbackground",
    "sel_fg": "selectforeground",
    "act_bg": "activebackground",
    "act_fg": "activeforeground",
    "trough": "troughcolor",
}


def color(value):
    """把令牌值换算成 Tk 认识的颜色字符串

    @param value: 颜色字符串或者 (r, g, b) 三元组
    @return: #RRGGBB 形式的颜色
    """
    if isinstance(value, tuple):
        return "#%02X%02X%02X" % value
    return value


def sans(size=SIZE_BODY, bold=False, italic=False):
    """返回界面统一使用的无衬线字体配置

    @param size: 字号 (像素)
    @param bold: 是否使用粗体
    @param italic: 是否使用斜体
    @return: Tk 字体元组
    """
    return (FONT_SANS, -size, "bold" if bold else "normal",
            "italic" if italic else "roman")


def mono(size=SIZE_BODY, bold=False):
    """返回界面统一使用的等宽字体配置

    @param size: 字号 (像素)
    @param bold: 是否使用粗体
    @return: Tk 字体元组
    """
    return (FONT_MONO, -size, "bold" if bold else "normal")


def icon(size=SIZE_BODY, bold=False):
    """返回图标字形使用的字体配置

    @param size: 字号 (像素)
    @param bold: 是否使用粗体
    @return: Tk 字体元组
    """
    return (FONT_ICON, -size, "bold" if bold else "normal")


def tint(widget, **roles):
    """登记控件的配色角色, 主题切换时由 ThemeManager 重绘

    @param widget: 需要跟随主题的控件
    @param roles: 角色名与令牌名, 例如 bg="panel", fg="muted"
    @return: 传入的控件, 便于链式书写
    """
    widget._thione_roles = roles
    return widget


class ThemeManager:
    """管理浅色与深色配色, 并同步更新 ttk 与 Tk 原生控件"""

    def __init__(self, root, mode="light"):
        self.root = root
        self.style = ttk.Style(root)
        self.style.theme_use("clam")
        self.mode = mode if mode in PALETTES else "light"
        self.palette = dict(PALETTES[self.mode])
        self._windows = [root]
        self._configure_fonts(root)
        self._apply_styles()
        root.configure(bg=self.palette["canvas"])
        self._default_font = tkfont.Font(
            root=root, family=FONT_SANS, size=-SIZE_BODY
        )
        self._apply_native_defaults()

    # ---------------- 资源解析 ----------------
    @staticmethod
    def _configure_fonts(root):
        """按系统可用字体解析字体族

        @param root: Tk 根窗口
        """
        global FONT_SANS, FONT_MONO, FONT_ICON
        try:
            available = set(tkfont.families(root))
        except tk.TclError:
            return
        FONT_SANS = next(
            (name for name in ("Segoe UI Variable Text", "Segoe UI",
                               "Microsoft YaHei UI", "Tahoma")
             if name in available),
            "TkDefaultFont",
        )
        FONT_MONO = next(
            (name for name in ("Cascadia Mono", "Cascadia Code", "Consolas",
                               "Courier New")
             if name in available),
            "TkFixedFont",
        )
        FONT_ICON = next(
            (name for name in ("Segoe Fluent Icons", "Segoe MDL2 Assets",
                               "Segoe UI Symbol")
             if name in available),
            "TkDefaultFont",
        )

    def rgb(self, token):
        """取令牌对应的颜色字符串

        @param token: 令牌名, 也可以直接是颜色字符串
        @return: #RRGGBB 形式的颜色
        """
        return color(self.palette.get(token, token))

    # ---------------- ttk 样式 ----------------
    def _apply_styles(self):
        s = self.style
        p = self.palette
        s.configure(".", font=sans(), foreground=p["text"], background=p["canvas"])

        # 表面
        s.configure("TFrame", background=p["canvas"])
        s.configure("Canvas.TFrame", background=p["canvas"])
        s.configure("Side.TFrame", background=p["side"])
        s.configure("Status.TFrame", background=p["side"])
        s.configure("Fill.TFrame", background=p["fill"])
        s.configure("Nav.TFrame", background=p["side"])
        s.configure("NavOn.TFrame", background=p["fill_hi"])
        s.configure("NavHover.TFrame", background=p["fill"])
        # 面板: 1 像素描边 + 面板底色
        s.configure("Panel.TFrame", background=p["panel"], borderwidth=1,
                    relief="solid", bordercolor=p["hair"])
        s.configure("PlainPanel.TFrame", background=p["panel"])
        # 控件框: 1 像素描边 + fill 底色
        s.configure("Field.TFrame", background=p["fill"], borderwidth=1,
                    relief="solid", bordercolor=p["hair"])
        s.configure("PlainField.TFrame", background=p["fill"])
        s.configure("Hair.TFrame", background=p["hair"])
        s.configure("Accent.TFrame", background=p["accent"])
        s.configure("Dot.TFrame", background=p["muted"])
        # 侧栏与内容区之间的拖拽分隔条: 平时与页面同色, 指针进入时用强调色
        s.configure("Drag.TFrame", background=p["canvas"])
        s.configure("DragHover.TFrame", background=p["accent"])
        s.configure("TPanedwindow", background=p["canvas"], sashwidth=0,
                    sashrelief="flat")
        s.configure("TSeparator", background=p["hair"])

        # 文字
        s.configure("TLabel", background=p["canvas"], foreground=p["text"],
                    font=sans())
        s.configure("Muted.TLabel", background=p["canvas"],
                    foreground=p["muted"], font=sans(SIZE_LABEL))
        s.configure("Head.TLabel", background=p["canvas"],
                    foreground=p["text"], font=sans(SIZE_TITLE, True))
        s.configure("Sub.TLabel", background=p["canvas"],
                    foreground=p["muted"], font=sans(SIZE_LABEL))
        s.configure("Brand.TLabel", background=p["side"], foreground=p["text"],
                    font=sans(SIZE_BRAND, True))
        s.configure("Foot.TLabel", background=p["side"],
                    foreground=p["muted"], font=sans(SIZE_LABEL))
        s.configure("Version.TLabel", background=p["side"],
                    foreground=p["muted"], font=mono(SIZE_LABEL))
        s.configure("Status.TLabel", background=p["side"],
                    foreground=p["muted"], font=sans(SIZE_LABEL))
        s.configure("Metric.TLabel", background=p["side"],
                    foreground=p["text"], font=mono(SIZE_LABEL))
        s.configure("Panel.TLabel", background=p["panel"],
                    foreground=p["text"], font=sans())
        s.configure("PanelMuted.TLabel", background=p["panel"],
                    foreground=p["muted"], font=sans(SIZE_LABEL))
        s.configure("PanelHint.TLabel", background=p["panel"],
                    foreground=p["muted"], font=sans(SIZE_LABEL))
        s.configure("PanelError.TLabel", background=p["panel"],
                    foreground=p["danger"], font=sans(SIZE_LABEL))
        s.configure("PanelHeader.TLabel", background=p["panel"],
                    foreground=p["text"], font=sans(SIZE_TITLE, True))
        s.configure("Section.TLabel", background=p["panel"],
                    foreground=p["muted"], font=sans(SIZE_SECTION, True))
        s.configure("Value.TLabel", background=p["panel"],
                    foreground=p["text"], font=sans(SIZE_VALUE))
        s.configure("Mono.TLabel", background=p["panel"],
                    foreground=p["text"], font=mono())
        s.configure("MonoMuted.TLabel", background=p["panel"],
                    foreground=p["muted"], font=mono())
        s.configure("Ok.TLabel", background=p["panel"], foreground=p["ok"],
                    font=sans())
        s.configure("Run.TLabel", background=p["panel"],
                    foreground=p["accent"], font=sans())
        s.configure("Fail.TLabel", background=p["panel"],
                    foreground=p["danger"], font=sans())
        s.configure("Idle.TLabel", background=p["panel"],
                    foreground=p["muted"], font=sans())
        s.configure("CardTitle.TLabel", background=p["panel"],
                    foreground=p["text"], font=sans(SIZE_TITLE, True))
        s.configure("EmptyIcon.TLabel", background=p["panel"],
                    foreground=p["accent"], font=icon(SIZE_EMPTY))
        s.configure("EmptyTitle.TLabel", background=p["panel"],
                    foreground=p["text"], font=sans(SIZE_VALUE, True))

        # 按钮: 一律 30 像素高, 方角, 无边框
        s.configure("TButton", padding=(13, 6), relief="flat", borderwidth=0,
                    background=p["fill"], foreground=p["text"], font=sans(),
                    focuscolor=p["fill"])
        s.map("TButton",
              background=[("disabled", p["disabled"]),
                          ("pressed", p["fill_hi"]),
                          ("active", p["fill_hi"])],
              foreground=[("disabled", p["disabled_text"])])
        s.configure("Primary.TButton", padding=(13, 6), relief="flat",
                    borderwidth=0, background=p["accent"],
                    foreground=p["on_accent"], font=sans(SIZE_BODY, True),
                    focuscolor=p["accent"])
        s.map("Primary.TButton",
              background=[("disabled", p["disabled"]),
                          ("pressed", p["accent"]),
                          ("active", p["accent"])],
              foreground=[("disabled", p["disabled_text"])])
        s.configure("Ghost.TButton", padding=(9, 6), relief="flat",
                    borderwidth=0, background=p["side"],
                    foreground=p["muted"], font=sans(),
                    focuscolor=p["side"])
        s.map("Ghost.TButton",
              background=[("pressed", p["fill"]), ("active", p["fill"])],
              foreground=[("active", p["text"])])
        # 危险按钮: 透明底 + 1 像素描边, 与设计稿一致
        s.configure("Danger.TButton", padding=(12, 4), relief="solid",
                    borderwidth=1, bordercolor=p["hair"],
                    background=p["side"], foreground=p["danger"],
                    font=sans(), focuscolor=p["side"])
        s.map("Danger.TButton",
              background=[("pressed", p["fill"]), ("active", p["fill"])])
        # 面板上的危险按钮: 透明底 + 1 像素描边
        s.configure("PanelDanger.TButton", padding=(12, 4), relief="solid",
                    borderwidth=1, bordercolor=p["hair"],
                    background=p["panel"], foreground=p["danger"],
                    font=sans(), focuscolor=p["panel"])
        s.map("PanelDanger.TButton",
              background=[("pressed", p["fill"]), ("active", p["fill"])])
        s.configure("Mini.TButton", padding=(9, 4), relief="flat",
                    borderwidth=0, background=p["fill"],
                    foreground=p["muted"], font=sans(SIZE_LABEL),
                    focuscolor=p["fill"])
        s.map("Mini.TButton",
              background=[("pressed", p["fill_hi"]), ("active", p["fill_hi"])],
              foreground=[("active", p["text"])])
        s.configure("MiniOn.TButton", padding=(9, 4), relief="flat",
                    borderwidth=0, background=p["fill_hi"],
                    foreground=p["accent"], font=sans(SIZE_LABEL, True),
                    focuscolor=p["fill_hi"])
        s.map("MiniOn.TButton", background=[("active", p["fill_hi"])])
        s.configure("MiniIcon.TButton", padding=(5, 3), relief="flat",
                    borderwidth=0, background=p["fill"],
                    foreground=p["muted"], font=icon(SIZE_LABEL + 1),
                    focuscolor=p["fill"])
        s.map("MiniIcon.TButton",
              background=[("pressed", p["fill_hi"]), ("active", p["fill_hi"])])
        s.configure("MiniIconOn.TButton", padding=(5, 3), relief="flat",
                    borderwidth=0, background=p["fill_hi"],
                    foreground=p["accent"], font=icon(SIZE_LABEL + 1),
                    focuscolor=p["fill_hi"])
        s.map("MiniIconOn.TButton", background=[("active", p["fill_hi"])])
        s.configure("MiniIcon.TButton", padding=(5, 3), relief="flat",
                    borderwidth=0, background=p["fill"],
                    foreground=p["muted"], font=icon(SIZE_LABEL + 1),
                    focuscolor=p["fill"])
        s.map("MiniIcon.TButton",
              background=[("pressed", p["fill_hi"]), ("active", p["fill_hi"])])

        # 输入
        s.configure("TEntry", fieldbackground=p["fill"], foreground=p["text"],
                    insertcolor=p["text"], padding=(9, 6), borderwidth=1,
                    relief="solid", bordercolor=p["hair"],
                    lightcolor=p["hair"], darkcolor=p["hair"])
        s.map("TEntry", bordercolor=[("focus", p["accent"])],
              lightcolor=[("focus", p["accent"])],
              darkcolor=[("focus", p["accent"])])
        s.configure("TCombobox", fieldbackground=p["fill"],
                    background=p["fill"], foreground=p["text"], padding=(9, 6),
                    arrowcolor=p["muted"], bordercolor=p["hair"],
                    lightcolor=p["hair"], darkcolor=p["hair"],
                    selectbackground=p["fill"], selectforeground=p["text"])
        s.map("TCombobox",
              fieldbackground=[("readonly", p["fill"])],
              selectbackground=[("readonly", p["fill"])],
              selectforeground=[("readonly", p["text"])])
        s.configure("TCheckbutton", background=p["panel"], foreground=p["text"],
                    font=sans(), focuscolor=p["panel"], padding=(2, 2))
        s.map("TCheckbutton", background=[("active", p["panel"])],
              indicatorcolor=[("selected", p["accent"]),
                              ("!selected", p["fill"])])

        # 表格与滚动条
        s.configure("Treeview", background=p["panel"], fieldbackground=p["panel"],
                    foreground=p["text"], rowheight=TABLE_ROW_HEIGHT,
                    borderwidth=0, font=sans())
        s.map("Treeview", background=[("selected", p["fill_hi"])],
              foreground=[("selected", p["text"])])
        s.configure("Treeview.Heading", background=p["panel"],
                    foreground=p["muted"], relief="flat", borderwidth=0,
                    padding=(12, 8), font=sans(SIZE_SECTION, True))
        s.map("Treeview.Heading", background=[("active", p["panel"])])
        s.configure("Vertical.TScrollbar", background=p["muted"],
                    troughcolor=p["panel"], bordercolor=p["panel"],
                    arrowcolor=p["muted"], relief="flat", width=10,
                    arrowsize=0)
        s.configure("Horizontal.TScrollbar", background=p["muted"],
                    troughcolor=p["panel"], bordercolor=p["panel"],
                    arrowcolor=p["muted"], relief="flat", width=10,
                    arrowsize=0)
        s.configure("Thin.Vertical.TScrollbar", background=p["muted"],
                    troughcolor=p["fill"], bordercolor=p["fill"],
                    arrowcolor=p["fill"], relief="flat", width=8,
                    arrowsize=0)
        s.configure("Track.Horizontal.TProgressbar", background=p["accent"],
                    troughcolor=p["fill_hi"], bordercolor=p["fill_hi"],
                    lightcolor=p["accent"], darkcolor=p["accent"],
                    relief="flat", thickness=4)
        s.configure("TLabelframe", background=p["panel"],
                    bordercolor=p["hair"], relief="solid")
        s.configure("TLabelframe.Label", background=p["panel"],
                    foreground=p["muted"], font=sans(SIZE_SECTION, True))

        # 兼容旧样式名: 对话框与沿用旧命名的调用点仍然按设计稿的配色渲染
        s.configure("Accent.TButton", padding=(13, 6), relief="flat",
                    borderwidth=0, background=p["accent"],
                    foreground=p["on_accent"], font=sans(SIZE_BODY, True))
        s.map("Accent.TButton",
              background=[("disabled", p["disabled"]),
                          ("pressed", p["accent"]), ("active", p["accent"])],
              foreground=[("disabled", p["disabled_text"])])
        s.configure("Secondary.TButton", padding=(13, 6), relief="flat",
                    borderwidth=0, background=p["fill"],
                    foreground=p["text"], font=sans())
        s.map("Secondary.TButton",
              background=[("disabled", p["disabled"]),
                          ("pressed", p["fill_hi"]), ("active", p["fill_hi"])])
        s.configure("Segment.TButton", padding=(12, 5), relief="flat",
                    borderwidth=0, background=p["panel"],
                    foreground=p["muted"], font=sans())
        s.map("Segment.TButton",
              background=[("pressed", p["fill"]), ("active", p["fill"])])
        s.configure("SegmentOn.TButton", padding=(12, 5), relief="flat",
                    borderwidth=0, background=p["accent_soft"],
                    foreground=p["accent"], font=sans(SIZE_BODY, True))
        s.map("SegmentOn.TButton", background=[("active", p["accent_soft"])])
        for name in ("Card.TCheckbutton", "Panel.TRadiobutton",
                     "Card.TRadiobutton"):
            s.configure(name, background=p["panel"], foreground=p["text"])

    def _apply_native_defaults(self):
        """设置 Tk 原生控件的默认配色 (菜单 输入框 弹出列表等)"""
        p = self.palette
        self.root.configure(bg=p["canvas"])
        self.root.option_add("*Font", self._default_font)
        self.root.option_add("*background", p["canvas"])
        self.root.option_add("*foreground", p["text"])
        self.root.option_add("*insertBackground", p["text"])
        self.root.option_add("*selectBackground", p["accent"])
        self.root.option_add("*selectForeground", p["on_accent"])
        self.root.option_add("*highlightBackground", p["hair"])
        self.root.option_add("*highlightColor", p["accent"])
        self.root.option_add("*Menu.background", p["panel"])
        self.root.option_add("*Menu.foreground", p["text"])
        self.root.option_add("*Menu.activeBackground", p["fill"])
        self.root.option_add("*Menu.activeForeground", p["text"])
        self.root.option_add("*Menu.borderWidth", 0)
        self.root.option_add("*Listbox.background", p["panel"])
        self.root.option_add("*Listbox.foreground", p["text"])
        self.root.option_add("*Listbox.selectBackground", p["fill_hi"])
        self.root.option_add("*Listbox.selectForeground", p["text"])
        self.root.option_add("*TCombobox*Listbox.background", p["panel"])
        self.root.option_add("*TCombobox*Listbox.foreground", p["text"])
        self.root.option_add("*TCombobox*Listbox.selectBackground", p["fill_hi"])
        self.root.option_add("*TCombobox*Listbox.selectForeground", p["text"])

    # ---------------- 主题切换 ----------------
    def set_mode(self, mode):
        """切换界面配色并刷新所有已登记窗口

        @param mode: 配色名称, 支持 light 和 dark
        @return: 配色发生变化时返回 True, 否则返回 False
        """
        if mode not in PALETTES or mode == self.mode:
            return False
        self.mode = mode
        self.palette = dict(PALETTES[mode])
        self._apply_styles()
        self._apply_native_defaults()
        for window in tuple(self._windows):
            try:
                if not window.winfo_exists():
                    self._windows.remove(window)
                    continue
            except tk.TclError:
                self._windows.remove(window)
                continue
            self._walk(window)
            if window is self.root:
                continue
            callback = getattr(window, "on_theme_changed", None)
            if callback is not None:
                try:
                    callback()
                except tk.TclError:
                    self._windows.remove(window)
        return True

    def register(self, window):
        """登记顶层窗口, 以便应用统一外观

        @param window: 顶层窗口
        """
        if window not in self._windows:
            self._windows.append(window)

    def apply_theme(self, window):
        """使用当前配色刷新窗口中的 Tk 原生表面

        @param window: 需要刷新的窗口或容器
        """
        self.register(window)
        self._walk(window)

    def _walk(self, widget):
        """递归刷新控件配色

        @param widget: 子树根控件
        """
        self._paint(widget)
        try:
            children = widget.winfo_children()
        except tk.TclError:
            return
        for child in children:
            self._walk(child)

    def _paint(self, widget):
        """按登记的角色重绘单个控件

        @param widget: 目标控件
        """
        roles = getattr(widget, "_thione_roles", None)
        default = getattr(widget, "_thione_surface", None)
        if not roles and default is not None:
            roles = {"bg": default}
        if not roles:
            roles = self._default_roles(widget)
        for role, attr in ROLE_ATTRS.items():
            if role not in roles:
                continue
            try:
                widget.configure(**{attr: self.rgb(roles[role])})
            except tk.TclError:
                pass
        callback = getattr(widget, "_thione_apply", None)
        if callback is not None:
            try:
                callback(self.palette)
            except tk.TclError:
                pass

    @staticmethod
    def _default_roles(widget):
        """没有登记角色时的兜底配色, 覆盖原生 Tk 控件

        @param widget: 目标控件
        @return: 角色字典
        """
        if isinstance(widget, (tk.Toplevel, tk.Canvas, tk.Text, tk.Listbox)):
            return {"bg": "canvas"}
        if isinstance(widget, tk.Menu):
            return {"bg": "panel", "fg": "text", "act_bg": "fill",
                    "act_fg": "text"}
        return {}
