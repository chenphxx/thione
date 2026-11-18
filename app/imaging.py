"""图片与视频缩略图生成 跨工具复用

图片查重与文件预览都需要'按给定尺寸等比缩小一张图'并且在读取失败时有占位图
统一放在这里 免得两个工具各写一遍 PIL 细节

@brief 图片缩放与占位图工具
"""

import io
import logging
import math
import os
import subprocess

from PIL import Image

logger = logging.getLogger(__name__)

#: 生成渐变时先按这个步长采样, 再插值放大, 免得逐像素计算太慢
GRADIENT_STEP = 4

#: 可以用 ffmpeg 提取首帧作为缩略图的视频扩展名
VIDEO_EXTS = {".mp4", ".m4v", ".mov", ".mkv", ".webm", ".avi", ".flv",
              ".wmv", ".mpg", ".mpeg"}

#: 打包成窗口程序后调用 ffmpeg 不弹出控制台窗口
_CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0

#: 视频取帧的超时时间 (秒)
_VIDEO_TIMEOUT = 15

#: 第一次查找 ffmpeg 后缓存结果, None 表示还没有查找过
_FFMPEG_PATH = None


def load_thumbnail(path, size):
    """读取图片并等比缩放到 size 之内

    返回的是副本而不是原对象, 因此可以在 with 里把文件关掉:
    否则读过缩略图的文件会一直占着句柄, 批量重命名碰到
    它们时会报'另一个程序正在使用此文件'

    @param path: 图片路径
    @param size: (宽, 高) 上限
    @return: PIL Image 对象 读取失败时返回 None
    """
    try:
        with Image.open(path) as img:
            img.thumbnail(size)
            return img.copy()
    except Exception:
        return None


def is_video_file(path):
    """按扩展名判断文件是否为可提取预览帧的视频

    @param path: 文件路径
    @return: 是否可作为视频读取
    """
    return os.path.splitext(path)[1].lower() in VIDEO_EXTS


def load_preview_thumbnail(path, size):
    """按文件类型生成图片或视频缩略图

    @param path: 文件路径
    @param size: (宽, 高) 上限
    @return: PIL Image 对象, 无法生成时返回 None
    """
    if is_video_file(path):
        return load_video_thumbnail(path, size)
    return load_thumbnail(path, size)


def load_video_thumbnail(path, size, ffmpeg_path=""):
    """读取视频首帧并等比缩放到 size 之内

    优先在 0.3 秒处快速定位, 短视频取不到时再尝试第一帧. 提取在独立进程中
    完成, 不把视频解码依赖引入主进程

    @param path: 视频路径
    @param size: (宽, 高) 上限
    @param ffmpeg_path: 可选的 ffmpeg 路径, 省略时复用文件格式转换的查找逻辑
    @return: PIL Image 对象, 读取失败时返回 None
    """
    engine = ffmpeg_path or _find_ffmpeg()
    if not engine:
        return None
    for seek in ("0.3", "0"):
        image = _extract_video_frame(engine, path, size, seek)
        if image is not None:
            return image
    return None


def _extract_video_frame(ffmpeg_path, path, size, seek):
    """用 ffmpeg 提取指定时间点的一帧

    @param ffmpeg_path: ffmpeg 可执行文件路径
    @param path: 视频路径
    @param size: 缩略图尺寸上限
    @param seek: 定位时间 (秒)
    @return: PIL Image 对象或 None
    """
    width = max(int(size[0]), 1)
    height = max(int(size[1]), 1)
    command = [
        ffmpeg_path, "-hide_banner", "-loglevel", "error", "-nostdin",
        "-ss", seek, "-i", path, "-map", "0:v:0", "-frames:v", "1",
        "-an", "-sn", "-dn", "-vf",
        f"scale={width}:{height}:force_original_aspect_ratio=decrease",
        "-f", "image2pipe", "-vcodec", "png", "pipe:1",
    ]
    try:
        result = subprocess.run(
            command, capture_output=True, timeout=_VIDEO_TIMEOUT,
            creationflags=_CREATE_NO_WINDOW)
    except (OSError, subprocess.SubprocessError):
        logger.debug("提取视频预览帧失败: %s", path, exc_info=True)
        return None
    if result.returncode != 0 or not result.stdout:
        return None
    try:
        with Image.open(io.BytesIO(result.stdout)) as image:
            image.thumbnail(size)
            return image.copy()
    except Exception:
        logger.debug("解析视频预览帧失败: %s", path, exc_info=True)
        return None


def _find_ffmpeg():
    """查找并缓存 ffmpeg, 与文件格式转换使用同一套定位逻辑"""
    global _FFMPEG_PATH
    if _FFMPEG_PATH is None:
        from .tools.convert.ffmpeg import find_ffmpeg

        _FFMPEG_PATH = find_ffmpeg()
    return _FFMPEG_PATH


def image_size(path):
    """读取图片的像素尺寸

    @param path: 图片路径
    @return: (宽, 高), 读取失败时返回 None
    """
    try:
        with Image.open(path) as img:
            return img.size
    except Exception:
        return None


def make_placeholder(size, color):
    """生成用于占位的纯色图

    @param size: (宽, 高)
    @param color: RGB 三元组
    @return: PIL Image 对象
    """
    return Image.new("RGB", size, color)


def make_gradient(size, start, end, angle=140):
    """生成一张线性渐变图, 用作缩略图的占位底

    角度与 CSS 的 linear-gradient 一致: 0 度朝上, 顺时针增加; 起始色在渐变线的
    起点一侧. 界面上的缩略图占位用的是设计稿里的 140 度 ph1 -> ph2

    @param size: (宽, 高)
    @param start: 起始色 (r, g, b)
    @param end: 结束色 (r, g, b)
    @param angle: 渐变方向的角度
    @return: PIL Image 对象
    """
    width, height = max(int(size[0]), 1), max(int(size[1]), 1)
    radians = math.radians(angle)
    step_x, step_y = math.sin(radians), -math.cos(radians)
    projections = [x * step_x + y * step_y
                   for x in (0, width) for y in (0, height)]
    low, high = min(projections), max(projections)
    span = (high - low) or 1.0

    small_width = max(2, width // GRADIENT_STEP)
    small_height = max(2, height // GRADIENT_STEP)
    small = Image.new("RGB", (small_width, small_height))
    pixels = small.load()
    for row in range(small_height):
        y = row * GRADIENT_STEP
        for column in range(small_width):
            x = column * GRADIENT_STEP
            ratio = ((x * step_x + y * step_y) - low) / span
            pixels[column, row] = tuple(
                round(start[channel] + (end[channel] - start[channel]) * ratio)
                for channel in range(3)
            )
    return small.resize((width, height), Image.BILINEAR)
