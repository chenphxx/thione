"""提供应用外壳中的工具导航栏

导航栏宽 208 像素, 自上而下是品牌行 工具列表与页脚 (主题切换 运行日志 版本号)
选中项使用 fill_hi 圆角底色, 左端画 2 像素强调条, 文字加粗并改用强调色图标
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
    SIZE_SECTION,
    SIDEBAR_WIDTH,
    icon,
    sans,
    tint,
)

#: 侧栏宽度的允许范围与拖拽后的取值
NAV_MIN_WIDTH = scale(180)
NAV_MAX_WIDTH = scale(320)

#: 导航文字沿用统一正文尺寸, 图标略小, 避免图标压过文字
NAV_TEXT_SIZE = SIZE_BODY
NAV_ICON_SIZE = SIZE_LABEL
BRAND_TEXT_SIZE = SIZE_BRAND
FOOT_TEXT_SIZE = SIZE_LABEL

#: 侧栏统一间距: 外缘与内容内缩为 12, 组内 4, 组间 16
NAV_GUTTER = scale(12)
NAV_CONTENT_PAD = scale(12)
NAV_ITEM_GAP = scale(4)
NAV_GROUP_GAP = scale(16)
NAV_ICON_GAP = scale(8)
NAV_ICON_BOX = scale(20)

#: 导航行需要容纳 13 像素文字及上下留白, 同时提供足够大的点击区域
NAV_ROW_HEIGHT = scale(40)

#: 导航项沿用面板的 8 像素圆角
NAV_RADIUS = scale(8)

#: 工具分类与组内顺序; 未归类的工具会放进末尾的 其他 组
NAV_GROUPS = (
    ("文件", ("rename", "dedupe", "markdown", "convert")),
    ("工具", ("translate", "radix", "port", "comm")),
)

#: 选中项左端强调条的宽度
MARK_WIDTH = scale(2)

#: 强调条上下留出的距离
MARK_INSET = scale(10)

#: 页脚按钮的宽度 (字符); clam 给按钮的默认最小宽度放不进页脚同一行
FOOT_BUTTON_WIDTH = 5


class Sidebar(tk.Frame):
    """显示可用工具 当前选中的导航项与底部的主题 日志入口"""

    def __init__(self, master, theme, items, on_select, on_toggle_theme,
                 on_open_log, on_check_update):
        super().__init__(master, bd=0, highlightthickness=0,
                         width=SIDEBAR_WIDTH)
        self.theme = theme
        tint(self, bg="side")
        self.configure(bg=theme.rgb("side"))
        self.pack_propagate(False)
        self._on_select = on_select
        self._on_toggle_theme = on_toggle_theme
        self._on_open_log = on_open_log
        self._on_check_update = on_check_update
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
        brand.pack(side="top", fill="x", padx=NAV_GUTTER,
                   pady=(scale(8), NAV_GROUP_GAP))

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
        nav.pack(side="top", fill="x", padx=NAV_GUTTER)
        for group_index, (label, group_items) in enumerate(
                self._group_items(items)):
            group_label = kit.text(
                nav, self.theme, value=label, size=SIZE_SECTION,
                token="muted", bold=True, surface="side",
            )
            group_label.pack(
                anchor="w", padx=(NAV_CONTENT_PAD, 0),
                pady=(
                    0 if group_index == 0 else NAV_GROUP_GAP,
                    NAV_ITEM_GAP,
                ),
            )
            for item_index, (key, glyph, title) in enumerate(group_items):
                gap = 0 if item_index == len(group_items) - 1 else NAV_ITEM_GAP
                self._rows[key] = self._build_row(
                    nav, key, glyph, title, gap,
                )
        self._paint()

        foot = tk.Frame(self, bd=0, highlightthickness=0)
        tint(foot, bg="side")
        foot.configure(bg=self.theme.rgb("side"))
        foot.pack(side="bottom", fill="x", padx=NAV_GUTTER)
        kit.hairline(foot, self.theme).pack(fill="x", pady=(0, scale(9)))
        self.theme_caption, self.theme_button = self._build_foot_row(
            foot, "深色模式", "切换", self._on_toggle_theme)
        self._build_foot_row(foot, "运行日志", "打开", self._on_open_log)

        version_row = tk.Frame(foot, bd=0, highlightthickness=0)
        tint(version_row, bg="side")
        version_row.configure(bg=self.theme.rgb("side"))
        version_row.pack(side="top", fill="x", pady=(0, scale(10)))
        kit.text(version_row, self.theme, value=f"v{APP_VERSION}",
                 size=FOOT_TEXT_SIZE, token="muted", mono_font=True,
                 surface="side").pack(side="left")
        self.update_button = ttk.Button(
            version_row, text="获取最新版", style="Mini.TButton",
            command=self._on_check_update,
        )
        self.update_button.pack(side="right")

    @staticmethod
    def _group_items(items):
        """按侧栏分类整理导航项

        @param items: (工具标识, 图标字形, 工具名) 序列
        @return: (分组名, 分组内导航项) 序列
        """
        by_key = {item[0]: item for item in items}
        grouped = []
        claimed = set()
        for label, keys in NAV_GROUPS:
            members = [by_key[key] for key in keys if key in by_key]
            if not members:
                continue
            grouped.append((label, members))
            claimed.update(item[0] for item in members)
        others = [item for item in items if item[0] not in claimed]
        if others:
            grouped.append(("其他", others))
        return grouped

    def _build_row(self, parent, key, glyph, title, gap):
        """建立一行导航项

        @param parent: 父容器
        @param key: 工具标识
        @param glyph: 图标字形
        @param title: 工具名
        @param gap: 与下一行之间的间距
        @return: 该行的控件字典
        """
        row = tk.Canvas(parent, height=NAV_ROW_HEIGHT, bd=0,
                        highlightthickness=0, cursor="hand2")
        tint(row, bg="side")
        row.configure(bg=self.theme.rgb("side"))
        row.pack(side="top", fill="x", pady=(0, gap))
        row.bind("<Button-1>", lambda _e, k=key: self._on_select(k))
        row.bind("<Enter>", lambda _e, k=key: self._set_hover(k))
        row.bind("<Leave>", lambda _e: self._set_hover(None))
        row.bind("<Configure>", lambda _e, k=key: self._draw_row(k))
        row._thione_apply = lambda _palette, k=key: self._draw_row(k)
        return {"canvas": row, "glyph": glyph, "title": title}

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

    def set_update_busy(self, busy, text=None):
        """切换获取最新版按钮的忙碌状态

        @param busy: True 时禁用按钮并显示检查中
        @param text: 忙碌时显示的文案
        """
        self.update_button.configure(
            state="disabled" if busy else "normal",
            text=(text or "检查中") if busy else "获取最新版",
        )

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
        for key in self._rows:
            self._draw_row(key)

    def _draw_row(self, key):
        """绘制导航行的圆角底色 图标与文字

        @param key: 工具标识
        """
        parts = self._rows.get(key)
        if parts is None:
            return
        canvas = parts["canvas"]
        width = max(canvas.winfo_width(), 1)
        height = max(canvas.winfo_height(), NAV_ROW_HEIGHT)
        if key == self._active_key:
            bg, fg, icon_fg, bold = ("fill_hi", "text", "accent", True)
        elif key == self._hover_key:
            bg, fg, icon_fg, bold = ("fill", "text", "muted", False)
        else:
            bg, fg, icon_fg, bold = (None, "muted", "muted", False)

        canvas.delete("all")
        if bg is not None:
            self._rounded_rect(canvas, width, height, self.theme.rgb(bg))
        if key == self._active_key:
            mark_x = NAV_CONTENT_PAD - scale(6)
            canvas.create_line(
                mark_x, MARK_INSET, mark_x, height - MARK_INSET,
                width=MARK_WIDTH, capstyle="round",
                fill=self.theme.rgb("accent"),
            )

        icon_x = NAV_CONTENT_PAD + NAV_ICON_BOX / 2
        text_x = NAV_CONTENT_PAD + NAV_ICON_BOX + NAV_ICON_GAP
        center_y = height / 2
        canvas.create_text(
            icon_x, center_y, text=parts["glyph"], anchor="center",
            font=icon(NAV_ICON_SIZE), fill=self.theme.rgb(icon_fg),
        )
        canvas.create_text(
            text_x, center_y, text=parts["title"], anchor="w",
            font=sans(NAV_TEXT_SIZE, bold), fill=self.theme.rgb(fg),
        )

    @staticmethod
    def _rounded_rect(canvas, width, height, fill):
        """在画布上画出无描边的圆角矩形

        @param canvas: 目标画布
        @param width: 矩形宽度
        @param height: 矩形高度
        @param fill: 填充颜色
        """
        radius = min(NAV_RADIUS, width // 2, height // 2)
        diameter = radius * 2
        canvas.create_rectangle(
            radius, 0, width - radius, height, outline="", fill=fill,
        )
        canvas.create_rectangle(
            0, radius, width, height - radius, outline="", fill=fill,
        )
        canvas.create_oval(
            0, 0, diameter, diameter, outline="", fill=fill,
        )
        canvas.create_oval(
            width - diameter, 0, width, diameter, outline="", fill=fill,
        )
        canvas.create_oval(
            0, height - diameter, diameter, height, outline="", fill=fill,
        )
        canvas.create_oval(
            width - diameter, height - diameter, width, height,
            outline="", fill=fill,
        )
