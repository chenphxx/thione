"""Windows DPI 感知与像素缩放

未声明 DPI 感知时, Windows 会把整个窗口按位图放大, 高缩放比例下文字会发虚.
本模块在创建 Tk 根窗口之前声明系统 DPI 感知, 并提供 scale() 把设计稿里的
逻辑像素换算成当前屏幕的物理像素
"""

import ctypes
import logging
import sys

logger = logging.getLogger(__name__)

_IS_WINDOWS = sys.platform == "win32"

#: 96 DPI 是 100% 缩放时的基准
_BASE_DPI = 96.0

_scale = 1.0
_initialized = False


def enable():
    """声明 Windows DPI 感知并计算缩放倍率

    必须在创建 Tk 根窗口之前调用. 重复调用只返回已经算好的倍率

    @return: 当前系统的缩放倍率, 例如 200% 返回 2.0
    """
    global _scale, _initialized
    if _initialized:
        return _scale
    _initialized = True
    if not _IS_WINDOWS:
        return _scale

    user32 = ctypes.windll.user32
    aware = False
    # -2 = DPI_AWARENESS_CONTEXT_SYSTEM_AWARE. 布局按启动时的系统 DPI
    # 缩放到物理像素, 跨显示器时由系统统一处理
    try:
        aware = bool(user32.SetProcessDpiAwarenessContext(
            ctypes.c_void_p(-2)))
    except Exception:
        logger.debug("SetProcessDpiAwarenessContext 不可用", exc_info=True)
    if not aware:
        try:
            aware = bool(ctypes.windll.shcore.SetProcessDpiAwareness(1))
        except Exception:
            logger.debug("SetProcessDpiAwareness 不可用", exc_info=True)
    if not aware:
        try:
            aware = bool(user32.SetProcessDPIAware())
        except Exception:
            logger.debug("SetProcessDPIAware 不可用", exc_info=True)

    dpi = _BASE_DPI
    try:
        dpi = int(user32.GetDpiForSystem())
    except Exception:
        logger.debug("GetDpiForSystem 不可用", exc_info=True)
        try:
            hdc = user32.GetDC(0)
            dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)
            user32.ReleaseDC(0, hdc)
        except Exception:
            logger.debug("读取系统 DPI 失败", exc_info=True)

    _scale = max(1.0, dpi / _BASE_DPI)
    logger.info("DPI 缩放已启用: %s DPI, 倍率 %.2f", dpi, _scale)
    return _scale


def scale(value):
    """把设计稿像素换算成当前 DPI 下的物理像素

    @param value: 逻辑像素
    @return: 按当前 DPI 取整后的像素
    """
    if not _initialized:
        enable()
    if value <= 0:
        return 0
    return max(1, int(round(value * _scale)))


def factor():
    """返回当前缩放倍率

    @return: 1.0 表示 100%, 2.0 表示 200%
    """
    if not _initialized:
        enable()
    return _scale
