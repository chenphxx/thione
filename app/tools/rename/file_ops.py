"""批量重命名专属的目录清理。

打开文件 打开目录 定位文件已移到共享层 app/win32.py。
"""

import os


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
