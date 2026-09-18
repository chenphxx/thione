"""图片读取与缩略图生成 跨工具复用。

图片查重与文件预览都需要「按给定尺寸等比缩小一张图」并且在读取失败时有占位图
统一放在这里 免得两个工具各写一遍 PIL 细节

@brief 图片缩放与占位图工具
"""

from PIL import Image


def load_thumbnail(path, size):
    """读取图片并等比缩放到 size 之内

    返回的是副本而不是原对象, 因此可以在 with 里把文件关掉:
    否则读过缩略图的文件会一直占着句柄, 批量重命名碰到
    它们时会报「另一个程序正在使用此文件」

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
    """读取图片的像素尺寸。

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