"""进程信息的查询与强制结束。

连接表只给出 PID, 因此这里补上进程名 可执行文件路径 命令行 启动时间 内存
与父进程, 供界面展示; 结束进程走 TerminateProcess, 与任务管理器的 结束任务
等价, 需要对该进程有 PROCESS_TERMINATE 权限, 权限不足时由调用方提示用户
以管理员身份重新运行。
"""

import ctypes
from ctypes import wintypes
from datetime import datetime
from typing import NamedTuple

# 打开进程时申请的权限
PROCESS_TERMINATE = 0x0001
PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PROCESS_SYNCHRONIZE = 0x00100000

TH32CS_SNAPPROCESS = 0x00000002
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

#: NtQueryInformationProcess 的信息类别
PROCESS_BASIC_INFORMATION_CLASS = 0
PROCESS_WOW64_INFORMATION_CLASS = 26

#: 这两个进程不属于任何程序, 结束它们会失败, 直接拦下
PROTECTED_PIDS = frozenset({0, 4})

#: 结束进程时常见的错误码, 换成能直接展示给用户的说法
ERROR_HINTS = {
    5: "拒绝访问, 该进程可能以管理员权限运行, 需要以管理员身份启动 thione",
    87: "进程不存在, 可能已经退出",
}

#: 命令行的最长读取长度 (字符), 防止异常数据撑爆界面
MAX_COMMAND_LINE = 8192

#: 结束进程后等待它真正退出的最长时间 (毫秒), 之后调用方再刷新占用情况
TERMINATE_WAIT_MS = 2000

_pointer_size = ctypes.sizeof(ctypes.c_void_p)


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
    ]


class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


class PROCESS_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("Reserved1", ctypes.c_void_p),
        ("PebBaseAddress", ctypes.c_void_p),
        ("Reserved2", ctypes.c_void_p * 2),
        ("UniqueProcessId", ctypes.c_void_p),
        ("Reserved3", ctypes.c_void_p),
    ]


class UNICODE_STRING(ctypes.Structure):
    _fields_ = [
        ("Length", wintypes.USHORT),
        ("MaximumLength", wintypes.USHORT),
        ("Buffer", ctypes.c_void_p),
    ]


class ProcessEntry(NamedTuple):
    """进程快照里的基本信息。"""

    pid: int
    name: str
    parent_pid: int


class ProcessDetail(NamedTuple):
    """界面展示用的进程详情, 读不到的字段为空字符串。"""

    pid: int
    name: str
    path: str
    cmdline: str
    started: str
    memory: str
    parent_pid: int
    parent_name: str


_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_psapi = ctypes.WinDLL("psapi", use_last_error=True)
_ntdll = ctypes.WinDLL("ntdll")

_kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_kernel32.OpenProcess.restype = wintypes.HANDLE
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
_kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
_kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
_kernel32.WaitForSingleObject.restype = wintypes.DWORD
_kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
_kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
_kernel32.Process32FirstW.argtypes = [wintypes.HANDLE,
                                      ctypes.POINTER(PROCESSENTRY32W)]
_kernel32.Process32NextW.argtypes = [wintypes.HANDLE,
                                     ctypes.POINTER(PROCESSENTRY32W)]
_kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
    ctypes.POINTER(wintypes.DWORD),
]
_kernel32.ReadProcessMemory.argtypes = [
    wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
    ctypes.POINTER(ctypes.c_size_t),
]
_psapi.GetProcessMemoryInfo.argtypes = [
    wintypes.HANDLE, ctypes.POINTER(PROCESS_MEMORY_COUNTERS), wintypes.DWORD,
]
_ntdll.NtQueryInformationProcess.argtypes = [
    wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.ULONG,
    ctypes.POINTER(wintypes.ULONG),
]


def snapshot():
    """取一份进程快照, 用于把 PID 换成进程名与父进程。

    @return: {pid: ProcessEntry} 的字典
    """
    handle = _kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if handle == INVALID_HANDLE_VALUE:
        return {}
    entries = {}
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        if not _kernel32.Process32FirstW(handle, ctypes.byref(entry)):
            return {}
        while True:
            entries[entry.th32ProcessID] = ProcessEntry(
                pid=entry.th32ProcessID,
                name=entry.szExeFile,
                parent_pid=entry.th32ParentProcessID,
            )
            if not _kernel32.Process32NextW(handle, ctypes.byref(entry)):
                break
    finally:
        _kernel32.CloseHandle(handle)
    return entries


def describe(pid, entries=None):
    """汇总一个进程的详细信息。

    @param pid: 进程 ID
    @param entries: 可选的进程快照, 一次取多份详情时传进来避免重复枚举
    @return: ProcessDetail; 进程已退出或者权限不足时只填得到的那部分
    """
    entries = snapshot() if entries is None else entries
    entry = entries.get(pid)
    parent_pid = entry.parent_pid if entry else 0
    parent = entries.get(parent_pid)

    path = started = memory = cmdline = ""
    handle = _open(pid, PROCESS_QUERY_LIMITED_INFORMATION)
    if handle:
        try:
            path = _image_path(handle)
            started = _start_time(handle)
        finally:
            _kernel32.CloseHandle(handle)

    # 这两项需要更高的权限, 普通用户对系统进程拿不到
    handle = _open(pid, PROCESS_QUERY_INFORMATION | PROCESS_VM_READ)
    if handle:
        try:
            memory = _memory(handle)
            cmdline = _command_line(handle)
        finally:
            _kernel32.CloseHandle(handle)

    return ProcessDetail(
        pid=pid,
        name=entry.name if entry else "",
        path=path,
        cmdline=cmdline,
        started=started,
        memory=memory,
        parent_pid=parent_pid,
        parent_name=parent.name if parent else "",
    )


