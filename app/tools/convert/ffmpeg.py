"""ffmpeg 的定位与音频转换调用。

转换本身全部交给 ffmpeg: 一套参数就能覆盖常见音频格式的容器与编码器组合, 因此
项目里不需要再引入音频编解码库。程序按 用户指定 -> 系统 PATH -> 随包副本 ->
常见安装位置 的顺序找 ffmpeg, 找不到时由页面引导用户手动选择。

转换在子进程里进行, 用 ffmpeg 的 -progress 输出换算进度; 取消时直接结束子进程,
并删掉没写完的输出文件, 因此不会留下半成品。
"""

import collections
import ctypes
import logging
import os
import re
import shutil
import subprocess

from . import constants

logger = logging.getLogger(__name__)

#: 打包成窗口程序后没有控制台, 用它避免每次调用都闪一个黑窗口
CREATE_NO_WINDOW = 0x08000000

#: 读取时长与进度用的匹配式
DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")
OUT_TIME_RE = re.compile(r"out_time_us=(\d+)")
VERSION_RE = re.compile(r"ffmpeg version (\S+)")
CHANNELS_RE = re.compile(r"(\d+) channels")

#: 失败时保留的最后几行输出
ERROR_TAIL_LINES = 8
#: 读不到声道数时按立体声估算
_DEFAULT_CHANNELS = 2
#: 失败原因的最长长度
MAX_REASON_CHARS = 200


class ConvertError(RuntimeError):
    """转换失败, 消息可以直接展示给用户。"""


def find_ffmpeg(configured=""):
    """按优先级找一个可用的 ffmpeg。

    @param configured: 用户在页面里指定的路径, 可以是空串
    @return: ffmpeg 可执行文件路径; 一个都找不到时返回空串
    """
    for candidate in (configured, *_candidates()):
        if candidate and os.path.isfile(candidate):
            return candidate
    return ""


def version(ffmpeg_path):
    """取 ffmpeg 的版本号, 用于确认选择的程序确实可用。

    @param ffmpeg_path: ffmpeg 可执行文件路径
    @return: 例如 7.1; 无法执行时返回空串
    """
    first_line = _version_line(ffmpeg_path)
    found = VERSION_RE.search(first_line)
    return found.group(1).split("-")[0] if found else ""


def convert(ffmpeg_path, source, target, codec, bitrate, extra_args=(),
            on_progress=None, on_start=None):
    """把一个音频文件转换成目标格式。

    @param ffmpeg_path: ffmpeg 可执行文件路径
    @param source: 源文件路径
    @param target: 输出文件路径
    @param codec: 目标格式的音频编码器名
    @param bitrate: 有损格式的码率 (kbps); 无损格式传 0; 传 AUTO_BITRATE 时按
                    每声道上限与源文件声道数算出最高码率; 其余超过编码器上限的
                    值按声道数下调 见 _effective_bitrate
    @param extra_args: 最高音质档附带的编码参数, 直接排在编码器参数之后
    @param on_progress: 可选回调, 参数是 0 到 1 的浮点进度
    @param on_start: 可选回调, 参数是刚启动的 Popen 对象, 供取消时结束进程
    @throws ConvertError: 转换失败, 消息可以直接展示给用户
    """
    if bitrate == constants.AUTO_BITRATE:
        bitrate = _auto_bitrate(ffmpeg_path, source, codec)
    elif bitrate:
        bitrate = _effective_bitrate(ffmpeg_path, source, codec, bitrate)

    args = [ffmpeg_path, "-hide_banner", "-nostdin", "-nostats", "-y",
            "-i", source, "-vn", "-sn", "-dn", "-map_metadata", "0",
            "-c:a", codec]
    if bitrate:
        args += ["-b:a", f"{bitrate}k"]
    args += list(extra_args)
    args += ["-progress", "pipe:1", target]

    try:
        process = subprocess.Popen(
            args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
            creationflags=CREATE_NO_WINDOW,
        )
    except OSError as exc:
        raise ConvertError(f"无法启动 ffmpeg: {exc}") from exc

    if on_start is not None:
        on_start(process)

    duration = 0.0
    tail = collections.deque(maxlen=ERROR_TAIL_LINES)
    for line in process.stdout:
        line = line.strip()
        if not line:
            continue
        if not duration:
            found = DURATION_RE.search(line)
            if found:
                duration = (int(found.group(1)) * 3600 + int(found.group(2)) * 60
                            + float(found.group(3)))
                continue
        found = OUT_TIME_RE.match(line)
        if found:
            if duration and on_progress is not None:
                seconds = int(found.group(1)) / 1_000_000
                on_progress(min(seconds / duration, 1.0))
            continue
        tail.append(line)

    code = process.wait()
    process.stdout.close()

    if code != 0:
        _remove_partial(target)
        raise ConvertError(_failure_message(code, tail))
    if on_progress is not None:
        on_progress(1.0)


