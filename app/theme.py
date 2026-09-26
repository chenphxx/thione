"""统一管理 Tk 界面的浅色外观。"""

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

FONT_SIZE = 10
FONT_SANS = "Segoe UI"
FONT_MONO = "Consolas"

PALETTE = {
    "bg": "#F4F6FA",
    "panel": "#FFFFFF",
    "card": "#FFFFFF",
    "input": "#FFFFFF",
    "disabled": "#F2F4F7",
    "disabled_text": "#98A2B3",
    "hover": "#F2F5FB",
    "active": "#E9EEF8",
    "selected": "#EAF0FF",
    "border": "#E3E8F0",
    "border_strong": "#CDD5E1",
    "text": "#202939",
    "muted": "#667085",
    "header": "#172033",
    "accent": "#5269E8",
    "accent_hover": "#4359D4",
    "accent_pressed": "#3549BA",
    "accent_weak": "#EAF0FF",
    "accent_soft_hover": "#DDE6FF",
    "secondary": "#5269E8",
    "accent_alt": "#D97706",
    "on_accent": "#FFFFFF",
    "link": "#4359D4",
    "ring": "#5269E8",
    "ok": "#16805D",
    "warn": "#B54708",
    "success": "#16805D",
    "danger": "#C43235",
    "danger_weak": "#FDF0F0",
    "danger_weak_pressed": "#F8DEDE",
    "danger_hover": "#A6292C",
    "scroll": "#AAB4C3",
    "trough": "#EDF0F5",
    "preview": "#F8FAFC",
    "placeholder": (229, 233, 240),
    "radius": 8,
    "mode": "light",
    "mode_name": "浅色",
    "is_dark": False,
}

DARK_PALETTE = {
    "bg": "#181C23",
    "panel": "#20252E",
    "card": "#252B35",
    "input": "#1C2129",
    "disabled": "#2A303A",
    "disabled_text": "#828C9D",
    "hover": "#2D3440",
    "active": "#394252",
    "selected": "#303C5B",
    "border": "#3A4351",
    "border_strong": "#4B5769",
    "text": "#E5E9F0",
    "muted": "#A0AABA",
    "header": "#F1F4F8",
    "accent": "#7185FF",
    "accent_hover": "#8394FF",
    "accent_pressed": "#5D70E6",
    "accent_weak": "#303B5C",
    "accent_soft_hover": "#39466B",
    "secondary": "#7185FF",
    "accent_alt": "#F0A34A",
    "on_accent": "#FFFFFF",
    "link": "#AAB8FF",
    "ring": "#8294FF",
    "ok": "#4CC39A",
    "warn": "#F3B35B",
    "success": "#4CC39A",
    "danger": "#F27878",
    "danger_weak": "#462B32",
    "danger_weak_pressed": "#59343D",
    "danger_hover": "#FF9696",
    "scroll": "#596579",
    "trough": "#2B323E",
    "preview": "#1C2129",
    "placeholder": (55, 64, 79),
    "radius": 8,
    "mode": "dark",
    "mode_name": "深色",
    "is_dark": True,
}

PALETTES = {"light": PALETTE, "dark": DARK_PALETTE}


def sans(size=FONT_SIZE, bold=False, italic=False):
    """返回界面统一使用的无衬线字体配置。"""
    return (FONT_SANS, size, "bold" if bold else "normal", "italic" if italic else "roman")


def mono(size=FONT_SIZE, bold=False):
    """返回界面统一使用的等宽字体配置。"""
    return (FONT_MONO, size, "bold" if bold else "normal")


