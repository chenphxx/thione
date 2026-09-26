"""转换任务的准备: 扫描输入文件 规划输出路径与显示大小。

页面只负责收集用户输入与展示进度, 文件系统相关的规则集中在这里; 该模块不
依赖 tkinter, 可以单独验证。
"""

import logging
import os
import shutil
from dataclasses import dataclass

from .constants import (EMPTY_VALUE, FORMAT_ALIASES, INPUT_EXTENSIONS,
                        STATUS_WAITING)

logger = logging.getLogger(__name__)

#: 输出文件重名时最多尝试多少个序号
MAX_NAME_ATTEMPTS = 1000


@dataclass
class ConvertItem:
    """列表里的一行: 源文件 大小 当前状态与状态颜色。

    @brief 输出路径要到开始转换时才决定, 因此这里只记录源文件
    """

    source: str
    size: int
    status: str = STATUS_WAITING
    tag: str = ""

    @property
    def name(self):
        """文件名 (不含目录)。"""
        return os.path.basename(self.source)

    @property
    def extension(self):
        """扩展名的大写形式, 没有扩展名时显示占位符。"""
        return os.path.splitext(self.source)[1].lstrip(".").upper() or EMPTY_VALUE


def file_size(path):
    """取文件大小。

    @param path: 文件路径
    @return: 字节数; 文件读不到时返回 0
    """
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def scan_folder(folder):
    """递归收集文件夹里可以作为输入的音频文件。

    @param folder: 要扫描的文件夹
    @return: 按路径排序的文件列表
    """
    found = []
    for root, _dirs, filenames in os.walk(folder):
        for name in filenames:
            if os.path.splitext(name)[1].lower() in INPUT_EXTENSIONS:
                found.append(os.path.join(root, name))
    return sorted(found)


def is_same_target(source, dest_dir, extension):
    """判断一次转换是否没有意义。

    源文件已经是目标格式 并且输出会落回源文件本身时 没有必要再转一次

    @param source: 源文件路径
    @param dest_dir: 指定的输出目录, 空串表示与源文件同目录
    @param extension: 目标扩展名, 不带点
    @return: 转换没有意义时为 True
    """
    directory = dest_dir or os.path.dirname(source)
    if _key(directory) != _key(os.path.dirname(source)):
        return False
    return os.path.splitext(source)[1].lstrip(".").lower() == extension.lower()


def is_same_format(extension, other):
    """判断两个扩展名是否属于同一编码格式。

    同一编码格式可能有多个扩展名, 例如 .oga 与 .ogg 因此按格式比较而不是直接
    比较扩展名字符串

    @param extension: 一个扩展名, 可以带点
    @param other: 另一个扩展名, 可以带点
    @return: 两者是同一编码格式时为 True
    """
    return _format_key(extension) == _format_key(other)


def copy_file(source, target):
    """把已经是目标格式的文件直接复制到输出位置。

    复制不经过编码器, 因此不会因为二次编码损失音质; 元数据与修改时间一并
    保留

    @param source: 源文件路径
    @param target: 输出文件路径
    @throws OSError: 复制失败, 例如目标位置没有写入权限
    """
    shutil.copy2(source, target)


def move_file(source, target):
    """把已经还原好的音频直接移到输出位置。

    还原结果本身就是目标格式时, 移动比再复制一份省一次读写

    @param source: 还原结果的临时路径
    @param target: 输出文件路径
    @throws OSError: 移动失败
    """
    shutil.move(source, target)


def remove_file(path):
    """删掉临时文件, 删不掉时只记日志。

    @param path: 文件路径
    """
    try:
        os.remove(path)
    except FileNotFoundError:
        # 还原结果被直接移到了输出位置, 临时文件已经不在了
        return
    except OSError:
        logger.warning("删除临时文件失败: %s", path, exc_info=True)


def output_path(source, dest_dir, extension):
    """给出这次转换的输出路径。

    @param source: 源文件路径
    @param dest_dir: 指定的输出目录, 空串表示与源文件同目录
    @param extension: 目标扩展名, 不带点
    @return: 输出文件路径; 重名时在文件名后追加序号, 不会覆盖已有文件
    """
    directory = dest_dir or os.path.dirname(source)
    stem = os.path.splitext(os.path.basename(source))[0]
    return _unique_path(os.path.join(directory, f"{stem}.{extension}"))


def format_size(size):
    """把字节数换成便于阅读的大小文字。

    @param size: 字节数
    @return: 例如 3.2 MB
    """
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    if size < 1024 * 1024 * 1024:
        return f"{size / 1024 / 1024:.1f} MB"
    return f"{size / 1024 / 1024 / 1024:.2f} GB"


def _unique_path(path):
    """文件名已经被占用时追加 (1) (2) 直到找到空位。

    @param path: 期望的输出路径
    @return: 可用的输出路径; 序号用尽时返回原路径
    """
    if not os.path.exists(path):
        return path
    stem, extension = os.path.splitext(path)
    for index in range(1, MAX_NAME_ATTEMPTS):
        candidate = f"{stem} ({index}){extension}"
        if not os.path.exists(candidate):
            return candidate
    return path


def _format_key(extension):
    """把扩展名归一到同一编码格式的代表名。

    @param extension: 扩展名, 可以带点
    @return: 小写的代表扩展名
    """
    extension = extension.lstrip(".").lower()
    for canonical, aliases in FORMAT_ALIASES.items():
        if extension == canonical or extension in aliases:
            return canonical
    return extension


def _key(path):
    """目录比较用的规范化形式。"""
    return os.path.normcase(os.path.abspath(path))
