"""提供应用外壳中的工具导航栏"""

from tkinter import ttk

from ..constants import APP_VERSION

NAV_WIDTH = 224
NAV_MIN_WIDTH = 180
NAV_MAX_WIDTH = 320

#: 日志按钮的宽度 (字符); clam 给按钮的默认最小宽度放不进页脚同一行
LOG_BUTTON_WIDTH = 4

#: 侧栏窄于这个宽度时主题按钮改用短文案
THEME_TEXT_MIN_WIDTH = 220


class Sidebar(ttk.Frame):
    """显示可用工具 当前选中的导航项与底部的主题 日志入口"""

    def __init__(self, master, items, on_select, on_toggle_theme, on_open_log):
        super().__init__(master, style="Panel.TFrame", width=NAV_WIDTH)
        self.pack_propagate(False)
        self._on_select = on_select
        self._on_toggle_theme = on_toggle_theme
        self._on_open_log = on_open_log
        self._width = NAV_WIDTH
        self._mode = "light"
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

        footer = ttk.Frame(self, style="Panel.TFrame", padding=(16, 14))
        footer.pack(side="bottom", fill="x")
        ttk.Separator(footer).pack(fill="x", pady=(0, 12))
        row = ttk.Frame(footer, style="Panel.TFrame")
        row.pack(fill="x", pady=(0, 10))
        # 先放日志按钮占住自己的宽度, 剩下的宽度全部留给主题按钮
        self.log_button = ttk.Button(row, text="日志", width=LOG_BUTTON_WIDTH,
                                     style="Secondary.TButton",
                                     command=self._on_open_log)
        self.log_button.pack(side="right")
        self.theme_button = ttk.Button(row, style="Secondary.TButton",
                                       command=self._on_toggle_theme)
        self.theme_button.pack(side="left", fill="x", expand=True,
                               padx=(0, 8))
        ttk.Label(footer, text=f"thione | v{APP_VERSION}",
                  style="SidebarMuted.TLabel").pack(anchor="w")
        self.set_theme("light")

    def set_width(self, width):
        """将侧栏宽度限制在允许范围内"""
        width = max(NAV_MIN_WIDTH, min(int(width), NAV_MAX_WIDTH))
        if width != self._width:
            self._width = width
            self.configure(width=width)
            self.set_theme(self._mode)

    def set_active(self, key):
        """突出显示当前选中的工具"""
        if key == self._active_key:
            return
        self._active_key = key
        for item_key, button in self._buttons.items():
            button.configure(
                style="NavSelected.TButton" if item_key == key else "Nav.TButton"
            )

    def set_theme(self, mode):
        """显示切换到另一种配色的按钮文案

        侧栏拖窄之后完整文案放不下, 因此窄侧栏用两字短文案

        @param mode: 当前主题, light 或 dark
        """
        self._mode = mode
        target = "深色" if mode == "light" else "浅色"
        if self._width < THEME_TEXT_MIN_WIDTH:
            self.theme_button.configure(text=target)
        else:
            self.theme_button.configure(text=f"切换到{target}模式")