def _auto_bitrate(ffmpeg_path, source, codec):
    """算最高音质档要用的码率: 每声道上限 x 源文件声道数。

    @param ffmpeg_path: ffmpeg 可执行文件路径
    @param source: 源文件路径
    @param codec: 目标音频编码器
    @return: 码率 (kbps); 该编码器没有记录每声道上限时返回 0 (不传码率)
    """
    limit = constants.BITRATE_LIMIT_PER_CHANNEL.get(codec)
    if not limit:
        return 0
    channels = _channel_count(ffmpeg_path, source) or _DEFAULT_CHANNELS
    return limit * channels


def _effective_bitrate(ffmpeg_path, source, codec, bitrate):
    """按编码器的每声道码率上限下调码率。

    单声道文件用 opus 或 vorbis 编码时, 码率超过每声道上限会让编码器直接
    失败; 因此请求值超过上限时先读一次源文件的声道数, 再按 声道数 x 上限
    取较小的值

    @param ffmpeg_path: ffmpeg 可执行文件路径
    @param source: 源文件路径
    @param codec: 目标音频编码器
    @param bitrate: 用户选择的码率 (kbps), 无损为 0
    @return: 实际使用的码率 (kbps)
    """
    limit = constants.BITRATE_LIMIT_PER_CHANNEL.get(codec)
    if not limit or not bitrate or bitrate <= limit:
        return bitrate
    channels = _channel_count(ffmpeg_path, source)
    if not channels:
        return bitrate
    return min(bitrate, limit * channels)


def _channel_count(ffmpeg_path, source):
    """读源文件的声道数。

    @param ffmpeg_path: ffmpeg 可执行文件路径
    @param source: 源文件路径
    @return: 声道数; 读不到时返回 0
    """
    try:
        result = subprocess.run([ffmpeg_path, "-hide_banner", "-i", source],
                                capture_output=True, text=True,
                                encoding="utf-8", errors="replace",
                                timeout=15, creationflags=CREATE_NO_WINDOW)
    except (OSError, subprocess.SubprocessError):
        logger.warning("无法读取声道数: %s", source, exc_info=True)
        return 0
    for line in (result.stderr or "").splitlines():
        if "Audio:" not in line:
            continue
        if ", mono," in line:
            return 1
        if ", stereo," in line:
            return 2
        found = CHANNELS_RE.search(line)
        if found:
            return int(found.group(1))
    return 0


def _candidates():
    """系统里可能存在的 ffmpeg, 按可靠性从高到低。"""
    found = shutil.which("ffmpeg")
    if found:
        yield found
    yield _bundled_path()
    for path in _common_paths():
        yield path


def _common_paths():
    """常见安装位置, 只做定点检查, 不做全盘搜索。"""
    roots = (
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WinGet",
                     "Links"),
        os.path.join(os.environ.get("ProgramData", ""), "chocolatey", "bin"),
        os.path.join(os.path.expanduser("~"), "scoop", "shims"),
        os.path.join(os.environ.get("ProgramFiles", ""), "ffmpeg", "bin"),
        r"C:\ffmpeg\bin",
    )
    return [os.path.join(root, "ffmpeg.exe") for root in roots if root]


def _bundled_path():
    """随程序附带的 ffmpeg 副本, 来自可选的 imageio-ffmpeg 依赖。"""
    try:
        import imageio_ffmpeg
    except ImportError:
        return ""
    try:
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # 第三方库在下载失败等情况下会抛各种异常
        logger.warning("随包的 ffmpeg 不可用", exc_info=True)
        return ""


def _version_line(ffmpeg_path):
    """取 ffmpeg -version 的第一行, 失败时返回空串。"""
    try:
        result = subprocess.run([ffmpeg_path, "-version"], capture_output=True,
                                text=True, encoding="utf-8", errors="replace",
                                timeout=15, creationflags=CREATE_NO_WINDOW)
    except (OSError, subprocess.SubprocessError):
        logger.warning("无法读取 ffmpeg 版本: %s", ffmpeg_path, exc_info=True)
        return ""
    return (result.stdout or "").splitlines()[0] if result.stdout else ""


def _failure_message(code, tail):
    """从末尾输出里挑一句能说明问题的原因。"""
    reason = ""
    for line in reversed(tail):
        if "rror" in line or "Invalid" in line or "failed" in line:
            reason = line
            break
    if not reason and tail:
        reason = tail[-1]
    reason = reason.strip()[:MAX_REASON_CHARS]
    if not reason:
        return f"{constants.CONVERT_FAILED} (退出码 {code})"
    return f"{constants.CONVERT_FAILED}: {reason}"


def _remove_partial(target):
    """删掉没转换完的输出文件, 失败时只记日志。"""
    try:
        os.remove(target)
    except OSError:
        pass
