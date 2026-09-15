"""左侧工具导航栏。

导航用 Canvas 自绘而不是 ttk.Button: 需要在同一块区域里画会滑动的选中指示条,
并让悬停底色淡入淡出, 这两种效果 ttk 样式做不到。导航项的位置由 _row_top()
统一计算, 绘制与命中测试共用同一份几何。
"""

import tkinter as tk
from tkinter import ttk

from ..constants import APP_TAGLINE, APP_VERSION
from ..motion import Tween, ease_out_cubic
from ..palettes import mix
from ..theme import sans

#: 侧栏固定宽度
NAV_WIDTH = 208

#: 导航项高度, 间距与左右留白
ITEM_HEIGHT = 40
ITEM_GAP = 4
ITEM_PAD = 8

#: 选中指示条
INDICATOR_WIDTH = 3
INDICATOR_HEIGHT = 18
INDICATOR_INSET = 6

#: 品牌标记尺寸
MARK_SIZE = 32

#: 悬停淡入与指示条滑动的时长 (毫秒), 都控制在 200 毫秒以内
HOVER_MS = 110
SLIDE_MS = 160


def _round_points(x1, y1, x2, y2, radius):
    """返回圆角矩形的顶点序列, 配合 smooth=True 使用。

    Tk 没有圆角图元: 把四条边与四个角的控制点交给平滑多边形, 就能得到
    足够平整的圆角, 而且改尺寸时只要重算这串点。
    """
    radius = max(0, min(radius, (x2 - x1) / 2, (y2 - y1) / 2))
    return [
        x1 + radius, y1, x2 - radius, y1, x2, y1,
        x2, y1 + radius, x2, y2 - radius, x2, y2,
        x2 - radius, y2, x1 + radius, y2, x1, y2,
        x1, y2 - radius, x1, y1 + radius, x1, y1,
    ]


def _draw_round_rect(canvas, x1, y1, x2, y2, radius, **kwargs):
    """在画布上画一个圆角矩形, 返回 item id。"""
    return canvas.create_polygon(
        _round_points(x1, y1, x2, y2, radius), smooth=True, **kwargs
    )


