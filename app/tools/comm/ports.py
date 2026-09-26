"""串口列表 本机地址与端口可用性检查

串口可用性用一次短打开来判定: 能打开说明没有被别的程序占用, 打不开则给出原因
端口占用者复用 端口与占用 工具的连接表与进程快照, 因此两个工具对 谁占用了这个
端口 的说法是一致的
"""

import logging
import socket
from typing import NamedTuple

import serial
from serial.tools import list_ports

from ..port import netconn, processes
from .constants import (
    CONNECT_TIMEOUT,
    PORT_AVAILABLE,
    PORT_BUSY,
    PORT_IN_USE_BY_US,
)

logger = logging.getLogger(__name__)

#: 读取进程快照失败时的占位说明
UNKNOWN_OWNER = "占用它的程序未知"

#: 判定串口占用时不必真的读数据, 打开后立刻关闭
PORT_PROBE_TIMEOUT = 0.05


class SerialPortInfo(NamedTuple):
    """一个串口的展示信息"""

    device: str
    description: str
    available: bool
    note: str


def list_serial_ports(held=""):
    """列出本机串口, 可用的排在前面

    @param held: 本程序当前已经打开的串口号, 单独标注
    @return: SerialPortInfo 列表
    """
    items = []
    try:
        found = list(list_ports.comports())
    except OSError:
        logger.warning("枚举串口失败", exc_info=True)
        return []
    for info in found:
        device = info.device
        if device == held:
            items.append(SerialPortInfo(device, info.description or device,
                                        True, PORT_IN_USE_BY_US))
            continue
        ok, note = _probe_port(device)
        items.append(SerialPortInfo(device, info.description or device, ok, note))
    items.sort(key=lambda item: (not item.available, _port_index(item.device)))
    return items


def _port_index(device):
    """COM 口按编号排序, 其它名字按文本排序

    @param device: 设备名
    @return: 排序用的键
    """
    digits = "".join(char for char in device if char.isdigit())
    return (0, int(digits), "") if digits else (1, 0, device)


def _probe_port(device):
    """试着打开一次串口, 判断是否被占用

    @param device: 串口号
    @return: (是否可用, 说明文本)
    """
    try:
        port = serial.Serial(device, timeout=PORT_PROBE_TIMEOUT)
    except (serial.SerialException, OSError, ValueError) as exc:
        return False, "%s: %s" % (PORT_BUSY, _short_reason(exc))
    else:
        try:
            port.close()
        except (serial.SerialException, OSError):
            pass
        return True, PORT_AVAILABLE


def _short_reason(exc):
    """把串口打开失败的原因压成一句话

    @param exc: 打开串口时的异常
    @return: 说明文本
    """
    text = str(exc).strip().splitlines()
    return text[0] if text else exc.__class__.__name__


def serial_label(info):
    """下拉框里展示串口的一行文本

    @param info: SerialPortInfo
    @return: 展示文本
    """
    parts = [info.device, "(%s)" % info.note]
    description = _short_description(info)
    if description:
        parts.append(description)
    return " ".join(parts)


def _short_description(info):
    """串口的友好名称, 去掉其中重复的串口号

    Windows 的描述常写成 通信端口 (COM1), 去掉之后下拉框才放得下

    @param info: SerialPortInfo
    @return: 描述文本, 没有额外信息时为空串
    """
    description = (info.description or "").strip()
    if not description or description == info.device:
        return ""
    suffix = "(%s)" % info.device
    if description.endswith(suffix):
        description = description[:-len(suffix)].strip()
    return description


def local_ipv4_addresses():
    """本机可用的 IPv4 地址, 主用地址排在最前

    主用地址取一条不发包的 UDP 连接的本地地址, 连不通时退回主机名解析的结果

    @return: 地址列表, 至少包含 127.0.0.1
    """
    addresses = []
    for candidate in (_primary_address(), *_host_addresses()):
        if candidate and candidate not in addresses:
            addresses.append(candidate)
    if "127.0.0.1" not in addresses:
        addresses.append("127.0.0.1")
    return addresses


def _primary_address():
    """取默认路由使用的本机地址

    @return: 地址, 取不到时为空串
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # 连一个外部地址只为让系统选路, 不会真的发包
        sock.connect(("8.8.8.8", 53))
        return sock.getsockname()[0]
    except OSError:
        return ""
    finally:
        sock.close()


def _host_addresses():
    """通过主机名解析本机地址

    @return: 地址列表
    """
    found = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            address = info[4][0]
            if address not in found:
                found.append(address)
    except OSError:
        logger.debug("解析主机名失败", exc_info=True)
    return found


def check_local_port(address, port, stream=True):
    """检查本机端口能不能绑定

    @param address: 本机地址, 空串表示所有网卡
    @param port: 端口号, 0 表示由系统分配
    @param stream: True 按 TCP 检查, False 按 UDP 检查
    @return: (是否可用, 说明文本)
    """
    if port == 0:
        return True, "端口留空, 由系统分配"
    kind = socket.SOCK_STREAM if stream else socket.SOCK_DGRAM
    sock = socket.socket(socket.AF_INET, kind)
    try:
        sock.bind((address or "", port))
    except OSError as exc:
        owner = describe_port_owner(port, stream)
        if owner:
            return False, "端口 %d 已被 %s 占用" % (port, owner)
        return False, "端口 %d 不可用: %s" % (port, _short_reason(exc))
    finally:
        sock.close()
    return True, "端口 %d 可用" % port


def describe_port_owner(port, stream=True):
    """查这个端口被哪个进程占用

    @param port: 端口号
    @param stream: True 表示只看 TCP, 否则只看 UDP
    @return: 形如 "PID 1234 (chrome.exe)" 的说明, 查不到时为空串
    """
    try:
        rows = netconn.list_connections()
        entries = processes.snapshot()
    except OSError:
        logger.warning("读取连接表失败", exc_info=True)
        return UNKNOWN_OWNER
    for row in rows:
        if row.local_port != port or not row.local_addr:
            continue
        is_tcp = row.protocol.startswith("TCP")
        if is_tcp != stream:
            continue
        if not is_tcp and not netconn.is_listening(row):
            continue
        entry = entries.get(row.pid)
        name = entry.name if entry is not None else UNKNOWN_OWNER
        return "PID %d (%s)" % (row.pid, name)
    return ""


def test_tcp_connect(host, port, timeout=CONNECT_TIMEOUT):
    """测试能不能连上目标地址

    @param host: 目标地址
    @param port: 目标端口
    @param timeout: 超时时间 (秒)
    @return: (是否成功, 说明文本)
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((host, port))
    except OSError as exc:
        return False, "连接 %s:%d 失败: %s" % (host, port, _short_reason(exc))
    finally:
        sock.close()
    return True, "已连接 %s:%d" % (host, port)


def check_host(text):
    """检查地址栏里填的是不是一个可用的 IPv4 或者主机名

    @param text: 输入内容
    @return: 出错原因, 合法时为空串
    """
    if not text:
        return "地址不能为空"
    if " " in text:
        return "地址里不能有空格"
    return ""
