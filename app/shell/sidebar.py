"""提供应用外壳中的工具导航栏。"""

from tkinter import ttk

from ..constants import APP_VERSION

NAV_WIDTH = 224
NAV_MIN_WIDTH = 180
NAV_MAX_WIDTH = 320


class Sidebar(ttk.Frame):
    """显示可用工具和当前选中的导航项。"""

    def __init__(self, master, items, on_select):
        super().__init__(master, style="Panel.TFrame", width=NAV_WIDTH)
        self.pack_propagate(False)
        self._on_select = on_select
        self._width = NAV_WIDTH
        self._buttons = {}
        self._active_key = None
        self._build(items)

    def _build(self, items):
        nav = ttk.Frame(self, style="Panel.TFrame", padding=(12, 0))
        nav.pack(side="top", fill="x")
        for key, icon, title in items:
            button = ttk.Button(
                nav, text=f"{icon}    {title}", style="Nav.TButton",
                command=lambda item_key=key: self._on_select(item_key),
            )
            button.pack(fill="x", pady=3)
            self._buttons[key] = button

        footer = ttk.Frame(self, style="Panel.TFrame", padding=(22, 14))
        footer.pack(side="bottom", fill="x")
        ttk.Separator(footer).pack(fill="x", pady=(0, 12))
        ttk.Label(footer, text=f"thione  ·  v{APP_VERSION}",
                  style="SidebarMuted.TLabel").pack(anchor="w")

    def set_width(self, width):
        """将侧栏宽度限制在允许范围内。"""
        width = max(NAV_MIN_WIDTH, min(int(width), NAV_MAX_WIDTH))
        if width != self._width:
            self._width = width
            self.configure(width=width)

    def set_active(self, key):
        """突出显示当前选中的工具。"""
        if key == self._active_key:
            return
        self._active_key = key
        for item_key, button in self._buttons.items():
            button.configure(
                style="NavSelected.TButton" if item_key == key else "Nav.TButton"
            )