class Sidebar(ttk.Frame):
    """固定宽度的工具导航栏。

    参数:
        theme:           ThemeManager, 提供调色板并负责在切换时回调
        items:           [(key, icon, title), ...], 顺序即显示顺序
        on_select:       callable(key), 用户点击某个工具时调用
        on_toggle_theme: callable(), 点击底部主题按钮时调用
    """

    def __init__(self, master, theme, items, on_select, on_toggle_theme):
        super().__init__(master, style="Panel.TFrame", width=NAV_WIDTH)
        # 固定宽度, 不让内部控件把侧栏撑开
        self.pack_propagate(False)

        self.theme = theme
        self._on_select = on_select
        self._items = list(items)
        self._rows = {}
        self._active_key = None
        self._indicator = None
        self._indicator_y = 0.0
        self._indicator_tween = None

        self._build_brand()
        self._build_nav()
        self._build_footer(on_toggle_theme)

        self.theme.add_frame_listener(self._on_palette_change)
        self.bind("<Destroy>", self._on_destroy)
        self._on_palette_change()

    # -- 几何 -------------------------------------------------------------
    def _row_top(self, index):
        """第 index 个导航项的顶边纵坐标。"""
        return ITEM_GAP + index * (ITEM_HEIGHT + ITEM_GAP)

    def _nav_height(self):
        """导航画布需要的高度。"""
        return len(self._items) * (ITEM_HEIGHT + ITEM_GAP) + ITEM_GAP

    def _row_at(self, y):
        """把画布纵坐标换算成导航项下标; 不在任何一项上时返回 None。"""
        for index in range(len(self._items)):
            top = self._row_top(index)
            if top <= y <= top + ITEM_HEIGHT:
                return index
        return None

    # -- 构建 -------------------------------------------------------------
    def _build_brand(self):
        brand = ttk.Frame(self, style="Panel.TFrame", padding=(16, 16, 16, 12))
        brand.pack(side="top", fill="x")

        top = ttk.Frame(brand, style="Panel.TFrame")
        top.pack(anchor="w")

        self.mark = tk.Canvas(top, width=MARK_SIZE, height=MARK_SIZE,
                              highlightthickness=0, bd=0)
        self.mark._thione_surface = "panel"
        self.mark.pack(side="left")

        ttk.Label(top, text="thione", style="Brand.TLabel").pack(
            side="left", padx=(10, 0)
        )

        ttk.Label(
            brand,
            text=APP_TAGLINE,
            style="SidebarMuted.TLabel",
            wraplength=NAV_WIDTH - 34,
            justify="left",
        ).pack(anchor="w", pady=(8, 0))

    def _build_nav(self):
        self.nav = tk.Canvas(
            self, width=NAV_WIDTH, height=self._nav_height(),
            highlightthickness=0, bd=0,
        )
        self.nav._thione_surface = "panel"
        self.nav.pack(side="top", fill="x")

        for index, (key, icon, title) in enumerate(self._items):
            top = self._row_top(index)
            self._rows[key] = {
                "index": index,
                "top": top,
                "pill": _draw_round_rect(
                    self.nav, ITEM_PAD, top, NAV_WIDTH - ITEM_PAD,
                    top + ITEM_HEIGHT, 8,
                ),
                "label": self.nav.create_text(
                    ITEM_PAD + 30, top + ITEM_HEIGHT / 2,
                    text="%s   %s" % (icon, title), anchor="w",
                    font=sans(11), fill="#000000",
                ),
                "tween": None,
                "hover": 0.0,
            }

        self._indicator = _draw_round_rect(
            self.nav, 0, -100, INDICATOR_WIDTH, -100 + INDICATOR_HEIGHT, 2
        )

        self.nav.bind("<Motion>", self._on_motion)
        self.nav.bind("<Leave>", self._on_leave)
        self.nav.bind("<Button-1>", self._on_click)

    def _build_footer(self, on_toggle_theme):
        footer = ttk.Frame(self, style="Panel.TFrame", padding=(12, 12))
        footer.pack(side="bottom", fill="x")

        self.btn_theme = ttk.Button(
            footer, style="Chip.TButton", command=on_toggle_theme
        )
        self.btn_theme.pack(fill="x")

        ttk.Label(
            footer, text="v%s" % APP_VERSION, style="SidebarMuted.TLabel"
        ).pack(anchor="w", pady=(10, 0))

    # -- 绘制 -------------------------------------------------------------
    def _on_palette_change(self):
        """调色板变化时重画品牌标记与导航; 过渡动画中每帧都会调用。"""
        try:
            self._paint_mark()
            self._paint_rows()
        except tk.TclError:
            pass

    def _paint_mark(self):
        """画品牌标记: 一个实心主色的圆角方块, 中间放品牌首字母。"""
        p = self.theme.palette
        self.mark.delete("all")
        size = MARK_SIZE
        _draw_round_rect(self.mark, 1, 1, size - 1, size - 1, 9,
                         fill=p["accent"], outline="")
        self.mark.create_text(
            size / 2, size / 2, text="t", fill=p["on_accent"],
            font=sans(14, bold=True),
        )

    def _paint_rows(self):
        """按当前状态刷新每一行导航的底色与文字色。"""
        p = self.theme.palette
        for key, row in self._rows.items():
            active = key == self._active_key
            if active:
                fill = mix(p["accent_weak"], p["accent"],
                           0.12 * row["hover"])
                text = p["link"]
            else:
                fill = mix(p["panel"], p["hover"], row["hover"])
                text = mix(p["muted"], p["text"], row["hover"])
            self.nav.itemconfigure(row["pill"], fill=fill)
            self.nav.itemconfigure(row["label"], fill=text)

        if self._indicator is not None:
            index = self._index_of(self._active_key)
            if index is None:
                self.nav.itemconfigure(self._indicator, state="hidden")
            else:
                self.nav.itemconfigure(self._indicator, state="normal",
                                       fill=p["accent"])
                self._place_indicator(self._indicator_y)

    def _place_indicator(self, offset):
        """把指示条画在第 offset 行上 (offset 允许是小数, 用于滑动中间态)。"""
        index = self._index_of(self._active_key)
        if index is None:
            return
        base = self._row_top(0)
        step = ITEM_HEIGHT + ITEM_GAP
        center = base + offset * step + ITEM_HEIGHT / 2
        y1 = center - INDICATOR_HEIGHT / 2
        x1 = ITEM_PAD + INDICATOR_INSET
        self.nav.coords(
            self._indicator,
            *_round_points(x1, y1, x1 + INDICATOR_WIDTH, y1 + INDICATOR_HEIGHT, 2)
        )

    def _index_of(self, key):
        """返回某个导航项的下标, 不存在时返回 None。"""
        row = self._rows.get(key)
        return None if row is None else row["index"]

    # -- 交互 -------------------------------------------------------------
    def _on_motion(self, event):
        index = self._row_at(event.y)
        hovered = None if index is None else self._items[index][0]
        self.nav.configure(cursor="hand2" if hovered else "")
        for key, row in self._rows.items():
            self._set_hover(row, 1.0 if key == hovered else 0.0)

    def _on_leave(self, _event):
        self.nav.configure(cursor="")
        for row in self._rows.values():
            self._set_hover(row, 0.0)

    def _on_click(self, event):
        index = self._row_at(event.y)
        if index is not None:
            self._on_select(self._items[index][0])

    def _set_hover(self, row, target):
        """把一行的悬停进度补间到目标值。"""
        if row["tween"] is not None:
            row["tween"].cancel()
            row["tween"] = None
        start = row["hover"]
        if abs(start - target) < 0.01:
            row["hover"] = target
            self._paint_rows()
            return
        row["tween"] = Tween(
            self.nav, HOVER_MS,
            on_frame=lambda progress: self._apply_hover(row, start, target, progress),
            easing=ease_out_cubic,
        ).start()

    def _apply_hover(self, row, start, target, progress):
        row["hover"] = start + (target - start) * progress
        if progress >= 1.0:
            row["tween"] = None
        self._paint_rows()

    # -- 状态同步 ---------------------------------------------------------
    def set_active(self, key):
        """高亮当前页面对应的导航项, 指示条会滑过去。"""
        if key == self._active_key:
            return
        previous = self._index_of(self._active_key)
        self._active_key = key
        target = self._index_of(key)
        if self._indicator_tween is not None:
            self._indicator_tween.cancel()
            self._indicator_tween = None
        if target is None:
            self._paint_rows()
            return
        if previous is None:
            self._indicator_y = float(target)
            self._paint_rows()
            return
        start = self._indicator_y
        self._indicator_tween = Tween(
            self.nav, SLIDE_MS,
            on_frame=lambda progress: self._slide(start, float(target), progress),
            easing=ease_out_cubic,
        ).start()

    def _slide(self, start, target, progress):
        self._indicator_y = start + (target - start) * progress
        if progress >= 1.0:
            self._indicator_tween = None
        self._paint_rows()

    def set_theme_name(self, name):
        """同步主题按钮上的文字。"""
        self.btn_theme.configure(
            text="☾   深色模式" if name == "dark" else "☀   浅色模式"
        )

    # -- 收尾 -------------------------------------------------------------
    def _on_destroy(self, event):
        if event.widget is not self:
            return
        self.theme.remove_frame_listener(self._on_palette_change)
        for row in self._rows.values():
            if row["tween"] is not None:
                row["tween"].cancel()
                row["tween"] = None
        if self._indicator_tween is not None:
            self._indicator_tween.cancel()
            self._indicator_tween = None
