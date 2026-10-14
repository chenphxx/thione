"""图片读取与缩略图生成 跨工具复用

图片查重与文件预览都需要'按给定尺寸等比缩小一张图'并且在读取失败时有占位图
统一放在这里 免得两个工具各写一遍 PIL 细节

@brief 图片缩放与占位图工具
"""

import math

from PIL import Image

#: 生成渐变时先按这个步长采样, 再插值放大, 免得逐像素计算太慢
GRADIENT_STEP = 4


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
