"""面向用户的提示与错误展示。

集成后的程序始终存在一个可见的主窗口, 因此直接使用 tkinter 的 messagebox
即可; 传入 parent 能保证弹窗挂在正确的窗口之上。
"""

import logging
import traceback
from tkinter import messagebox

from .constants import APP_TITLE

logger = logging.getLogger(__name__)

MAX_DETAIL = 1200


def show_info(message, title=APP_TITLE, parent=None):
    messagebox.showinfo(title, message, parent=parent)


def show_warning(message, title=APP_TITLE, parent=None):
    messagebox.showwarning(title, message, parent=parent)


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
