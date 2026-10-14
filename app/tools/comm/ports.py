"""串口列表 本机地址与端口可用性检查

串口可用性用一次短打开来判定: 能打开说明没有被别的程序占用, 打不开则给出原因
打开串口本身可能很慢 (蓝牙与虚拟串口尤其明显), 因此枚举与探测分成两步:
enumerate_serial_ports() 只列出系统里的串口, probe_serial_ports() 才逐个探测占用
情况, 由调用方放到后台线程里执行; 探测结果按串口号缓存一小段时间, 短时间内重复
刷新不会反复打开同一个串口
端口占用者复用 端口与占用 工具的连接表与进程快照, 因此两个工具对 谁占用了这个
端口 的说法是一致的
"""

import logging
import socket
import time
from typing import NamedTuple

import serial
from serial.tools import list_ports

from ..port import netconn, processes
from .constants import (
    CONNECT_TIMEOUT,
    PORT_AVAILABLE,
    PORT_BUSY,
    PORT_IN_USE_BY_US,
    PROBE_CACHE_SECONDS,
)

logger = logging.getLogger(__name__)

#: 读取进程快照失败时的占位说明
UNKNOWN_OWNER = "占用它的程序未知"

#: 判定串口占用时不必真的读数据, 打开后立刻关闭
PORT_PROBE_TIMEOUT = 0.05

#: 串口占用探测结果的缓存: 串口号 -> (记下的时间, 是否可用, 说明)
_probe_cache = {}


class SerialPortInfo(NamedTuple):
    """一个串口的展示信息

    available 为 None 表示占用状态还没有探测
    """

    device: str
    description: str
    available: bool | None
    note: str


def enumerate_serial_ports(held=""):
    """列出本机串口, 不做占用探测

    枚举只读系统里的串口信息, 本身很快, 因此可以放在主线程里做; 占用状态要真的打开
    一次串口才能确定, 交给 probe_serial_ports() 在后台线程里补齐

    @param held: 本程序当前已经打开的串口号, 直接标注为 本程序使用中
    @return: SerialPortInfo 列表, available 为 None 表示占用状态还没探测; 缓存里
             还有结果的串口直接带上缓存里的状态
    """
    items = []
    try:
        found = list(list_ports.comports())
    except OSError:
        logger.warning("枚举串口失败", exc_info=True)
        return []
    for info in found:
        device = info.device
        description = info.description or device
        if device == held:
            items.append(SerialPortInfo(device, description, True,
                                        PORT_IN_USE_BY_US))
            continue
        cached = _cached_probe(device)
        if cached is None:
            items.append(SerialPortInfo(device, description, None, ""))
        else:
            items.append(SerialPortInfo(device, description, cached[0],
                                        cached[1]))
    _sort_ports(items)
    return items


def probe_serial_ports(items, held="", force=False):
    """补齐串口的占用状态, 应当在后台线程里调用

    每个串口都要真的打开一次才能确定是否被占用, 打开蓝牙或者虚拟串口可能要几百毫秒
    到几秒, 因此这里只负责探测, 结果由调用方带回主线程刷新界面

    @param items: enumerate_serial_ports() 的返回值
    @param held: 本程序当前已经打开的串口号, 保持 本程序使用中 的标注
    @param force: True 时忽略缓存, 重新探测每一个串口
    @return: 占用状态已经确定的 SerialPortInfo 列表, 可用的排在前面
    """
    probed = []
    for item in items:
        if item.device == held:
            probed.append(item)
            continue
        cached = None if force else _cached_probe(item.device)
        if cached is None:
            available, note = _probe_port(item.device)
            _remember_probe(item.device, available, note)
        else:
            available, note = cached
        probed.append(item._replace(available=available, note=note))
    _sort_ports(probed)
    return probed


def forget_port(device):
    """丢掉一个串口的探测缓存

    本程序刚放开这个串口时调用, 免得缓存在有效期内一直用旧的占用状态

    @param device: 串口号
    """
    if device:
        _probe_cache.pop(device, None)


def _port_index(device):
    """COM 口按编号排序, 其它名字按文本排序

    @param device: 设备名
    @return: 排序用的键
    """
    digits = "".join(char for char in device if char.isdigit())
    return (0, int(digits), "") if digits else (1, 0, device)


def _sort_ports(items):
    """可用的串口排在前面, 其余按串口号排序

    @param items: SerialPortInfo 列表, 原地排序
    """
    items.sort(key=lambda item: (item.available is not True,
                                _port_index(item.device)))


def _cached_probe(device):
    """取缓存里的占用探测结果

    @param device: 串口号
    @return: (是否可用, 说明); 没有缓存或者已经过期时返回 None
    """
    entry = _probe_cache.get(device)
    if entry is None:
        return None
    if time.monotonic() - entry[0] > PROBE_CACHE_SECONDS:
        del _probe_cache[device]
        return None
    return entry[1], entry[2]


def _remember_probe(device, available, note):
    """记下这次的占用探测结果

    @param device: 串口号
    @param available: 是否可用
    @param note: 说明文本
    """
    _probe_cache[device] = (time.monotonic(), available, note)


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

    展示成 端口 占用状态 描述 三段, 界面按状态分别配色, 因此这里不带括号;
    占用状态还没探测出来时只有端口与描述, 探测结果回来后会再刷新一次

    @param info: SerialPortInfo
    @return: 展示文本
    """
    return " ".join(part for part in serial_parts(info) if part)


def serial_parts(info):
    """串口下拉框里的三段内容

    界面按这三段分别配色: 端口用正文色, 占用状态用状态色, 描述用弱化色

    @param info: SerialPortInfo
    @return: (端口, 占用状态, 描述); 没有内容的一段是空串
    """
    return (info.device,
            _short_note(info.note) if info.note else "",
            _short_description(info))


def _short_note(note):
    """占用状态只保留最前面那个词

    探测失败时的说明形如 占用中: 拒绝访问, 下拉框里只展示 占用中

    @param note: 探测得到的说明文本
    @return: 简短的状态词
    """
    return note.split(":", 1)[0].strip() or note


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
    """本机 IPv4 地址里不用等解析的那一份, 主用地址排在最前

    主用地址取一条不发包的 UDP 连接的本地地址, 因此这个调用本身很快; 网卡上其余的
    地址由 extended_ipv4_addresses() 在后台线程里补齐

    @return: 地址列表, 至少包含 127.0.0.1
    """
    return _merge_addresses([_primary_address()])


def extended_ipv4_addresses():
    """在 local_ipv4_addresses() 之外补齐主机名解析出来的地址

    主机名解析要等 DNS, 网络不通时可能阻塞好几秒, 因此只应当在后台线程里调用

    @return: 地址列表, 主用地址排在最前
    """
    return _merge_addresses([_primary_address(), *_host_addresses()])


def _merge_addresses(candidates):
    """去重并保证 127.0.0.1 在最后

    @param candidates: 候选地址, 其中的空串会被丢掉
    @return: 地址列表
    """
    addresses = []
    for candidate in candidates:
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

    解析要等 DNS, 网络不通时可能阻塞几秒, 因此只应当在后台线程里调用

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
