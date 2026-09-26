"""面向用户的提示与错误展示。

集成后的程序始终存在一个可见的主窗口, 因此直接使用 tkinter 的 messagebox
即可; 传入 parent 能保证弹窗挂在正确的窗口之上。

打开文件与打开目录同样需要失败提示, 因此一并收在这里, 各工具调用同一份,
不会再出现同一个动作在不同页面提示不同文案的情况。
"""

import logging
import traceback
from tkinter import messagebox

from .constants import APP_TITLE
from .win32 import open_file, reveal_file

logger = logging.getLogger(__name__)

MAX_DETAIL = 1200


def show_error(message, title=APP_TITLE, parent=None):
    messagebox.showerror(title, message, parent=parent)


def show_exception(exc, context="", title=APP_TITLE, parent=None):
    """把异常连同堆栈写进日志, 并给用户一条可读的提示。"""
    logger.error("%s: %s", context or title, exc, exc_info=True)
    message = f"{context}\n\n{exc}" if context else str(exc)
    detail = traceback.format_exc()
    if len(detail) > MAX_DETAIL:
        detail = detail[:MAX_DETAIL] + "\n...(详见日志)"
    show_error(f"{message}\n\n技术细节:\n{detail}", title=title, parent=parent)


def open_path(path, parent=None, reveal=False):
    """打开文件或目录, 失败时弹出统一提示。

    @param path: 目标路径, 文件或目录均可
    @param parent: 弹窗挂靠的窗口
    @param reveal: True 时打开所在目录并选中该文件
    @return: 是否成功
    """
    opener = reveal_file if reveal else open_file
    if opener(path):
        return True
    show_error(f"无法打开: {path}", parent=parent)
    return False
