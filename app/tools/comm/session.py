"""串口与网络会话: 后台收发线程与统一的回调接口

页面只与 BaseSession 打交道: start 打开 stop 关闭 send 发送 收到的数据与状态变化
都通过回调交回页面, 由页面投递到主线程。所有读线程都是守护线程, 关闭会话时先置
停止标志再关闭套接字或者串口, 因此阻塞中的读操作会立刻返回

@brief 串口 TCP Client TCP Server UDP 四种会话的实现
"""

import logging
import select
import socket
import threading

import serial

from .constants import CLOSE_JOIN_TIMEOUT, CONNECT_TIMEOUT

logger = logging.getLogger(__name__)

#: 一次最多读取的字节数
RECV_CHUNK = 4096
#: 读操作的等待时间 (秒), 同时用来周期性检查停止标志
POLL_TIMEOUT = 0.2
#: TCP Server 同时保持的连接上限
MAX_CLIENTS = 64

#: 校验位下拉框取值到 pyserial 常量
PARITY_VALUES = {
    "NONE": serial.PARITY_NONE,
    "EVEN": serial.PARITY_EVEN,
    "ODD": serial.PARITY_ODD,
    "MARK": serial.PARITY_MARK,
    "SPACE": serial.PARITY_SPACE,
}

#: 停止位下拉框取值到 pyserial 常量
STOP_BIT_VALUES = {
    "1": serial.STOPBITS_ONE,
    "1.5": serial.STOPBITS_ONE_POINT_FIVE,
    "2": serial.STOPBITS_TWO,
}


class SessionError(RuntimeError):
    """会话打不开或者发不出去时抛出, 消息可以直接展示给用户"""


class BaseSession:
    """会话公共部分: 停止标志 回调投递与线程收尾"""

    kind = ""
    label = "会话"

    def __init__(self, on_data=None, on_event=None):
        self._on_data = on_data if on_data is not None else (lambda data, source="": None)
        self._on_event = on_event if on_event is not None else (lambda kind, payload=None: None)
        self._stop = threading.Event()
        self._threads = []
        self._open = False
        self._closed = False
        self._lock = threading.Lock()

    @property
    def is_open(self):
        """会话是否处于打开状态"""
        return self._open and not self._closed

    def start(self):
        """打开会话, 失败时抛出 SessionError

        @throws SessionError: 打不开时
        """
        self._open = True
        return None

    def stop(self):
        """停止收发并释放资源, 可以重复调用"""
        self._stop.set()
        self._release()
        self._join()
        self._open = False
        self._closed = True

    def send(self, payload, targets=None):
        """发送一段数据

        @param payload: 字节串
        @param targets: 发送对象, None 表示全部 (只有 TCP Server 用得到)
        @throws SessionError: 发送失败时
        """
        raise SessionError("%s 不支持发送" % self.label)

    def _release(self):
        """关闭套接字或者串口, 由子类实现"""

    def _emit(self, data, source=""):
        """把收到的数据交给页面"""
        try:
            self._on_data(data, source)
        except Exception:
            logger.exception("处理收到的数据失败")

    def _event(self, kind, payload=None):
        """把状态变化交给页面"""
        try:
            self._on_event(kind, payload)
        except Exception:
            logger.exception("处理会话事件失败")

    def _start_thread(self, target, name):
        """启动一个守护线程并登记

        @param target: 线程函数
        @param name: 线程名, 便于排查
        """
        thread = threading.Thread(target=target, name=name, daemon=True)
        self._threads.append(thread)
        thread.start()

    def _join(self):
        """等待读线程退出"""
        for thread in self._threads:
            if thread.is_alive():
                thread.join(timeout=CLOSE_JOIN_TIMEOUT)
        self._threads = []

    def _fail(self, reason):
        """读线程里的致命错误: 通知页面并结束会话"""
        self._open = False
        self._closed = True
        self._event("closed", reason)


