"""提供应用外壳中的工具导航栏

导航栏宽 208 像素, 自上而下是品牌行 工具列表与页脚 (主题切换 运行日志 版本号)
选中项使用 fill_hi 底色, 左端画 2 像素强调条, 文字加粗并改用强调色图标
"""

import tkinter as tk
from tkinter import ttk

from .. import kit
from ..constants import APP_VERSION
from ..dpi import scale
from ..theme import (
    ICON_BRAND,
    SIZE_BODY,
    SIZE_BRAND,
    SIZE_LABEL,
    SIZE_TITLE,
    SIDEBAR_WIDTH,
    sans,
    tint,
)

#: 侧栏宽度的允许范围与拖拽后的取值
NAV_MIN_WIDTH = scale(180)
NAV_MAX_WIDTH = scale(320)

#: 导航行的文字与图标比设计稿放大 1 像素, 保证在常见缩放下依然清晰
NAV_TEXT_SIZE = SIZE_BODY + 1
NAV_ICON_SIZE = SIZE_TITLE + 1
BRAND_TEXT_SIZE = SIZE_BRAND + 1
FOOT_TEXT_SIZE = SIZE_LABEL + 1

#: 导航行的高度 (与设计稿一致)
NAV_ROW_HEIGHT = scale(34)

#: 选中项左端强调条的宽度
MARK_WIDTH = scale(2)

#: 强调条上下留出的距离
MARK_INSET = scale(6)

#: 选中项左侧的缩进, 减去强调条宽度后与其它行保持对齐
ROW_PAD = scale(16) - MARK_WIDTH

#: 页脚按钮的宽度 (字符); clam 给按钮的默认最小宽度放不进页脚同一行
FOOT_BUTTON_WIDTH = 5


