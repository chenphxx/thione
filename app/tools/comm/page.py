"""串口助手页面: 串口与网络两条链路各自收发数据

顶部一行连接配置: 左边切换串口通信与网络通信, 右边是当前链路的参数与开关按钮;
下方接收区与发送区上下排列, 每个区域的左侧是数据视图, 右侧是配置列, 展示的内容
随当前链路切换。两条链路的会话互相独立, 读线程只把收到的数据与状态变化放进队列,
主线程按固定间隔取出来刷新界面, 因此后台线程不会碰到 tkinter 对象; 打开串口
测试连接与端口检查同样放在后台线程, 避免连接超时把界面卡住
"""

import logging
import os
import queue
import threading
import time
import tkinter as tk
from tkinter import filedialog, ttk

from ...errors import show_error
from ...shell.page import ToolPage
from . import ports
from .codec import ParseError
from .constants import (
    ALL_ADDRESSES,
    BAUD_COMBO_WIDTH,
    BAUD_RATES,
    BITS_COMBO_WIDTH,
    BTN_CLOSE_NET,
    BTN_CLOSE_PORT,
    BTN_LOAD_CONFIG,
    BTN_OPEN_PORT,
    BTN_REFRESH_PORTS,
    BTN_TEST_CONNECT,
    CHECK_FAIL,
    CHECK_OK,
    CLOSE_JOIN_TIMEOUT,
    DATA_BITS,
    DEFAULT_BAUD,
    DEFAULT_DATA_BITS,
    DEFAULT_PARITY,
    DEFAULT_PROTO,
    DEFAULT_STOP_BITS,
    DISPLAY_AUTO,
    HINT_NEED_PORT,
    HINT_NET_IDLE,
    HINT_NO_PORTS,
    HINT_SERIAL_IDLE,
    HOST_ENTRY_WIDTH,
    IP_COMBO_WIDTH,
    LINK_CHOICES,
    LINK_NET,
    LINK_SERIAL,
    MAX_MESSAGES_PER_POLL,
    PAGE_TITLE,
    PANEL_NET_RECEIVE,
    PANEL_NET_SEND,
    PANEL_SERIAL_RECEIVE,
    PANEL_SERIAL_SEND,
    PARITY_COMBO_WIDTH,
    PARITY_LABELS,
    POLL_INTERVAL_MS,
    PORT_COMBO_WIDTH,
    PORT_ENTRY_WIDTH,
    PROTO_COMBO_WIDTH,
    PROTO_HINTS,
    PROTOCOLS,
    PROTO_TCP_CLIENT,
    PROTO_TCP_SERVER,
    PROTO_UDP,
    STOP_BITS,
    SUBTITLE,
)
from .panels import ReceivePanel, SendPanel
from .session import (
    SerialSession,
    SessionError,
    TcpClientSession,
    TcpServerSession,
    UdpSession,
)
from .target_window import ask_targets

logger = logging.getLogger(__name__)

#: 控件可用状态下的 ttk state, 关闭时统一置为 disabled, 打开时按此恢复
STATE_ATTR = "_comm_state"

#: 载入文本与保存接收数据的文件类型
TEXT_FILE_TYPES = (("文本文件", "*.txt"), ("所有文件", "*.*"))

#: 两条链路的中文名, 用于提示文案
LINK_LABELS = {LINK_SERIAL: "串口", LINK_NET: "网络"}


def _choice_key(choices, label, default):
    """把下拉框的显示值换回键

    @param choices: (键, 显示名) 组成的元组
    @param label: 显示值
    @param default: 找不到时的返回值
    @return: 键
    """
    for key, text in choices:
        if text == label:
            return key
    return default


def _choice_label(choices, key):
    """把键换成下拉框的显示值

    @param choices: (键, 显示名) 组成的元组
    @param key: 键
    @return: 显示值
    """
    for item, text in choices:
        if item == key:
            return text
    return choices[0][1]


def _read_number(text, label):
    """把输入框里的内容读成整数

    @param text: 输入内容
    @param label: 出错提示里使用的名称
    @return: 整数
    @throws ValueError: 内容为空或者不是整数时
    """
    body = text.strip()
    if not body:
        raise ValueError("%s不能为空" % label)
    try:
        return int(body)
    except ValueError:
        raise ValueError("%s必须是整数" % label) from None


def _parse_port(text, label):
    """把端口输入框的内容读成端口号

    @param text: 输入内容
    @param label: 出错提示里使用的名称
    @return: 端口号, 0 表示留空由系统分配
    @throws ValueError: 不是数字或者超出 0 到 65535 时
    """
    body = text.strip()
    if not body:
        return 0
    value = _read_number(body, label)
    if not 0 <= value <= 65535:
        raise ValueError("%s超出 0 到 65535" % label)
    return value


def _mark_state(widget, state):
    """登记控件可用时的 ttk state

    配置区整体开关时需要把每个控件恢复成各自的状态, 例如波特率可以手填而校验位
    只能从列表里选

    @param widget: ttk 控件
    @param state: normal 或者 readonly
    """
    setattr(widget, STATE_ATTR, state)
    widget.configure(state=state)