class SerialSession(BaseSession):
    """串口会话"""

    kind = "serial"
    label = "串口"

    def __init__(self, port, baudrate, bytesize, parity, stopbits,
                 on_data=None, on_event=None):
        super().__init__(on_data, on_event)
        self._port = port
        self._baudrate = baudrate
        self._bytesize = bytesize
        self._parity = PARITY_VALUES.get(parity, serial.PARITY_NONE)
        self._stopbits = STOP_BIT_VALUES.get(str(stopbits), serial.STOPBITS_ONE)
        self._serial = None

    def start(self):
        """打开串口并启动读线程

        @throws SessionError: 串口打不开或者参数不合法时
        """
        try:
            self._serial = _open_serial(
                self._port, self._baudrate, self._bytesize, self._parity,
                self._stopbits)
        except (serial.SerialException, OSError, ValueError) as exc:
            self._serial = None
            raise SessionError("打开 %s 失败: %s" % (self._port, exc)) from exc
        self._open = True
        self._start_thread(self._read_loop, "comm-serial-read")
        self._event("open", "%s @ %d" % (self._port, self._baudrate))
        return True

    def _read_loop(self):
        """读线程: 有数据就交给页面, 串口被拔出时结束会话"""
        while not self._stop.is_set():
            try:
                data = self._serial.read(RECV_CHUNK)
            except (serial.SerialException, OSError, TypeError) as exc:
                if not self._stop.is_set():
                    self._fail("串口读取失败: %s" % exc)
                return
            if data:
                self._emit(bytes(data))
        return None

    def send(self, payload, targets=None):
        """往串口写一段数据

        @param payload: 字节串
        @throws SessionError: 串口没有打开或者写入失败时
        """
        if not self.is_open or self._serial is None:
            raise SessionError("串口还没有打开")
        with self._lock:
            try:
                self._serial.write(payload)
            except (serial.SerialException, OSError) as exc:
                raise SessionError("串口发送失败: %s" % exc) from exc

    def _release(self):
        """取消正在进行的读并关闭串口"""
        if self._serial is None:
            return
        try:
            self._serial.cancel_read()
        except (AttributeError, serial.SerialException, OSError):
            logger.debug("取消串口读操作失败", exc_info=True)
        try:
            self._serial.close()
        except (serial.SerialException, OSError):
            logger.warning("关闭串口失败", exc_info=True)
        self._serial = None


def _open_serial(port, baudrate, bytesize, parity, stopbits):
    """按端口名打开串口

    端口名里带 "://" 时按 URL 处理, 例如 pyserial 自带的 loop:// 环路口, 便于在没有
    硬件的情况下自测; 其余情况就是普通的串口号

    @param port: 串口号或者串口 URL
    @param baudrate: 波特率
    @param bytesize: 数据位
    @param parity: 校验位常量
    @param stopbits: 停止位常量
    @return: serial.Serial 实例
    @throws serial.SerialException: 打不开时
    """
    options = dict(baudrate=baudrate, bytesize=bytesize, parity=parity,
                   stopbits=stopbits, timeout=POLL_TIMEOUT,
                   write_timeout=CONNECT_TIMEOUT)
    if "://" in port:
        return serial.serial_for_url(port, **options)
    return serial.Serial(port=port, **options)


