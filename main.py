"""thione 启动入口。

    1. 初始化日志 —— 之后所有异常都有迹可循;
    2. 单实例检测 —— 避免多开导致多个键盘钩子各弹各的窗口,
       第二个实例只负责把已有实例的主窗口唤到前台;
    3. 设置 AppUserModelID —— 让任务栏使用本程序图标而不是 python;
    4. 创建唯一的 Tk 根窗口, 交给外壳组装三个工具页面;
    5. 进入 mainloop —— 划词翻译的热键与托盘在各自的后台线程。
"""

import logging
import sys
import tkinter as tk

from app import logging_setup, win32
from app.errors import show_exception
from app.settings import AppSettings
from app.shell import ShellWindow
from app.tools import TOOL_PAGES

logger = logging.getLogger("thione")


class Application:
    """进程级应用对象: 负责单实例、外壳窗口与退出清理。"""

    def __init__(self):
        self.shell = None
        self._activation_server = None

    def run(self):
        logging_setup.install_excepthook()

        if not win32.acquire_single_instance():
            win32.notify_existing_instance()
            logger.info("已有实例在运行, 本实例退出")
            return 0

        win32.set_app_user_model_id()

        # 第二个实例启动时会被唤起, 由外壳把主窗口拉到前台 (经投递队列回到主线程)
        self._activation_server = win32.start_activation_server(
            lambda: self.shell and self.shell.post(self.shell.raise_window)
        )

        root = tk.Tk()
        self.shell = ShellWindow(root, AppSettings.load(), TOOL_PAGES)
        logger.info("thione 已就绪: 左侧选择工具, 双击 Ctrl 触发划词翻译")

        try:
            root.mainloop()
        except KeyboardInterrupt:
            self.shell.on_close()

        logger.info("thione 已退出")
        self._cleanup()
        return 0

    def _cleanup(self):
        server, self._activation_server = self._activation_server, None
        if server is not None:
            try:
                server.close()
            except OSError:
                pass


def main(argv=None):
    """进程入口, 返回退出码。"""
    argv = list(sys.argv[1:] if argv is None else argv)
    logging_setup.setup()
    logger.info(
        "thione 启动 (Python %s, frozen=%s, argv=%s)",
        sys.version.split()[0],
        bool(getattr(sys, "frozen", False)),
        argv or "-",
    )
    try:
        return Application().run()
    except Exception as exc:
        show_exception(exc, context="程序启动失败")
        return 1


def _flush_streams():
    """窗口模式下 sys.stdout/stderr 可能为 None (甚至整个属性都不存在)。"""
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        if stream is not None:
            try:
                stream.flush()
            except (OSError, ValueError):
                pass


if __name__ == "__main__":
    _code = main()
    # 打包后没有终端, 退出前的日志要立即落盘; 同时把退出码明确交给系统
    _flush_streams()
    sys.exit(_code)