def _set_group_enabled(group, enabled):
    """打开或者关闭一组控件

    @param group: 容器
    @param enabled: True 按各自的状态恢复, False 全部禁用
    """
    for child in group.winfo_children():
        if isinstance(child, ttk.Frame):
            _set_group_enabled(child, enabled)
        elif isinstance(child, (ttk.Entry, ttk.Button, ttk.Combobox)):
            state = getattr(child, STATE_ATTR, "normal")
            child.configure(state=state if enabled else "disabled")


def _add_field(parent, label, width, values, variable, readonly=False):
    """按 标签加下拉框 的形式往一行里加一个串口参数

    @param parent: 所在的行
    @param label: 标签文字
    @param width: 下拉框宽度 (字符数)
    @param values: 下拉框取值
    @param variable: 绑定的变量
    @param readonly: True 只能从列表里选
    @return: 下拉框
    """
    ttk.Label(parent, text=label, style="CardMuted.TLabel").pack(side="left")
    combo = ttk.Combobox(parent, width=width, values=list(values),
                         textvariable=variable)
    combo.pack(side="left", padx=(4, 10))
    _mark_state(combo, "readonly" if readonly else "normal")
    return combo


def _client_addresses(session):
    """当前在线的客户端地址

    只有 TCP Server 有客户端列表, 读线程同时可能在改动这份数据, 因此这里兜住
    可能出现的异常, 取不到时当作还没有客户端

    @param session: 会话
    @return: 地址列表
    """
    try:
        return list(session.client_addresses())
    except (AttributeError, RuntimeError):
        logger.debug("读取客户端列表失败", exc_info=True)
        return []


