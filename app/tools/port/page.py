"""端口与文件占用页面: 扫描端口 查询指定端口 查询文件被哪个程序占用

版式与设计稿一致: 内容区顶部一行是查询条件, 下面左栏是占用列表 右栏固定 304
像素宽显示选中进程的详情并提供强制结束. 强制结束走 TerminateProcess, 与任务
管理器的 结束任务 等价, 结束前先让用户确认; 以管理员权限运行的进程需要 thione
自身也以管理员身份启动才能结束
"""

import logging
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from ... import kit
from ...errors import open_path, show_error
from ...shell.page import ToolPage
from ...theme import (
    SIZE_LABEL,
    tint,
)
from . import filelocks, netconn, processes
from .constants import (
    DETAIL_FIELDS,
    DETAIL_LABEL_WIDTH,
    DETAIL_MAX_WIDTH,
    DETAIL_MIN_WIDTH,
    DETAIL_WIDTH,
    EMPTY_STATES,
    EMPTY_VALUE,
    FILE_COLUMNS,
    MAX_PORT,
    MIN_PORT,
    PAGE_TITLE,
    PORT_COLUMNS,
    PORT_ENTRY_WIDTH,
    SUBTITLE,
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
NOT_SCANNED_HINT = "还没有扫描, 点击右上角的'扫描本机端口'开始"
#: 文件查询的说明
EMPTY_FILE_HINT = "选择文件后点击'查询'"


class PortPage(ToolPage):
    """扫描端口占用并查询文件被哪个程序占用的工具页面"""

    key = "port"
    title = PAGE_TITLE
    icon = "\uE839"
    subtitle = SUBTITLE

    def __init__(self, master, shell):
        super().__init__(master, shell)

        self._view = VIEW_PORTS
        self._connections = []
        self._entries = {}
        self._row_pids = {}
        self._selected_pid = None
        self._only_listen_var = tk.BooleanVar(value=True)
        self._file_path = ""

        self._build_toolbar()
        self._build_query()
        self._build_split()
        self._build_statusbar()
        self._apply_view()

    # ---------------- 界面构建 ----------------
    def _build_toolbar(self):
        """顶栏按钮"""
        self.btn_scan = self.add_actions((
            ("扫描本机端口", "Primary.TButton", self._scan),
        ))[0]

    def _build_query(self):
        """查询条件行: 查询方式切换与两种查询条件"""
        panel = self.add_panel(head=False, grow=False, body_pad=(14, 12))
        row = tk.Frame(panel.body, bd=0, highlightthickness=0)
        tint(row, bg="panel")
        row.configure(bg=self.theme.rgb("panel"))
        row.pack(side="top", fill="x")

        self.view_switch = kit.Segment(row, self.theme, VIEW_LABELS,
                                       value=self._view,
                                       command=self._select_view,
                                       surface="panel")
        self.view_switch.pack(side="left")

        self._port_controls = tk.Frame(row, bd=0, highlightthickness=0)
        tint(self._port_controls, bg="panel")
        self._port_controls.configure(bg=self.theme.rgb("panel"))
        kit.text(self._port_controls, self.theme, value="端口",
                 size=SIZE_LABEL, token="muted",
                 surface="panel").pack(side="left", padx=(14, 8))
        self.entry_port = kit.EntryField(self._port_controls, self.theme,
                                         width=PORT_ENTRY_WIDTH)
        self.entry_port.pack(side="left")
        self.entry_port.entry.bind("<Return>", lambda _e: self._search_port())
        ttk.Button(self._port_controls, text="查询", style="Primary.TButton",
                   command=self._search_port).pack(side="left", padx=(8, 0))
        self.check_listen = kit.Check(self._port_controls, self.theme,
                                      value="只看监听中的端口",
                                      variable=self._only_listen_var,
                                      command=lambda _v: self._search_port())
        self.check_listen.pack(side="left", padx=(14, 0))

        self._file_controls = tk.Frame(row, bd=0, highlightthickness=0)
        tint(self._file_controls, bg="panel")
        self._file_controls.configure(bg=self.theme.rgb("panel"))
        ttk.Button(self._file_controls, text="查询", style="Primary.TButton",
                   command=self._query_file).pack(side="right")
        ttk.Button(self._file_controls, text="选择文件", style="TButton",
                   command=self._choose_file).pack(side="right", padx=(0, 8))
        kit.text(self._file_controls, self.theme, value="文件",
                 size=SIZE_LABEL, token="muted",
                 surface="panel").pack(side="left", padx=(14, 8))
        self.field_file = kit.Field(self._file_controls, self.theme,
                                    value="未选择", token="muted", width=320)
        self.field_file.pack(side="left", fill="x", expand=True)

    def _build_split(self):
        """左栏是占用列表, 右栏是选中进程的详情"""
        split = tk.Frame(self.body, bd=0, highlightthickness=0)
        tint(split, bg="canvas")
        split.configure(bg=self.theme.rgb("canvas"))
        split.pack(side="top", fill="both", expand=True)

        right = kit.Panel(split, self.theme, title="进程详情", body_pad=(14, 14))
        right.configure(width=DETAIL_WIDTH)
        right.pack(side="right", fill="y")
        right.pack_propagate(False)
        self.details_panel = right
        self._detail_width = DETAIL_WIDTH
        self._build_details(right.body)

        # 占用列表与进程详情之间的拖拽分隔条: 左右拖动改变详情栏的宽度
        self.splitter = kit.Splitter(split, self.theme, orient="vertical",
                                     on_drag=self._on_splitter_drag,
                                     on_start=self._on_splitter_start)
        self.splitter.pack(side="right", fill="y")

        left = kit.Panel(split, self.theme, title="占用列表",
                         body_pad=(14, 10))
        left.pack(side="left", fill="both", expand=True, padx=(0, 14))
        self.result_panel = left
        self.table = kit.Table(
            left.body, self.theme, PORT_COLUMNS,
            on_select=self._on_row_select,
            empty_text="", surface="panel")
        self.table.pack(side="top", fill="both", expand=True)

    def _build_details(self, parent):
        """右栏: 选中进程的详情与操作按钮

        @param parent: 详情面板的内容区
        """
        grid, self._detail_labels, self._apply_details = kit.value_grid(
            parent, self.theme, DETAIL_FIELDS, surface="panel",
            label_width=DETAIL_LABEL_WIDTH)
        grid.pack(side="top", fill="x")

        actions = tk.Frame(parent, bd=0, highlightthickness=0)
        tint(actions, bg="panel")
        actions.configure(bg=self.theme.rgb("panel"))
        actions.pack(side="bottom", anchor="w")
        self.btn_kill = ttk.Button(actions, text="结束进程",
                                   style="PanelDanger.TButton",
                                   state="disabled", command=self._terminate)
        self.btn_kill.pack(side="left")
        self.btn_reveal = ttk.Button(actions, text="打开所在文件夹",
                                     style="TButton",
                                     command=self._open_location)
        self.btn_reveal.pack(side="left", padx=(8, 0))
        parent.bind("<Configure>", self._on_details_resize)

    def _build_statusbar(self):
        """状态栏: 圆点 说明与右侧的计数指标"""
        self.status.set_kind("idle")
        self.status.set_text(NOT_SCANNED_HINT)
        self.metric = kit.text(self.status.tail, self.theme, size=SIZE_LABEL,
                               mono_font=True, surface="side")
        self.status.add_tail(self.metric)

    def _on_details_resize(self, event):
        """路径与命令行可能很长, 按面板宽度换行

        @param event: 面板尺寸变化事件
        """
        width = max(120, event.width - DETAIL_LABEL_WIDTH - 40)
        for key in ("path", "cmdline"):
            self._detail_labels[key].configure(wraplength=width)

    def _on_splitter_start(self):
        """记下拖动开始时的详情栏宽度, 之后按绝对偏移量计算新宽度"""
        self._detail_origin = self._detail_width

    def _on_splitter_drag(self, delta):
        """拖动分隔条时调整进程详情栏的宽度

        @param delta: 相对按下位置的像素偏移, 向右为正
        """
        width = max(DETAIL_MIN_WIDTH,
                    min(DETAIL_MAX_WIDTH,
                        getattr(self, "_detail_origin", self._detail_width)
                        - delta))
        if width == self._detail_width:
            return
        self._detail_width = width
        self.details_panel.configure(width=width)

    # ---------------- 视图切换 ----------------
    def _select_view(self, key):
        """切换端口占用与文件占用两种查询方式

        @param key: 视图标识
        """
        if key == self._view:
            return
        self._view = key
        self._apply_view()

    def _apply_view(self):
        """按当前视图切换查询条件与列表列"""
        self.view_switch.set(key=self._view)
        if self._view == VIEW_PORTS:
            self._file_controls.pack_forget()
            self._port_controls.pack(side="left")
            self.result_panel.set_title("占用列表")
            self._set_columns(PORT_COLUMNS)
            self._set_hint(EMPTY_PORT_HINT if self._connections
                           else NOT_SCANNED_HINT)
        else:
            self._port_controls.pack_forget()
            self._file_controls.pack(side="left", fill="x", expand=True)
            self.result_panel.set_title("占用该文件的进程")
            self._set_columns(FILE_COLUMNS)
            self._set_hint(EMPTY_FILE_HINT)

        self.table.set_rows([], keep_selection=False)
        self.table.set_empty_text(EMPTY_STATES[self._view][0])
        self._set_panel_count("")
        self._row_pids.clear()
        self._show_details(None)

    def _set_columns(self, columns):
        """按当前视图重建表格的列

        @param columns: 列定义序列
        """
        self.table.set_columns(columns)

    def _set_hint(self, text, error=False):
        """更新状态栏里的查询说明

        @param text: 要显示的内容
        @param error: True 时用危险色圆点提醒
        """
        self.status.set_text(text)
        self.status.set_kind("fail" if error else "idle")

    def _set_panel_count(self, text):
        """更新列表面板头部右侧的计数

        @param text: 计数文本
        """
        self.result_panel.set_right(text)

    # ---------------- 端口查询 ----------------
    def _scan(self):
        """扫描本机端口: 清空端口条件后列出当前的连接"""
        self.entry_port.set("")
        if not self._reload_connections():
            return
        self._search_port()

    def _reload_connections(self):
        """重新读取连接表与进程快照

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
        """按 只看监听中的端口 筛出列表要展示的连接

        @return: Connection 列表
        """
        if not self._only_listen_var.get():
            return self._connections
        return [row for row in self._connections if netconn.is_listening(row)]

    def _scan_summary(self, rows):
        """扫描结果的一句话说明

        @param rows: 列表中实际展示的连接
        @return: 说明文本
        """
        text = "扫描完成"
        if len(rows) != len(self._connections):
            text += f" | 已隐藏 {len(self._connections) - len(rows)} 条非监听连接"
        return text

    def _search_port(self):
        """按输入框里的端口号过滤连接, 留空表示显示全部"""
        text = self.entry_port.get().strip()
        if not text:
            rows = self._visible_connections()
            self._fill_ports(rows)
            self._set_hint(self._scan_summary(rows) if self._connections
                           else NOT_SCANNED_HINT)
            return

        if not text.isdigit():
            self._set_hint("端口号只能是数字", error=True)
            return
        port = int(text)
        if not MIN_PORT <= port <= MAX_PORT:
            self._set_hint(f"端口号需要在 {MIN_PORT} 到 {MAX_PORT} 之间",
                           error=True)
            return

        # 还没有扫描过就先扫一次, 保留输入框里的端口号
        if not self._connections and not self._reload_connections():
            return

        matched = [row for row in self._connections if row.local_port == port]
        if not matched:
            self._fill_ports([], empty=(f"端口 {port} 当前没有被占用",
                                        "换一个端口号再查, 或者点右上角的"
                                        "'扫描本机端口'看全部占用"))
            self._set_hint(f"端口 {port} 当前没有被占用")
            return

        self._fill_ports(matched, select_first=True)
        names = " ".join(self._names_of(matched))
        self._set_hint(f"端口 {port} 被 {len(matched)} 条连接占用: {names}")
        self.status.set_kind("ok")

    def _fill_ports(self, rows, select_first=False, empty=None):
        """把连接记录填进表格

        @param rows: Connection 列表
        @param select_first: True 时选中第一行, 右栏立即显示详情
        @param empty: 没有结果时的 (标题, 说明)
        """
        self._row_pids.clear()
        table_rows = []
        for row in rows:
            table_rows.append({
                "data": row.pid,
                "proto": row.protocol,
                "local": f"{row.local_addr}:{row.local_port}",
                "state": _state_cell(row),
                "pid": str(row.pid),
                "process": self._process_name(row.pid),
            })
        self.table.set_rows(table_rows)
        self.table.set_empty_text((empty or EMPTY_STATES[self._view])[0])
        self._set_panel_count(f"{len(rows)} 条连接")
        pids = {row.pid for row in rows}
        self.metric.configure(
            text=f"{len(rows)} 条连接 · {len(pids)} 个进程" if rows else "")
        if select_first and rows:
            self.table.select(0, notify=True)

    def _names_of(self, rows):
        """结果里出现过的进程名, 去重后保持稳定顺序

        @param rows: Connection 列表
        @return: 进程名列表
        """
        seen = []
        for row in rows:
            name = self._process_name(row.pid)
            if name not in seen:
                seen.append(name)
        return seen

    def _process_name(self, pid):
        """从进程快照里取进程名

        @param pid: 进程 ID
        @return: 进程名
        """
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
        self._set_file(os.path.normpath(path))
        self._query_file()

    def _set_file(self, path):
        """更新查询条件里的文件路径

        @param path: 文件路径
        """
        self._file_path = path
        self.field_file.set(path or "未选择", token="text" if path else "muted")

    def _query_file(self):
        """查询选中文件被哪些进程占用"""
        path = self._file_path
        if not path:
            self._set_hint("先选择要查询的文件", error=True)
            return

        # 文件可能是刚启动的程序打开的, 每次查询都取一份新的进程快照
        self._entries = processes.snapshot()
        try:
            locks = filelocks.list_locks(path)
        except OSError as exc:
            self._fill_files([], empty=("无法查询这个文件", str(exc)))
            self._set_hint(str(exc), error=True)
            return

        name = os.path.basename(path)
        if not locks:
            self._report_free_file(path, name)
            return

        self._fill_files(locks)
        self._set_hint(f"{name} 正被 {len(locks)} 个进程占用")
        self.status.set_kind("ok")

    def _report_free_file(self, path, name):
        """重启管理器没有返回占用者时, 再用独占打开复核一次

        查看器之类的程序读完文件就释放句柄, 重启管理器因此查不到它们; 反过来,
        独占打开失败说明确实有程序按独占方式持有文件, 只是没能列出是谁

        @param path: 文件的完整路径
        @param name: 文件名, 用于提示
        """
        probe = filelocks.is_available(path)
        if probe is False:
            self._fill_files([], empty=(
                "文件正被占用, 但没有查到占用它的程序",
                "文件无法独占打开, 占用它的程序可能以管理员权限运行",
            ))
            self._set_hint(
                f"{name} 正被占用, 但重启管理器没有返回占用它的进程", error=True)
            return
        if probe is None:
            self._fill_files([], empty=(
                "没能确认文件是否被占用",
                "重启管理器没有返回占用者, 独占打开又因为权限不足无法验证",
            ))
            self._set_hint(f"无法确认 {name} 是否被占用", error=True)
            return
        self._fill_files([], empty=(
            "没有程序占用该文件",
            "独占打开验证通过, 文件当前可以正常修改或者删除",
        ))
        self._set_hint(f"{name} 当前没有程序占用")
        self.status.set_kind("ok")

    def _fill_files(self, locks, empty=None):
        """把占用文件的进程填进表格

        @param locks: FileLock 列表
        @param empty: 没有结果时的 (标题, 说明)
        """
        self._row_pids.clear()
        table_rows = []
        for lock in locks:
            detail = processes.describe(lock.pid, self._entries)
            table_rows.append({
                "data": lock.pid,
                "pid": str(lock.pid),
                "process": detail.name or lock.app_name or "未知",
                "type": lock.app_type,
                "path": detail.path or EMPTY_VALUE,
            })
        self.table.set_rows(table_rows)
        self.table.set_empty_text((empty or EMPTY_STATES[self._view])[0])
        self._set_panel_count(f"{len(locks)} 个进程" if locks else "")
        self.metric.configure(text=f"{len(locks)} 个进程" if locks else "")
        if locks:
            self.table.select(0, notify=True)

    # ---------------- 详情与结束进程 ----------------
    def _on_row_select(self, pid, _index):
        """表格选中行变化时刷新右栏

        @param pid: 行对应的进程 ID
        @param _index: 行号
        """
        self._show_details(pid)

    def _show_details(self, pid):
        """把选中进程的详情填进右栏

        @param pid: 进程 ID, None 表示没有选中任何一行
        """
        self._selected_pid = pid
        if pid is None:
            self._apply_details({key: EMPTY_VALUE for key, _label in
                                 DETAIL_FIELDS})
            self._apply_details({"process": NO_SELECTION})
            self.btn_kill.configure(state="disabled")
            return

        detail = processes.describe(pid, self._entries)
        parent = EMPTY_VALUE
        if detail.parent_name:
            parent = f"{detail.parent_name} (PID {detail.parent_pid})"
        self._apply_details({
            "process": detail.name or "未知",
            "pid": str(detail.pid),
            "started": detail.started or EMPTY_VALUE,
            "memory": detail.memory or EMPTY_VALUE,
            "path": detail.path or EMPTY_VALUE,
            # 命令行里的换行会撑高详情, 统一压成空格
            "cmdline": " ".join(detail.cmdline.split()) or EMPTY_VALUE,
            "parent": parent,
        })
        self.btn_kill.configure(state="normal")

    def _open_location(self):
        """在资源管理器中定位选中进程的可执行文件"""
        pid = self._selected_pid
        if pid is None:
            return
        path = processes.describe(pid, self._entries).path
        if not path:
            self._set_hint("这个进程没有可用的可执行文件路径", error=True)
            return
        open_path(path, parent=self.window, reveal=True)

    def _terminate(self):
        """确认后强制结束选中的进程, 然后刷新列表"""
        pid = self._selected_pid
        if pid is None:
            return
        name = self._process_name(pid)
        if not messagebox.askyesno(
                "结束进程",
                f"确定要强制结束 {name} (PID {pid}) 吗?\n\n"
                f"程序未保存的数据会丢失, 以管理员身份运行的进程需要 thione "
                f"也以管理员身份启动",
                parent=self.window):
            return

        try:
            processes.terminate(pid)
        except OSError as exc:
            show_error(str(exc), title="结束进程失败", parent=self.window)
            return

        self.status.set_kind("ok")
        self.status.set_text(f"已结束 {name} (PID {pid})")
        self._refresh_view()

    def _refresh_view(self):
        """结束进程之后重新取一次数据, 保持当前的查询条件"""
        if self._view == VIEW_PORTS:
            if self._reload_connections():
                self._search_port()
        else:
            self._query_file()

    # ---------------- 生命周期 ----------------
    def on_show(self):
        """进入页面时刷新进程快照, 详情才不会显示过期数据"""
        if self._entries:
            self._entries = processes.snapshot()

    def on_theme_changed(self):
        """主题切换后重新填一次列表, 状态列的颜色来自表格的绘制"""
        if self._view == VIEW_PORTS:
            self._search_port()


def _state_cell(row):
    """把连接状态转成表格单元格

    监听中的连接用强调色里的成功色, 其余 (已建立 等待等) 用弱化色, 与设计稿一致

    @param row: Connection 记录
    @return: 文本, 或者 (文本, 颜色令牌)
    """
    state = row.state or EMPTY_VALUE
    if netconn.is_listening(row):
        return state, "ok"
    return state, "muted"
