"""图片查重页面: 缩略图浏览文件夹, 右侧预览窗格与重复查找入口

版式与设计稿一致: 内容区顶部一行是文件夹与筛选 视图控件, 下面的面板里左边是
缩略图网格, 右边固定 276 像素宽的预览列 (预览框 + 属性 + 打开按钮);
状态栏右侧是终止按钮与两个窗格开关
"""

import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from ... import kit
from ...browser import DetailsPane, FileGrid, PaneToggles, PreviewPane, ViewSwitch
from ...browser.constants import DEFAULT_TIER, DEFAULT_VIEW
from ...dpi import scale
from ...errors import open_path
from ...imaging import image_size
from ...shell.page import ToolPage
from ...theme import ICON_EMPTY, SIZE_LABEL, tint
from ...widgets import unbind_mousewheel
from .constants import PAGE_TITLE, SUBTITLE
from .dedupe import HASH_BITS, dedupe_worker
from .duplicate_window import DuplicateGroupWindow
from .scanner import is_image_file, scan_folder

#: 预览列的高度 (与设计稿一致)
PREVIEW_FIELDS = (("name", "文件名"), ("dims", "尺寸"), ("size", "大小"),
                  ("similarity", "相似度"))


class DedupePage(ToolPage):
    """按感知哈希查找重复图片的工具页面"""

    key = "dedupe"
    title = PAGE_TITLE
    icon = "\uE91B"
    subtitle = SUBTITLE

    def __init__(self, master, shell):
        super().__init__(master, shell)

        self.current_folder = ""
        self.all_files = []
        self.filtered_files = []
        self.extensions = []
        self.tier = DEFAULT_TIER
        self.view = DEFAULT_VIEW
        self.preview_visible = True
        self.details_visible = False
        self.dedupe_thread = None
        self.dedupe_stop_event = None
        self.progress_queue = queue.Queue()
        self.duplicates = []
        self._badges = {}
        self._similarity = {}
        self._scanning = False

        self._build_toolbar()
        self._build_main_area()
        self._build_statusbar()
        self._sync_view_controls()

        self.root.after(200, self._poll_progress_queue)

    # -------------------------- 界面构建 --------------------------
    def _build_toolbar(self):
        """顶栏按钮与文件夹筛选行"""
        self.btn_find, self.btn_rescan, self.btn_preview = self.add_actions((
            ("预览", None, self.toggle_preview),
            ("刷新扫描", None, self._rescan_current_folder),
            ("查找重复项", "Primary.TButton", self.on_find_duplicates),
        ))

        row = self.add_row()
        self.view_switch = ViewSwitch(row, self.theme, self._on_view_change,
                                      self._on_tier_change, self.view,
                                      self.tier, surface="canvas")
        self.view_switch.pack(side="right", padx=(8, 0))
        kit.text(row, self.theme, value="视图", size=SIZE_LABEL,
                 token="muted", surface="canvas").pack(side="right")
        self.combo_ext = kit.Dropdown(row, self.theme, values=["全部"],
                                      command=self._on_filter_change,
                                      surface="canvas", width=104)
        self.combo_ext.set("全部")
        self.combo_ext.pack(side="right", padx=(8, 16))
        kit.text(row, self.theme, value="筛选类型", size=SIZE_LABEL,
                 token="muted", surface="canvas").pack(side="right")

        self.btn_choose = ttk.Button(row, text="选择文件夹", style="TButton",
                                     command=self.on_select_folder)
        self.btn_choose.pack(side="left")
        kit.text(row, self.theme, value="当前文件夹", size=SIZE_LABEL,
                 token="muted", surface="canvas").pack(side="left",
                                                      padx=(12, 8))
        self.lbl_folder = kit.text(row, self.theme, value="未选择",
                                   size=SIZE_LABEL, token="muted",
                                   mono_font=True, surface="canvas")
        self.lbl_folder.pack(side="left")

    def _build_main_area(self):
        """缩略图网格与右侧预览列共用一个面板"""
        panel = self.add_panel(head=False, body_pad=(0, 0))
        area = tk.Frame(panel.body, bd=0, highlightthickness=0)
        tint(area, bg="panel")
        area.configure(bg=self.theme.rgb("panel"))
        area.pack(fill="both", expand=True)

        self.preview = PreviewPane(area, self.theme, fields=PREVIEW_FIELDS,
                                   on_open=self._open_file,
                                   on_reveal=self._reveal_file)
        self.preview.set_info_provider(self._preview_info)
        self.preview.pack(side="right", fill="y")

        grid_holder = tk.Frame(area, bd=0, highlightthickness=0)
        tint(grid_holder, bg="panel")
        grid_holder.configure(bg=self.theme.rgb("panel"))
        grid_holder.pack(side="left", fill="both", expand=True,
                         padx=scale(14), pady=scale(14))

        self.grid_box = tk.Frame(grid_holder, bd=0, highlightthickness=0)
        tint(self.grid_box, bg="panel")
        self.grid_box.configure(bg=self.theme.rgb("panel"))
        self.grid_box.pack(side="top", fill="both", expand=True)
        self.grid = FileGrid(self.grid_box, self.theme,
                             on_select=self._on_select_file,
                             on_activate=self._open_file,
                             on_context=self._on_context_menu,
                             tier=self.tier, view=self.view,
                             surface="panel")
        self.grid.pack(fill="both", expand=True)

        self.empty_state = self._build_empty_state(grid_holder)
        self._update_empty_state()

        self.menu = tk.Menu(self, tearoff=0)
        self.menu.add_command(label="打开文件", command=self._open_selected_file)
        self.menu.add_command(label="打开所在文件夹",
                              command=self._open_file_location)

        self.details = DetailsPane(self, self.theme)

    def _build_empty_state(self, parent):
        """建立文件网格的空状态占位块

        没有可显示的文件时用它顶替网格, 给出下一步该做什么, 而不是留一块白屏

        @param parent: 承载占位块的父容器
        @return: 占位块 Frame (默认不显示)
        """
        box = tk.Frame(parent, bd=0, highlightthickness=0)
        tint(box, bg="panel")
        box.configure(bg=self.theme.rgb("panel"))
        inner = tk.Frame(box, bd=0, highlightthickness=0)
        tint(inner, bg="panel")
        inner.configure(bg=self.theme.rgb("panel"))
        inner.place(relx=0.5, rely=0.42, anchor="center")
        kit.text(inner, self.theme, value=ICON_EMPTY, size=34, token="accent",
                 icon_font=True, surface="panel").pack()
        self.empty_title = kit.text(inner, self.theme, value="", size=15,
                                    bold=True, surface="panel")
        self.empty_title.pack(pady=(scale(10), 0))
        self.empty_hint = kit.text(inner, self.theme, value="", size=SIZE_LABEL,
                                   token="muted", surface="panel")
        self.empty_hint.pack(pady=(6, 0))
        return box

    def _update_empty_state(self):
        """按当前是否有可显示的文件, 在网格与空状态之间切换"""
        if self.filtered_files:
            self.empty_state.pack_forget()
            self.grid_box.pack(side="top", fill="both", expand=True)
            return
        if self.current_folder:
            self.empty_title.configure(text="这个文件夹里没有可显示的图片")
            self.empty_hint.configure(text="换一个文件夹, 或者把筛选类型改回'全部'")
        else:
            self.empty_title.configure(text="还没有选择文件夹")
            self.empty_hint.configure(text="点击左上角的'选择文件夹'开始扫描")
        self.grid_box.pack_forget()
        self.empty_state.pack(side="top", fill="both", expand=True)

    def _build_statusbar(self):
        """状态栏: 左侧是扫描进度, 右侧是终止按钮与两个窗格开关"""
        self.status.set_kind("idle")
        self.status.set_text("还没有选择文件夹")
        self.metric = kit.text(self.status.tail, self.theme, size=SIZE_LABEL,
                               mono_font=True, surface="side")
        self.status.add_tail(self.metric)
        self.toggles = PaneToggles(self.status.actions, self.theme,
                                   self.toggle_details, self.toggle_preview)
        self.btn_stop = ttk.Button(self.status.actions, text="终止",
                                   style="Danger.TButton", command=self.on_stop,
                                   state="disabled")
        self.status.add_action(self.btn_stop)
        self.toggles.pack(side="right")

    # -------------------------- 视图切换 --------------------------
    def toggle_preview(self):
        """显示或收起右侧预览窗格"""
        self.preview_visible = not self.preview_visible
        if self.preview_visible:
            self.preview.pack(side="right", fill="y")
        else:
            self.preview.pack_forget()
        self._sync_view_controls()

    def toggle_details(self):
        """显示或收起底部详细信息窗格"""
        self.details_visible = not self.details_visible
        if self.details_visible:
            self.details.pack(side="bottom", fill="x")
        else:
            self.details.pack_forget()
        self._sync_view_controls()

    def _sync_view_controls(self):
        """把两个窗格的开关状态同步到右下角的按钮"""
        self.toggles.set_state(self.details_visible, self.preview_visible)
        self.btn_preview.configure(
            style="Primary.TButton" if self.preview_visible else "TButton")

    def _on_view_change(self, view):
        """切换列表与缩略图展示; 同一展示方式会被忽略

        @param view: 展示方式
        """
        if view == self.view:
            return
        self.view = view
        self.grid.set_view(view)
        self.view_switch.set_state(self.view, self.tier)

    def _on_tier_change(self, tier):
        """切换缩略图档位; 在列表展示下点档位即切回缩略图展示

        @param tier: 档位
        """
        changed = tier != self.tier
        self.tier = tier
        self.grid.set_tier(tier)
        if self.view != "icons":
            self.view = "icons"
            self.grid.set_view("icons")
        elif not changed:
            return
        self.view_switch.set_state(self.view, self.tier)

    def _on_filter_change(self, _value):
        self.apply_filter_and_show_list()

    def on_hide(self):
        """切走时解除滚轮绑定, 避免在其他页面上仍然响应本页的滚动"""
        unbind_mousewheel(self.grid.canvas)

    def on_theme_changed(self):
        self.grid.apply_palette()
        self.preview.refresh()

    # -------------------------- 文件操作 --------------------------
    def _on_select_file(self, path):
        """选中项变化时同步右侧预览与底部详细信息

        @param path: 文件路径
        """
        self.details.show(path)
        self.preview.show(path)

    def _preview_info(self, path):
        """预览列里需要额外查询的属性

        @param path: 文件路径
        @return: {字段键: 取值}
        """
        info = {}
        size = image_size(path) if is_image_file(path) else None
        info["dims"] = f"{size[0]} x {size[1]}" if size else "-"
        similarity = self._similarity.get(path)
        info["similarity"] = f"{similarity}%" if similarity else "-"
        return info

    def _open_file(self, path):
        open_path(path, parent=self.window)

    def _reveal_file(self, path):
        open_path(path, parent=self.window, reveal=True)

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
            self.lbl_folder.configure(text=folder)
            self._scan_folder(folder)

    def _rescan_current_folder(self):
        if self.current_folder:
            self._scan_folder(self.current_folder)

    def _scan_folder(self, folder):
        self.all_files, extensions = scan_folder(folder)
        self.extensions = extensions
        self.combo_ext.set_values(["全部"] + extensions)
        self.combo_ext.set("全部")
        self.apply_filter_and_show_list()
        self.status.set_kind("idle")
        self.status.set_text("已扫描 1 个文件夹")
        self.metric.configure(text=f"{len(self.all_files)} 项")

    # -------------------------- 筛选 / 网格显示 --------------------------
    def apply_filter_and_show_list(self):
        """按当前筛选条件刷新网格与计数"""
        selected_ext = self.combo_ext.value()
        if selected_ext in ("", "全部"):
            self.filtered_files = [f for f in self.all_files
                                   if is_image_file(f)]
        else:
            self.filtered_files = [f for f in self.all_files
                                   if f.lower().endswith(selected_ext)]
        # 换文件夹或换筛选后, 上一次查找重复项的进度提示不再适用
        self.grid.set_files(self.filtered_files)
        self.grid.set_badges(self._badges)
        self.metric.configure(text=self._counts_text())
        self._update_empty_state()
        self._on_select_file(None)

    def _counts_text(self):
        """状态栏右侧的计数说明

        @return: 计数文本
        """
        text = f"{len(self.filtered_files)} 项"
        if self.duplicates:
            text += f" · {len(self.duplicates)} 组重复"
        elif len(self.filtered_files) != len(self.all_files):
            text += f" · 已筛选 {len(self.filtered_files)} 个"
        return text

    # -------------------------- 重复查找 --------------------------
    def on_find_duplicates(self):
        if not self.filtered_files:
            messagebox.showinfo("提示", "没有可处理文件",
                                parent=self.window)
            return
        if self.dedupe_thread and self.dedupe_thread.is_alive():
            messagebox.showwarning("警告", "正在进行重复查找",
                                   parent=self.window)
            return
        self.dedupe_stop_event = threading.Event()
        self.dedupe_thread = threading.Thread(
            target=dedupe_worker,
            args=(self.filtered_files, self.progress_queue,
                  self.dedupe_stop_event),
            daemon=True)
        self.dedupe_thread.start()
        self.btn_stop.configure(state="normal")
        self.status.set_kind("run")
        self.status.set_text("正在查找重复图片")

    def on_stop(self):
        if self.dedupe_stop_event:
            self.dedupe_stop_event.set()

    def _poll_progress_queue(self):
        """按后台线程投递的消息刷新状态栏与结果标记"""
        try:
            while True:
                item = self.progress_queue.get_nowait()
                if item[0] == "progress":
                    processed, total = item[1], item[2]
                    self.status.set_kind("run")
                    self.status.set_text(f"重复查找: {processed}/{total}")
                elif item[0] == "result":
                    self.duplicates = item[1]
                    self._apply_duplicates()
                elif item[0] == "distances":
                    self._similarity = {
                        path: round((1 - distance / HASH_BITS) * 100)
                        for path, distance in item[1].items()
                    }
                elif item[0] == "done":
                    self.btn_stop.configure(state="disabled")
                    self.status.set_kind("ok")
                    self.status.set_text("重复查找完成")
                    self.metric.configure(text=self._counts_text())
                    if self.duplicates:
                        DuplicateGroupWindow(self.window, self.duplicates,
                                             self.all_files, theme=self.theme)
                    else:
                        messagebox.showinfo("提示", "未发现重复图片",
                                            parent=self.window)
                elif item[0] == "stopped":
                    self.btn_stop.configure(state="disabled")
                    self.status.set_kind("idle")
                    self.status.set_text("重复查找被终止")
        except queue.Empty:
            pass
        self.root.after(200, self._poll_progress_queue)

    def _apply_duplicates(self):
        """把查重结果转成网格右下角的 保留 / 重复 标记"""
        badges = {}
        for index, group in enumerate(self.duplicates, start=1):
            for position, path in enumerate(group):
                badges[path] = (f"保留 {index}" if position == 0
                                else f"重复 {index}")
        self._badges = badges
        self.grid.set_badges(badges)
        self.preview.show(self.grid.selected_path())