class CommPage(ToolPage):
    """通过串口或者网络与外部设备收发数据的工具页面"""

    key = "comm"
    title = PAGE_TITLE
    icon = "📡"
    subtitle = SUBTITLE

    def __init__(self, master, shell):
        super().__init__(master, shell)

        self._messages = queue.Queue()
        self._workers = []
        self._poll_job = None
        self._closing = False

        self._serial_session = None
        self._net_session = None
        self._serial_busy = False
        self._net_busy = False
        self._open_port = ""
        self._port_devices = {}
        self._config_loaded = False
        self._active_link = LINK_SERIAL
        # 每条链路各自保留最近一条提示, 切换回来时显示的还是它自己的状态
        self._hints = {LINK_SERIAL: (HINT_SERIAL_IDLE, False),
                       LINK_NET: (HINT_NET_IDLE, False)}

        self._port_var = tk.StringVar()
        self._baud_var = tk.StringVar(value=str(DEFAULT_BAUD))
        self._parity_var = tk.StringVar(value=DEFAULT_PARITY)
        self._data_var = tk.StringVar(value=str(DEFAULT_DATA_BITS))
        self._stop_var = tk.StringVar(value=DEFAULT_STOP_BITS)

        self._proto_var = tk.StringVar(value=_choice_label(PROTOCOLS, DEFAULT_PROTO))
        self._dest_host_var = tk.StringVar()
        self._dest_port_var = tk.StringVar()
        self._local_var = tk.StringVar()
        self._recv_port_var = tk.StringVar()
        self._send_port_var = tk.StringVar()
        self._config_hint = tk.StringVar(value=HINT_SERIAL_IDLE)

        self._build_toolbar()
        self.add_divider()
        self._build_config_card()
        self._build_panels()
        self._apply_link()

        self._poll_job = self.root.after(POLL_INTERVAL_MS, self._poll_messages)

    # ---------------- 界面构建 ----------------
    def _build_toolbar(self):
        _bar, head, actions = self.build_toolbar()
        self._actions = actions
        ttk.Label(head, text=PAGE_TITLE,
                  style="PanelHeader.TLabel").pack(side="left")
        ttk.Label(head, text="两条链路可以同时打开, 这里切换当前配置与展示",
                  style="PanelHint.TLabel").pack(side="left", padx=(12, 0))

    def _build_config_card(self):
        """顶部连接配置: 左边切换链路, 右边是当前链路的参数, 操作按钮挂工具条"""
        card = ttk.LabelFrame(self, text="连接配置", padding=(16, 12))
        card.pack(side="top", fill="x")
        row = ttk.Frame(card, style="CardFlat.TFrame")
        row.pack(side="top", fill="x")

        # 两个参数组都先建好, 由 _apply_link 决定显示哪一组; 主操作按钮在工具条右侧
        self._serial_group = ttk.Frame(row, style="CardFlat.TFrame")
        self._net_row = ttk.Frame(row, style="CardFlat.TFrame")
        self._build_serial_group(self._serial_group)
        self._build_net_group(self._net_row)
        self.btn_serial = ttk.Button(self._actions, text=BTN_OPEN_PORT,
                                     style="Accent.TButton",
                                     command=self._toggle_serial)
        self.btn_net = ttk.Button(self._actions, text=BTN_LOAD_CONFIG,
                                  style="Accent.TButton", command=self._toggle_net)
        self.btn_test = ttk.Button(self._actions, text=BTN_TEST_CONNECT,
                                   style="Secondary.TButton",
                                   command=self._test_connect)
        # 刷新串口与 图片查重 批量重命名 的 刷新扫描 一样挂在工具条上,
        # 配置行只留参数控件
        self.btn_ports = ttk.Button(self._actions, text=BTN_REFRESH_PORTS,
                                    style="Secondary.TButton",
                                    command=self.refresh_ports)

        switch = ttk.Frame(row, style="CardFlat.TFrame")
        switch.pack(side="left", padx=(0, 12))
        self._link_buttons = {}
        for link, label in LINK_CHOICES:
            button = ttk.Button(switch, text=label, style="Segment.TButton",
                                command=lambda item=link: self._select_link(item))
            button.pack(side="left", padx=(0, 6))
            self._link_buttons[link] = button

        self.lbl_config_hint = ttk.Label(card, textvariable=self._config_hint,
                                         anchor="w", style="CardMuted.TLabel")
        self.lbl_config_hint.pack(side="top", fill="x", pady=(10, 0))

    def _build_serial_group(self, group):
        """串口号 波特率 校验位 数据位 停止位, 刷新串口 按钮挂在工具条上

        @param group: 承载串口控件的容器
        """
        ttk.Label(group, text="串口",
                  style="CardMuted.TLabel").pack(side="left")
        self.combo_port = ttk.Combobox(group, width=PORT_COMBO_WIDTH,
                                       values=[], textvariable=self._port_var)
        self.combo_port.pack(side="left", padx=(4, 10))
        _mark_state(self.combo_port, "readonly")

        self.combo_baud = _add_field(group, "波特率",
                                     BAUD_COMBO_WIDTH, BAUD_RATES, self._baud_var)
        self.combo_parity = _add_field(group, "校验位",
                                       PARITY_COMBO_WIDTH, PARITY_LABELS,
                                       self._parity_var, readonly=True)
        self.combo_data = _add_field(group, "数据位",
                                     BITS_COMBO_WIDTH, DATA_BITS, self._data_var)
        self.combo_stop = _add_field(group, "停止位",
                                     BITS_COMBO_WIDTH, STOP_BITS, self._stop_var)

    def _build_net_group(self, group):
        """协议 目的地址与端口 本机地址 接收端口 与发送端口

        @param group: 承载网络控件的容器
        """
        self._proto_group = ttk.Frame(group, style="CardFlat.TFrame")
        self._proto_group.pack(side="left")
        ttk.Label(self._proto_group, text="协议",
                  style="CardMuted.TLabel").pack(side="left")
        self.combo_proto = ttk.Combobox(self._proto_group, width=PROTO_COMBO_WIDTH,
                                        values=[label for _key, label in PROTOCOLS],
                                        textvariable=self._proto_var)
        self.combo_proto.pack(side="left", padx=(4, 8))
        _mark_state(self.combo_proto, "readonly")
        self.combo_proto.bind("<<ComboboxSelected>>", self._on_proto_change)

        self._dest_group = self._build_dest_group(group)
        self._local_group = self._build_local_group(group)
        self._send_group = self._build_send_group(group)

        for entry in (self.entry_dest_host, self.entry_dest_port,
                      self.entry_recv_port, self.entry_send_port):
            entry.bind("<Return>", lambda _event: self._load_net_config())

    def _build_dest_group(self, row):
        """目的地址与端口, TCP Server 用不到

        @param row: 所在的行
        @return: 承载这一组控件的容器
        """
        group = ttk.Frame(row, style="CardFlat.TFrame")
        group.pack(side="left")
        ttk.Label(group, text="目的IP",
                  style="CardMuted.TLabel").pack(side="left")
        self.entry_dest_host = ttk.Entry(group, textvariable=self._dest_host_var,
                                         width=HOST_ENTRY_WIDTH)
        self.entry_dest_host.pack(side="left", padx=(4, 2))
        ttk.Label(group, text=":", style="CardMuted.TLabel").pack(side="left")
        self.entry_dest_port = ttk.Entry(group, textvariable=self._dest_port_var,
                                        width=PORT_ENTRY_WIDTH)
        self.entry_dest_port.pack(side="left", padx=(2, 8))
        return group

    def _build_local_group(self, row):
        """本机地址与接收端口, 标签按上下文简写为 接收

        @param row: 所在的行
        @return: 承载这一组控件的容器
        """
        group = ttk.Frame(row, style="CardFlat.TFrame")
        group.pack(side="left")
        ttk.Label(group, text="本机IP",
                  style="CardMuted.TLabel").pack(side="left")
        self.combo_local = ttk.Combobox(group, width=IP_COMBO_WIDTH, values=[],
                                        textvariable=self._local_var)
        self.combo_local.pack(side="left", padx=(4, 8))
        _mark_state(self.combo_local, "readonly")
        ttk.Label(group, text="接收",
                  style="CardMuted.TLabel").pack(side="left")
        self.entry_recv_port = ttk.Entry(group, textvariable=self._recv_port_var,
                                         width=PORT_ENTRY_WIDTH)
        self.entry_recv_port.pack(side="left", padx=(4, 8))
        return group

    def _build_send_group(self, row):
        """本地发送端口, 只有 UDP 用得到, 标签按上下文简写为 发送

        @param row: 所在的行
        @return: 承载这一组控件的容器
        """
        group = ttk.Frame(row, style="CardFlat.TFrame")
        group.pack(side="left")
        ttk.Label(group, text="发送",
                  style="CardMuted.TLabel").pack(side="left")
        self.entry_send_port = ttk.Entry(group, textvariable=self._send_port_var,
                                         width=PORT_ENTRY_WIDTH)
        self.entry_send_port.pack(side="left", padx=(4, 0))
        return group

    def _build_panels(self):
        """接收区与发送区上下排列, 每个区域的左侧是数据视图, 右侧是配置列"""
        body = ttk.Frame(self)
        body.pack(side="top", fill="both", expand=True, pady=(12, 0))
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1, uniform="comm")
        body.rowconfigure(1, weight=1, uniform="comm")

        self._recv_area = ttk.Frame(body)
        self._recv_area.grid(row=0, column=0, sticky="nsew")
        self._recv_area.columnconfigure(0, weight=1)
        self._recv_area.rowconfigure(0, weight=1)
        self.recv_serial = ReceivePanel(self._recv_area, self.theme, self,
                                        PANEL_SERIAL_RECEIVE, DISPLAY_AUTO)
        self.recv_serial.grid(row=0, column=0, sticky="nsew")
        self.recv_net = ReceivePanel(self._recv_area, self.theme, self,
                                     PANEL_NET_RECEIVE, DISPLAY_AUTO,
                                     show_source=True)
        self.recv_net.grid(row=0, column=0, sticky="nsew")

        self._send_area = ttk.Frame(body)
        self._send_area.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        self._send_area.columnconfigure(0, weight=1)
        self._send_area.rowconfigure(0, weight=1)
        self.send_serial = SendPanel(self._send_area, self.theme, self,
                                     PANEL_SERIAL_SEND, kind=LINK_SERIAL)
        self.send_serial.grid(row=0, column=0, sticky="nsew")
        self.send_net = SendPanel(self._send_area, self.theme, self,
                                  PANEL_NET_SEND, kind=LINK_NET, with_targets=True)
        self.send_net.grid(row=0, column=0, sticky="nsew")

        self._sync_control_width()

    def _sync_control_width(self):
        """把四个面板的配置列宽度统一成最宽的那个

        配置列的宽度由列内的控件决定, 不统一时接收与发送的数据视图会一宽一窄;
        这里取四个面板里最宽的一份, 左右两列因此对齐
        """
        panels = (self.recv_serial, self.recv_net, self.send_serial, self.send_net)
        # 控件的请求宽度要等几何管理器算过一遍才准, 否则读到的是初始值
        self.update_idletasks()
        width = max(panel.controls.winfo_reqwidth() for panel in panels)
        for panel in panels:
            panel.columnconfigure(1, minsize=width)

    # ---------------- 生命周期 ----------------
    def on_show(self):
        """首次进入本页时才枚举串口与本机地址, 不拖慢程序启动"""
        if self._config_loaded:
            return
        self._config_loaded = True
        self.refresh_ports()
        self.refresh_addresses()

    def on_theme_changed(self):
        """主题切换后刷新四个数据面板的颜色"""
        for panel in (self.recv_serial, self.recv_net, self.send_serial,
                      self.send_net):
            panel.on_theme_changed()

    def on_close(self):
        """退出前停掉定时器与两条链路, 避免后台线程继续跑"""
        self._closing = True
        self._stop_session(LINK_SERIAL)
        self._stop_session(LINK_NET)
        self.send_serial.close()
        self.send_net.close()
        for thread in list(self._workers):
            if thread.is_alive():
                thread.join(timeout=CLOSE_JOIN_TIMEOUT)
        if self._poll_job is not None:
            self.root.after_cancel(self._poll_job)
            self._poll_job = None
        self._drain_sessions()
        return True

    # ---------------- 链路切换 ----------------
    def _select_link(self, link):
        """切换当前配置与展示的链路

        @param link: LINK_SERIAL 或 LINK_NET
        """
        if link == self._active_link:
            return
        self._active_link = link
        self._apply_link()

    def _apply_link(self):
        """按当前链路刷新切换按钮 配置行与两对收发面板"""
        serial = self._active_link == LINK_SERIAL
        for link, button in self._link_buttons.items():
            style = ("SegmentOn.TButton" if link == self._active_link
                     else "Segment.TButton")
            if button.cget("style") != style:
                button.configure(style=style)
        for widget in (self._serial_group, self._net_row, self.btn_serial,
                       self.btn_net, self.btn_test, self.btn_ports):
            widget.pack_forget()
        if serial:
            self.btn_serial.pack(side="right")
            self.btn_ports.pack(side="right", padx=(0, 8))
            self._serial_group.pack(side="left")
        else:
            self.btn_net.pack(side="right")
            self.btn_test.pack(side="right", padx=(0, 8))
            self._net_row.pack(side="left")
        (self.recv_serial if serial else self.recv_net).grid()
        (self.recv_net if serial else self.recv_serial).grid_remove()
        (self.send_serial if serial else self.send_net).grid()
        (self.send_net if serial else self.send_serial).grid_remove()
        self._sync_controls()
        self._show_hint()

    # ---------------- 配置区 ----------------
    def refresh_ports(self):
        """重新枚举本机串口, 可用的排在前面"""
        infos = ports.list_serial_ports(self._open_port)
        labels = [ports.serial_label(info) for info in infos]
        self._port_devices = {label: info.device
                              for label, info in zip(labels, infos)}
        self.combo_port.configure(values=labels)
        if self._port_var.get() not in labels:
            self._port_var.set(labels[0] if labels else "")
        if not labels:
            self._report_config(HINT_NO_PORTS, link=LINK_SERIAL)

    def refresh_addresses(self):
        """刷新本机地址下拉框, 默认选中系统识别出来的地址"""
        addresses = ports.local_ipv4_addresses()
        self.combo_local.configure(values=[ALL_ADDRESSES] + addresses)
        if self._local_var.get() not in addresses:
            self._local_var.set(addresses[0] if addresses else ALL_ADDRESSES)

    def _current_proto(self):
        """当前协议"""
        return _choice_key(PROTOCOLS, self._proto_var.get(), DEFAULT_PROTO)

    def _selected_port(self):
        """串口下拉框当前选中的串口号

        @return: 串口号, 例如 COM3
        """
        label = self._port_var.get().strip()
        # 显示名里带有可用状态, 因此按显示名反查串口号; 手工写入的串口 URL
        # (例如 pyserial 自带的 loop://) 不在列表里, 直接当作串口号使用
        return self._port_devices.get(label, label)

    def _serial_params(self):
        """读取串口配置并做基本校验

        @return: (串口号, 波特率, 数据位, 校验位, 停止位)
        @throws ValueError: 串口号为空或者参数不是合法取值时
        """
        port = self._selected_port()
        if not port:
            raise ValueError(HINT_NEED_PORT)
        baud = _read_number(self._baud_var.get(), "波特率")
        if baud <= 0:
            raise ValueError("波特率必须大于 0")
        bits = _read_number(self._data_var.get(), "数据位")
        if bits not in DATA_BITS:
            raise ValueError("数据位只支持 %s"
                             % "/".join(str(item) for item in DATA_BITS))
        parity = self._parity_var.get().strip().upper()
        if parity not in PARITY_LABELS:
            raise ValueError("校验位只支持 %s" % "/".join(PARITY_LABELS))
        stop = self._stop_var.get().strip()
        if stop not in STOP_BITS:
            raise ValueError("停止位只支持 %s" % "/".join(STOP_BITS))
        return port, baud, bits, parity, stop

    def _net_params(self):
        """读取网络配置并做基本校验

        @return: 参数字典
        @throws ValueError: 缺少必填项或者取值不合法时
        """
        proto = self._current_proto()
        host = self._dest_host_var.get().strip()
        port = _parse_port(self._dest_port_var.get(), "目的端口")
        address = self._local_var.get().strip()
        recv_port = _parse_port(self._recv_port_var.get(), "接收端口")
        send_port = _parse_port(self._send_port_var.get(), "发送端口")
        if proto in (PROTO_TCP_CLIENT, PROTO_UDP):
            # 这两种协议都要往目的地址发数据, 因此地址与端口必须填全
            if not host or not port:
                raise ValueError("%s 需要填写目的地址与端口"
                                 % _choice_label(PROTOCOLS, proto))
            reason = ports.check_host(host)
            if reason:
                raise ValueError("目的地址不合法: %s" % reason)
        if proto == PROTO_TCP_SERVER and not recv_port:
            raise ValueError("TCP Server 需要填写接收端口")
        return {"proto": proto, "host": host, "port": port, "address": address,
                "recv_port": recv_port, "send_port": send_port}

    def _sync_controls(self):
        """按协议与连接状态刷新配置区控件的可用性"""
        proto = self._current_proto()
        serial_open = self._serial_session is not None
        net_open = self._net_session is not None
        # 已经打开的链路不再允许改参数, 避免界面上的配置与实际使用的不一致
        _set_group_enabled(self._serial_group,
                           not serial_open and not self._serial_busy)
        self.btn_serial.configure(
            text=BTN_CLOSE_PORT if serial_open else BTN_OPEN_PORT,
            state="disabled" if self._serial_busy else "normal")
        self.btn_ports.configure(
            state="disabled" if self._serial_busy else "normal")
        free = not net_open and not self._net_busy
        _set_group_enabled(self._proto_group, free)
        _set_group_enabled(self._local_group, free)
        _set_group_enabled(self._dest_group, free and proto != PROTO_TCP_SERVER)
        _set_group_enabled(self._send_group, free and proto == PROTO_UDP)
        self._layout_net_groups(proto)
        self.btn_net.configure(
            text=BTN_CLOSE_NET if net_open else BTN_LOAD_CONFIG,
            state="disabled" if self._net_busy else "normal")
        self.btn_test.configure(
            state="normal" if proto == PROTO_TCP_CLIENT and free else "disabled")
        self.send_net.show_target_controls(proto == PROTO_TCP_SERVER)

    def _layout_net_groups(self, proto):
        """按协议决定哪几组网络控件需要显示

        用不到的控件收起来一行才放得下; 重新显示时按固定顺序 pack 一次, 避免顺序
        因为隐藏与显示而错乱

        @param proto: 当前协议
        """
        groups = ((self._dest_group, proto != PROTO_TCP_SERVER),
                  (self._local_group, True),
                  (self._send_group, proto == PROTO_UDP))
        for group, _visible in groups:
            group.pack_forget()
        for group, visible in groups:
            if visible:
                group.pack(side="left")

    def _report_config(self, text, error=False, link=None):
        """更新配置区下方的说明与状态栏

        提示按链路分别记住, 配置区的说明只显示当前链路; 另一条链路在后台的
        消息仍然要写到状态栏

        @param text: 说明文本
        @param error: True 用错误色
        @param link: 消息属于哪条链路, 默认是当前链路
        """
        link = link or self._active_link
        self._hints[link] = (text, error)
        if link == self._active_link:
            self._show_hint()
        else:
            # 另一条链路在后台的消息也要让状态栏看得见, 配置区的说明仍然
            # 只跟着当前链路
            self.set_status(text)

    def _show_hint(self):
        """把当前链路的提示写到配置卡片下方与状态栏"""
        text, error = self._hints[self._active_link]
        self._config_hint.set(text)
        style = "CardError.TLabel" if error else "CardMuted.TLabel"
        if self.lbl_config_hint.cget("style") != style:
            self.lbl_config_hint.configure(style=style)
        self.set_status(text)

    def _on_proto_change(self, _event=None):
        """切换协议后刷新控件状态与说明"""
        self._sync_controls()
        self._report_config(PROTO_HINTS.get(self._current_proto(), HINT_NET_IDLE),
                            link=LINK_NET)

    # ---------------- 串口 ----------------
    def _toggle_serial(self):
        """打开或者关闭串口"""
        if self._serial_busy:
            return
        if self._serial_session is not None:
            self._close_serial()
            return
        try:
            params = self._serial_params()
        except ValueError as exc:
            self._report_config("串口参数不合法: %s" % exc, error=True,
                            link=LINK_SERIAL)
            return
        self._serial_busy = True
        self._sync_controls()
        self._report_config("正在打开 %s ..." % params[0], link=LINK_SERIAL)
        self._start_worker(self._open_serial_worker, (params,), "comm-serial-open")

    def _open_serial_worker(self, params):
        """后台线程: 打开串口, 结果经队列交回主线程

        @param params: _serial_params 的返回值
        """
        port, baud, bits, parity, stop = params
        session = SerialSession(port, baud, bits, parity, stop,
                                on_data=self._data_callback(LINK_SERIAL),
                                on_event=self._event_callback(LINK_SERIAL))
        try:
            session.start()
        except SessionError as exc:
            self._messages.put(("link", LINK_SERIAL, "fail", None,
                                {"note": str(exc)}))
            return
        if self._closing:
            session.stop()
            return
        self._messages.put(("link", LINK_SERIAL, "open", session,
                            {"note": "已打开 %s @ %d" % (port, baud),
                             "port": port}))

    def _close_serial(self, note="串口已关闭"):
        """关闭串口

        @param note: 写进接收区的说明
        """
        self._stop_session(LINK_SERIAL)
        self._open_port = ""
        self.recv_serial.note(note)
        self.refresh_ports()
        self._sync_controls()
        self._report_config(note, link=LINK_SERIAL)

    # ---------------- 网络 ----------------
    def _toggle_net(self):
        """载入网络配置打开链路, 已经打开时按同一个按钮关闭"""
        if self._net_busy:
            return
        if self._net_session is not None:
            self._close_net()
            return
        self._load_net_config()

    def _load_net_config(self):
        """校验配置并在后台线程里检查端口与目标地址"""
        if self._net_busy or self._net_session is not None:
            return
        try:
            params = self._net_params()
        except ValueError as exc:
            self._report_config(str(exc), error=True, link=LINK_NET)
            return
        self._net_busy = True
        self._sync_controls()
        self._report_config("正在检查 %s 配置 ..."
                            % _choice_label(PROTOCOLS, params["proto"]),
                            link=LINK_NET)
        self._start_worker(self._open_net_worker, (params,), "comm-net-open")

    def _open_net_worker(self, params):
        """后台线程: 检查本地端口与目标地址, 然后建立网络会话

        @param params: _net_params 的返回值
        """
        proto = params["proto"]
        notes = []
        stream = proto != PROTO_UDP
        ok, text = ports.check_local_port(params["address"], params["recv_port"],
                                          stream=stream)
        notes.append(text)
        if ok and proto == PROTO_UDP and params["send_port"]:
            ok, text = ports.check_local_port(params["address"],
                                             params["send_port"], stream=False)
            notes.append(text)
        if ok and proto == PROTO_TCP_CLIENT:
            ok, text = ports.test_tcp_connect(params["host"], params["port"])
            # 连接成功时下面还会写一条已连接, 这里只在失败时补充原因
            if not ok:
                notes.append(text)
        if not ok:
            self._messages.put(("link", LINK_NET, "fail", None,
                                {"note": "%s: %s" % (CHECK_FAIL, text)}))
            return
        session = self._make_net_session(params)
        try:
            session.start()
        except SessionError as exc:
            self._messages.put(("link", LINK_NET, "fail", None,
                                {"note": str(exc)}))
            return
        notes.append(self._open_note(proto, params, session))
        if self._closing:
            session.stop()
            return
        self._messages.put(("link", LINK_NET, "open", session, {
            "note": "%s: %s" % (CHECK_OK, " · ".join(notes)),
            "clients": _client_addresses(session),
        }))

    def _make_net_session(self, params):
        """按协议建立会话对象

        @param params: _net_params 的返回值
        @return: BaseSession 实例
        """
        data = self._data_callback(LINK_NET)
        event = self._event_callback(LINK_NET)
        proto = params["proto"]
        if proto == PROTO_TCP_CLIENT:
            return TcpClientSession(params["host"], params["port"],
                                    address=params["address"],
                                    local_port=params["recv_port"],
                                    on_data=data, on_event=event)
        if proto == PROTO_TCP_SERVER:
            return TcpServerSession(params["address"], params["recv_port"],
                                    on_data=data, on_event=event)
        return UdpSession(params["host"], params["port"],
                          address=params["address"],
                          recv_port=params["recv_port"],
                          send_port=params["send_port"],
                          on_data=data, on_event=event)

    def _open_note(self, proto, params, session):
        """链路打开后写进接收区的一行说明

        @param proto: 协议
        @param params: _net_params 的返回值
        @param session: 已经打开的会话
        @return: 说明文本
        """
        if proto == PROTO_TCP_CLIENT:
            return "已连接 %s:%d" % (params["host"], params["port"])
        if proto == PROTO_TCP_SERVER:
            return "正在监听 %s:%d" % (params["address"] or ALL_ADDRESSES,
                                       params["recv_port"])
        return "接收端口 %d, 发往 %s:%d" % (session.bound_port, params["host"],
                                            params["port"])

    def _close_net(self, note="网络已关闭"):
        """关闭网络链路

        @param note: 写进接收区的说明
        """
        self._stop_session(LINK_NET)
        self.send_net.set_targets([])
        self.recv_net.note(note)
        self._sync_controls()
        self._report_config(note, link=LINK_NET)

    def _test_connect(self):
        """测试能不能连上目的地址"""
        if self._net_busy:
            return
        try:
            host, port = self._dest_target()
        except ValueError as exc:
            self._report_config(str(exc), error=True, link=LINK_NET)
            return
        self._net_busy = True
        self._sync_controls()
        self._report_config("正在测试 %s:%d ..." % (host, port), link=LINK_NET)
        self._start_worker(self._test_connect_worker, (host, port),
                           "comm-test-connect")

    def _dest_target(self):
        """目的地址与端口

        @return: (地址, 端口)
        @throws ValueError: 地址为空或者不合法时
        """
        host = self._dest_host_var.get().strip()
        if not host:
            raise ValueError("先填写目的地址")
        reason = ports.check_host(host)
        if reason:
            raise ValueError("目的地址不合法: %s" % reason)
        port = _parse_port(self._dest_port_var.get(), "目的端口")
        if not port:
            raise ValueError("先填写目的端口")
        return host, port

    def _test_connect_worker(self, host, port):
        """后台线程: 测一次 TCP 连接

        @param host: 目标地址
        @param port: 目标端口
        """
        ok, text = ports.test_tcp_connect(host, port)
        self._messages.put(("check", text, ok))

    # ---------------- 后台消息 ----------------
    def _data_callback(self, link):
        """会话收到数据时的回调: 只投递到队列, 由主线程写进视图

        @param link: 链路标识
        @return: 回调函数
        """
        def handler(data, source=""):
            self._messages.put(("data", link, data, source))
        return handler

    def _event_callback(self, link):
        """会话状态变化时的回调

        @param link: 链路标识
        @return: 回调函数
        """
        def handler(kind, payload=None):
            self._messages.put(("event", link, kind, payload))
        return handler

    def _start_worker(self, target, args, name):
        """启动一个后台线程

        @param target: 线程函数
        @param args: 参数元组
        @param name: 线程名, 便于排查
        """
        self._workers = [thread for thread in self._workers if thread.is_alive()]
        thread = threading.Thread(target=target, args=args, name=name,
                                  daemon=True)
        self._workers.append(thread)
        thread.start()

    def _poll_messages(self):
        """主线程按固定间隔处理后台消息, 一次不要处理过多以免界面卡顿"""
        self._poll_job = None
        for _count in range(MAX_MESSAGES_PER_POLL):
            try:
                message = self._messages.get_nowait()
            except queue.Empty:
                break
            self._handle_message(message)
        if not self._closing:
            self._poll_job = self.root.after(POLL_INTERVAL_MS,
                                             self._poll_messages)

    def _handle_message(self, message):
        """处理一条后台消息

        @param message: 队列里的消息
        """
        tag = message[0]
        if tag == "data":
            _tag, link, data, source = message
            self._recv_panel(link).feed(data, source)
        elif tag == "event":
            _tag, link, kind, payload = message
            self._handle_event(link, kind, payload)
        elif tag == "link":
            _tag, link, state, session, info = message
            self._finish_link(link, state, session, info)
        elif tag == "check":
            _tag, text, ok = message
            self._net_busy = False
            self.recv_net.note(text, error=not ok)
            self._report_config(text, error=not ok, link=LINK_NET)
            self._sync_controls()

    def _handle_event(self, link, kind, payload):
        """处理会话线程报告的状态变化

        @param link: 链路标识
        @param kind: 事件名
        @param payload: 事件内容
        """
        if kind == "clients":
            self.send_net.set_targets(payload or [])
            return
        if kind != "closed":
            # open 事件已经由 _finish_link 提示过, 这里不再重复
            return
        reason = payload or "连接已结束"
        if link == LINK_SERIAL:
            self._serial_session = None
            self._open_port = ""
            self.refresh_ports()
        else:
            self._net_session = None
            self.send_net.set_targets([])
        self._recv_panel(link).note(reason, error=True)
        self._report_config(reason, error=True, link=link)
        self._sync_controls()

    def _finish_link(self, link, state, session, info):
        """后台线程打开链路之后的收尾

        @param link: 链路标识
        @param state: open 表示已经打开, 其它值表示失败
        @param session: 打开成功时的会话
        @param info: 提示信息字典
        """
        if link == LINK_SERIAL:
            self._serial_busy = False
        else:
            self._net_busy = False
        ok = state == "open"
        if ok and self._closing:
            session.stop()
            return
        self._recv_panel(link).note(info["note"], error=not ok)
        self._report_config(info["note"], error=not ok, link=link)
        if ok:
            if link == LINK_SERIAL:
                self._serial_session = session
                self._open_port = info.get("port", "")
            else:
                self._net_session = session
                self.send_net.set_targets(info.get("clients", []))
        self._sync_controls()

    def _stop_session(self, link):
        """停掉一条链路的会话

        @param link: 链路标识
        """
        if link == LINK_SERIAL:
            session, self._serial_session = self._serial_session, None
        else:
            session, self._net_session = self._net_session, None
        if session is not None:
            session.stop()

    def _drain_sessions(self):
        """把队列里还没处理完的会话停掉, 避免退出时留下打开的端口"""
        while True:
            try:
                message = self._messages.get_nowait()
            except queue.Empty:
                return
            if message[0] == "link" and message[2] == "open" and message[3]:
                message[3].stop()

    def _session_for(self, link):
        """取一条链路的会话

        @param link: 链路标识
        @return: 会话, 没有打开时返回 None
        """
        return self._serial_session if link == LINK_SERIAL else self._net_session

    def _recv_panel(self, link):
        """取一条链路的接收卡片

        @param link: 链路标识
        @return: ReceivePanel
        """
        return self.recv_serial if link == LINK_SERIAL else self.recv_net

    # ---------------- 面板回调 ----------------
    def toggle_receive(self, panel):
        """开始或者暂停接收区展示数据

        暂停期间收到的数据只计数不展示, 继续之后会说明跳过了多少字节

        @param panel: 接收卡片
        """
        capturing = not panel.is_capturing()
        panel.set_capturing(capturing)
        if capturing:
            self.set_status("已继续接收数据")
        else:
            self.set_status("已暂停展示数据, 期间收到的数据仍然计数")

    def save_receive(self, panel):
        """把接收区的内容保存成 txt

        @param panel: 接收卡片
        """
        prefix = "串口接收" if panel is self.recv_serial else "网络接收"
        path = filedialog.asksaveasfilename(
            parent=self.window, title="保存接收数据", defaultextension=".txt",
            initialfile="%s_%s.txt" % (prefix, time.strftime("%Y%m%d_%H%M%S")),
            filetypes=TEXT_FILE_TYPES)
        if not path:
            return
        try:
            panel.save(path)
        except OSError as exc:
            show_error("保存失败: %s\n%s" % (path, exc), parent=self.window)
            return
        self.set_status("已保存到 %s" % path)

    def toggle_send(self, panel):
        """开始或者暂停发送, 循环发送的时间间隔由卡片上的输入框决定

        @param panel: 发送卡片
        """
        if panel.is_looping():
            panel.stop_loop()
            self.set_status("已暂停发送")
            return
        if not self._send_once(panel):
            return
        if panel.loop_var.get():
            panel.start_loop()
            self.set_status("正在循环发送, 间隔 %d 毫秒" % panel.interval_ms())

    def send_from(self, panel):
        """循环发送的一拍

        @param panel: 发送卡片
        @return: 是否继续循环
        """
        return self._send_once(panel)

    def load_send_text(self, panel):
        """把文本文件的内容载入发送区

        @param panel: 发送卡片
        """
        path = filedialog.askopenfilename(parent=self.window, title="载入文本文件",
                                          filetypes=TEXT_FILE_TYPES)
        if not path:
            return
        try:
            with open(path, "rb") as handle:
                raw = handle.read()
        except OSError as exc:
            show_error("无法读取文件: %s\n%s" % (path, exc), parent=self.window)
            return
        # 先按发送区当前的编码解读, 解读不了再退回 UTF-8 兜底, 这样发出去的内容
        # 与文件里的内容保持一致
        try:
            text = raw.decode(panel.encoding())
        except (UnicodeDecodeError, LookupError):
            text = raw.decode("utf-8", errors="replace")
        panel.set_content(text)
        panel.set_hint("已载入 %s" % os.path.basename(path))
        self.set_status("已载入 %s" % path)

    def choose_targets(self, panel):
        """为 TCP Server 勾选要发送到的设备

        @param panel: 发送卡片
        """
        addresses = panel.target_addresses()
        if not addresses:
            panel.set_hint("还没有设备连接, 无法选择发送对象", error=True)
            return
        chosen = ask_targets(self.window, addresses,
                             panel.selected_targets() or (), theme=self.theme)
        if chosen is None:
            return
        panel.set_multi_targets(chosen)
        if chosen:
            panel.set_hint("已选择 %d 个发送对象" % len(chosen))
        else:
            panel.set_hint("没有勾选设备, 已改回发送给全部设备")

    def _send_once(self, panel):
        """发一次数据并刷新卡片上的提示

        @param panel: 发送卡片
        @return: 是否发送成功
        """
        link = panel.kind
        session = self._session_for(link)
        if session is None or not session.is_open:
            panel.set_hint("%s还没有打开" % LINK_LABELS.get(link, "链路"),
                           error=True)
            return False
        try:
            payload = panel.payload()
        except ParseError as exc:
            panel.set_hint(str(exc), error=True)
            return False
        try:
            session.send(payload, panel.selected_targets())
        except SessionError as exc:
            panel.set_hint(str(exc), error=True)
            return False
        panel.note_sent(len(payload))
        panel.set_hint("已发送 %d 字节" % len(payload))
        return True
