"""工具箱主窗口: 顶部主色条 + 侧栏 + 内容区 + 状态栏。

它同时负责页面装载与切换, 以及跨线程投递队列的轮询。
"""

import logging
import queue
import tkinter as tk
from tkinter import ttk

from ..constants import APP_MIN_SIZE, APP_SIZE, APP_TITLE, QUEUE_POLL_MS
from ..motion import Tween, ease_out_cubic
from ..theme import ThemeManager
from .sidebar import Sidebar

logger = logging.getLogger(__name__)

#: 窗口顶部主色条的高度
ACCENT_LINE_HEIGHT = 2

#: 页面切换时内容上移到位: 起始偏移与时长 (毫秒)
REVEAL_OFFSET = 8
REVEAL_MS = 140


class ShellWindow:
    """把若干个 ToolPage 组装成一个单窗口应用。

    参数:
        root:         tkinter 根窗口, 由入口创建并负责 mainloop
        settings:     AppSettings, 记录主题与上次停留的页面
        page_classes: ToolPage 子类序列, 顺序即侧栏顺序
    """

    def __init__(self, root, settings, page_classes):
        self.root = root
        self.settings = settings
        self._page_classes = list(page_classes)
        self._pages = {}
        self._current_key = None
        self._indicators = {}
        self._queue = queue.Queue()
        self._queue_job = None
        self._reveal = None
        self._closing = False

        root.title(APP_TITLE)
        root.geometry(APP_SIZE)
        root.minsize(*APP_MIN_SIZE)

        self.theme = ThemeManager(root, settings.theme)
        self.theme.add_listener(self._on_theme_settled)
        self.settings.theme = self.theme.mode

        self._build_accent_line()
        self._build_statusbar()
        self._build_body()
        self._build_pages()

        self.sidebar.set_theme_name(self.theme.mode)
        self.theme.add_frame_listener(self._paint_accent_line)
        root.bind_all("<Control-t>", self._on_toggle_theme)
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.show(self._initial_key())
        self._queue_job = root.after(QUEUE_POLL_MS, self._drain_queue)

    # -- 构建 -------------------------------------------------------------
    def _build_accent_line(self):
        """窗口顶部的主色条, 位置在侧栏与内容区之上。"""
        self.accent_line = tk.Canvas(
            self.root, height=ACCENT_LINE_HEIGHT, highlightthickness=0, bd=0
        )
        self.accent_line.pack(side="top", fill="x")
        self.accent_line.bind("<Configure>", lambda _event: self._paint_accent_line())

    def _paint_accent_line(self):
        """把主色条刷成实心主色; 窗口宽度变化与主题过渡时都会调用。"""
        canvas = self.accent_line
        try:
            width = canvas.winfo_width()
        except tk.TclError:
            return
        if width <= 1:
            return
        canvas.delete("all")
        canvas.create_rectangle(
            0, 0, width, ACCENT_LINE_HEIGHT,
            fill=self.theme.palette["accent"], outline="",
        )

    def _build_statusbar(self):
        bar = ttk.Frame(self.root, style="Panel.TFrame", padding=(16, 8))
        bar.pack(side="bottom", fill="x")

        self._status_var = tk.StringVar(value="")
        ttk.Label(
            bar, textvariable=self._status_var, style="PanelMuted.TLabel"
        ).pack(side="left")

        self._indicator_var = tk.StringVar(value="")
        ttk.Label(
            bar, textvariable=self._indicator_var, style="PanelMuted.TLabel"
        ).pack(side="right")

    def _build_body(self):
        body = ttk.Frame(self.root)
        body.pack(side="top", fill="both", expand=True)

        self.sidebar = Sidebar(
            body,
            self.theme,
            [(cls.key, cls.icon, cls.title) for cls in self._page_classes],
            on_select=self.show,
            on_toggle_theme=self._on_toggle_theme,
        )
        self.sidebar.pack(side="left", fill="y")

        self.content = ttk.Frame(body)
        self.content.pack(side="left", fill="both", expand=True)

    def _build_pages(self):
        """一次性创建所有页面, 但只有当前页面会被 pack 到内容区。

        页面之间共享同一套主题与根窗口, 因此创建成本很低; 提前建好可以让需要
        常驻后台能力的工具 (划词翻译) 在启动时就完成初始化。
        """
        for cls in self._page_classes:
            self._pages[cls.key] = cls(self.content, self)

    def _initial_key(self):
        keys = [cls.key for cls in self._page_classes]
        if self.settings.page in keys:
            return self.settings.page
        return keys[0]

    # -- 页面切换 ---------------------------------------------------------
    def show(self, key):
        """切换到指定页面; 重复调用同一个 key 不会重复触发生命周期。"""
        if key not in self._pages or key == self._current_key:
            return

        previous = self._pages.get(self._current_key)
        if previous is not None:
            previous.on_hide()
            previous.pack_forget()

        page = self._pages[key]
        page.pack(fill="both", expand=True)
        self._current_key = key
        self.sidebar.set_active(key)
        self.settings.page = key
        self.set_status(page.subtitle)
        page.on_show()
        self._play_reveal(page)

    def _play_reveal(self, page):
        """让刚切过来的页面轻微上移到位, 避免整块内容生硬出现。"""
        self._stop_reveal()
        if REVEAL_OFFSET <= 0:
            return
        self._reveal = Tween(
            self.root,
            REVEAL_MS,
            on_frame=lambda progress: self._apply_reveal(page, progress),
            on_done=lambda: self._apply_reveal(page, 1.0),
            easing=ease_out_cubic,
        ).start()

    def _apply_reveal(self, page, progress):
        """把上移进度写回页面内边距。"""
        if page.winfo_manager() != "pack":
            return
        try:
            offset = int(round(REVEAL_OFFSET * (1 - progress)))
            page.pack_configure(pady=(offset, 0))
        except tk.TclError:
            pass

    def _stop_reveal(self):
        if self._reveal is not None:
            self._reveal.cancel()
            self._reveal = None

    # -- 状态栏 -----------------------------------------------------------
    def set_status(self, message):
        """设置状态栏左侧的提示文字。"""
        self._status_var.set(message or "")

    def set_indicator(self, key, text):
        """设置状态栏右侧的一个指示器; text 为空时移除该项。"""
        if text:
            self._indicators[key] = text
        else:
            self._indicators.pop(key, None)
        self._indicator_var.set("  ·  ".join(self._indicators.values()))

    # -- 跨线程投递 -------------------------------------------------------
    def post(self, action):
        """任何线程都可以调用, 把要在主线程执行的动作排队。

        后台线程 (单实例激活监听、托盘图标) 不能直接碰 tkinter, 一律先投递
        到这里, 再由主线程的轮询执行。
        """
        self._queue.put(action)

    def _drain_queue(self):
        if self._closing:
            return
        while True:
            try:
                action = self._queue.get_nowait()
            except queue.Empty:
                break
            try:
                action()
            except Exception:
                logger.exception("处理投递任务失败")
        try:
            self._queue_job = self.root.after(QUEUE_POLL_MS, self._drain_queue)
        except tk.TclError:
            self._queue_job = None

    # -- 主题 -------------------------------------------------------------
    def _on_toggle_theme(self, event=None):
        """在深色与浅色之间切换; 颜色过渡结束后才会写设置与刷新页面。"""
        self.theme.toggle()

    def _on_theme_settled(self):
        """主题落定后同步设置、侧栏文案与页面内缓存的颜色。"""
        self.settings.theme = self.theme.mode
        self.sidebar.set_theme_name(self.theme.mode)
        for page in self._pages.values():
            try:
                page.on_theme_changed()
            except Exception:
                logger.exception("刷新页面主题失败: %s", page.key)

    # -- 窗口级操作 -------------------------------------------------------
    def raise_window(self):
        """把主窗口从最小化恢复并置前 (托盘菜单使用)。"""
        try:
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
        except tk.TclError:
            logger.debug("恢复主窗口失败", exc_info=True)

    def on_close(self):
        """关闭窗口: 先让各页面收尾, 任一页面拒绝则取消退出。"""
        for page in list(self._pages.values()):
            try:
                if not page.on_close():
                    return
            except Exception:
                logger.exception("页面收尾失败: %s", page.key)

        self._closing = True
        self._stop_reveal()
        self.theme.remove_listener(self._on_theme_settled)
        self.theme.remove_frame_listener(self._paint_accent_line)
        if self._queue_job is not None:
            try:
                self.root.after_cancel(self._queue_job)
            except tk.TclError:
                pass
            self._queue_job = None
        self.settings.save()
        try:
            self.root.destroy()
        except tk.TclError:
            pass

