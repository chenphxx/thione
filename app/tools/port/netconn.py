"""本机 TCP 与 UDP 连接的枚举。

数据取自 IP 助手 API 的 GetExtendedTcpTable 与 GetExtendedUdpTable, 这两支
接口直接按拥有者 PID 返回连接表, 因此不需要解析 netstat 的文本输出, 也不会
受系统显示语言影响。
"""

import ctypes
import socket
from ctypes import wintypes
from typing import NamedTuple

# GetExtendedTcpTable 的表类型: 所有连接, 带拥有者 PID
TCP_TABLE_OWNER_PID_ALL = 5
# GetExtendedUdpTable 的表类型: UDP 监听表, 带拥有者 PID
UDP_TABLE_OWNER_PID = 1

AF_INET = 2
AF_INET6 = 23

ERROR_SUCCESS = 0
ERROR_INSUFFICIENT_BUFFER = 122

#: TCP 的监听状态, 端口被程序占用的典型状态
LISTENING = "监听中"

#: MIB_TCP_STATE 的取值
TCP_STATES = {
    1: "已关闭",
    2: LISTENING,
    3: "正在连接",
    4: "正在握手",
    5: "已建立",
    6: "关闭等待 1",
    7: "关闭等待 2",
    8: "被动关闭",
    9: "正在关闭",
    10: "最后确认",
    11: "时间等待",
    12: "正在删除",
}

#: UDP 没有连接状态, 用这个占位
NO_STATE = "-"


class MIB_TCPROW_OWNER_PID(ctypes.Structure):
    _fields_ = [
        ("dwState", wintypes.DWORD),
        ("dwLocalAddr", wintypes.DWORD),
        ("dwLocalPort", wintypes.DWORD),
        ("dwRemoteAddr", wintypes.DWORD),
        ("dwRemotePort", wintypes.DWORD),
        ("dwOwningPid", wintypes.DWORD),
    ]


class MIB_TCP6ROW_OWNER_PID(ctypes.Structure):
    _fields_ = [
        ("ucLocalAddr", ctypes.c_ubyte * 16),
        ("dwLocalScopeId", wintypes.DWORD),
        ("dwLocalPort", wintypes.DWORD),
        ("ucRemoteAddr", ctypes.c_ubyte * 16),
        ("dwRemoteScopeId", wintypes.DWORD),
        ("dwRemotePort", wintypes.DWORD),
        ("dwState", wintypes.DWORD),
        ("dwOwningPid", wintypes.DWORD),
    ]


class MIB_UDPROW_OWNER_PID(ctypes.Structure):
    _fields_ = [
        ("dwLocalAddr", wintypes.DWORD),
        ("dwLocalPort", wintypes.DWORD),
        ("dwOwningPid", wintypes.DWORD),
    ]


class MIB_UDP6ROW_OWNER_PID(ctypes.Structure):
    _fields_ = [
        ("ucLocalAddr", ctypes.c_ubyte * 16),
        ("dwLocalScopeId", wintypes.DWORD),
        ("dwLocalPort", wintypes.DWORD),
        ("dwOwningPid", wintypes.DWORD),
    ]


class Connection(NamedTuple):
    """一条连接记录; UDP 没有远端与状态。"""

    protocol: str
    local_addr: str
    local_port: int
    remote_addr: str
    remote_port: int
    state: str
    pid: int


_iphlpapi = ctypes.WinDLL("iphlpapi.dll")
_iphlpapi.GetExtendedTcpTable.argtypes = [
    ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD), wintypes.BOOL,
    wintypes.ULONG, ctypes.c_int, wintypes.ULONG,
]
_iphlpapi.GetExtendedUdpTable.argtypes = [
    ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD), wintypes.BOOL,
    wintypes.ULONG, ctypes.c_int, wintypes.ULONG,
]


