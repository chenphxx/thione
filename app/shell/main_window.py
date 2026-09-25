"""管理应用外壳、工具页面切换及工作线程到界面的消息队列。"""

import logging
import queue
import tkinter as tk
from tkinter import ttk

from ..constants import APP_MIN_SIZE, APP_SIZE, APP_TITLE, QUEUE_POLL_MS
from ..theme import ThemeManager
from .sidebar import Sidebar

logger = logging.getLogger(__name__)
SPLITTER_WIDTH = 5


class ShellWindow:
    """承载侧栏、工具页面和应用状态栏。"""

    def __init__(self, root, settings, page_classes):
        self.root = root
        self.settings = settings
        self._page_classes = list(page_classes)
        self._pages = {}
        self._current_key = None
        self._indicators = {}
        self._queue = queue.Queue()
        self._queue_job = None
        self._splitter_origin = None
        self._closing = False

        root.title(APP_TITLE)
        root.geometry(APP_SIZE)
        root.minsize(*APP_MIN_SIZE)

        self.theme = ThemeManager(root)
        self._build_statusbar()
        self._build_body()
        self._build_pages()
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.show(self._initial_key())
        self._queue_job = root.after(QUEUE_POLL_MS, self._drain_queue)

    def _build_statusbar(self):
        bar = ttk.Frame(self.root, style="Panel.TFrame", padding=(18, 9))
        bar.pack(side="bottom", fill="x")
        ttk.Separator(bar).place(relx=0, rely=0, relwidth=1)
        self._status_var = tk.StringVar(value="")
        ttk.Label(bar, textvariable=self._status_var,
                  style="PanelMuted.TLabel").pack(side="left")
        self._indicator_var = tk.StringVar(value="")
        ttk.Label(bar, textvariable=self._indicator_var,
                  style="PanelMuted.TLabel").pack(side="right")

    def _build_body(self):
        body = ttk.Frame(self.root)
        body.pack(side="top", fill="both", expand=True)
        self.sidebar = Sidebar(
            body,
            [(cls.key, cls.icon, cls.title) for cls in self._page_classes],
            on_select=self.show,
        )
        self.sidebar.pack(side="left", fill="y")
        ttk.Separator(body, orient="vertical").pack(side="left", fill="y")
        self.splitter = ttk.Frame(body, style="Drag.TFrame", width=SPLITTER_WIDTH,
                                  cursor="sb_h_double_arrow")
        self.splitter.pack_propagate(False)
        self.splitter.pack(side="left", fill="y")
        self.splitter.bind("<Button-1>", self._on_splitter_press)
        self.splitter.bind("<B1-Motion>", self._on_splitter_drag)
        self.splitter.bind("<ButtonRelease-1>", self._on_splitter_release)
        self.splitter.bind("<Enter>", lambda _event: self._hover_splitter(True))
        self.splitter.bind("<Leave>", lambda _event: self._hover_splitter(False))
        self.content = ttk.Frame(body, padding=(24, 22, 24, 20))
        self.content.pack(side="left", fill="both", expand=True)

    def _on_splitter_press(self, event):
        self._splitter_origin = (event.x_root, self.sidebar.winfo_width())

    def _on_splitter_drag(self, event):
        if self._splitter_origin is None:
            return
        start_x, start_width = self._splitter_origin
        self.sidebar.set_width(start_width + event.x_root - start_x)

    def _on_splitter_release(self, _event):
        self._splitter_origin = None

    def _hover_splitter(self, hovering):
        if self._splitter_origin is None:
            self.splitter.configure(
                style="DragHover.TFrame" if hovering else "Drag.TFrame"
            )

    def _build_pages(self):
        for page_class in self._page_classes:
            self._pages[page_class.key] = page_class(self.content, self)

    def _initial_key(self):
        keys = [page_class.key for page_class in self._page_classes]
        return self.settings.page if self.settings.page in keys else keys[0]

    def show(self, key):
        """切换到指定工具并通知页面生命周期钩子。"""
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

    def set_status(self, message):
        self._status_var.set(message or "")

    def set_indicator(self, key, text):
        if text:
            self._indicators[key] = text
        else:
            self._indicators.pop(key, None)
        self._indicator_var.set("   \u00b7   ".join(self._indicators.values()))

    def post(self, action):
        """将回调加入队列, 由 Tk 主线程执行。"""
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
                logger.exception("Shell action failed")
        try:
            self._queue_job = self.root.after(QUEUE_POLL_MS, self._drain_queue)
        except tk.TclError:
            self._queue_job = None

    def raise_window(self):
        """还原并聚焦主窗口, 供托盘回调使用。"""
        try:
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
        except tk.TclError:
            logger.debug("Could not restore the main window", exc_info=True)

    def on_close(self):
        """通知活动页面清理资源, 保存偏好并关闭窗口。"""
        for page in list(self._pages.values()):
            try:
                if not page.on_close():
                    return
            except Exception:
                logger.exception("Shell action failed")
        self._closing = True
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
