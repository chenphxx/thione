"""文件夹卡片: 选择路径 筛选与文件视图。

卡片本身撑满所在区域, 文件网格再撑满卡片的剩余高度, 因此批量重命名页下方
不会留白; 卡片多到一屏放不下时由外层画布滚动
"""

import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from ...browser import FileGrid
from ...errors import open_path
from .constants import LIST_MIN_HEIGHT


class FolderCard(ttk.LabelFrame):
    """一个文件夹卡片: 路径 筛选 计数 文件网格 删除按钮。"""

    def __init__(self, parent, app, idx):
        super().__init__(parent, text=f"文件夹 {idx}", padding=12)
        self.app = app
        self.idx = idx

        self.folder_path = ""
        self.files = []           # 文件名列表 (仅名称)
        self.filtered_files = []  # 筛选后的文件名列表

        self.pack(fill="both", expand=True, pady=(0, 12))

        # ---- 操作行 ----
        row = ttk.Frame(self, style="Card.TFrame")
        row.pack(fill="x", pady=(0, 10))

        self.btn_select = ttk.Button(row, text="选择文件夹",
                                     style="Secondary.TButton",
                                     command=self.select_folder)
        self.btn_select.pack(side="left")

        # 路径输入框是这一行里唯一会被压缩的控件, 因此把它的最小宽度设小
        self.entry_path = ttk.Entry(row, width=12)
        self.entry_path.pack(side="left", fill="x", expand=True, padx=(8, 8))

        ttk.Label(row, text="筛选", style="Card.TLabel").pack(side="left")
        self.combo_filter = ttk.Combobox(row, state="readonly", width=8)
        self.combo_filter.pack(side="left", padx=(6, 8))
        self.combo_filter.bind("<<ComboboxSelected>>", lambda e: self.apply_filter())

        self.lbl_counts = ttk.Label(row, text="总数 0 · 筛选 0",
                                    style="CardMuted.TLabel", width=18,
                                    anchor="center")
        self.lbl_counts.pack(side="left", padx=(0, 8))

        self.btn_delete = ttk.Button(row, text="删除", style="Danger.TButton",
                                     command=self.delete_block)
        self.btn_delete.pack(side="left")

        # ---- 文件网格: 撑满卡片剩余高度 ----
        self.list_frame = ttk.Frame(self, style="Card.TFrame",
                                    height=LIST_MIN_HEIGHT)
        self.list_frame.pack_propagate(False)
        self.list_frame.pack(fill="both", expand=True)

        self.grid = FileGrid(self.list_frame, app.theme, surface="card",
                             tier=app.tier, view=app.view,
                             on_select=self._on_select,
                             on_activate=self.open_selected_file,
                             on_context=self._on_context_menu)
        self.grid.pack(fill="both", expand=True)

        # ---- 右键菜单 ----
        self.menu = tk.Menu(self, tearoff=0)
        self.menu.add_command(label="打开文件", command=self.open_selected_file)
        self.menu.add_command(label="打开所在文件夹",
                              command=self.open_file_location)

    # ---------------- 文件夹操作 ----------------
    def select_folder(self):
        folder = filedialog.askdirectory()
        if not folder:
            return
        self.folder_path = folder
        self.entry_path.delete(0, tk.END)
        self.entry_path.insert(0, folder)
        self.load_files()
        self.app.refresh_overall_counts()

    def load_files(self):
        self.files = []
        self.filtered_files = []
        # 只列出文件夹下的文件 (不递归)
        try:
            for name in os.listdir(self.folder_path):
                full = os.path.join(self.folder_path, name)
                if os.path.isfile(full):
                    self.files.append(name)
        except Exception as e:
            messagebox.showerror("错误", f"读取文件夹失败: {e}")
            return

        # 计算扩展名
        exts = sorted({os.path.splitext(n)[1].lower() for n in self.files if os.path.splitext(n)[1]})
        values = ["全部"] + exts if exts else ["全部"]
        self.combo_filter["values"] = values
        self.combo_filter.set("全部")
        self.apply_filter()

    def apply_filter(self):
        sel = self.combo_filter.get()
        if sel == "全部" or not sel:
            self.filtered_files = list(self.files)
        else:
            self.filtered_files = [n for n in self.files if n.lower().endswith(sel)]
        self.grid.set_files(
            [os.path.join(self.folder_path, n) for n in self.filtered_files])
        self.lbl_counts.config(
            text=f"总数 {len(self.files)} · 筛选 {len(self.filtered_files)}")
        self.app.refresh_overall_counts()
        # 列表内容变化后清空预览
        self.app.on_file_selected(None)

    def set_tier(self, tier):
        """切换缩略图档位; 由页面统一驱动, 保证各卡片一致。"""
        self.grid.set_tier(tier)

    def set_view(self, view):
        """切换展示方式; 由页面统一驱动, 保证各卡片一致。"""
        self.grid.set_view(view)
    def delete_block(self):
        # 按要求直接删除, 不提示
        self.destroy()
        # 从 app 中移除
        self.app.remove_folder(self)

    # ---------------- 选中与打开 ----------------
    def get_selected_path(self):
        return self.grid.selected_path()

    def _on_select(self, path):
        self.app.on_file_selected(path)

    def _on_context_menu(self, path, event):
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    def open_selected_file(self, path=None):
        path = path or self.get_selected_path()
        if path:
            open_path(path, parent=self.winfo_toplevel())

    def open_file_location(self):
        path = self.get_selected_path()
        if path:
            open_path(path, parent=self.winfo_toplevel(), reveal=True)
