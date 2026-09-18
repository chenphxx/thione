"""底部详细信息窗格: 展示当前选中对象的属性。

字段与 Windows 资源管理器的详细信息窗格保持一致 (名称 类型 大小 修改时间
位置), 图片额外带上像素尺寸, 便于查重时判断两张图是不是同一张
"""

import os
import time
from tkinter import ttk

from ..imaging import image_size
from .constants import DETAILS_HEIGHT, IMAGE_EXTS, TABLE_EXTS, TEXT_EXTS

#: (键, 标题, 列宽权重)
FIELDS = (
    ("name", "名称", 3),
    ("kind", "类型", 2),
    ("size", "大小", 1),
    ("modified", "修改时间", 2),
    ("location", "位置", 4),
)

#: 单个字段的最大字符数, 超出时保留尾部
VALUE_LIMIT = 46


def _shorten(text, limit=VALUE_LIMIT):
    """超长时保留尾部, 路径与长文件名都能看出关键信息。"""
    return text if len(text) <= limit else "..." + text[-(limit - 3):]


class DetailsPane(ttk.Frame):
    """显示选中文件的属性; 选中为空时所有字段显示占位符。"""

    def __init__(self, master, theme):
        super().__init__(master, style="Panel.TFrame", padding=(16, 8))
        self.configure(height=DETAILS_HEIGHT)
        self.pack_propagate(False)
        self.theme = theme

        self._values = {}
        for index, (key, caption, weight) in enumerate(FIELDS):
            column = ttk.Frame(self, style="Panel.TFrame")
            column.grid(row=0, column=index, sticky="nsew", padx=(0, 20))
            ttk.Label(column, text=caption,
                      style="PanelMuted.TLabel").pack(anchor="w")
            label = ttk.Label(column, text="-", style="Panel.TLabel",
                              anchor="w")
            label.pack(anchor="w", fill="x")
            self._values[key] = label
            self.columnconfigure(index, weight=weight)

        self.show(None)

    def show(self, path):
        """按选中文件刷新各字段; path 为空或不存在时回到占位状态。"""
        if not path or not os.path.isfile(path):
            for label in self._values.values():
                label.config(text="-")
            return

        name = os.path.basename(path)
        ext = os.path.splitext(name)[1].lower()
        self._values["name"].config(text=_shorten(name))
        self._values["kind"].config(text=self._kind_text(path, ext))
        self._values["size"].config(text=self._format_size(self._size(path)))
        self._values["modified"].config(text=self._modified(path))
        self._values["location"].config(text=_shorten(os.path.dirname(path)))

    # ---------------- 字段 ----------------
    @staticmethod
    def _size(path):
        try:
            return os.path.getsize(path)
        except OSError:
            return 0

    @staticmethod
    def _modified(path):
        try:
            stamp = os.path.getmtime(path)
        except OSError:
            return "-"
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(stamp))

    def _kind_text(self, path, ext):
        """类型描述; 图片额外带上像素尺寸。"""
        if ext in IMAGE_EXTS:
            kind = f"{ext.lstrip('.').upper()} 图片"
            size = image_size(path)
            return f"{kind} ({size[0]} x {size[1]})" if size else kind
        if ext in TEXT_EXTS:
            return f"{ext.lstrip('.').upper()} 文本"
        if ext in TABLE_EXTS:
            return f"{ext.lstrip('.').upper()} 表格"
        if ext:
            return f"{ext.lstrip('.').upper()} 文件"
        return "文件"

    @staticmethod
    def _format_size(size):
        if size < 1024:
            return f"{size} B"
        if size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        return f"{size / 1024 / 1024:.1f} MB"