class TcpClientSession(BaseSession):
    """TCP Client 会话"""

    kind = "tcp_client"
    label = "TCP Client"

    def __init__(self, host, port, address="", local_port=0,
                 on_data=None, on_event=None):
        super().__init__(on_data, on_event)
        self._host = host
        self._port = port
        self._address = address
        self._local_port = local_port
        self._socket = None

    def start(self):
        """连接目标地址

        @throws SessionError: 连接失败时
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            if self._local_port or self._address:
                sock.bind((self._address or "", self._local_port or 0))
            sock.settimeout(CONNECT_TIMEOUT)
            sock.connect((self._host, self._port))
        except OSError as exc:
            sock.close()
            raise SessionError("连接 %s:%d 失败: %s" % (self._host, self._port, exc)) from exc
        sock.settimeout(POLL_TIMEOUT)
        self._socket = sock
        self._open = True
        self._start_thread(self._read_loop, "comm-tcp-client-read")
        self._event("open", "%s:%d" % (self._host, self._port))
        return True

    def _read_loop(self):
        """读线程: 目标断开时结束会话"""
        while not self._stop.is_set():
            try:
                data = self._socket.recv(RECV_CHUNK)
            except socket.timeout:
                continue
            except OSError as exc:
                if not self._stop.is_set():
                    self._fail("连接已断开: %s" % exc)
                return
            if not data:
                if not self._stop.is_set():
                    self._fail("目标已关闭连接")
                return
            self._emit(data, self._peer_text())
        return None

    def _peer_text(self):
        """本端看到的对端地址

        @return: "地址:端口"
        """
        try:
            peer = self._socket.getpeername()
            return "%s:%d" % (peer[0], peer[1])
        except OSError:
            return "%s:%d" % (self._host, self._port)

    def send(self, payload, targets=None):
        """往连接上写数据

        @param payload: 字节串
        @throws SessionError: 没有连接或者发送失败时
        """
        if not self.is_open or self._socket is None:
            raise SessionError("还没有连接目标")
        with self._lock:
            try:
                self._socket.sendall(payload)
            except OSError as exc:
                raise SessionError("发送失败: %s" % exc) from exc

    def _release(self):
        """关闭套接字, 让阻塞中的 recv 立刻返回"""
        if self._socket is not None:
            try:
                self._socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                logger.debug("关闭连接失败", exc_info=True)
            try:
                self._socket.close()
            except OSError:
                logger.warning("关闭套接字失败", exc_info=True)
            self._socket = None


class TcpServerSession(BaseSession):
    """TCP Server 会话: 监听端口并管理多个客户端"""

    kind = "tcp_server"
    label = "TCP Server"

    def __init__(self, address, port, on_data=None, on_event=None):
        super().__init__(on_data, on_event)
        self._address = address
        self._port = port
        self._server = None
        self._clients = {}

    def start(self):
        """绑定端口并开始监听

        @throws SessionError: 绑定失败时
        """
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            server.bind((self._address or "", self._port))
            server.listen(8)
            server.setblocking(False)
        except OSError as exc:
            server.close()
            raise SessionError("监听 %s:%d 失败: %s" % (self._address or "0.0.0.0", self._port, exc)) from exc
        self._server = server
        self._open = True
        self._start_thread(self._read_loop, "comm-tcp-server-read")
        self._event("open", "%s:%d" % (self._address or "0.0.0.0", self._port))
        return True

    def _read_loop(self):
        """读线程: 接受新连接并读取各客户端的数据"""
        while not self._stop.is_set():
            readables = [self._server] + list(self._clients)
            try:
                ready, _w, _x = select.select(readables, [], [], POLL_TIMEOUT)
            except (OSError, ValueError):
                if not self._stop.is_set():
                    self._fail("监听套接字已关闭")
                return
            for sock in ready:
                if sock is self._server:
                    self._accept()
                elif not self._read_client(sock):
                    return
        return None

    def _accept(self):
        """接受一个客户端连接"""
        try:
            client, address = self._server.accept()
        except OSError:
            return
        if len(self._clients) >= MAX_CLIENTS:
            client.close()
            return
        client.setblocking(False)
        self._clients[client] = address
        self._publish_clients()

    def _read_client(self, sock):
        """读取一个客户端的数据, 断开时移除

        @param sock: 客户端套接字
        @return: 是否继续读循环
        """
        try:
            data = sock.recv(RECV_CHUNK)
        except BlockingIOError:
            return True
        except OSError:
            data = b""
        if not data:
            self._drop(sock)
            return True
        address = self._clients.get(sock)
        source = "%s:%d" % address if address else ""
        self._emit(data, source)
        return True

    def _drop(self, sock):
        """移除一个客户端并通知页面

        @param sock: 客户端套接字
        """
        self._clients.pop(sock, None)
        try:
            sock.close()
        except OSError:
            pass
        self._publish_clients()

    def _publish_clients(self):
        """把当前客户端列表告诉页面"""
        self._event("clients", self.client_addresses())

    def client_addresses(self):
        """当前所有客户端的地址

        @return: "地址:端口" 列表
        """
        return ["%s:%d" % address for address in self._clients.values()]

    def send(self, payload, targets=None):
        """给全部或者指定的客户端发送数据

        @param payload: 字节串
        @param targets: "地址:端口" 列表, None 表示全部
        @throws SessionError: 一个都没发出去时
        """
        if not self.is_open:
            raise SessionError("监听还没有启动")
        chosen = []
        for sock, address in list(self._clients.items()):
            text = "%s:%d" % address
            if targets is None or text in targets:
                chosen.append((sock, text))
        if not chosen:
            raise SessionError("当前没有可发送的客户端")
        sent = 0
        failed = []
        with self._lock:
            for sock, text in chosen:
                try:
                    sock.sendall(payload)
                    sent += 1
                except OSError:
                    failed.append(sock)
        for sock in failed:
            self._drop(sock)
        if not sent:
            raise SessionError("发送失败: 客户端已断开")
        return sent

    def _release(self):
        """关闭监听套接字与所有客户端"""
        for sock in list(self._clients):
            try:
                sock.close()
            except OSError:
                pass
        self._clients.clear()
        if self._server is not None:
            try:
                self._server.close()
            except OSError:
                logger.warning("关闭监听套接字失败", exc_info=True)
            self._server = None


class UdpSession(BaseSession):
    """UDP 会话: 一个接收套接字, 需要固定发送端口时再加一个发送套接字"""

    kind = "udp"
    label = "UDP"

    def __init__(self, host, port, address="", recv_port=0, send_port=0,
                 on_data=None, on_event=None):
        super().__init__(on_data, on_event)
        self._host = host
        self._port = port
        self._address = address
        self._recv_port = recv_port
        self._send_port = send_port
        self._recv_socket = None
        self._send_socket = None
        self.bound_port = 0

    def start(self):
        """绑定本机端口

        @throws SessionError: 绑定失败时
        """
        recv_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            recv_socket.bind((self._address or "", self._recv_port or 0))
        except OSError as exc:
            recv_socket.close()
            raise SessionError("绑定 %s:%d 失败: %s" % (
                self._address or "0.0.0.0", self._recv_port or 0, exc)) from exc
        recv_socket.settimeout(POLL_TIMEOUT)
        self._recv_socket = recv_socket
        self.bound_port = recv_socket.getsockname()[1]
        if self._send_port:
            self._send_socket = self._open_send_socket()
        self._open = True
        self._start_thread(self._read_loop, "comm-udp-read")
        self._event("open", "%s:%d" % (self._address or "0.0.0.0", self.bound_port))
        return True

    def _open_send_socket(self):
        """建立固定发送端口的套接字

        @return: 套接字
        @throws SessionError: 端口被占用时
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.bind((self._address or "", self._send_port))
        except OSError as exc:
            sock.close()
            raise SessionError("绑定发送端口 %d 失败: %s" % (self._send_port, exc)) from exc
        return sock

    def _read_loop(self):
        """读线程: 收到谁的数据就在视图里标出谁"""
        while not self._stop.is_set():
            try:
                data, address = self._recv_socket.recvfrom(RECV_CHUNK)
            except socket.timeout:
                continue
            except OSError as exc:
                if not self._stop.is_set():
                    self._fail("接收失败: %s" % exc)
                return
            self._emit(data, "%s:%d" % (address[0], address[1]))
        return None

    def send(self, payload, targets=None):
        """往目的地址发送数据

        @param payload: 字节串
        @throws SessionError: 没有绑定或者发送失败时
        """
        if not self.is_open:
            raise SessionError("UDP 还没有绑定本机端口")
        sock = self._send_socket or self._recv_socket
        with self._lock:
            try:
                sock.sendto(payload, (self._host, self._port))
            except OSError as exc:
                raise SessionError("发送失败: %s" % exc) from exc

    def _release(self):
        """关闭收发套接字"""
        for name in ("_send_socket", "_recv_socket"):
            sock = getattr(self, name)
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    logger.warning("关闭 UDP 套接字失败", exc_info=True)
                setattr(self, name, None)
