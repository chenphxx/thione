"""批量重命名页面: 工具栏、文件夹卡片列表、预览面板与重命名流程。"""

import os
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from ...shell.page import ToolPage
from .constants import APP_TITLE
from .file_ops import clear_files_in_folder, open_folder
from .folder_card import FolderCard
from .preview_panel import PreviewPanel
from .renamer import (
    build_tasks,
    prepare_inplace_temps,
    restore_inplace_temp,
    restore_inplace_temps,
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

        self._build_toolbar()
        self.add_divider()
        self._build_stats()
        self._build_main_area()
        self._build_statusbar()

    # ---------------- 界面构建 ----------------
    def _build_toolbar(self):
        bar, head, actions = self.build_toolbar()

        ttk.Label(head, text=APP_TITLE, style="PanelHeader.TLabel").pack(side="left")
        ttk.Label(head, text="按前缀与起始序号批量改名, 可在原文件夹内直接改",
                  style="PanelHint.TLabel").pack(side="left", padx=(12, 0))

        self.btn_rename = ttk.Button(actions, text="开始处理",
                                     style="Accent.TButton",
                                     command=self.rename_and_save)
        self.btn_rename.pack(side="right")

        row = ttk.Frame(bar, style="Panel.TFrame")
        row.pack(side="top", fill="x", pady=(10, 0))

        self.btn_add_folder = ttk.Button(row, text="+ 添加文件夹",
                                         style="Secondary.TButton",
                                         command=self.add_folder)
        self.btn_add_folder.pack(side="left")

        ttk.Label(row, text="文件名前缀", style="Panel.TLabel").pack(
            side="left", padx=(16, 6))
        self.entry_prefix = ttk.Entry(row, width=18)
        self.entry_prefix.pack(side="left")

        ttk.Label(row, text="起始数字", style="Panel.TLabel").pack(
            side="left", padx=(14, 6))
        self.entry_start = ttk.Entry(row, width=6)
        self.entry_start.insert(0, "1")
        self.entry_start.pack(side="left")

    def _build_stats(self):
        stats = ttk.Frame(self, padding=(16, 10))
        stats.pack(side="top", fill="x")

        self.lbl_folders = ttk.Label(stats, text="文件夹: 0", style="Muted.TLabel")
        self.lbl_folders.pack(side="left", padx=(0, 16))
        self.lbl_total = ttk.Label(stats, text="总文件数: 0", style="Muted.TLabel")
        self.lbl_total.pack(side="left")
        ttk.Label(stats, text="保存位置选原文件夹即原地重命名",
                  style="Muted.TLabel").pack(side="right")

    def _build_main_area(self):
        main = ttk.Frame(self)
        main.pack(side="top", fill="both", expand=True)

        # 可拖拽分隔的垂直分栏: 上方文件夹卡片列表, 下方文件预览
        self.paned = ttk.Panedwindow(main, orient="vertical")
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
        self.canvas_window = self.canvas.create_window((0, 0), window=self.blocks_frame,
                                                       anchor="nw")
        self.blocks_frame.bind("<Configure>",
                               lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>",
                         lambda e: self.canvas.itemconfig(self.canvas_window, width=e.width))
        self.canvas.bind("<Enter>", lambda e: self._bind_mousewheel())
        self.canvas.bind("<Leave>", lambda e: self._unbind_mousewheel())

        self.preview = PreviewPanel(self.paned, self.theme)
        self.paned.add(self.preview, weight=0)

        self.add_folder()

    def _build_statusbar(self):
        status = ttk.Frame(self, style="Panel.TFrame", padding=(16, 8))
        status.pack(side="bottom", fill="x")

        self.progress = ttk.Progressbar(status, orient="horizontal", mode="determinate")
        self.progress.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self.lbl_progress_text = ttk.Label(status, text="已处理 0 / 0 (0%)",
                                           style="Panel.TLabel")
        self.lbl_progress_text.pack(side="left", padx=(0, 8))

        self.btn_cancel = ttk.Button(status, text="终止", style="Danger.TButton",
                                     command=self.cancel_process, state="disabled")
        self.btn_cancel.pack(side="left")

    # ---------------- 主题切换 ----------------
    def on_theme_changed(self):
        """主题切换后, 列表行标签色与已渲染的预览需要重刷。"""
        self._refresh_tree_tags()
        self.preview.refresh()

    def on_hide(self):
        """切走时解除滚轮绑定, 避免在其他页面上仍然响应本页的滚动。"""
        self._unbind_mousewheel()

    def _refresh_tree_tags(self):
        p = self.theme.palette
        for card in self.folder_blocks:
            card.tree.tag_configure("oddrow", background=p["card"])
            card.tree.tag_configure("evenrow", background=p["hover"])

    # ---------------- 文件夹卡片管理 ----------------
    def add_folder(self):
        idx = self._next_folder_id
        self._next_folder_id += 1
        card = FolderCard(self.blocks_frame, self, idx)
        card.tree.tag_configure("oddrow", background=self.theme.palette["card"])
        card.tree.tag_configure("evenrow", background=self.theme.palette["hover"])
        self.folder_blocks.append(card)
        self.refresh_overall_counts()
        self.root.after(50, lambda: self.canvas.configure(scrollregion=self.canvas.bbox("all")))

    def remove_folder(self, card):
        if card in self.folder_blocks:
            self.folder_blocks.remove(card)
        self.refresh_overall_counts()
        self.root.after(50, lambda: self.canvas.configure(scrollregion=self.canvas.bbox("all")))

    def refresh_overall_counts(self):
        folders = len([b for b in self.folder_blocks if b.folder_path])
        total = sum(len(b.files) for b in self.folder_blocks if b.folder_path)
        self.lbl_folders.config(text=f"文件夹: {folders}")
        self.lbl_total.config(text=f"总文件数: {total}")

    # ---------------- 鼠标滚轮 ----------------
    def _bind_mousewheel(self):
        self.root.bind_all("<MouseWheel>", self._on_mousewheel)

    def _unbind_mousewheel(self):
        self.root.unbind_all("<MouseWheel>")

    def _on_mousewheel(self, event):
        bbox = self.canvas.bbox("all")
        if bbox is None:
            return
        canvas_h = self.canvas.winfo_height()
        content_h = bbox[3] - bbox[1]
        if content_h <= canvas_h:
            return
        if os.name == "nt":
            self.canvas.yview_scroll(-1 * (event.delta // 120), "units")
        else:
            self.canvas.yview_scroll(-1 * event.delta, "units")

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
        processed = 0
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

        # 逐项处理
        try:
            for src, dst, inplace, src_name in tasks:
                if self.cancel_flag:
                    restore_inplace_temps(folder, moved)
                    messagebox.showinfo("已取消", "操作已取消")
                    self._update_progress(processed, total)
                    self.btn_cancel.config(state="disabled")
                    return

                # 原位重命名：文件已是指定名称则跳过
                if inplace and os.path.normcase(os.path.normpath(src)) == os.path.normcase(os.path.normpath(dst)):
                    processed += 1
                    self._update_progress(processed, total)
                    continue

                cur_src = moved.get(src_name) if inplace else None
                if cur_src is None:
                    cur_src = src

                # 处理冲突
                if os.path.exists(dst):
                    action = self._conflict_dialog(os.path.basename(dst))
                    if action == "cancel":
                        restore_inplace_temp(folder, src_name, cur_src)
                        restore_inplace_temps(folder, moved)
                        messagebox.showinfo("已取消", "操作已取消")
                        self._update_progress(processed, total)
                        self.btn_cancel.config(state="disabled")
                        return
                    if action == "skip":
                        # 若文件已被挪到临时名，则还原为原名
                        restore_inplace_temp(folder, src_name, cur_src)
                        moved.pop(src_name, None)
                        processed += 1
                        self._update_progress(processed, total)
                        continue
                    # 覆盖 => 继续处理

                if inplace:
                    os.replace(cur_src, dst)
                    moved.pop(src_name, None)
                else:
                    shutil.copy2(cur_src, dst)

                processed += 1
                self._update_progress(processed, total)
        except Exception as e:
            restore_inplace_temps(folder, moved)
            messagebox.showerror("错误", f"处理失败: {src}\n{e}")
            self._update_progress(processed, total)
            self.btn_cancel.config(state="disabled")
            return

        # 处理完成
        self.btn_cancel.config(state="disabled")
        self.lbl_progress_text.config(text="处理完成")
        self.progress["value"] = 0
        if messagebox.askyesno("完成", "文件处理完成，是否现在打开目标文件夹？"):
            try:
                open_folder(save_folder)
            except Exception:
                pass

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
