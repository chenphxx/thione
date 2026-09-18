"""批量重命名页面: 图标视图 预览窗格与重命名流程。

按 Windows 资源管理器的方式组织: 主区是文件夹卡片的滚动列表 (每张卡片内部
是缩略图网格), 右侧是可收起的预览窗格, 底部是可收起的详细信息窗格
"""

import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from ...browser import DetailsPane, PaneToggles, PreviewPane, ViewSwitch
from ...browser.constants import DEFAULT_TIER, DEFAULT_VIEW
from ...errors import open_path
from ...shell.page import ToolPage
from ...widgets import bind_mousewheel, unbind_mousewheel
from .constants import PAGE_TITLE
from .file_ops import clear_files_in_folder
from .folder_card import FolderCard
from .renamer import (
    CancelledError,
    TaskError,
    build_tasks,
    prepare_inplace_temps,
    restore_inplace_temps,
    run_tasks,
)


class RenamePage(ToolPage):
    """把文件夹内的文件按前缀 + 序号批量重命名的工具页面。"""

    key = "rename"
    title = "批量重命名"
    icon = "🏷"
    subtitle = "按前缀与起始序号重命名文件, 支持原文件夹内直接改名"

    def __init__(self, master, shell):
        super().__init__(master, shell)

        self.folder_blocks = []
        self._next_folder_id = 1
        self.global_action = None  # None / "overwrite" / "skip"
        self.cancel_flag = False
        self.tier = DEFAULT_TIER
        self.view = DEFAULT_VIEW
        self.preview_visible = False
        self.details_visible = False

        self._build_toolbar()
        self.add_divider()
        self._build_main_area()
        self._build_statusbar()
        self._build_details()

        # 卡片列表会刷新状态栏上的计数, 因此放在状态栏之后再建
        self.add_folder()

    # ---------------- 界面构建 ----------------
    def _build_toolbar(self):
        bar, head, actions = self.build_toolbar()

        ttk.Label(head, text=PAGE_TITLE, style="PanelHeader.TLabel").pack(side="left")
        ttk.Label(head, text="按前缀与起始序号批量改名, 可在原文件夹内直接改",
                  style="PanelHint.TLabel").pack(side="left", padx=(12, 0))

        self.btn_rename = ttk.Button(actions, text="开始处理",
                                     style="Accent.TButton",
                                     command=self.rename_and_save)
        self.btn_rename.pack(side="right")

        self.btn_preview = ttk.Button(actions, text="预览",
                                      style="Secondary.TButton",
                                      command=self.toggle_preview)
        self.btn_preview.pack(side="right", padx=(0, 8))

        row = ttk.Frame(bar, style="Panel.TFrame")
        row.pack(side="top", fill="x", pady=(10, 0))

        # 先 pack 右侧控件, 再 pack 左侧的伸缩项
        self.view_switch = ViewSwitch(row, self._on_view_change,
                                      self._on_tier_change, self.view,
                                      self.tier)
        self.view_switch.pack(side="right", padx=(0, 16))
        ttk.Label(row, text="视图", style="Panel.TLabel").pack(
            side="right", padx=(0, 6))

        self.btn_add_folder = ttk.Button(row, text="+ 添加文件夹",
                                         style="Secondary.TButton",
                                         command=self.add_folder)
        self.btn_add_folder.pack(side="left", padx=(0, 16))

        ttk.Label(row, text="文件名前缀", style="Panel.TLabel").pack(side="left")
        self.entry_prefix = ttk.Entry(row, width=18)
        self.entry_prefix.pack(side="left", padx=(6, 0))

        ttk.Label(row, text="起始数字", style="Panel.TLabel").pack(
            side="left", padx=(14, 6))
        self.entry_start = ttk.Entry(row, width=6)
        self.entry_start.insert(0, "1")
        self.entry_start.pack(side="left")

    def _build_main_area(self):
        main = ttk.Frame(self)
        main.pack(side="top", fill="both", expand=True)

        # 可拖拽分隔的水平分栏: 左侧文件夹卡片, 右侧预览窗格
        self.paned = ttk.Panedwindow(main, orient="horizontal")
        self.paned.pack(side="top", fill="both", expand=True)

        cards_container = ttk.Frame(self.paned, padding=(16, 12))
        self.paned.add(cards_container, weight=1)

        self.canvas = tk.Canvas(cards_container, highlightthickness=0)
        self.v_scroll = ttk.Scrollbar(cards_container, orient="vertical",
                                      command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.v_scroll.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.v_scroll.pack(side="right", fill="y")

        self.blocks_frame = ttk.Frame(self.canvas)
        self.canvas_window = self.canvas.create_window(
            (0, 0), window=self.blocks_frame, anchor="nw")
        self.blocks_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(
                scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", self._on_cards_resize)
        bind_mousewheel(self.canvas, self.canvas)

        self.preview = PreviewPane(self.paned, self.theme)
        self.paned.add(self.preview, weight=0)
        self.paned.forget(self.preview)  # 默认收起

    def _build_statusbar(self):
        status = ttk.Frame(self, style="Panel.TFrame", padding=(16, 8))
        status.pack(side="bottom", fill="x")

        # 右下角的窗格开关, 与 Windows 资源管理器的位置一致
        self.toggles = PaneToggles(status, self.toggle_details,
                                   self.toggle_preview)
        self.toggles.pack(side="right")

        self.btn_cancel = ttk.Button(status, text="终止", style="Danger.TButton",
                                     command=self.cancel_process,
                                     state="disabled")
        self.btn_cancel.pack(side="right", padx=(8, 12))

        self.lbl_counts = ttk.Label(status, text="文件夹: 0 · 总文件数: 0",
                                    style="PanelMuted.TLabel")
        self.lbl_counts.pack(side="left", padx=(0, 12))

        self.progress = ttk.Progressbar(status, orient="horizontal",
                                        mode="determinate")
        self.progress.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self.lbl_progress_text = ttk.Label(status, text="已处理 0 / 0 (0%)",
                                           style="Panel.TLabel")
        self.lbl_progress_text.pack(side="left")

    def _build_details(self):
        """底部详细信息窗格; 在状态栏之后构建, 因此排在状态栏上方。"""
        self.details = DetailsPane(self, self.theme)

    # ---------------- 视图切换 ----------------
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
        """切换列表与缩略图展示, 并同步到每一张文件夹卡片。"""
        if view == self.view:
            return
        self.view = view
        for card in self.folder_blocks:
            card.set_view(view)
        self.view_switch.set_state(self.view, self.tier)

    def _on_tier_change(self, tier):
        """切换缩略图档位; 在列表展示下点档位即切回缩略图展示。"""
        changed = tier != self.tier
        self.tier = tier
        for card in self.folder_blocks:
            card.set_tier(tier)
        if self.view != "icons":
            self.view = "icons"
            for card in self.folder_blocks:
                card.set_view("icons")
        elif not changed:
            return
        self.view_switch.set_state(self.view, self.tier)

    def on_file_selected(self, path):
        """任意卡片里的选中项变化时, 同步右侧预览与底部详细信息。"""
        self.details.show(path)
        self.preview.show(path)

    # ---------------- 主题与页面生命周期 ----------------
    def on_theme_changed(self):
        """主题切换后, 网格里自绘的文字与选中框, 以及已渲染的预览需要重刷。"""
        for card in self.folder_blocks:
            card.apply_palette()
        self.preview.refresh()

    def on_hide(self):
        """切走时解除滚轮绑定, 避免在其他页面上仍然响应本页的滚动。"""
        unbind_mousewheel(self.canvas)
        for card in self.folder_blocks:
            unbind_mousewheel(card.grid.canvas)

    # ---------------- 文件夹卡片管理 ----------------
    def _on_cards_resize(self, event):
        """卡片区随窗口变化: 宽度跟窗口走, 高度至少铺满可视区。"""
        self.canvas.itemconfigure(self.canvas_window, width=event.width)
        self._fit_cards_height(event.height)

    def _fit_cards_height(self, height):
        """把卡片区撑到可视高度; 卡片的最小高度之和更大时保留原高度并滚动。"""
        needed = self.blocks_frame.winfo_reqheight()
        self.canvas.itemconfigure(self.canvas_window,
                                  height=max(height, needed))

    def add_folder(self):
        idx = self._next_folder_id
        self._next_folder_id += 1
        card = FolderCard(self.blocks_frame, self, idx)
        self.folder_blocks.append(card)
        self.refresh_overall_counts()
        self._queue_card_layout()

    def remove_folder(self, card):
        if card in self.folder_blocks:
            self.folder_blocks.remove(card)
        self.refresh_overall_counts()
        self._queue_card_layout()

    def _queue_card_layout(self):
        """卡片增删后等一轮布局完成, 再按新的最小高度重新贴合可视区。"""
        def fit():
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
            self._fit_cards_height(self.canvas.winfo_height())
        self.root.after(50, fit)

    def refresh_overall_counts(self):
        folders = len([b for b in self.folder_blocks if b.folder_path])
        total = sum(len(b.files) for b in self.folder_blocks if b.folder_path)
        self.lbl_counts.config(text=f"文件夹: {folders} · 总文件数: {total}")

    # ---------------- 取消处理 ----------------
    def cancel_process(self):
        self.cancel_flag = True

    # ---------------- 核心处理 ----------------
    def rename_and_save(self):
        prefix = self.entry_prefix.get().strip()
        if not prefix:
            messagebox.showwarning("警告", "请输入文件名前缀")
            return
        try:
            start_num = int(self.entry_start.get())
        except ValueError:
            messagebox.showwarning("警告", "起始数字必须为整数")
            return

        # 收集所有卡片中的文件
        items = []
        for b in self.folder_blocks:
            if b.folder_path:
                for name in b.filtered_files:
                    items.append((b.folder_path, name))
        if not items:
            messagebox.showwarning("警告", "没有可处理的文件")
            return

        save_folder = filedialog.askdirectory(title="选择保存目标文件夹")
        if not save_folder:
            return

        tasks = build_tasks(items, save_folder, prefix, start_num)

        # 原位重命名模式下跳过“清空/新增”选择，避免清空源文件夹
        if not any(t[2] for t in tasks):
            choice = messagebox.askyesnocancel(
                "保存模式选择",
                "请选择目标文件夹操作方式：\n\n是 = 清空文件夹\n否 = 在文件夹内新增\n取消 = 终止操作",
            )
            if choice is None:
                return
            if choice:
                try:
                    clear_files_in_folder(save_folder)
                except Exception as e:
                    messagebox.showerror("错误", f"清空目标文件夹失败: {e}")
                    return

        # 重置标志
        self.cancel_flag = False
        self.global_action = None

        total = len(tasks)
        moved = {}

        # 初始化进度条 UI
        self.progress["maximum"] = total
        self.progress["value"] = 0
        self.btn_cancel.config(state="normal")
        self._update_progress(0, total)

        # 原位重命名：先把目标名与其他待处理源文件冲突的文件挪到临时名
        inplace_tasks = [t for t in tasks if t[2]]
        if inplace_tasks:
            folder = os.path.dirname(inplace_tasks[0][0])
            inplace_jobs = [(t[3], os.path.basename(t[1])) for t in inplace_tasks]
            try:
                moved = prepare_inplace_temps(folder, inplace_jobs)
            except Exception as e:
                messagebox.showerror("错误", f"准备重命名失败: {e}")
                self.btn_cancel.config(state="disabled")
                self._update_progress(0, total)
                return
        else:
            folder = save_folder

        finished = True
        try:
            run_tasks(tasks, folder, moved, self._conflict_dialog,
                      self._update_progress, lambda: self.cancel_flag)
        except CancelledError:
            restore_inplace_temps(folder, moved)
            messagebox.showinfo("已取消", "操作已取消")
            finished = False
        except TaskError as e:
            restore_inplace_temps(folder, moved)
            messagebox.showerror("错误", f"处理失败: {e.src}\n{e}")
            finished = False
        finally:
            self.btn_cancel.config(state="disabled")

        if not finished:
            return

        # 处理完成
        self.lbl_progress_text.config(text="处理完成")
        self.progress["value"] = 0
        if messagebox.askyesno("完成", "文件处理完成，是否现在打开目标文件夹？"):
            open_path(save_folder, parent=self.window)

    def _conflict_dialog(self, filename):
        """返回 'overwrite'、'skip' 或 'cancel'。支持全局应用。"""
        if self.global_action == "overwrite":
            return "overwrite"
        if self.global_action == "skip":
            return "skip"

        choice = messagebox.askyesnocancel("文件已存在", f"{filename} 已存在。\n\n是 = 覆盖\n否 = 跳过\n取消 = 终止操作")
        if choice is None:
            return "cancel"
        elif choice:
            apply_all = messagebox.askyesno("应用到全部", "是否对后续冲突文件全部覆盖？")
            if apply_all:
                self.global_action = "overwrite"
            return "overwrite"
        else:
            apply_all = messagebox.askyesno("应用到全部", "是否对后续冲突文件全部跳过？")
            if apply_all:
                self.global_action = "skip"
            return "skip"

    def _update_progress(self, processed, total):
        pct = int((processed / total) * 100) if total else 0
        self.progress["value"] = processed
        self.lbl_progress_text.config(text=f"已处理 {processed} / {total} ({pct}%)")
        self.root.update_idletasks()
