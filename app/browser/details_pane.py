"""底部详细信息窗格: 展示当前选中对象的属性

一行 5 列, 每列上方是 12 像素的字段名, 下方是取值; 窗格顶部一条 1 像素分隔线
"""

import os
import time
import tkinter as tk

from .. import kit
from ..dpi import scale
from ..imaging import image_size
from ..theme import SIZE_BODY, SIZE_LABEL, tint
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
    """超长时保留尾部, 路径与长文件名都能看出关键信息

    @param text: 原始文本
    @param limit: 最大字符数
    @return: 截断后的文本
    """
    return text if len(text) <= limit else "..." + text[-(limit - 3):]


class DetailsPane(tk.Frame):
    """显示选中文件的属性; 选中为空时所有字段显示占位符"""

    def __init__(self, master, theme):
        super().__init__(master, bd=0, highlightthickness=0)
        self.theme = theme
        tint(self, bg="panel")
        self.configure(bg=theme.rgb("panel"))
        hair = kit.hairline(self, theme)
        hair.pack(side="top", fill="x")
        inner = tk.Frame(self, bd=0, highlightthickness=0,
                         height=DETAILS_HEIGHT)
        tint(inner, bg="panel")
        inner.configure(bg=theme.rgb("panel"))
        inner.pack(side="top", fill="both", expand=True, padx=scale(14),
                   pady=scale(8))
        inner.pack_propagate(False)

        self._values = {}
        for index, (key, caption, weight) in enumerate(FIELDS):
            column = tk.Frame(inner, bd=0, highlightthickness=0)
            tint(column, bg="panel")
            column.configure(bg=theme.rgb("panel"))
            column.grid(row=0, column=index, sticky="nsew",
                        padx=(0, scale(20)))
            kit.text(column, theme, value=caption, size=SIZE_LABEL,
                     token="muted", surface="panel").pack(anchor="w")
            label = kit.text(column, theme, value="-", size=SIZE_BODY,
                             surface="panel")
            label.pack(anchor="w", fill="x", pady=(scale(2), 0))
            self._values[key] = label
            inner.columnconfigure(index, weight=weight)

        self.show(None)

    def show(self, path):
        """按选中文件刷新各字段; path 为空或不存在时回到占位状态

        @param path: 文件路径
        """
        if not path or not os.path.isfile(path):
            for label in self._values.values():
                label.configure(text="-")
            return

        name = os.path.basename(path)
        ext = os.path.splitext(name)[1].lower()
        self._values["name"].configure(text=_shorten(name))
        self._values["kind"].configure(text=self._kind_text(path, ext))
        self._values["size"].configure(text=self._format_size(self._size(path)))
        self._values["modified"].configure(text=self._modified(path))
        self._values["location"].configure(text=_shorten(os.path.dirname(path)))

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
        """类型描述; 图片额外带上像素尺寸

        @param path: 文件路径
        @param ext: 小写扩展名
        @return: 类型描述
        """
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
