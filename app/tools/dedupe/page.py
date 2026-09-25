"""图片查重页面: 图标视图浏览文件夹, 预览窗格与重复查找入口。

列表按 Windows 资源管理器的方式组织: 主区是缩略图网格, 右侧是可收起的
预览窗格, 底部是可收起的详细信息窗格, 缩略图大小分小 中 大三档
"""

import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from ...browser import (
    DetailsPane,
    FileGrid,
    PaneToggles,
    PreviewPane,
    ViewSwitch,
)
from ...browser.constants import DEFAULT_TIER, DEFAULT_VIEW
from ...errors import open_path
from ...shell.page import ToolPage
from ...widgets import unbind_mousewheel
from .constants import PAGE_TITLE
from .dedupe import dedupe_worker
from .duplicate_window import DuplicateGroupWindow
from .scanner import is_image_file, scan_folder


class DedupePage(ToolPage):
    """按感知哈希查找重复图片的工具页面。"""

    key = "dedupe"
    title = "图片查重"
    icon = "🔍"
    subtitle = "查找并整理文件夹内的重复图片"

    def __init__(self, master, shell):
        super().__init__(master, shell)

        self.current_folder = ""
        self.all_files = []
        self.filtered_files = []
        self.extensions = []
        self.tier = DEFAULT_TIER
        self.view = DEFAULT_VIEW
        self.preview_visible = False
        self.details_visible = False
        self.dedupe_thread = None
        self.dedupe_stop_event = None
        self.progress_queue = queue.Queue()
        self.duplicates = []

        self._build_toolbar()
        self.add_divider()
        self._build_main_area()
        self._build_statusbar()
        self._build_details()

        self.root.after(200, self._poll_progress_queue)

    # -------------------------- 界面构建 --------------------------
    def _build_toolbar(self):
        bar, head, actions = self.build_toolbar()

        ttk.Label(head, text=PAGE_TITLE, style="PanelHeader.TLabel").pack(side="left")
        ttk.Label(head, text="扫描文件夹, 找出视觉上重复的图片",
                  style="PanelHint.TLabel").pack(side="left", padx=(12, 0))

        ttk.Button(actions, text="查找重复项", style="Accent.TButton",
                   command=self.on_find_duplicates).pack(side="right")
        ttk.Button(actions, text="刷新扫描", style="Secondary.TButton",
                   command=self._rescan_current_folder).pack(side="right",
                                                             padx=(0, 8))
        self.btn_preview = ttk.Button(actions, text="预览",
                                      style="Secondary.TButton",
                                      command=self.toggle_preview)
        self.btn_preview.pack(side="right", padx=(0, 8))

        row = ttk.Frame(bar, style="Panel.TFrame")
        row.pack(side="top", fill="x", pady=(10, 0))

        # 先 pack 右侧控件再 pack 左侧的伸缩项, 否则右侧会被挤到可视区之外
        self.view_switch = ViewSwitch(row, self._on_view_change,
                                      self._on_tier_change, self.view,
                                      self.tier)
        self.view_switch.pack(side="right", padx=(0, 16))
        ttk.Label(row, text="视图", style="Panel.TLabel").pack(
            side="right", padx=(0, 6))

        self.combo_ext = ttk.Combobox(row, state="readonly", width=10)
        self.combo_ext.pack(side="right", padx=(6, 16))
        self.combo_ext.bind("<<ComboboxSelected>>",
                            lambda e: self.apply_filter_and_show_list())
        ttk.Label(row, text="筛选类型", style="Panel.TLabel").pack(side="right")

        ttk.Button(row, text="选择文件夹", style="Secondary.TButton",
                   command=self.on_select_folder).pack(side="left")
        self.lbl_folder = ttk.Label(row, text="当前文件夹: (未选择)",
                                    style="PanelMuted.TLabel", anchor="w")
        self.lbl_folder.pack(side="left", padx=(10, 0), fill="x", expand=True)

    def _build_main_area(self):
        main = ttk.Frame(self)
        main.pack(side="top", fill="both", expand=True)

        # 可拖拽分隔的水平分栏: 左侧文件网格, 右侧预览窗格
        self.paned = ttk.Panedwindow(main, orient="horizontal")
        self.paned.pack(side="top", fill="both", expand=True)

        list_frame = ttk.Frame(self.paned, padding=(16, 12))
        self.paned.add(list_frame, weight=1)

        # 文件网格与空状态占位块共用同一块区域, 按需要显示其中之一
        self.grid_box = ttk.Frame(list_frame)
        self.grid_box.pack(side="top", fill="both", expand=True)
        self.grid = FileGrid(self.grid_box, self.theme,
                             on_select=self._on_select_file,
                             on_activate=self._open_file,
                             on_context=self._on_context_menu,
                             tier=self.tier, view=self.view)
        self.grid.pack(fill="both", expand=True)

        self.empty_state = self._build_empty_state(list_frame)
        self._update_empty_state()

        self.menu = tk.Menu(self, tearoff=0)
        self.menu.add_command(label="打开文件", command=self._open_selected_file)
        self.menu.add_command(label="打开所在文件夹",
                              command=self._open_file_location)

        self.preview = PreviewPane(self.paned, self.theme)
        self.paned.add(self.preview, weight=0)
        self.paned.forget(self.preview)  # 默认收起

    def _build_empty_state(self, parent):
        """建立文件网格的空状态占位块。

        没有可显示的文件时用它顶替网格, 给出下一步该做什么, 而不是留一块白屏。

        @param parent: 承载占位块的父容器
        @return: 占位块 Frame (默认不显示)
        """
        box = ttk.Frame(parent, style="Card.TFrame")
        inner = ttk.Frame(box, style="Card.TFrame")
        inner.place(relx=0.5, rely=0.42, anchor="center")
        ttk.Label(inner, text="🗂", style="EmptyIcon.TLabel").pack()
        self.empty_title = ttk.Label(inner, text="", style="EmptyTitle.TLabel")
        self.empty_title.pack(pady=(8, 0))
        self.empty_hint = ttk.Label(inner, text="", style="EmptyHint.TLabel")
        self.empty_hint.pack(pady=(6, 0))
        return box

    def _update_empty_state(self):
        """按当前是否有可显示的文件, 在网格与空状态之间切换。"""
        if self.filtered_files:
            self.empty_state.pack_forget()
            self.grid_box.pack(side="top", fill="both", expand=True)
            return
        if self.current_folder:
            self.empty_title.config(text="这个文件夹里没有可显示的图片")
            self.empty_hint.config(text="换一个文件夹, 或者把筛选类型改回「全部」")
        else:
            self.empty_title.config(text="还没有选择文件夹")
            self.empty_hint.config(text="点击左上角的「选择文件夹」开始扫描")
        self.grid_box.pack_forget()
        self.empty_state.pack(side="top", fill="both", expand=True)

    def _build_statusbar(self):
        status = ttk.Frame(self, style="Panel.TFrame", padding=(16, 8))
        status.pack(side="bottom", fill="x")

        # 右下角的窗格开关, 与 Windows 资源管理器的位置一致
        self.toggles = PaneToggles(status, self.toggle_details,
                                   self.toggle_preview)
        self.toggles.pack(side="right")

        self.btn_stop = ttk.Button(status, text="终止", style="Danger.TButton",
                                   command=self.on_stop, state="disabled")
        self.btn_stop.pack(side="right", padx=(8, 12))

        self.lbl_counts = ttk.Label(status, text="0 个项目",
                                    style="PanelMuted.TLabel")
        self.lbl_counts.pack(side="left", padx=(0, 12))

        self.progress = ttk.Progressbar(status, orient="horizontal",
                                        mode="determinate")
        self.progress.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.lbl_progress_text = ttk.Label(status, text="", style="Panel.TLabel")
        self.lbl_progress_text.pack(side="left")

    def _build_details(self):
        """底部详细信息窗格; 在状态栏之后构建, 因此排在状态栏上方。"""
        self.details = DetailsPane(self, self.theme)

    # -------------------------- 视图切换 --------------------------
    def toggle_preview(self):
        """显示或收起右侧预览窗格。"""
        self.preview_visible = not self.preview_visible
        if self.preview_visible:
            self.paned.add(self.preview, weight=0)
        else:
            self.paned.forget(self.preview)
        self._sync_view_controls()

    def toggle_details(self):
        """显示或收起底部详细信息窗格。"""
        self.details_visible = not self.details_visible
        if self.details_visible:
            self.details.pack(side="bottom", fill="x")
        else:
            self.details.pack_forget()
        self._sync_view_controls()

    def _sync_view_controls(self):
        """把两个窗格的开关状态同步到右下角与工具条上的按钮。"""
        self.toggles.set_state(self.details_visible, self.preview_visible)
        self.btn_preview.configure(
            style="SegmentOn.TButton" if self.preview_visible
            else "Secondary.TButton")

    def _on_view_change(self, view):
        """切换列表与缩略图展示; 同一展示方式会被忽略。"""
        if view == self.view:
            return
        self.view = view
        self.grid.set_view(view)
        self.view_switch.set_state(self.view, self.tier)

    def _on_tier_change(self, tier):
        """切换缩略图档位; 在列表展示下点档位即切回缩略图展示。"""
        changed = tier != self.tier
        self.tier = tier
        self.grid.set_tier(tier)
        if self.view != "icons":
            self.view = "icons"
            self.grid.set_view("icons")
        elif not changed:
            return
        self.view_switch.set_state(self.view, self.tier)
    def on_hide(self):
        """切走时解除滚轮绑定, 避免在其他页面上仍然响应本页的滚动。"""
        unbind_mousewheel(self.grid.canvas)

    # -------------------------- 文件操作 --------------------------
    def _on_select_file(self, path):
        """选中项变化时同步右侧预览与底部详细信息。"""
        self.details.show(path)
        self.preview.show(path)

    def _open_file(self, path):
        open_path(path, parent=self.window)

    def _on_context_menu(self, path, event):
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    def _open_selected_file(self):
        path = self.grid.selected_path()
        if path:
            open_path(path, parent=self.window)

    def _open_file_location(self):
        path = self.grid.selected_path()
        if path:
            open_path(path, parent=self.window, reveal=True)

    # -------------------------- 文件夹选择 / 扫描 --------------------------
    def on_select_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.current_folder = folder
            self.lbl_folder.config(text=f"当前文件夹: {folder}")
            self._scan_folder(folder)

    def _rescan_current_folder(self):
        if self.current_folder:
            self._scan_folder(self.current_folder)

    def _scan_folder(self, folder):
        self.all_files, exts = scan_folder(folder)
        self.extensions = exts
        self.combo_ext["values"] = ["全部"] + exts
        self.combo_ext.current(0)
        self.apply_filter_and_show_list()

    # -------------------------- 筛选 / 网格显示 --------------------------
    def apply_filter_and_show_list(self):
        selected_ext = self.combo_ext.get()
        if selected_ext == "全部":
            self.filtered_files = [f for f in self.all_files if is_image_file(f)]
        else:
            self.filtered_files = [f for f in self.all_files
                                   if f.lower().endswith(selected_ext)]
        # 换文件夹或换筛选后, 上一次查找重复项的进度提示不再适用
        self.lbl_progress_text.config(text="")
        self.grid.set_files(self.filtered_files)
        self.lbl_counts.config(text=self._counts_text())
        self._update_empty_state()
        self._on_select_file(None)

    def _counts_text(self):
        text = f"{len(self.all_files)} 个项目"
        if len(self.filtered_files) != len(self.all_files):
            text += f" · 已筛选 {len(self.filtered_files)} 个"
        return text

    # -------------------------- 重复查找 --------------------------
    def on_find_duplicates(self):
        if not self.filtered_files:
            messagebox.showinfo("提示", "没有可处理文件")
            return
        if self.dedupe_thread and self.dedupe_thread.is_alive():
            messagebox.showwarning("警告", "正在进行重复查找")
            return
        self.dedupe_stop_event = threading.Event()
        self.dedupe_thread = threading.Thread(
            target=dedupe_worker,
            args=(self.filtered_files, self.progress_queue,
                  self.dedupe_stop_event),
            daemon=True)
        self.dedupe_thread.start()
        self.btn_stop.config(state="normal")

    def on_stop(self):
        if self.dedupe_stop_event:
            self.dedupe_stop_event.set()

    def _poll_progress_queue(self):
        try:
            while True:
                item = self.progress_queue.get_nowait()
                if item[0] == "progress":
                    processed, total = item[1], item[2]
                    self.progress["maximum"] = total
                    self.progress["value"] = processed
                    self.lbl_progress_text.config(
                        text=f"重复查找: {processed}/{total}")
                elif item[0] == "result":
                    self.duplicates = item[1]
                elif item[0] == "done":
                    self.btn_stop.config(state="disabled")
                    self.progress["value"] = 0
                    self.lbl_progress_text.config(text="重复查找完成")
                    if self.duplicates:
                        DuplicateGroupWindow(self.window, self.duplicates,
                                             self.all_files, theme=self.theme)
                    else:
                        messagebox.showinfo("提示", "未发现重复图片")
                elif item[0] == "stopped":
                    self.btn_stop.config(state="disabled")
                    self.progress["value"] = 0
                    self.lbl_progress_text.config(text="重复查找被终止")
        except queue.Empty:
            pass
        self.root.after(200, self._poll_progress_queue)
