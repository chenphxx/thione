"""视图控件: 展示方式 缩略图大小分档与右下角的窗格开关。"""

from tkinter import ttk

from .constants import (
    DEFAULT_TIER,
    DEFAULT_VIEW,
    LIST_LABEL,
    TIER_LABELS,
    TIERS,
)


class ViewSwitch(ttk.Frame):
    """展示方式与缩略图档位: 列表 小 中 大。

    对应 Windows 资源管理器的「查看」菜单, 选中 小 中 大 即回到缩略图展示,
    同一时刻只有一项处于打开状态
    """

    def __init__(self, master, on_view, on_tier, view=DEFAULT_VIEW,
                 tier=DEFAULT_TIER):
        super().__init__(master, style="Panel.TFrame")
        self._on_view = on_view
        self._on_tier = on_tier
        self._buttons = {}

        button = ttk.Button(self, text=LIST_LABEL, width=4,
                            style="Secondary.TButton",
                            command=lambda: self._on_view("list"))
        button.pack(side="left", padx=(0, 4))
        self._buttons["list"] = button

        for name in TIERS:
            button = ttk.Button(self, text=TIER_LABELS[name], width=3,
                                style="Secondary.TButton",
                                command=lambda n=name: self._on_tier(n))
            button.pack(side="left", padx=(0, 4))
            self._buttons[name] = button

        self.set_state(view, tier)

    def set_state(self, view, tier):
        """同步选中态; 由页面在每次切换后调用, 不触发回调。"""
        for name, button in self._buttons.items():
            if name == "list":
                opened = view == "list"
            else:
                opened = view == "icons" and name == tier
            button.configure(
                style="SegmentOn.TButton" if opened else "Segment.TButton"
            )


class PaneToggles(ttk.Frame):
    """右下角的两个窗格开关: 详细信息窗格与预览窗格。"""

    def __init__(self, master, on_toggle_details, on_toggle_preview):
        super().__init__(master, style="Panel.TFrame")
        self._details = ttk.Button(self, text="\u25a4", width=3,
                                   style="Secondary.TButton",
                                   command=on_toggle_details)
        self._details.pack(side="left", padx=(0, 4))
        self._preview = ttk.Button(self, text="\u25a3", width=3,
                                   style="Secondary.TButton",
                                   command=on_toggle_preview)
        self._preview.pack(side="left")

    def set_state(self, details, preview):
        """同步两个开关的打开状态, 由页面在切换窗格后调用。"""
        self._details.configure(
            style="SegmentOn.TButton" if details else "Segment.TButton"
        )
        self._preview.configure(
            style="SegmentOn.TButton" if preview else "Segment.TButton"
        )
