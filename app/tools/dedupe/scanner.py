"""文件夹扫描与图片识别。

缩略图与占位图已收进 app/imaging.py, 文件预览面板也在用同一份。
"""

import os

from .constants import SUPPORTED_IMAGE_EXTS


def scan_folder(folder):
    """递归扫描文件夹, 返回 (全部文件路径列表, 排序后的扩展名列表)。"""
    files = []
    exts = set()
    for root, dirs, filenames in os.walk(folder):
        for name in filenames:
            path = os.path.join(root, name)
            ext = os.path.splitext(name)[1].lower()
            files.append(path)
            if ext:
                exts.add(ext)
    return files, sorted(exts)


def is_image_file(path):
    """根据扩展名判断是否为支持的图片文件。"""
    return os.path.splitext(path)[1].lower() in SUPPORTED_IMAGE_EXTS
