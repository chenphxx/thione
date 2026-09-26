"""端口与文件占用页面: 扫描端口 查询指定端口 查询文件被哪个程序占用。

结果区按查询方式切换, 右侧固定显示选中进程的详情并提供强制结束。强制结束走
TerminateProcess, 与任务管理器的 结束任务 等价, 结束前先让用户确认; 以管理员
权限运行的进程需要 thione 自身也以管理员身份启动才能结束。
"""

import logging
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from ...errors import show_error
from ...shell.page import ToolPage
from . import filelocks, netconn, processes
from .constants import (
    DETAIL_FIELDS,
    EMPTY_STATES,
    EMPTY_VALUE,
    FILE_COLUMNS,
    DETAIL_WIDTH,
    MIN_PORT,
    MAX_PORT,
    PAGE_TITLE,
    PORT_COLUMNS,
    PORT_ENTRY_WIDTH,
    VIEW_FILES,
    VIEW_LABELS,
    VIEW_PORTS,
)

logger = logging.getLogger(__name__)

#: 没有选中进程时的占位文案
NO_SELECTION = "未选择"
#: 端口输入框为空时的说明
EMPTY_PORT_HINT = "输入端口号可只查这个端口, 留空表示显示全部"
#: 还没有扫描过时的说明
NOT_SCANNED_HINT = "还没有扫描, 点击右上角的「扫描本机端口」开始"
#: 文件查询的说明
EMPTY_FILE_HINT = "选择文件后点击「查询占用」"