class ThemeManager:
    """管理浅色与深色配色, 并同步更新 ttk 和 Tk 原生控件。"""

    def __init__(self, root, mode="light"):
        self.root = root
        self.style = ttk.Style(root)
        self.style.theme_use("clam")
        self.mode = mode if mode in PALETTES else "light"
        self.palette = dict(PALETTES[self.mode])
        self._windows = [root]
        self._configure_fonts(root)
        self._apply_styles()
        root.configure(bg=self.palette["bg"])
        self._default_font = tkfont.Font(
            root=root, family=FONT_SANS, size=FONT_SIZE
        )
        self._apply_native_defaults()

    @staticmethod
    def _configure_fonts(root):
        global FONT_SANS, FONT_MONO
        try:
            available = set(tkfont.families(root))
        except tk.TclError:
            return
        FONT_SANS = next(
            (name for name in ("Segoe UI Variable Text", "Segoe UI", "Microsoft YaHei UI", "Tahoma")
             if name in available),
            "TkDefaultFont",
        )
        FONT_MONO = next(
            (name for name in ("Cascadia Code", "Cascadia Mono", "Consolas", "Courier New")
             if name in available),
            "TkFixedFont",
        )

    def _apply_styles(self):
        s = self.style
        p = self.palette
        s.configure(".", font=sans(), foreground=p["text"], background=p["bg"])
        s.configure("TFrame", background=p["bg"])
        s.configure("Panel.TFrame", background=p["panel"])
        s.configure("Card.TFrame", background=p["card"], borderwidth=1,
                     relief="solid", bordercolor=p["border"])
        # 卡片内部的普通容器: 与卡片同底但不额外画边框
        s.configure("CardFlat.TFrame", background=p["card"], borderwidth=0,
                     relief="flat")
        s.configure("Divider.TFrame", background=p["border"])
        s.configure("Drag.TFrame", background=p["bg"])
        s.configure("DragHover.TFrame", background=p["accent"])
        s.configure("TPanedwindow", background=p["bg"], sashwidth=5,
                     sashrelief="flat")
        s.configure("TSeparator", background=p["border"])

        for name, surface in (("TLabel", "bg"), ("Panel.TLabel", "panel"),
                              ("Card.TLabel", "card")):
            s.configure(name, background=p[surface], foreground=p["text"],
                        font=sans())
        for name, surface in (("Muted.TLabel", "bg"),
                              ("PanelMuted.TLabel", "panel"),
                              ("CardMuted.TLabel", "card"),
                              ("PanelHint.TLabel", "panel"),
                              ("EmptyHint.TLabel", "card"),
                              ("SidebarMuted.TLabel", "panel")):
            s.configure(name, background=p[surface], foreground=p["muted"],
                        font=sans(9))
        # 输入不合法等需要提醒用户的说明文字
        s.configure("CardError.TLabel", background=p["card"],
                    foreground=p["danger"], font=sans())
        s.configure("Header.TLabel", background=p["bg"], foreground=p["header"],
                    font=sans(20, True))
        s.configure("PanelHeader.TLabel", background=p["panel"],
                    foreground=p["header"], font=sans(16, True))
        s.configure("CardTitle.TLabel", background=p["card"],
                    foreground=p["header"], font=sans(12, True))
        s.configure("EmptyIcon.TLabel", background=p["card"],
                    foreground=p["accent"], font=sans(28))
        s.configure("EmptyTitle.TLabel", background=p["card"],
                    foreground=p["header"], font=sans(14, True))
        s.configure("Brand.TLabel", background=p["panel"],
                    foreground=p["header"], font=sans(19, True))
        s.configure("NavSection.TLabel", background=p["panel"],
                    foreground=p["muted"], font=sans(9, True))

        s.configure("TButton", padding=(12, 8), relief="solid", borderwidth=1,
                    background=p["panel"], foreground=p["text"],
                    bordercolor=p["border"], focuscolor=p["accent"])
        s.map("TButton", background=[("disabled", p["disabled"]),
                                     ("pressed", p["active"]),
                                     ("active", p["hover"])],
              foreground=[("disabled", p["disabled_text"])])
        s.configure("Secondary.TButton", padding=(12, 8), relief="solid",
                    borderwidth=1, background=p["panel"], foreground=p["text"],
                    bordercolor=p["border"])
        s.map("Secondary.TButton", background=[("disabled", p["disabled"]),
                                                ("pressed", p["active"]),
                                                ("active", p["hover"])])
        s.configure("Accent.TButton", padding=(14, 8), relief="solid",
                    borderwidth=1, background=p["accent"], foreground=p["on_accent"],
                    bordercolor=p["accent_hover"],
                    font=sans(10, True))
        s.map("Accent.TButton", background=[("disabled", p["disabled"]),
                                             ("pressed", p["accent_pressed"]),
                                             ("active", p["accent_hover"])],
              foreground=[("disabled", p["disabled_text"])])
        s.configure("Danger.TButton", padding=(12, 8), relief="solid",
                    borderwidth=1, background=p["panel"], foreground=p["danger"],
                    bordercolor=p["border"])
        s.map("Danger.TButton", background=[("pressed", p["danger_weak_pressed"]),
                                             ("active", p["danger_weak"])])
        s.configure("Chip.TButton", padding=(10, 7), relief="solid",
                    borderwidth=1, bordercolor=p["border"],
                    background=p["hover"], foreground=p["muted"])
        s.configure("Segment.TButton", padding=(10, 6), relief="solid",
                    borderwidth=1, bordercolor=p["border"],
                    background=p["panel"], foreground=p["muted"])
        s.map("Segment.TButton", background=[("active", p["hover"])])
        s.configure("SegmentOn.TButton", padding=(10, 6), relief="solid",
                    borderwidth=1, bordercolor=p["accent"],
                    background=p["accent_weak"], foreground=p["link"],
                    font=sans(9, True))
        s.configure("Nav.TButton", anchor="w", padding=(14, 11), relief="solid",
                    borderwidth=1, bordercolor=p["border"],
                    background=p["panel"], foreground=p["muted"], font=sans(11))
        s.map("Nav.TButton", background=[("active", p["hover"])],
              foreground=[("active", p["text"])])
        s.configure("NavSelected.TButton", anchor="w", padding=(14, 11),
                    relief="solid", borderwidth=1, bordercolor=p["accent"],
                    background=p["accent_weak"],
                    foreground=p["link"], font=sans(11, True))
        s.configure("TCheckbutton", background=p["bg"], foreground=p["text"],
                    padding=(4, 3))
        s.configure("Card.TCheckbutton", background=p["card"],
                    foreground=p["text"], padding=(4, 3))
        s.configure("Card.TRadiobutton", background=p["card"],
                    foreground=p["text"], padding=(6, 4))

        s.configure("TEntry", fieldbackground=p["input"], foreground=p["text"],
                    insertcolor=p["text"], padding=(8, 7), bordercolor=p["border"],
                    lightcolor=p["border"], darkcolor=p["border"])
        s.map("TEntry", bordercolor=[("focus", p["accent"])],
              lightcolor=[("focus", p["accent"])],
              darkcolor=[("focus", p["accent"])])
        s.configure("TCombobox", fieldbackground=p["input"],
                    background=p["panel"], foreground=p["text"], padding=(8, 6),
                    arrowcolor=p["muted"], bordercolor=p["border"])
        s.map("TCombobox", fieldbackground=[("readonly", p["input"])],
              selectbackground=[("readonly", p["selected"])],
              selectforeground=[("readonly", p["text"])])
        s.configure("Treeview", background=p["panel"], fieldbackground=p["panel"],
                    foreground=p["text"], rowheight=32, borderwidth=0,
                    font=sans(10))
        s.map("Treeview", background=[("selected", p["accent_weak"])],
              foreground=[("selected", p["text"])])
        s.configure("Treeview.Heading", background=p["bg"],
                    foreground=p["muted"], relief="flat", padding=(10, 8),
                    font=sans(9, True))
        s.map("Treeview.Heading", background=[("active", p["hover"])])
        s.configure("Card.Treeview", background=p["card"],
                    fieldbackground=p["card"], foreground=p["text"],
                    rowheight=30, borderwidth=0, font=sans(10))
        s.map("Card.Treeview", background=[("selected", p["accent_weak"])],
              foreground=[("selected", p["text"])])
        s.configure("Vertical.TScrollbar", background=p["scroll"],
                    troughcolor=p["trough"], bordercolor=p["trough"],
                    arrowcolor=p["muted"], relief="flat", width=10)
        s.configure("Horizontal.TScrollbar", background=p["scroll"],
                    troughcolor=p["trough"], bordercolor=p["trough"],
                    arrowcolor=p["muted"], relief="flat", width=10)
        s.configure("Horizontal.TProgressbar", background=p["accent"],
                    troughcolor=p["trough"], bordercolor=p["trough"],
                    thickness=8)
        s.configure("Vertical.TProgressbar", background=p["accent"],
                    troughcolor=p["trough"], bordercolor=p["trough"],
                    thickness=8)
        s.configure("TLabelframe", background=p["card"],
                    bordercolor=p["border"], relief="solid")
        s.configure("TLabelframe.Label", background=p["card"],
                    foreground=p["muted"], font=sans(9, True))

    def _apply_native_defaults(self):
        p = self.palette
        self.root.configure(bg=p["bg"])
        self.root.option_add("*Font", self._default_font)
        self.root.option_add("*background", p["bg"])
        self.root.option_add("*foreground", p["text"])
        self.root.option_add("*insertBackground", p["text"])
        self.root.option_add("*selectBackground", p["accent"])
        self.root.option_add("*selectForeground", p["on_accent"])
        self.root.option_add("*highlightBackground", p["border"])
        self.root.option_add("*highlightColor", p["accent"])
        self.root.option_add("*Menu.activeBackground", p["hover"])
        self.root.option_add("*Menu.activeForeground", p["text"])
        self.root.option_add("*Listbox.background", p["input"])
        self.root.option_add("*Listbox.foreground", p["text"])
        self.root.option_add("*Listbox.selectBackground", p["accent_weak"])
        self.root.option_add("*Listbox.selectForeground", p["text"])
        self.root.option_add("*TCombobox*Listbox.background", p["input"])
        self.root.option_add("*TCombobox*Listbox.foreground", p["text"])
        self.root.option_add("*TCombobox*Listbox.selectBackground",
                             p["accent_weak"])
        self.root.option_add("*TCombobox*Listbox.selectForeground", p["text"])

    def set_mode(self, mode):
        """切换界面配色并刷新所有已登记窗口。

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
        """登记顶层窗口, 以便应用统一外观。"""
        if window not in self._windows:
            self._windows.append(window)

    def apply_theme(self, window):
        """使用当前配色刷新窗口中的 Tk 原生表面。"""
        self.register(window)
        self._walk(window)

    def _walk(self, widget):
        surface = getattr(widget, "_thione_surface", "bg")
        color = self.palette.get(surface, self.palette["bg"])
        try:
            if isinstance(widget, (tk.Toplevel, tk.Canvas, tk.Frame,
                                   tk.Label, tk.Menu, tk.Text, tk.Listbox)):
                widget.configure(bg=color)
                if isinstance(widget, tk.Toplevel):
                    widget.configure(highlightbackground=self.palette["border"])
                if isinstance(widget, (tk.Label, tk.Text, tk.Listbox)):
                    widget.configure(fg=self.palette["text"])
                if isinstance(widget, tk.Text):
                    widget.configure(
                        insertbackground=self.palette["text"],
                        selectbackground=self.palette["accent"],
                        selectforeground=self.palette["on_accent"],
                    )
                if isinstance(widget, tk.Menu):
                    widget.configure(
                        fg=self.palette["text"],
                        activebackground=self.palette["hover"],
                        activeforeground=self.palette["text"],
                    )
                if isinstance(widget, (tk.Canvas, tk.Listbox)):
                    widget.configure(highlightbackground=self.palette["border"])
        except tk.TclError:
            pass
        try:
            children = widget.winfo_children()
        except tk.TclError:
            return
        for child in children:
            self._walk(child)
