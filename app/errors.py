"""面向用户的提示与错误展示"""

import logging
import os
import traceback
from tkinter import messagebox

from .constants import APP_TITLE
from .win32 import open_file, open_folder, reveal_file

logger = logging.getLogger(__name__)

MAX_DETAIL = 1200


def show_error(message, title=APP_TITLE, parent=None):
    messagebox.showerror(title, message, parent=parent)


def show_exception(exc, context="", title=APP_TITLE, parent=None):
    """把异常连同堆栈写进日志, 并给用户一条可读的提示"""
    logger.error("%s: %s", context or title, exc, exc_info=True)
    message = f"{context}\n\n{exc}" if context else str(exc)
    detail = traceback.format_exc()
    if len(detail) > MAX_DETAIL:
        detail = detail[:MAX_DETAIL] + "\n...(详见日志)"
    show_error(f"{message}\n\n技术细节:\n{detail}", title=title, parent=parent)


def open_path(path, parent=None, reveal=False):
    """打开文件或目录, 失败时弹出统一提示

    @param path: 目标路径, 文件或目录均可
    @param parent: 弹窗挂靠的窗口
    @param reveal: True 时打开所在目录并选中该文件
    @return: 是否成功
    """
    if reveal:
        opener = reveal_file
    else:
        # 目录交给 open_folder, 失败时日志里能区分文件与目录
        opener = open_folder if os.path.isdir(path) else open_file
    if opener(path):
        return True
    show_error(f"无法打开: {path}", parent=parent)
    return False