class Sidebar(tk.Frame):
    """显示可用工具 当前选中的导航项与底部的主题 日志入口"""

    def __init__(self, master, theme, items, on_select, on_toggle_theme,
                 on_open_log):
        super().__init__(master, bd=0, highlightthickness=0,
                         width=SIDEBAR_WIDTH)
        self.theme = theme
        tint(self, bg="side")
        self.configure(bg=theme.rgb("side"))
        self.pack_propagate(False)
        self._on_select = on_select
        self._on_toggle_theme = on_toggle_theme
        self._on_open_log = on_open_log
        self._rows = {}
        self._active_key = None
        self._hover_key = None
        self._mode = "light"
        self._width = SIDEBAR_WIDTH
        self._build(items)

    # ---------------- 构建 ----------------
    def _build(self, items):
        brand = tk.Frame(self, bd=0, highlightthickness=0)
        tint(brand, bg="side")
        brand.configure(bg=self.theme.rgb("side"))
        brand.pack(side="top", fill="x", padx=scale(16),
                   pady=(scale(4), scale(16)))

        mark = tk.Frame(brand, width=scale(20), height=scale(20),
                        highlightthickness=scale(2))
        tint(mark, bg="side", hl="accent", hlc="accent")
        mark.configure(bg=self.theme.rgb("side"),
                       highlightbackground=self.theme.rgb("accent"),
                       highlightcolor=self.theme.rgb("accent"))
        mark.pack(side="left")
        mark.pack_propagate(False)
        glyph = kit.text(mark, self.theme, value=ICON_BRAND,
                         size=SIZE_LABEL + 1, token="accent", icon_font=True,
                         surface="side", anchor="center")
        glyph.pack(fill="both", expand=True)
        kit.text(brand, self.theme, value="thione", size=BRAND_TEXT_SIZE,
                 bold=True,
                 surface="side").pack(side="left", padx=(scale(9), 0))

        nav = tk.Frame(self, bd=0, highlightthickness=0)
        tint(nav, bg="side")
        nav.configure(bg=self.theme.rgb("side"))
        nav.pack(side="top", fill="x")
        for key, glyph, title in items:
            self._rows[key] = self._build_row(nav, key, glyph, title)
        self._paint()

        foot = tk.Frame(self, bd=0, highlightthickness=0)
        tint(foot, bg="side")
        foot.configure(bg=self.theme.rgb("side"))
        foot.pack(side="bottom", fill="x", padx=scale(16))
        kit.hairline(foot, self.theme).pack(fill="x", pady=(0, scale(9)))
        self.theme_caption, self.theme_button = self._build_foot_row(
            foot, "深色模式", "切换", self._on_toggle_theme)
        self._build_foot_row(foot, "运行日志", "打开", self._on_open_log)
        kit.text(foot, self.theme, value=f"v{APP_VERSION}", size=FOOT_TEXT_SIZE,
                 token="muted", mono_font=True,
                 surface="side").pack(anchor="w", pady=(0, scale(10)))

    def _build_row(self, parent, key, glyph, title):
        """建立一行导航项

        @param parent: 父容器
        @param key: 工具标识
        @param glyph: 图标字形
        @param title: 工具名
        @return: 该行的控件字典
        """
        row = tk.Frame(parent, height=NAV_ROW_HEIGHT, bd=0,
                       highlightthickness=0, cursor="hand2")
        tint(row, bg="side")
        row.configure(bg=self.theme.rgb("side"))
        row.pack(side="top", fill="x")
        row.pack_propagate(False)

        mark = tk.Frame(row, width=MARK_WIDTH, bd=0, highlightthickness=0)
        tint(mark, bg="side")
        mark.configure(bg=self.theme.rgb("side"))
        mark.pack(side="left", fill="y", pady=MARK_INSET)

        icon_label = kit.text(row, self.theme, value=glyph, size=NAV_ICON_SIZE,
                              token="muted", icon_font=True, surface="side")
        icon_label.pack(side="left", padx=(ROW_PAD, 0))
        text_label = kit.text(row, self.theme, value=title, size=NAV_TEXT_SIZE,
                              token="muted", surface="side")
        text_label.pack(side="left", padx=(scale(10), 0))
        for widget in (row, mark, icon_label, text_label):
            widget.bind("<Button-1>", lambda _e, k=key: self._on_select(k))
            widget.bind("<Enter>", lambda _e, k=key: self._set_hover(k))
            widget.bind("<Leave>", lambda _e, k=key: self._set_hover(None))
        return {"frame": row, "mark": mark, "icon": icon_label,
                "text": text_label}

    def _build_foot_row(self, parent, caption, button_text, command):
        """建立一行页脚 (左侧说明 + 右侧小按钮)

        @param parent: 父容器
        @param caption: 左侧说明
        @param button_text: 按钮文案
        @param command: 按钮回调
        @return: (左侧说明控件, 按钮控件)
        """
        row = tk.Frame(parent, bd=0, highlightthickness=0)
        tint(row, bg="side")
        row.configure(bg=self.theme.rgb("side"))
        row.pack(side="top", fill="x", pady=(0, scale(9)))
        button = ttk.Button(row, text=button_text, width=FOOT_BUTTON_WIDTH,
                            style="Mini.TButton", command=command)
        button.pack(side="right")
        caption_label = kit.text(row, self.theme, value=caption,
                                 size=FOOT_TEXT_SIZE, token="muted",
                                 surface="side")
        caption_label.pack(side="left")
        return caption_label, button

    # ---------------- 状态 ----------------
    def set_width(self, width):
        """把侧栏宽度限制在允许范围内

        @param width: 目标宽度 (像素)
        """
        width = max(NAV_MIN_WIDTH, min(int(width), NAV_MAX_WIDTH))
        if width == self._width:
            return
        self._width = width
        self.configure(width=width)

    @property
    def width(self):
        """当前侧栏宽度"""
        return self._width

    def set_active(self, key):
        """突出显示当前选中的工具

        @param key: 工具标识
        """
        if key == self._active_key:
            return
        self._active_key = key
        self._paint()

    def set_theme(self, mode):
        """更新主题按钮的文案

        @param mode: 当前主题, light 或 dark
        """
        self._mode = mode
        target = "深色模式" if mode == "light" else "浅色模式"
        self.theme_caption.configure(text=target)

    def _set_hover(self, key):
        """记录指针所在的导航行

        @param key: 工具标识, None 表示指针移出
        """
        if key == self._hover_key:
            return
        self._hover_key = key
        self._paint()

    def _paint(self):
        """按选中与悬停状态刷新各导航行"""
        palette = self.theme.palette
        for key, parts in self._rows.items():
            if key == self._active_key:
                bg, fg, icon_fg, bold = ("fill_hi", "text", "accent", True)
            elif key == self._hover_key:
                bg, fg, icon_fg, bold = ("fill", "text", "muted", False)
            else:
                bg, fg, icon_fg, bold = ("side", "muted", "muted", False)
            mark_bg = "accent" if key == self._active_key else bg
            parts["frame"].configure(bg=palette[bg])
            parts["mark"].configure(bg=palette[mark_bg])
            parts["icon"].configure(bg=palette[bg], fg=palette[icon_fg])
            parts["text"].configure(bg=palette[bg], fg=palette[fg],
                                    font=sans(NAV_TEXT_SIZE, bold))
            tint(parts["frame"], bg=bg)
            tint(parts["mark"], bg=mark_bg)
            tint(parts["icon"], bg=bg, fg=icon_fg)
            tint(parts["text"], bg=bg, fg=fg)
