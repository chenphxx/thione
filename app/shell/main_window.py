"""管理应用外壳, 工具页面切换及工作线程到界面的消息队列

窗口由左侧固定宽度 208 像素的导航栏与右侧主列组成, 主列自上而下是页面内容区
与 32 像素高的状态栏; 状态栏的内容由当前页面通过 StatusRow 填充
"""

import logging
import queue
import tkinter as tk
from tkinter import ttk

from .. import kit, win32
from ..constants import (APP_ICON, APP_MIN_SIZE, APP_SIZE, APP_TITLE,
                         QUEUE_POLL_MS)
from ..dpi import scale
from ..errors import open_path, show_error
from ..paths import ensure_dir, resource_path, user_log_dir
from ..theme import BODY_PAD_X, SIZE_LABEL, STATUSBAR_HEIGHT, ThemeManager, tint
from .sidebar import Sidebar

logger = logging.getLogger(__name__)

#: 侧栏拖拽分隔条的宽度
SPLITTER_WIDTH = scale(5)


class ShellWindow:
    """承载侧栏, 工具页面和应用状态栏"""

    def __init__(self, root, settings, page_classes):
        self.root = root
        self.settings = settings
        self._page_classes = list(page_classes)
        self._pages = {}
        self._current_key = None
        self._indicators = {}
        self._queue = queue.Queue()
        self._queue_job = None
        self._show_job = None
        self._splitter_origin = None
        self._closing = False

        root.title(APP_TITLE)
        self._apply_window_icon()
        root.geometry(APP_SIZE)
        root.minsize(*APP_MIN_SIZE)

        self.theme = ThemeManager(root, settings.theme)
        self._build_layout()
        self._build_pages()
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.bind_all("<Control-t>", self.toggle_theme)

        self.show(self._initial_key())
        self._queue_job = root.after(QUEUE_POLL_MS, self._drain_queue)

    def _apply_window_icon(self):
        """把程序图标写到窗口上

        任务栏与 Alt+Tab 显示的是窗口图标: 源码运行时进程图标是 python, 不设置
        的话任务栏就不显示本程序的图标; default 让之后创建的对话框也沿用
        """
        icon = resource_path(APP_ICON)
        try:
            self.root.iconbitmap(default=icon)
        except tk.TclError:
            logger.debug("Tk 默认图标设置失败", exc_info=True)
        self.root.update_idletasks()
        if not win32.set_window_icon(self.root.winfo_id(), icon):
            logger.warning("设置窗口图标失败: %s", icon)

    # ---------------- 布局 ----------------
    def _build_layout(self):
        """建立导航栏 内容区与状态栏"""
        body = tk.Frame(self.root, bd=0, highlightthickness=0)
        tint(body, bg="canvas")
        body.configure(bg=self.theme.rgb("canvas"))
        body.pack(side="top", fill="both", expand=True)

        self.sidebar = Sidebar(
            body,
            self.theme,
            [(cls.key, cls.icon, cls.title) for cls in self._page_classes],
            on_select=self.show,
            on_toggle_theme=self.toggle_theme,
            on_open_log=self.open_log_folder,
        )
        self.sidebar.pack(side="left", fill="y")

        # 侧栏与主列之间的拖拽条: 平时与页面同色, 指针进入或拖动时用强调色
        self.splitter = ttk.Frame(body, style="Drag.TFrame",
                                  width=SPLITTER_WIDTH,
                                  cursor="sb_h_double_arrow")
        self.splitter.pack_propagate(False)
        self.splitter.pack(side="left", fill="y")
        self.splitter.bind("<Button-1>", self._on_splitter_press)
        self.splitter.bind("<B1-Motion>", self._on_splitter_drag)
        self.splitter.bind("<ButtonRelease-1>", self._on_splitter_release)
        self.splitter.bind("<Enter>", lambda _e: self._hover_splitter(True))
        self.splitter.bind("<Leave>", lambda _e: self._hover_splitter(False))

        main = tk.Frame(body, bd=0, highlightthickness=0)
        tint(main, bg="canvas")
        main.configure(bg=self.theme.rgb("canvas"))
        main.pack(side="left", fill="both", expand=True)
        self._build_statusbar(main)

        self.content = tk.Frame(main, bd=0, highlightthickness=0)
        tint(self.content, bg="canvas")
        self.content.configure(bg=self.theme.rgb("canvas"))
        self.content.pack(side="top", fill="both", expand=True)

    # ---------------- 侧栏拖拽 ----------------
    def _on_splitter_press(self, event):
        """记下拖动起点与当时的侧栏宽度

        @param event: 鼠标按下事件
        """
        self._splitter_origin = (event.x_root, self.sidebar.width)

    def _on_splitter_drag(self, event):
        """按横向移动量调整侧栏宽度

        @param event: 鼠标拖动事件
        """
        if self._splitter_origin is None:
            return
        start_x, start_width = self._splitter_origin
        self.sidebar.set_width(start_width + event.x_root - start_x)

    def _on_splitter_release(self, _event):
        """结束拖动, 分隔条回到平时的颜色"""
        self._splitter_origin = None
        self.splitter.configure(style="Drag.TFrame")

    def _hover_splitter(self, hovering):
        """指针进入与离开时分隔条换色

        @param hovering: 指针是否在分隔条上
        """
        if self._splitter_origin is not None:
            return
        self.splitter.configure(
            style="DragHover.TFrame" if hovering else "Drag.TFrame")

    def _build_statusbar(self, master):
        """建立状态栏, 左右两端留给当前页面填充内容

        @param master: 主列容器
        """
        bar = tk.Frame(master, bd=0, highlightthickness=0,
                       height=STATUSBAR_HEIGHT)
        tint(bar, bg="side")
        bar.configure(bg=self.theme.rgb("side"))
        bar.pack(side="bottom", fill="x")
        bar.pack_propagate(False)
        kit.hairline(bar, self.theme).pack(side="top", fill="x")

        inner = tk.Frame(bar, bd=0, highlightthickness=0)
        tint(inner, bg="side")
        inner.configure(bg=self.theme.rgb("side"))
        inner.pack(fill="both", expand=True, padx=BODY_PAD_X)

        self.status_left = tk.Frame(inner, bd=0, highlightthickness=0)
        tint(self.status_left, bg="side")
        self.status_left.configure(bg=self.theme.rgb("side"))
        self.status_left.pack(side="left", fill="y")
        self.status_right = tk.Frame(inner, bd=0, highlightthickness=0)
        tint(self.status_right, bg="side")
        self.status_right.configure(bg=self.theme.rgb("side"))
        self.status_right.pack(side="right", fill="y")

        # 与页面无关的常驻提示 (例如翻译是否已启动), 没有内容时整块收起
        self._indicator_frame = tk.Frame(self.status_left, bd=0,
                                         highlightthickness=0)
        tint(self._indicator_frame, bg="side")
        self._indicator_frame.configure(bg=self.theme.rgb("side"))
        self._indicator = kit.text(self._indicator_frame, self.theme,
                                   size=SIZE_LABEL, token="muted", bold=True,
                                   surface="side")
        self._indicator.pack(side="left")

    def new_status(self):
        """为页面建立一块状态栏内容

        @return: kit.StatusRow 实例
        """
        return kit.StatusRow(self.status_left, self.status_right, self.theme)

    def _build_pages(self):
        for page_class in self._page_classes:
            self._pages[page_class.key] = page_class(self.content, self)

    # ---------------- 页面切换 ----------------
    def _initial_key(self):
        keys = [page_class.key for page_class in self._page_classes]
        return self.settings.page if self.settings.page in keys else keys[0]

    def show(self, key):
        """切换到指定工具并通知页面生命周期钩子

        @param key: 工具标识
        """
        if key not in self._pages or key == self._current_key:
            return
        previous = self._pages.get(self._current_key)
        if previous is not None:
            previous.on_hide()
            previous.status.hide()
            previous.pack_forget()
        page = self._pages[key]
        page.pack(fill="both", expand=True)
        page.status.show()
        self._current_key = key
        self.sidebar.set_active(key)
        self.settings.page = key
        self._schedule_show(key)

    def _schedule_show(self, key):
        """把页面的 on_show 推迟到本次事件处理完再执行

        页面首次显示时可能要做一些准备 (读配置 列设备 找外部程序), 排在空闲时执行 Tk
        会先把新页面画出来, 用户看到的是立刻切换, 而不是一段没有反应的等待

        @param key: 刚切换到的页面标识
        """
        self._show_job = self.root.after_idle(lambda: self._run_show(key))

    def _run_show(self, key):
        """执行页面的 on_show, 页面已经切换走时跳过

        @param key: 页面标识
        """
        self._show_job = None
        if key != self._current_key:
            return
        page = self._pages.get(key)
        if page is None:
            return
        # 先把待处理的绘制做掉, 钩子里耗时的准备才不会把页面挡在屏幕外
        self.root.update_idletasks()
        try:
            page.on_show()
        except Exception:
            logger.exception("页面显示失败: %s", key)

    def toggle_theme(self, _event=None):
        """切换浅色与深色外观并保存用户选择"""
        mode = "dark" if self.theme.mode == "light" else "light"
        if not self.theme.set_mode(mode):
            return "break"
        self.settings.theme = mode
        self.settings.save()
        self.sidebar.set_theme(mode)
        for page in self._pages.values():
            page.on_theme_changed()
        return "break"

    def open_log_folder(self):
        """打开运行日志目录, 供用户查看日志或反馈问题"""
        folder = user_log_dir()
        try:
            ensure_dir(folder)
        except OSError:
            logger.exception("创建日志目录失败: %s", folder)
            show_error("无法创建日志目录:\n%s" % folder, parent=self.root)
            return
        open_path(folder, parent=self.root)

    # ---------------- 状态栏 ----------------
    def set_status(self, message):
        """把提示写到当前页面的状态栏

        @param message: 提示文字
        """
        page = self._pages.get(self._current_key)
        if page is not None:
            page.status.set_text(message or "")

    def set_indicator(self, key, text):
        """设置与页面无关的常驻提示

        @param key: 提示来源标识, 例如 translate
        @param text: 提示文字, 空串表示清除
        """
        if text:
            self._indicators[key] = text
        else:
            self._indicators.pop(key, None)
        value = "   ·   ".join(self._indicators.values())
        self._indicator.configure(text=value)
        if value:
            self._indicator_frame.pack(side="left", padx=(scale(12), 0))
        else:
            self._indicator_frame.pack_forget()

    # ---------------- 跨线程消息 ----------------
    def post(self, action):
        """将回调加入队列, 由 Tk 主线程执行

        @param action: 无参可调用对象
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
                logger.exception("Shell action failed")
        try:
            self._queue_job = self.root.after(QUEUE_POLL_MS, self._drain_queue)
        except tk.TclError:
            self._queue_job = None

    def raise_window(self):
        """还原并聚焦主窗口, 供托盘回调使用"""
        try:
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
        except tk.TclError:
            logger.debug("Could not restore the main window", exc_info=True)

    def on_close(self):
        """通知活动页面清理资源, 保存偏好并关闭窗口"""
        for page in list(self._pages.values()):
            try:
                if not page.on_close():
                    return
            except Exception:
                logger.exception("Shell action failed")
        self._closing = True
        if self._show_job is not None:
            try:
                self.root.after_cancel(self._show_job)
            except tk.TclError:
                pass
            self._show_job = None
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