class PortPage(ToolPage):
    """扫描端口占用并查询文件被哪个程序占用的工具页面。"""

    key = "port"
    title = PAGE_TITLE
    icon = "🔌"
    subtitle = "扫描本机端口占用, 查询端口或者文件被哪个程序占用"

    def __init__(self, master, shell):
        super().__init__(master, shell)

        self._view = VIEW_PORTS
        self._connections = []
        self._entries = {}
        self._row_pids = {}
        self._selected_pid = None
        self._port_var = tk.StringVar()
        self._file_var = tk.StringVar()
        self._only_listen_var = tk.BooleanVar(value=True)
        self._query_hint = tk.StringVar(value=EMPTY_PORT_HINT)
        self._detail_vars = {key: tk.StringVar(value=EMPTY_VALUE)
                             for key, _label in DETAIL_FIELDS}

        self._build_toolbar()
        self.add_divider()
        self._build_query_card()
        self._build_body()
        self._apply_view()

    # ---------------- 界面构建 ----------------
    def _build_toolbar(self):
        _bar, head, actions = self.build_toolbar()
        ttk.Label(head, text=PAGE_TITLE,
                  style="PanelHeader.TLabel").pack(side="left")
        ttk.Label(head, text="查看端口被哪个程序占用, 也可以反过来查文件",
                  style="PanelHint.TLabel").pack(side="left", padx=(12, 0))

        self.btn_scan = ttk.Button(actions, text="扫描本机端口",
                                   style="Accent.TButton", command=self._scan)
        self.btn_scan.pack(side="right")

    def _build_query_card(self):
        """查询方式切换与两种查询条件。"""
        card = ttk.LabelFrame(self, text="查询", padding=(16, 12))
        card.pack(side="top", fill="x")

        row = ttk.Frame(card, style="CardFlat.TFrame")
        row.pack(side="top", fill="x")

        switch = ttk.Frame(row, style="CardFlat.TFrame")
        switch.pack(side="left", padx=(0, 16))
        self._view_buttons = {}
        for key, label in VIEW_LABELS:
            button = ttk.Button(switch, text=label, style="Segment.TButton",
                                command=lambda item=key: self._select_view(item))
            button.pack(side="left", padx=(0, 6))
            self._view_buttons[key] = button

        self._port_controls = ttk.Frame(row, style="CardFlat.TFrame")
        ttk.Label(self._port_controls, text="端口",
                  style="Card.TLabel").pack(side="left")
        entry = ttk.Entry(self._port_controls, textvariable=self._port_var,
                          width=PORT_ENTRY_WIDTH)
        entry.pack(side="left", padx=(8, 8))
        entry.bind("<Return>", lambda _event: self._search_port())
        ttk.Button(self._port_controls, text="查询", style="Secondary.TButton",
                   command=self._search_port).pack(side="left")
        ttk.Checkbutton(self._port_controls, text="只看监听中的端口",
                        style="Card.TCheckbutton",
                        variable=self._only_listen_var,
                        command=self._search_port).pack(side="left",
                                                       padx=(14, 0))

        self._file_controls = ttk.Frame(row, style="CardFlat.TFrame")
        # 按钮先 pack: 窗口缩到最小时宽度不足的部分由最后的路径框承担,
        # 免得按钮文字被挤掉
        ttk.Button(self._file_controls, text="查询占用", style="Accent.TButton",
                   command=self._query_file).pack(side="right")
        ttk.Button(self._file_controls, text="选择文件", style="Secondary.TButton",
                   command=self._choose_file).pack(side="right", padx=(0, 8))
        ttk.Label(self._file_controls, text="文件",
                  style="Card.TLabel").pack(side="left")
        entry = ttk.Entry(self._file_controls, textvariable=self._file_var,
                          width=18, state="readonly")
        entry.pack(side="left", fill="x", expand=True, padx=(8, 8))

        # 查询结果或错误都写在这一行, 不弹窗打断操作
        self.lbl_hint = ttk.Label(card, textvariable=self._query_hint, anchor="w",
                                  style="CardMuted.TLabel")
        self.lbl_hint.pack(side="top", fill="x", pady=(10, 0))

    def _build_body(self):
        """左栏是占用列表, 右栏是选中进程的详情。"""
        body = ttk.Panedwindow(self, orient="horizontal")
        body.pack(side="top", fill="both", expand=True, pady=(12, 0))

        left = ttk.Frame(body)
        body.add(left, weight=1)
        self._build_result_card(left)

        # 固定初始宽度: 详情里的路径与命令行要有足够的换行空间,
        # 之后仍可由分隔条拖动调整
        right = ttk.Frame(body, width=DETAIL_WIDTH)
        right.pack_propagate(False)
        body.add(right, weight=0)
        self._build_details_card(right)

    def _build_result_card(self, parent):
        """结果列表与空状态占位块共用一块区域, 按需要显示其中之一。"""
        self.result_card = ttk.LabelFrame(parent, text="占用列表",
                                          padding=(16, 12))
        self.result_card.pack(side="top", fill="both", expand=True)

        box = ttk.Frame(self.result_card, style="CardFlat.TFrame")
        box.pack(side="top", fill="both", expand=True)

        self.table_area = ttk.Frame(box, style="CardFlat.TFrame")
        self.table = ttk.Treeview(self.table_area, show="headings",
                                  style="Card.Treeview")
        scroll = ttk.Scrollbar(self.table_area, orient="vertical",
                               command=self.table.yview)
        self.table.configure(yscrollcommand=scroll.set)
        # 滚动条先占位: 表格的列宽之和超过面板时, 先 pack 的表格会把宽度用光,
        # 之后 pack 的滚动条拿不到空间会被 Tk 直接隐藏
        scroll.pack(side="right", fill="y")
        self.table.pack(side="left", fill="both", expand=True)
        self.table.bind("<<TreeviewSelect>>", self._on_select)

        self.empty_state = self._build_empty_state(box)

    def _build_empty_state(self, parent):
        """没有结果时顶替列表的占位块。

        @param parent: 承载占位块的容器
        @return: 占位块 Frame (默认不显示)
        """
        box = ttk.Frame(parent, style="CardFlat.TFrame")
        inner = ttk.Frame(box, style="CardFlat.TFrame")
        inner.place(relx=0.5, rely=0.42, anchor="center")
        ttk.Label(inner, text="🔌", style="EmptyIcon.TLabel").pack()
        self.empty_title = ttk.Label(inner, text="", style="EmptyTitle.TLabel")
        self.empty_title.pack(pady=(8, 0))
        self.empty_hint = ttk.Label(inner, text="", style="EmptyHint.TLabel",
                                    justify="center")
        self.empty_hint.pack(pady=(6, 0))
        # 说明文案可能较长, 按容器宽度换行, 避免占位块被撑出卡片
        box.bind("<Configure>", lambda event: self._wrap_empty_state(event.width))
        return box

    def _wrap_empty_state(self, width):
        """按容器宽度调整占位块文字的换行宽度。

        @param width: 占位块容器的当前宽度 (像素)
        """
        wrap = max(240, width - 80)
        self.empty_title.configure(wraplength=wrap)
        self.empty_hint.configure(wraplength=wrap)

    def _build_details_card(self, parent):
        """右栏: 选中进程的详情与强制结束按钮。"""
        card = ttk.LabelFrame(parent, text="进程详情", padding=(16, 12))
        card.pack(side="top", fill="both", expand=True)
        self.details_card = card

        self.btn_kill = ttk.Button(card, text="结束进程", style="Danger.TButton",
                                   state="disabled", command=self._terminate)
        self.btn_kill.pack(side="top", anchor="e")

        grid = ttk.Frame(card, style="CardFlat.TFrame")
        grid.pack(side="top", fill="both", expand=True, pady=(10, 0))
        grid.columnconfigure(1, weight=1)

        self._detail_labels = []
        for row, (key, label) in enumerate(DETAIL_FIELDS):
            ttk.Label(grid, text=label, style="CardMuted.TLabel").grid(
                row=row, column=0, sticky="nw", padx=(0, 12), pady=2)
            value = ttk.Label(grid, textvariable=self._detail_vars[key],
                              style="Card.TLabel", anchor="w", justify="left")
            value.grid(row=row, column=1, sticky="we", pady=2)
            self._detail_labels.append(value)

        # 路径与命令行可能很长, 按卡片宽度换行
        card.bind("<Configure>", self._on_details_resize)

    def _on_details_resize(self, event):
        for label in self._detail_labels:
            label.configure(wraplength=max(160, event.width - 110))

    # ---------------- 视图切换 ----------------
    def _select_view(self, key):
        if key == self._view:
            return
        self._view = key
        self._apply_view()

    def _apply_view(self):
        """按当前视图重建列并复位列表与提示。"""
        self._clear_rows()
        for name, button in self._view_buttons.items():
            button.configure(
                style="SegmentOn.TButton" if name == self._view else "Segment.TButton"
            )

        if self._view == VIEW_PORTS:
            self._file_controls.pack_forget()
            self._port_controls.pack(side="left")
            self.btn_scan.pack(side="right")
            self._set_query_hint(EMPTY_PORT_HINT if self._connections
                                 else NOT_SCANNED_HINT)
            self._set_columns(PORT_COLUMNS)
            self.result_card.configure(text="占用列表")
            empty = EMPTY_STATES[VIEW_PORTS]
        else:
            self._port_controls.pack_forget()
            self._file_controls.pack(side="left", fill="x", expand=True)
            self.btn_scan.pack_forget()
            self._set_query_hint(EMPTY_FILE_HINT)
            self._set_columns(FILE_COLUMNS)
            self.result_card.configure(text="占用该文件的进程")
            empty = EMPTY_STATES[VIEW_FILES]

        self._update_empty_state(*empty)
        self._show_details(None)

    def _set_columns(self, columns):
        """按当前视图重建表格的列。

        @param columns: (列标识, 标题, 宽度, 对齐) 组成的序列
        """
        self.table.configure(columns=[key for key, _title, _width, _anchor
                                      in columns])
        for key, title, width, anchor in columns:
            self.table.heading(key, text=title, anchor="center")
            self.table.column(key, width=width, minwidth=48, anchor=anchor,
                              stretch=key in ("local", "remote", "process", "path"))

    def _clear_rows(self):
        self.table.delete(*self.table.get_children())
        self._row_pids.clear()
        self._selected_pid = None

    def _update_empty_state(self, title, hint):
        """列表为空时显示占位块, 否则显示列表。"""
        if self.table.get_children():
            self.empty_state.pack_forget()
            self.table_area.pack(side="top", fill="both", expand=True)
            return
        self.empty_title.configure(text=title)
        self.empty_hint.configure(text=hint)
        self.table_area.pack_forget()
        self.empty_state.pack(side="top", fill="both", expand=True)

    # ---------------- 端口查询 ----------------
    def _scan(self):
        """扫描本机端口: 清空端口条件后列出当前的连接。"""
        self._port_var.set("")
        if not self._reload_connections():
            return
        self._search_port()

    def _reload_connections(self):
        """重新读取连接表与进程快照。

        @return: 是否成功; 失败时提示用户并保留原有数据
        """
        try:
            self._connections = netconn.list_connections()
        except OSError as exc:
            show_error(str(exc), title="扫描端口失败", parent=self.window)
            return False
        self._entries = processes.snapshot()
        return True

    def _visible_connections(self):
        """按 只看监听中的端口 筛出列表要展示的连接。

        @return: Connection 列表
        """
        if not self._only_listen_var.get():
            return self._connections
        return [row for row in self._connections if netconn.is_listening(row)]

    def _scan_summary(self, rows):
        """扫描结果的一句话说明。

        @param rows: 列表中实际展示的连接
        @return: 说明文本
        """
        pids = {row.pid for row in rows}
        text = f"共 {len(rows)} 条连接, 来自 {len(pids)} 个进程"
        if len(rows) != len(self._connections):
            text += f" · 已隐藏 {len(self._connections) - len(rows)} 条非监听连接"
        return text

    def _search_port(self):
        """按输入框里的端口号过滤连接, 留空表示显示全部。"""
        text = self._port_var.get().strip()
        if not text:
            rows = self._visible_connections()
            self._fill_ports(rows)
            self._set_query_hint(self._scan_summary(rows) if self._connections
                                 else NOT_SCANNED_HINT)
            return

        if not text.isdigit():
            self._set_query_hint("端口号只能是数字", error=True)
            return
        port = int(text)
        if not MIN_PORT <= port <= MAX_PORT:
            self._set_query_hint(f"端口号需要在 {MIN_PORT} 到 {MAX_PORT} 之间",
                                 error=True)
            return

        # 还没有扫描过就先扫一次, 保留输入框里的端口号
        if not self._connections and not self._reload_connections():
            return

        matched = [row for row in self._connections if row.local_port == port]
        if not matched:
            self._fill_ports([], empty=(
                f"端口 {port} 当前没有被占用",
                "换一个端口号再查, 或者点右上角的「扫描本机端口」看全部占用",
            ))
            self._set_query_hint(f"端口 {port} 当前没有被占用")
            return

        self._fill_ports(matched, select_first=True)
        names = " ".join(self._names_of(matched))
        self._set_query_hint(f"端口 {port} 被 {len(matched)} 条连接占用: {names}")

    def _fill_ports(self, rows, select_first=False, empty=None):
        """把连接记录填进表格。

        @param rows: Connection 列表
        @param select_first: True 时选中第一行, 右栏立即显示详情
        @param empty: 没有结果时的 (标题, 说明)
        """
        self._clear_rows()
        for row in rows:
            remote = f"{row.remote_addr}:{row.remote_port}" if row.remote_addr else ""
            item = self.table.insert("", "end", values=(
                row.protocol, row.local_addr, row.local_port, row.state,
                remote, row.pid, self._process_name(row.pid),
            ))
            self._row_pids[item] = row.pid
        self._update_empty_state(*(empty or EMPTY_STATES[VIEW_PORTS]))
        if select_first and rows:
            self._select_first_row()

    def _names_of(self, rows):
        """结果里出现过的进程名, 去重后保持稳定顺序。"""
        seen = []
        for row in rows:
            name = self._process_name(row.pid)
            if name not in seen:
                seen.append(name)
        return seen

    def _process_name(self, pid):
        """从进程快照里取进程名。"""
        entry = self._entries.get(pid)
        if entry is not None:
            return entry.name
        return f"PID {pid}"

    # ---------------- 文件查询 ----------------
    def _choose_file(self):
        path = filedialog.askopenfilename(title="选择要查询占用的文件",
                                          parent=self.window)
        if not path:
            return
        self._file_var.set(os.path.normpath(path))
        self._query_file()

    def _query_file(self):
        """查询选中文件被哪些进程占用。"""
        path = self._file_var.get().strip()
        if not path:
            self._set_query_hint("先选择要查询的文件", error=True)
            return

        # 文件可能是刚启动的程序打开的, 每次查询都取一份新的进程快照
        self._entries = processes.snapshot()
        try:
            locks = filelocks.list_locks(path)
        except OSError as exc:
            self._fill_files([], empty=("无法查询这个文件", str(exc)))
            self._set_query_hint(str(exc), error=True)
            return

        name = os.path.basename(path)
        if not locks:
            self._report_free_file(path, name)
            return

        self._fill_files(locks)
        self._set_query_hint(f"{name} 正被 {len(locks)} 个进程占用")

    def _report_free_file(self, path, name):
        """重启管理器没有返回占用者时, 再用独占打开复核一次。

        查看器之类的程序读完文件就释放句柄, 重启管理器因此查不到它们; 反过来,
        独占打开失败说明确实有程序按独占方式持有文件, 只是没能列出是谁。

        @param path: 文件的完整路径
        @param name: 文件名, 用于提示行
        """
        probe = filelocks.is_available(path)
        if probe is False:
            self._fill_files([], empty=(
                "文件正被占用, 但没有查到占用它的程序",
                "文件无法独占打开, 占用它的程序可能以管理员权限运行, "
                "试着以管理员身份启动 thione 再查",
            ))
            self._set_query_hint(
                f"{name} 正被占用, 但重启管理器没有返回占用它的进程", error=True)
            return
        if probe is None:
            self._fill_files([], empty=(
                "没能确认文件是否被占用",
                "重启管理器没有返回占用者, 独占打开又因为权限不足无法验证",
            ))
            self._set_query_hint(f"无法确认 {name} 是否被占用", error=True)
            return
        self._fill_files([], empty=(
            "没有程序占用该文件",
            "独占打开验证通过, 文件当前可以正常修改或者删除; "
            "读完就释放的程序 (多数图片查看器) 不会一直占用文件",
        ))
        self._set_query_hint(f"{name} 当前没有程序占用")

    def _fill_files(self, locks, empty=None):
        """把占用文件的进程填进表格。

        @param locks: FileLock 列表
        @param empty: 没有结果时的 (标题, 说明)
        """
        self._clear_rows()
        for lock in locks:
            detail = processes.describe(lock.pid, self._entries)
            item = self.table.insert("", "end", values=(
                lock.pid, detail.name or lock.app_name or "未知",
                lock.app_type, detail.path or EMPTY_VALUE,
            ))
            self._row_pids[item] = lock.pid
        self._update_empty_state(*(empty or EMPTY_STATES[VIEW_FILES]))
        if locks:
            self._select_first_row()

    # ---------------- 详情与结束进程 ----------------
    def _select_first_row(self):
        children = self.table.get_children()
        if not children:
            return
        self.table.selection_set(children[0])
        self.table.focus(children[0])

    def _on_select(self, _event=None):
        selection = self.table.selection()
        if not selection:
            self._show_details(None)
            return
        self._show_details(self._row_pids.get(selection[0]))

    def _show_details(self, pid):
        """把选中进程的详情填进右栏。

        @param pid: 进程 ID, None 表示没有选中任何一行
        """
        self._selected_pid = pid
        if pid is None:
            for key, _label in DETAIL_FIELDS:
                self._detail_vars[key].set(EMPTY_VALUE)
            self._detail_vars["process"].set(NO_SELECTION)
            self.btn_kill.configure(state="disabled")
            return

        detail = processes.describe(pid, self._entries)
        parent = EMPTY_VALUE
        if detail.parent_name:
            parent = f"{detail.parent_name} (PID {detail.parent_pid})"
        values = {
            "process": f"{detail.name or '未知'} (PID {detail.pid})",
            "path": detail.path or EMPTY_VALUE,
            # 命令行里的换行会撑高详情, 统一压成空格
            "cmdline": " ".join(detail.cmdline.split()) or EMPTY_VALUE,
            "started": detail.started or EMPTY_VALUE,
            "memory": detail.memory or EMPTY_VALUE,
            "parent": parent,
        }
        for key, value in values.items():
            self._detail_vars[key].set(value)
        self.btn_kill.configure(state="normal")

    def _terminate(self):
        """确认后强制结束选中的进程, 然后刷新列表。"""
        pid = self._selected_pid
        if pid is None:
            return
        name = self._process_name(pid)
        if not messagebox.askyesno(
                "结束进程",
                f"确定要强制结束 {name} (PID {pid}) 吗?\n\n"
                f"程序未保存的数据会丢失, 以管理员身份运行的进程需要 thione "
                f"也以管理员身份启动。",
                parent=self.window):
            return

        try:
            processes.terminate(pid)
        except OSError as exc:
            show_error(str(exc), title="结束进程失败", parent=self.window)
            return

        self.set_status(f"已结束 {name} (PID {pid})")
        self._refresh_view()

    def _refresh_view(self):
        """结束进程之后重新取一次数据, 保持当前的查询条件。"""
        if self._view == VIEW_PORTS:
            if self._reload_connections():
                self._search_port()
        else:
            self._query_file()

    # ---------------- 提示 ----------------
    def _set_query_hint(self, text, error=False):
        """更新查询卡片下方的说明。

        @param text: 要显示的内容
        @param error: True 时改用危险色
        """
        self._query_hint.set(text)
        style = "CardError.TLabel" if error else "CardMuted.TLabel"
        if self.lbl_hint.cget("style") != style:
            self.lbl_hint.configure(style=style)
