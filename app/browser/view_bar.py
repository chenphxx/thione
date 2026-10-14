"""视图控件: 展示方式 缩略图大小分档与窗格开关"""

from tkinter import ttk

from .. import kit
from ..theme import ICON_PANE_DETAILS, ICON_PANE_PREVIEW
from .constants import (
    DEFAULT_TIER,
    DEFAULT_VIEW,
    LIST_LABEL,
    TILE_LABEL,
    TIER_LABELS,
    TIERS,
)


class ViewSwitch(kit.Segment):
    """展示方式与缩略图档位: 列表 小 中 大

    对应 Windows 资源管理器的'查看'菜单, 选中 小 中 大 即回到缩略图展示,
    同一时刻只有一项处于打开状态
    """

    def __init__(self, master, theme, on_view, on_tier, view=DEFAULT_VIEW,
                 tier=DEFAULT_TIER, surface="canvas", tiers=TIERS):
        options = [("list", LIST_LABEL)]
        if tiers:
            options.extend((name, TIER_LABELS[name]) for name in tiers)
        else:
            options.append(("tile", TILE_LABEL))
        self._tiers = tuple(tiers)
        super().__init__(master, theme, options,
                         value=self._key(view, tier),
                         command=self._on_change, surface=surface)
        self._on_view = on_view
        self._on_tier = on_tier

    def _key(self, view, tier):
        """把展示方式与档位换算成分段控件里的选中项

        @param view: 展示方式
        @param tier: 档位
        @return: 选项标识
        """
        if view == "list":
            return "list"
        return tier if self._tiers else "tile"

    def _on_change(self, key):
        """分段控件被点击: 列表项走展示方式回调, 其余走档位回调

        @param key: 选项标识
        """
        if key == "list":
            self._on_view("list")
        elif key == "tile":
            self._on_view("icons")
        else:
            self._on_tier(key)

    def set_state(self, view, tier):
        """同步选中态; 由页面在每次切换后调用, 不触发回调

        @param view: 展示方式
        @param tier: 档位
        """
        self.set(self._key(view, tier))


class PaneToggles(ttk.Frame):
    """右下角的两个窗格开关: 详细信息窗格与预览窗格"""

    def __init__(self, master, theme, on_toggle_details, on_toggle_preview):
        super().__init__(master)
        self.theme = theme
        self._details = ttk.Button(self, text=ICON_PANE_DETAILS,
                                   style="MiniIcon.TButton",
                                   command=on_toggle_details)
        self._details.pack(side="left")
        self._preview = ttk.Button(self, text=ICON_PANE_PREVIEW,
                                   style="MiniIcon.TButton",
                                   command=on_toggle_preview)
        self._preview.pack(side="left", padx=(8, 0))

    def set_state(self, details, preview):
        """同步两个开关的打开状态, 由页面在切换窗格后调用

        @param details: 详细信息窗格是否打开
        @param preview: 预览窗格是否打开
        """
        self._details.configure(
            style="MiniIconOn.TButton" if details else "MiniIcon.TButton")
        self._preview.configure(
            style="MiniIconOn.TButton" if preview else "MiniIcon.TButton")
