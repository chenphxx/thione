"""文件系统操作：打开文件/文件夹、定位文件、清空目录。"""

import os
import subprocess
import sys


def open_file(path):
    """使用系统默认程序打开文件。"""
    if os.name == "nt":
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.call(["open", path])
    else:
        subprocess.call(["xdg-open", path])


def open_folder(path):
    """在系统文件管理器中打开文件夹。"""
    if os.name == "nt":
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.call(["open", path])
    else:
        subprocess.call(["xdg-open", path])


def reveal_file(path):
    """打开文件所在文件夹，并在文件管理器中选中该文件。"""
    folder = os.path.dirname(path)
    if os.name == "nt":
        subprocess.Popen(["explorer", f"/select,{path}"])
    else:
        open_folder(folder)


def clear_files_in_folder(folder):
    """删除文件夹内的所有文件（不递归，保留子文件夹）。

    返回被删除文件的完整路径列表，便于调用方统计。
    """
    removed = []
    for name in os.listdir(folder):
        full = os.path.join(folder, name)
        if os.path.isfile(full):
            os.remove(full)
            removed.append(full)
    return removed
