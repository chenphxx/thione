"""划词翻译的后台服务: 全局热键 + 系统托盘 + 主线程投递。

线程模型 (与独立版 transpy 一致, 这是本工具最容易出错的地方):

    主线程      —— 唯一的 Tk 根窗口与 mainloop, 所有窗口都只能在这里创建
    pynput 线程 —— 键盘监听, 只把待展示的文本投递到队列
    pystray线程 —— 托盘菜单, 回调同样只投递队列

跨线程一律不碰 tkinter 对象, 统一走 self._queue + root.after 轮询。

与独立版 transpy 的唯一区别是根窗口的来源: 这里不再自己创建 Tk, 也不跑
mainloop, 而是借用外壳的根窗口做定时轮询, 因此可以作为一个工具挂进工具箱。
"""

import logging
import queue
import threading

from ...constants import APP_TITLE
from ...errors import show_error
from .constants import UI_POLL_INTERVAL_MS
from .hotkey import DoubleCtrlListener
from .result_window import ResultWindow
from .translator import Translator

logger = logging.getLogger(__name__)


class TranslateService:
    """持有翻译器、热键监听与托盘图标的后台服务。

    参数:
        root:             外壳的根窗口 (用于 after 轮询, 并作为弹窗的 master)
        on_state_change:  callable(), 已配置/热键开关等状态变化时调用
        on_show_window:   callable(), 用户在托盘选择「打开主窗口」时调用
        on_exit:          callable(), 用户在托盘选择「退出」时调用
        theme:            ThemeManager, 仅用于让翻译结果弹窗跟随当前配色
    """

    def __init__(self, root, on_state_change=None, on_show_window=None,
                 on_exit=None, theme=None):
        self.root = root
        self._on_state_change = on_state_change
        self._on_show_window = on_show_window
        self._on_exit = on_exit
        self._theme = theme

        self.config = None
        self.translator = None
        self.last_result = ""
        self.paused = False

        self._queue = queue.Queue()
        self._listener = None
        self._tray = None
        self._poll_id = None
        self._running = False
        self._stopping = False

    # -- 生命周期 ---------------------------------------------------------
    @property
    def running(self):
        """翻译功能是否已启动, 即热键与托盘是否在工作。"""
        return self._running

    def start(self):
        """启动翻译: 建立全局热键监听并显示托盘图标。

        凭据尚未就绪时不会启动, 返回 False 交给调用方提示用户。
        程序启动时不自动调用, 由用户在划词翻译页面显式开启。
        """
        if self._running:
            return True
        if self.translator is None:
            return False

        self._stopping = False
        self._running = True
        # 每次启动都从「不暂停」开始, 避免上次的暂停状态让人以为热键坏了
        self.paused = False

        self._start_listener()
        self._ensure_tray()
        self._schedule_poll()
        logger.info("划词翻译已启动")
        self._notify_state()
        return True

    def stop(self):
        """停止翻译: 释放键盘钩子并移除托盘图标, 已保存的凭据不受影响。"""
        if not self._running:
            return

        self._running = False
        self.paused = False

        self._cancel_poll()
        self._stop_listener()
        self._stop_tray()
        logger.info("划词翻译已停止")
        self._notify_state()

    def shutdown(self):
        """进程退出前的收尾: 停掉翻译并禁止再续排定时器。"""
        self.stop()
        self._stopping = True

    # -- 组件开关 ---------------------------------------------------------
    def _start_listener(self):
        self._listener = DoubleCtrlListener(self.translator, self._on_result)
        self._listener.start()

    def _stop_listener(self):
        listener, self._listener = self._listener, None
        if listener is not None:
            listener.stop()

    def _stop_tray(self):
        tray, self._tray = self._tray, None
        if tray is None:
            return
        # pystray 的 stop 在 Windows 上偶有阻塞, 不能让它卡住退出流程
        stopper = threading.Thread(
            target=tray.stop, name="thione-tray-stop", daemon=True
        )
        stopper.start()
        stopper.join(timeout=2.0)

    def _cancel_poll(self):
        if self._poll_id is None:
            return
        try:
            self.root.after_cancel(self._poll_id)
        except Exception:
            logger.debug("取消轮询失败", exc_info=True)
        self._poll_id = None

    # -- 配置 -------------------------------------------------------------
    @property
    def ready(self):
        """凭据是否已就绪, 即是否具备启动翻译的条件。"""
        return self.translator is not None

    def set_config(self, config):
        """记住凭据并重建翻译客户端, 不改变运行状态。"""
        self.config = config
        self.translator = Translator(config)

        if self._listener is not None:
            # 运行中改凭据: 热键监听下一次调用就会用上新的客户端
            self._listener.translator = self.translator

        logger.info("凭据已装载 (region=%s)", config.region)
        self._notify_state()

    # -- 热键开关 ---------------------------------------------------------
    def set_paused(self, paused):
        """暂停或恢复全局热键。"""
        self.paused = bool(paused)
        if self._listener is not None:
            if self.paused:
                self._listener.pause()
            else:
                self._listener.resume()
        if self._tray is not None:
            self._tray.set_paused(self.paused)
        self._notify_state()

    def toggle_paused(self):
        """在暂停与恢复之间切换, 返回切换后的状态。"""
        self.set_paused(not self.paused)
        return self.paused

    # -- 托盘 -------------------------------------------------------------
    def _ensure_tray(self):
        """创建并启动托盘图标; 托盘不可用不应导致程序无法运行。"""
        if self._tray is not None:
            return
        try:
            from .tray import TrayIcon

            self._tray = TrayIcon(
                on_show=lambda: self._post(self._request_show),
                on_pause=lambda paused: self._post(
                    lambda: self.set_paused(paused)
                ),
                on_exit=lambda: self._post(self._request_exit),
            )
            self._tray.set_paused(self.paused)
            self._tray.start()
        except Exception:
            self._tray = None
            logger.exception("托盘图标不可用")
            show_error(
                f"系统托盘图标初始化失败, 划词翻译仍会在后台工作。\n"
                f"如需退出, 直接关闭 {APP_TITLE} 主窗口即可。\n"
                f"详情见日志文件。",
                parent=self.root,
            )

    def _request_show(self):
        if self._on_show_window is not None:
            self._on_show_window()

    def _request_exit(self):
        if self._on_exit is not None:
            self._on_exit()

    # -- 跨线程投递 -------------------------------------------------------
    def _post(self, action):
        """任何线程都可以调用, 把要在主线程执行的动作排队。"""
        self._queue.put(action)

    def _schedule_poll(self):
        if self._stopping:
            return
        try:
            self._poll_id = self.root.after(UI_POLL_INTERVAL_MS, self._dispatch)
        except Exception:
            self._poll_id = None

    def _dispatch(self):
        """主线程轮询: 只在这里执行后台线程排队的动作。"""
        self._poll_id = None
        if self._stopping:
            return
        while True:
            try:
                action = self._queue.get_nowait()
            except queue.Empty:
                break
            try:
                action()
            except Exception:
                logger.exception("处理后台任务失败")
        self._schedule_poll()

    # -- 翻译结果 ---------------------------------------------------------
    def _on_result(self, text):
        """热键线程的结果回调: 只投递, 绝不在这里碰 tkinter。"""
        self._post(lambda: self._show_result(text))

    def _show_result(self, text):
        self.last_result = text
        self._notify_state()
        try:
            ResultWindow(self.root, text, theme=self._theme)
        except Exception:
            logger.exception("显示翻译结果失败")

    def _notify_state(self):
        if self._on_state_change is None:
            return
        try:
            self._on_state_change()
        except Exception:
            logger.exception("刷新翻译状态失败")