def list_connections():
    """列出本机全部 TCP 与 UDP 连接。

    @return: Connection 列表, 按本地端口升序排列
    @throws OSError: 系统接口返回错误时
    """
    rows = []
    for family, suffix in ((AF_INET, ""), (AF_INET6, "6")):
        for row in _table(_iphlpapi.GetExtendedTcpTable, family,
                          TCP_TABLE_OWNER_PID_ALL, _tcp_row(family)):
            rows.append(_tcp_connection(row, suffix))
        for row in _table(_iphlpapi.GetExtendedUdpTable, family,
                          UDP_TABLE_OWNER_PID, _udp_row(family)):
            rows.append(_udp_connection(row, suffix))
    rows.sort(key=lambda item: (item.local_port, item.protocol, item.state))
    return rows


def is_listening(connection):
    """这条连接是不是一个正在监听的端口。

    UDP 没有连接状态, 一条 UDP 记录就代表该端口已被绑定, 因此按监听算。

    @param connection: Connection
    @return: 是否属于监听中的端口
    """
    return (connection.state == LISTENING
            or connection.protocol.startswith("UDP"))


def _tcp_row(family):
    return MIB_TCPROW_OWNER_PID if family == AF_INET else MIB_TCP6ROW_OWNER_PID


def _udp_row(family):
    return MIB_UDPROW_OWNER_PID if family == AF_INET else MIB_UDP6ROW_OWNER_PID


def _table(function, family, table_class, row_type):
    """取一张连接表并解析成结构体列表。

    先按空缓冲区问一次长度, 再按返回的长度申请缓冲区取数据; 表头是一个
    DWORD 的行数, 后面紧跟定长的行结构。

    @param function: GetExtendedTcpTable 或 GetExtendedUdpTable
    @param family: AF_INET 或 AF_INET6
    @param table_class: 表类型
    @param row_type: 行结构体类型
    @return: 行结构体列表
    @throws OSError: 两次调用都没有返回成功或需要更多缓冲区时
    """
    size = wintypes.DWORD(0)
    result = function(None, ctypes.byref(size), False, family, table_class, 0)
    if result != ERROR_INSUFFICIENT_BUFFER:
        raise OSError(_error_message("读取连接表失败", result))
    buffer = ctypes.create_string_buffer(size.value)
    result = function(buffer, ctypes.byref(size), False, family, table_class, 0)
    if result != ERROR_SUCCESS:
        raise OSError(_error_message("读取连接表失败", result))

    count = ctypes.cast(buffer, ctypes.POINTER(wintypes.DWORD)).contents.value
    if not count:
        return []
    base = ctypes.cast(ctypes.byref(buffer, ctypes.sizeof(wintypes.DWORD)),
                       ctypes.POINTER(row_type))
    return [base[index] for index in range(count)]


def _tcp_connection(row, suffix):
    is_v6 = bool(suffix)
    return Connection(
        protocol=f"TCP{suffix}",
        local_addr=_ipv6(row.ucLocalAddr) if is_v6 else _ipv4(row.dwLocalAddr),
        local_port=socket.ntohs(row.dwLocalPort & 0xFFFF),
        remote_addr=_ipv6(row.ucRemoteAddr) if is_v6 else _ipv4(row.dwRemoteAddr),
        remote_port=socket.ntohs(row.dwRemotePort & 0xFFFF),
        state=TCP_STATES.get(row.dwState, str(row.dwState)),
        pid=row.dwOwningPid,
    )


def _udp_connection(row, suffix):
    is_v6 = bool(suffix)
    return Connection(
        protocol=f"UDP{suffix}",
        local_addr=_ipv6(row.ucLocalAddr) if is_v6 else _ipv4(row.dwLocalAddr),
        local_port=socket.ntohs(row.dwLocalPort & 0xFFFF),
        remote_addr="",
        remote_port=0,
        state=NO_STATE,
        pid=row.dwOwningPid,
    )


def _ipv4(value):
    """IPv4 地址在表里是网络序的双字, 按内存顺序还原成点分文本。"""
    return socket.inet_ntoa(value.to_bytes(4, "little"))


def _ipv6(raw):
    return socket.inet_ntop(socket.AF_INET6, bytes(raw))


def _error_message(context, code):
    return f"{context} (错误码 {code})"
