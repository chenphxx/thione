"""文件夹面板: 一个文件夹里的待改名文件

面板头部左侧是文件夹路径, 右侧是文件数; 内容区是文件视图, 列表展示时每一行
画出 原名 -> 改后名. 面板高度贴合文件行数, 一屏放不下时由外层画布滚动
"""

import os
import tkinter as tk
from tkinter import filedialog, messagebox

from ... import kit
from ...browser import FileGrid
from ...errors import open_path
from .constants import LIST_MIN_HEIGHT

#: 内容区上下各留出的空白, 与设计稿的 10 像素内边距一致
BODY_PAD_Y = 10


class FolderCard(kit.Panel):
    """一个文件夹面板: 路径 文件数 与文件视图"""

    def __init__(self, parent, app):
        super().__init__(parent, app.theme, head=True,
                         body_pad=(14, BODY_PAD_Y))
        self.app = app
        self.folder_path = ""
        self.files = []
        self.filtered_files = []
        self.pack(fill="x", pady=(0, 12))

        self.body.pack_propagate(False)
        self.grid = FileGrid(self.body, app.theme, surface="panel",
                             tier=app.tier, view=app.view,
                             on_select=self._on_select,
                             on_activate=self.open_selected_file,
                             on_context=self._on_context_menu)
        self.grid.pack(fill="both", expand=True)
        self.grid.canvas.bind("<Configure>", self._on_grid_resize, add="+")
        self._fit_height()

        self.menu = tk.Menu(self, tearoff=0)
        self.menu.add_command(label="打开文件", command=self.open_selected_file)
        self.menu.add_command(label="打开所在文件夹",
                              command=self.open_file_location)
        self.menu.add_separator()
        self.menu.add_command(label="移除此文件夹", command=self.remove_block)

    # ---------------- 文件夹操作 ----------------
    def select_folder(self):
        """弹出目录选择框并读取其中的文件

        @return: 用户选定了文件夹时返回 True
        """
        folder = filedialog.askdirectory(parent=self.app.window)
        if not folder:
            return False
        self.folder_path = folder
        self.set_title(folder)
        self.load_files()
        return True

    def load_files(self):
        """重新读取文件夹下的文件 (不递归)"""
        self.files = []
        try:
            for name in sorted(os.listdir(self.folder_path), key=str.lower):
                if os.path.isfile(os.path.join(self.folder_path, name)):
                    self.files.append(name)
        except OSError as error:
            messagebox.showerror("错误", f"读取文件夹失败: {error}",
                                 parent=self.app.window)
            return
        self.filtered_files = list(self.files)
        self.set_right(f"{len(self.files)} 个文件")
        self.grid.set_files(self.paths())
        self.refresh_preview()
        self.app.refresh_overall_counts()
        self.app.on_file_selected(None)

    def paths(self):
        """当前展示文件的完整路径

        @return: 路径列表
        """
        return [os.path.join(self.folder_path, name)
                for name in self.filtered_files]

    def set_tier(self, tier):
        """切换缩略图档位; 由页面统一驱动, 保证各面板一致

        @param tier: 档位
        """
        self.grid.set_tier(tier)
        self._fit_height()

    def set_view(self, view):
        """切换展示方式; 由页面统一驱动, 保证各面板一致

        @param view: 展示方式
        """
        self.grid.set_view(view)
        self.refresh_preview()

    def refresh_preview(self):
        """重画 原名 -> 改后名 那一列, 并让面板高度重新贴合行数"""
        self.grid.set_secondary_text(self.app.new_name_of)
        self._fit_height()

    def remove_block(self):
        """从页面上移除这个文件夹"""
        self.destroy()
        self.app.remove_folder(self)

    def fit_height(self):
        """让面板内容区高度重新贴合当前的文件行数

        切换列表与平铺后行高不同, 由页面统一调用
        """
        self._fit_height()

    def _on_grid_resize(self, _event=None):
        self._fit_height()

    def _fit_height(self):
        """面板内容区高度贴合文件行数"""
        self.body.configure(
            height=max(self.grid.content_height(), LIST_MIN_HEIGHT)
            + BODY_PAD_Y * 2)

    # ---------------- 选中与打开 ----------------
    def get_selected_path(self):
        """当前选中的文件路径

        @return: 路径或 None
        """
        return self.grid.selected_path()

    def _on_select(self, path):
        self.app.on_file_selected(path)

    def _on_context_menu(self, path, event):
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    def open_selected_file(self, path=None):
        """用系统默认程序打开选中文件

        @param path: 文件路径, 省略时取选中项
        """
        path = path or self.get_selected_path()
        if path:
            open_path(path, parent=self.app.window)

    def open_file_location(self):
        """在资源管理器中定位选中文件"""
        path = self.get_selected_path()
        if path:
            open_path(path, parent=self.app.window, reveal=True)