def terminate(pid):
    """强制结束进程。

    @param pid: 目标进程 ID
    @throws OSError: 系统进程 权限不足或者进程已经退出, 消息可直接展示给用户
    """
    if pid in PROTECTED_PIDS:
        raise OSError("这是系统进程, 不能结束")
    handle = _open(pid, PROCESS_TERMINATE | PROCESS_SYNCHRONIZE)
    if not handle:
        raise OSError(f"结束进程失败: {_last_error()}")
    try:
        if not _kernel32.TerminateProcess(handle, 1):
            raise OSError(f"结束进程失败: {_last_error()}")
        # 等目标真正退出再返回, 否则调用方紧接着刷新时占用记录还没来得及消失
        _kernel32.WaitForSingleObject(handle, TERMINATE_WAIT_MS)
    finally:
        _kernel32.CloseHandle(handle)


def _open(pid, access):
    """按给定权限打开进程, 失败时返回 None 而不是抛异常。"""
    return _kernel32.OpenProcess(access, False, pid) or None


def _image_path(handle):
    """取可执行文件完整路径。"""
    size = wintypes.DWORD(32768)
    buffer = ctypes.create_unicode_buffer(size.value)
    if not _kernel32.QueryFullProcessImageNameW(handle, 0, buffer,
                                                ctypes.byref(size)):
        return ""
    return buffer.value


def _start_time(handle):
    """取进程启动时间并换成本地时间。"""
    creation = wintypes.FILETIME()
    exit_time = wintypes.FILETIME()
    kernel = wintypes.FILETIME()
    user = wintypes.FILETIME()
    if not _kernel32.GetProcessTimes(handle, ctypes.byref(creation),
                                     ctypes.byref(exit_time),
                                     ctypes.byref(kernel), ctypes.byref(user)):
        return ""
    ticks = (creation.dwHighDateTime << 32) | creation.dwLowDateTime
    try:
        # FILETIME 以 1601-01-01 起的 100 纳秒为单位
        timestamp = ticks / 10_000_000 - 11644473600
        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
    except (OSError, OverflowError, ValueError):
        return ""


def _memory(handle):
    """取工作集大小。"""
    counters = PROCESS_MEMORY_COUNTERS()
    counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
    if not _psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters),
                                       counters.cb):
        return ""
    return f"{counters.WorkingSetSize / 1024 / 1024:.1f} MB"


def _command_line(handle):
    """从目标进程的 PEB 里读命令行。

    进程参数在 PEB 中的偏移与位数有关, 32 位目标进程 (WOW64) 的布局也不同,
    因此只有本进程是 64 位且目标不是 WOW64 时才尝试, 读不到就返回空串。

    @param handle: 以 PROCESS_QUERY_INFORMATION | PROCESS_VM_READ 打开的句柄
    @return: 命令行文本, 失败时为空字符串
    """
    if _pointer_size != 8 or _is_wow64(handle):
        return ""

    basic = PROCESS_BASIC_INFORMATION()
    length = wintypes.ULONG()
    status = _ntdll.NtQueryInformationProcess(
        handle, PROCESS_BASIC_INFORMATION_CLASS, ctypes.byref(basic),
        ctypes.sizeof(basic), ctypes.byref(length))
    if status != 0 or not basic.PebBaseAddress:
        return ""

    parameters = ctypes.c_void_p()
    if not _read(handle, basic.PebBaseAddress + 0x20, ctypes.byref(parameters),
                 _pointer_size):
        return ""

    text = UNICODE_STRING()
    if not _read(handle, parameters.value + 0x70, ctypes.byref(text),
                 ctypes.sizeof(text)):
        return ""
    if not text.Length or not text.Buffer:
        return ""

    size = min(text.Length // 2, MAX_COMMAND_LINE)
    buffer = ctypes.create_unicode_buffer(size)
    if not _read(handle, text.Buffer, buffer, size * 2):
        return ""
    return buffer.value.strip()


def _is_wow64(handle):
    """判断目标进程是不是 32 位 (WOW64), 判断失败按 False 处理。"""
    value = ctypes.c_void_p()
    length = wintypes.ULONG()
    status = _ntdll.NtQueryInformationProcess(
        handle, PROCESS_WOW64_INFORMATION_CLASS, ctypes.byref(value),
        ctypes.sizeof(value), ctypes.byref(length))
    return status == 0 and bool(value.value)


def _read(handle, address, buffer, size):
    """读目标进程的内存, 失败返回 False。"""
    read = ctypes.c_size_t()
    return bool(_kernel32.ReadProcessMemory(handle, ctypes.c_void_p(address),
                                            buffer, size, ctypes.byref(read)))


def _last_error():
    """把 GetLastError 换成可读文本, 常见错误给出更明确的说法。"""
    error = ctypes.WinError(ctypes.get_last_error())
    hint = ERROR_HINTS.get(error.winerror)
    if hint:
        return f"{hint} (错误码 {error.winerror})"
    text = (error.strerror or "").strip()
    if text:
        return f"{text} (错误码 {error.winerror})"
    return f"错误码 {error.winerror}"
