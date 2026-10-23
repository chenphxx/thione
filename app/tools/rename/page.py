"""批量重命名页面: 文件夹面板列表 预览窗格与重命名流程

版式与设计稿一致: 工具条上是 添加文件夹 文件名前缀 起始数字 与视图切换, 下面
按文件夹逐个展示文件的 原名 -> 改后名, 右侧是可收起的预览窗格, 状态栏显示
文件夹与文件计数以及处理进度
"""

import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from ... import kit
from ...browser import PreviewPane, ViewSwitch
from ...dpi import scale
from ...errors import open_path
from ...shell.page import ToolPage
from ...theme import SIZE_LABEL, tint
from ...widgets import bind_mousewheel, unbind_mousewheel
from .constants import PAGE_TITLE, SUBTITLE
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

#: 预览列的宽度
PREVIEW_FIELDS = (("name", "文件名"), ("size", "大小"))

#: 平铺视图使用的档位 (设计稿里 rename 的视图只有 列表 与 平铺)
TILE_TIER = "medium"


class RenamePage(ToolPage):
    """把文件夹内的文件按前缀 + 序号批量重命名的工具页面"""

    key = "rename"
    title = PAGE_TITLE
    icon = "\uE8AC"
    subtitle = SUBTITLE

    def __init__(self, master, shell):
        super().__init__(master, shell)

        self.folder_blocks = []
        self.global_action = None  # None 表示未指定, overwrite 覆盖, skip 跳过
        self.cancel_flag = False
        self.tier = TILE_TIER
        self.view = "list"
        self.preview_visible = False
        self._new_names = {}

        self._build_toolbar()
        self._build_main_area()
        self._build_statusbar()
        self._apply_view()

    # ---------------- 界面构建 ----------------
    def _build_toolbar(self):
        """顶栏按钮与参数行"""
        self.btn_preview, self.btn_rescan, self.btn_rename = self.add_actions((
            ("预览", None, self.toggle_preview),
            ("刷新扫描", None, self.rescan_folders),
            ("开始处理", "Primary.TButton", self.rename_and_save),
        ))

        row = self.add_row()
        self.view_switch = ViewSwitch(row, self.theme, self._on_view_change,
                                      self._on_tier_change, self.view,
                                      self.tier, surface="canvas", tiers=())
        # rename 只区分 列表 与 平铺, 因此收起两档缩略图按钮
        self.view_switch.pack(side="right", padx=(8, 0))
        kit.text(row, self.theme, value="视图", size=SIZE_LABEL,
                 token="muted", surface="canvas").pack(side="right")

        self.btn_add_folder = ttk.Button(row, text="+ 添加文件夹",
                                         style="TButton",
                                         command=self.add_folder)
        self.btn_add_folder.pack(side="left")

        kit.text(row, self.theme, value="文件名前缀", size=SIZE_LABEL,
                 token="muted", surface="canvas").pack(side="left",
                                                      padx=(16, 8))
        self.entry_prefix = kit.EntryField(row, self.theme, width=150)
        self.entry_prefix.pack(side="left")
        self.entry_prefix.entry.bind("<KeyRelease>", self._on_parameter_change)

        kit.text(row, self.theme, value="起始数字", size=SIZE_LABEL,
                 token="muted", surface="canvas").pack(side="left",
                                                      padx=(16, 8))
        self.entry_start = kit.EntryField(row, self.theme, width=76)
        self.entry_start.set("1")
        self.entry_start.pack(side="left")
        self.entry_start.entry.bind("<KeyRelease>", self._on_parameter_change)

    def _build_main_area(self):
        """左侧是可滚动的文件夹面板, 右侧是可收起的预览窗格"""
        area = tk.Frame(self.body, bd=0, highlightthickness=0)
        tint(area, bg="canvas")
        area.configure(bg=self.theme.rgb("canvas"))
        area.pack(side="top", fill="both", expand=True)

        self.preview = PreviewPane(area, self.theme, fields=PREVIEW_FIELDS,
                                   on_open=self._open_file,
                                   on_reveal=self._reveal_file)
        self.preview.configure(width=scale(276))

        self.panel = kit.Panel(area, self.theme, head=False, body_pad=(0, 0))
        self.panel.pack(side="left", fill="both", expand=True)

        self.canvas = tk.Canvas(self.panel.body, bd=0, highlightthickness=0)
        tint(self.canvas, bg="panel")
        self.canvas.configure(bg=self.theme.rgb("panel"))
        self.v_scroll = ttk.Scrollbar(self.panel.body, orient="vertical",
                                      command=self.canvas.yview,
                                      style="Thin.Vertical.TScrollbar")
        self.canvas.configure(yscrollcommand=self._on_yscroll)
        self.canvas.pack(side="left", fill="both", expand=True)

        self.blocks_frame = tk.Frame(self.canvas, bd=0, highlightthickness=0)
        tint(self.blocks_frame, bg="panel")
        self.blocks_frame.configure(bg=self.theme.rgb("panel"))
        self.canvas_window = self.canvas.create_window(
            (0, 0), window=self.blocks_frame, anchor="nw")
        self.blocks_frame.bind(
            "<Configure>", lambda _e: self.canvas.configure(
                scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", self._on_cards_resize)
        bind_mousewheel(self.canvas, self.canvas)

        self.empty_state = self._build_empty_state(self.panel.body)
        self._update_empty_state()

    def _build_empty_state(self, parent):
        """建立没有任何文件夹时的占位块

        @param parent: 父容器
        @return: 占位块
        """
        box = tk.Frame(parent, bd=0, highlightthickness=0)
        tint(box, bg="panel")
        box.configure(bg=self.theme.rgb("panel"))
        inner = tk.Frame(box, bd=0, highlightthickness=0)
        tint(inner, bg="panel")
        inner.configure(bg=self.theme.rgb("panel"))
        inner.place(relx=0.5, rely=0.42, anchor="center")
        kit.text(inner, self.theme, value="\uE8AC", size=34, token="accent",
                 icon_font=True, surface="panel").pack()
        kit.text(inner, self.theme, value="还没有添加文件夹", size=15,
                 bold=True, surface="panel").pack(pady=(10, 0))
        kit.text(inner, self.theme, value="点击左上角的'添加文件夹'开始处理",
                 size=SIZE_LABEL, token="muted",
                 surface="panel").pack(pady=(6, 0))
        return box

    def _build_statusbar(self):
        """状态栏: 左侧是计数与进度, 右侧是终止按钮"""
        self.status.set_kind("idle")
        self.status.set_text("文件夹: 0 | 总文件数: 0")
        self.lbl_progress_text = kit.text(self.status.tail, self.theme,
                                          size=SIZE_LABEL, token="muted",
                                          surface="side")
        self.status.add_tail(self.lbl_progress_text)
        self.lbl_progress_text.configure(text="已处理 0 / 0 (0%)")
        self.btn_cancel = ttk.Button(self.status.actions, text="终止",
                                     style="Danger.TButton",
                                     command=self.cancel_process,
                                     state="disabled")
        self.status.add_action(self.btn_cancel)

    # ---------------- 视图切换 ----------------
    def toggle_preview(self):
        """显示或收起右侧预览窗格"""
        self.preview_visible = not self.preview_visible
        if self.preview_visible:
            self.preview.pack(side="right", fill="y")
        else:
            self.preview.pack_forget()
        self.btn_preview.configure(
            style="Primary.TButton" if self.preview_visible else "TButton")

    def _apply_view(self):
        """把当前的展示方式同步到视图控件与各文件夹面板"""
        self.view_switch.set_state(self.view, self.tier)
        for card in self.folder_blocks:
            card.grid.set_tier(self.tier)
            card.set_view(self.view)

    def _on_view_change(self, view):
        """切换列表与平铺展示; 同一展示方式会被忽略

        @param view: 展示方式
        """
        if view == self.view:
            return
        self.view = view
        for card in self.folder_blocks:
            card.set_view(view)
        self.view_switch.set_state(self.view, self.tier)
        self._relayout_blocks()

    def _relayout_blocks(self):
        """按新的展示方式重算各文件夹面板的高度并刷新滚动区"""
        for card in self.folder_blocks:
            card.fit_height()
        self._queue_card_layout()

    def _on_tier_change(self, _tier):
        """rename 只区分 列表 与 平铺, 忽略档位切换"""

    def _on_parameter_change(self, _event=None):
        """前缀或起始数字变化后重算每个文件的新名字"""
        self._rebuild_new_names()

    def on_file_selected(self, path):
        """任意面板里的选中项变化时同步右侧预览

        @param path: 文件路径
        """
        self.preview.show(path)

    def _open_file(self, path):
        """用系统默认程序打开文件

        @param path: 文件路径
        """
        open_path(path, parent=self.window)

    def _reveal_file(self, path):
        """在资源管理器中定位文件

        @param path: 文件路径
        """
        open_path(path, parent=self.window, reveal=True)

    def on_theme_changed(self):
        for card in self.folder_blocks:
            card.grid.apply_palette()
        self.preview.refresh()

    def on_hide(self):
        """切走时解除滚轮绑定, 避免在其他页面上仍然响应本页的滚动"""
        unbind_mousewheel(self.canvas)
        for card in self.folder_blocks:
            unbind_mousewheel(card.grid.canvas)

    # ---------------- 文件夹管理 ----------------
    def _on_cards_resize(self, event):
        """面板区随窗口变化: 宽度跟窗口走"""
        self.canvas.itemconfigure(self.canvas_window, width=event.width)

    def _on_yscroll(self, first, last):
        """内容超出可视高度时才显示滚动条, 否则保持设计稿里的干净外观"""
        self.v_scroll.set(first, last)
        need = not (float(first) <= 0.0 and float(last) >= 1.0)
        if need == bool(self.v_scroll.winfo_manager()):
            return
        if need:
            self.v_scroll.pack(side="right", fill="y")
        else:
            self.v_scroll.pack_forget()

    def add_folder(self):
        """弹窗选择文件夹并新增一个文件夹面板"""
        card = FolderCard(self.blocks_frame, self)
        if not card.select_folder():
            card.destroy()
            return
        self.folder_blocks.append(card)
        self._rebuild_new_names()
        self._update_empty_state()
        self._queue_card_layout()

    def remove_folder(self, card):
        """移除一个文件夹面板

        @param card: 要移除的面板
        """
        if card in self.folder_blocks:
            self.folder_blocks.remove(card)
        self._rebuild_new_names()
        self.refresh_overall_counts()
        self._update_empty_state()
        self._queue_card_layout()

    def _update_empty_state(self):
        """没有任何文件夹时显示占位块, 否则显示面板区"""
        if self.folder_blocks:
            self.empty_state.pack_forget()
            self.canvas.pack(side="left", fill="both", expand=True)
            return
        self.canvas.pack_forget()
        self.v_scroll.pack_forget()
        self.empty_state.pack(side="top", fill="both", expand=True)

    def _queue_card_layout(self):
        """面板增删后等一轮布局完成, 再按新的内容高度重算滚动区"""
        def fit():
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
            self.canvas.yview_moveto(0)
        self.root.after(50, fit)

    def rescan_folders(self):
        """重新读取各文件夹里的文件, 与图片查重页的'刷新扫描'一致"""
        for card in self.folder_blocks:
            if card.folder_path:
                card.load_files()
        self._rebuild_new_names()
        self.refresh_overall_counts()

    def refresh_overall_counts(self):
        """刷新状态栏里的文件夹与文件计数"""
        folders = len([b for b in self.folder_blocks if b.folder_path])
        total = sum(len(b.files) for b in self.folder_blocks if b.folder_path)
        self.status.set_text(f"文件夹: {folders} | 总文件数: {total}")

    # ---------------- 新文件名预览 ----------------
    def _collect_items(self):
        """按面板顺序收集 (文件夹, 文件名)

        @return: 列表
        """
        items = []
        for card in self.folder_blocks:
            if card.folder_path:
                for name in card.filtered_files:
                    items.append((card.folder_path, name))
        return items

    def _rebuild_new_names(self):
        """按前缀与起始序号算出每个文件的新名字, 供列表视图预览

        编号顺序与 build_tasks 一致: 先按面板顺序, 再按面板内的文件顺序
        """
        prefix = self.entry_prefix.get().strip()
        try:
            start = int(self.entry_start.get())
        except ValueError:
            start = None
        self._new_names = {}
        if not prefix or start is None:
            for card in self.folder_blocks:
                card.refresh_preview()
            return
        number = start
        for folder, name in self._collect_items():
            extension = os.path.splitext(name)[1]
            self._new_names[os.path.join(folder, name)] = \
                f"{prefix}{number}{extension}"
            number += 1
        for card in self.folder_blocks:
            card.refresh_preview()

    def new_name_of(self, path):
        """取某个文件改后的文件名

        @param path: 文件路径
        @return: 新文件名, 还没有前缀时返回空串
        """
        return self._new_names.get(path, "")

    # ---------------- 取消处理 ----------------
    def cancel_process(self):
        self.cancel_flag = True

    # ---------------- 核心处理 ----------------
    def rename_and_save(self):
        """校验参数并逐个执行重命名任务"""
        prefix = self.entry_prefix.get().strip()
        if not prefix:
            messagebox.showwarning("警告", "请输入文件名前缀", parent=self.window)
            return
        try:
            start_num = int(self.entry_start.get())
        except ValueError:
            messagebox.showwarning("警告", "起始数字必须为整数",
                                   parent=self.window)
            return

        items = self._collect_items()
        if not items:
            messagebox.showwarning("警告", "没有可处理的文件", parent=self.window)
            return

        save_folder = filedialog.askdirectory(title="选择保存目标文件夹",
                                             parent=self.window)
        if not save_folder:
            return

        tasks = build_tasks(items, save_folder, prefix, start_num)

        # 原位重命名模式下跳过'清空/新增'选择, 避免清空源文件夹
        if not any(task[2] for task in tasks):
            choice = messagebox.askyesnocancel(
                "保存模式选择",
                "请选择目标文件夹操作方式:\n\n是 = 清空文件夹\n否 = 在文件夹内新增\n取消 = 终止操作",
                parent=self.window,
            )
            if choice is None:
                return
            if choice:
                try:
                    clear_files_in_folder(save_folder)
                except OSError as error:
                    messagebox.showerror("错误", f"清空目标文件夹失败: {error}",
                                         parent=self.window)
                    return

        self.cancel_flag = False
        self.global_action = None

        total = len(tasks)
        moved = {}
        self.btn_cancel.configure(state="normal")
        self._update_progress(0, total)
        self.status.set_kind("run")

        # 原位重命名: 先把目标名与其他待处理源文件冲突的文件挪到临时名
        inplace_tasks = [task for task in tasks if task[2]]
        if inplace_tasks:
            folder = os.path.dirname(inplace_tasks[0][0])
            inplace_jobs = [(task[3], os.path.basename(task[1]))
                            for task in inplace_tasks]
            try:
                moved = prepare_inplace_temps(folder, inplace_jobs)
            except OSError as error:
                messagebox.showerror("错误", f"准备重命名失败: {error}",
                                     parent=self.window)
                self.btn_cancel.configure(state="disabled")
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
            messagebox.showinfo("已取消", "操作已取消", parent=self.window)
            finished = False
        except TaskError as error:
            restore_inplace_temps(folder, moved)
            messagebox.showerror("错误", f"处理失败: {error.src}\n{error}",
                                 parent=self.window)
            finished = False
        finally:
            self.btn_cancel.configure(state="disabled")

        if not finished:
            return

        self.status.set_kind("ok")
        self.status.set_text("处理完成")
        if messagebox.askyesno("完成", "文件处理完成, 是否现在打开目标文件夹?",
                               parent=self.window):
            open_path(save_folder, parent=self.window)

    def _conflict_dialog(self, filename):
        """返回 overwrite / skip / cancel, 支持对后续冲突文件全局应用

        @param filename: 已存在的目标文件名
        @return: 处理方式
        """
        if self.global_action == "overwrite":
            return "overwrite"
        if self.global_action == "skip":
            return "skip"

        choice = messagebox.askyesnocancel(
            "文件已存在",
            f"{filename} 已存在.\n\n是 = 覆盖\n否 = 跳过\n取消 = 终止操作",
            parent=self.window)
        if choice is None:
            return "cancel"
        if choice:
            if messagebox.askyesno("应用到全部", "是否对后续冲突文件全部覆盖?",
                                   parent=self.window):
                self.global_action = "overwrite"
            return "overwrite"
        if messagebox.askyesno("应用到全部", "是否对后续冲突文件全部跳过?",
                               parent=self.window):
            self.global_action = "skip"
        return "skip"

    def _update_progress(self, processed, total):
        """刷新状态栏里的处理进度

        @param processed: 已处理数量
        @param total: 总数
        """
        percent = int((processed / total) * 100) if total else 0
        self.lbl_progress_text.configure(
            text=f"已处理 {processed} / {total} ({percent}%)")
        self.root.update_idletasks()
