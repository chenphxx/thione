"""查询文件被哪些进程占用。

用的是 Windows 重启管理器 (Restart Manager) 接口, 它正是系统弹出「该文件
正被另一个程序使用」时所依据的接口: 以普通用户身份就能列出持有该文件句柄
的进程, 不需要管理员权限, 也不需要自己枚举全系统的句柄表。
"""

import ctypes
import os
from ctypes import wintypes
from typing import NamedTuple

# RmGetList 的返回码
ERROR_SUCCESS = 0
ERROR_MORE_DATA = 234

# CreateFileW 的参数
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
OPEN_EXISTING = 3
FILE_ATTRIBUTE_NORMAL = 0x80

ERROR_ACCESS_DENIED = 5
ERROR_SHARING_VIOLATION = 32

INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

# 会话密钥长度
CCH_RM_SESSION_KEY = 32
CCH_RM_MAX_APP_NAME = 255
CCH_RM_MAX_SVC_NAME = 63

#: RM_APP_TYPE 的取值
APPLICATION_TYPES = {
    0: "未知",
    1: "主窗口程序",
    2: "后台窗口程序",
    3: "服务",
    4: "资源管理器",
    5: "控制台程序",
    1000: "关键系统进程",
}


class RM_UNIQUE_PROCESS(ctypes.Structure):
    _fields_ = [
        ("dwProcessId", wintypes.DWORD),
        ("ProcessStartTime", wintypes.FILETIME),
    ]


class RM_PROCESS_INFO(ctypes.Structure):
    _fields_ = [
        ("Process", RM_UNIQUE_PROCESS),
        ("strAppName", wintypes.WCHAR * (CCH_RM_MAX_APP_NAME + 1)),
        ("strServiceShortName", wintypes.WCHAR * (CCH_RM_MAX_SVC_NAME + 1)),
        ("ApplicationType", ctypes.c_int),
        ("AppStatus", wintypes.ULONG),
        ("TSSessionId", wintypes.DWORD),
        ("bRestartable", wintypes.BOOL),
    ]


class FileLock(NamedTuple):
    """占用文件的一个进程。"""

    pid: int
    app_name: str
    app_type: str
    service_name: str


_rstrtmgr = ctypes.WinDLL("RstrtMgr.dll", use_last_error=True)
_rstrtmgr.RmStartSession.argtypes = [
    ctypes.POINTER(wintypes.DWORD), wintypes.DWORD, wintypes.LPWSTR,
]
_rstrtmgr.RmRegisterResources.argtypes = [
    wintypes.DWORD, wintypes.UINT, ctypes.POINTER(wintypes.LPCWSTR),
    wintypes.UINT, ctypes.c_void_p, wintypes.UINT, ctypes.c_void_p,
]
_rstrtmgr.RmGetList.argtypes = [
    wintypes.DWORD, ctypes.POINTER(wintypes.UINT), ctypes.POINTER(wintypes.UINT),
    ctypes.POINTER(RM_PROCESS_INFO), ctypes.POINTER(wintypes.DWORD),
]
_rstrtmgr.RmEndSession.argtypes = [wintypes.DWORD]

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.CreateFileW.argtypes = [
    wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
    wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
]
_kernel32.CreateFileW.restype = wintypes.HANDLE
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]


def list_locks(path):
    """列出占用指定文件的进程。

    重启管理器只登记文件, 文件夹要查占用得逐个文件登记, 因此这里只
    接受文件路径。

    @param path: 文件的完整路径
    @return: FileLock 列表, 没有进程占用时为空列表
    @throws OSError: 路径不存在或不是文件, 会话建立失败或路径无法注册时
    """
    if not os.path.exists(path):
        raise OSError("文件不存在, 请重新选择")
    if os.path.isdir(path):
        raise OSError("这是文件夹, 占用查询只支持文件")
    session = wintypes.DWORD()
    key = ctypes.create_unicode_buffer(CCH_RM_SESSION_KEY + 1)
    result = _rstrtmgr.RmStartSession(ctypes.byref(session), 0, key)
    if result != ERROR_SUCCESS:
        raise OSError(f"无法开始占用查询 (错误码 {result})")
    try:
        names = (wintypes.LPCWSTR * 1)(path)
        result = _rstrtmgr.RmRegisterResources(session, 1, names, 0, None, 0,
                                              None)
        if result != ERROR_SUCCESS:
            raise OSError(f"无法查询该路径, 请确认文件存在且可访问 (错误码 {result})")
        return _collect(session)
    finally:
        _rstrtmgr.RmEndSession(session)


def is_available(path):
    """判断文件当前能不能被独占打开。

    重启管理器只登记会妨碍文件被替换的进程, 读完就释放句柄的程序 (多数图片
    查看器) 不在其中; 独占打开是直接问系统现在还有没有别的句柄开着这个文件,
    因此两种结果可以互相印证。

    @param path: 文件的完整路径
    @return: True 可以独占打开, 说明当前没有别的程序占用; False 文件被别的
        程序占用; None 因为权限等原因无法判断
    """
    return _try_open(path, GENERIC_READ | GENERIC_WRITE)


def _try_open(path, access):
    """以不共享的方式打开文件, 写权限不足时退回只读再试一次。"""
    handle = _kernel32.CreateFileW(path, access, 0, None, OPEN_EXISTING,
                                   FILE_ATTRIBUTE_NORMAL, None)
    if handle != INVALID_HANDLE_VALUE:
        _kernel32.CloseHandle(handle)
        return True
    error = ctypes.get_last_error()
    if error == ERROR_SHARING_VIOLATION:
        return False
    if access != GENERIC_READ:
        # 只读文件和没有写权限的文件会在这里被拒, 换成只读再试一次;
        # 共享模式仍然是 0, 只要有别的句柄开着这个文件就一样会失败
        return _try_open(path, GENERIC_READ)
    if error == ERROR_SHARING_VIOLATION:
        return False
    return None


def _collect(session):
    """取会话里登记的进程列表。

    第一次调用只为拿到需要的数组长度, 返回 ERROR_MORE_DATA; 按长度重新申请
    再取一次。没有进程占用时第一次调用就返回成功且数量为 0。
    """
    needed = wintypes.UINT(0)
    count = wintypes.UINT(0)
    reasons = wintypes.DWORD(0)
    result = _rstrtmgr.RmGetList(session, ctypes.byref(needed),
                                 ctypes.byref(count), None, ctypes.byref(reasons))
    if result == ERROR_SUCCESS and not needed.value:
        return []
    if result not in (ERROR_SUCCESS, ERROR_MORE_DATA):
        raise OSError(f"读取占用进程失败 (错误码 {result})")

    size = max(needed.value, 1)
    array = (RM_PROCESS_INFO * size)()
    count = wintypes.UINT(size)
    result = _rstrtmgr.RmGetList(session, ctypes.byref(needed),
                                 ctypes.byref(count), array,
                                 ctypes.byref(reasons))
    if result not in (ERROR_SUCCESS, ERROR_MORE_DATA):
        raise OSError(f"读取占用进程失败 (错误码 {result})")

    locks = []
    for info in array[:count.value]:
        locks.append(FileLock(
            pid=info.Process.dwProcessId,
            app_name=info.strAppName,
            app_type=APPLICATION_TYPES.get(info.ApplicationType,
                                           str(info.ApplicationType)),
            service_name=info.strServiceShortName,
        ))
    locks.sort(key=lambda item: item.pid)
    return locks
