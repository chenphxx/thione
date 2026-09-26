"""加密容器还原的公共类型。

平台实现与注册表都要用到这里的异常与返回结构, 单独放一个模块可以避免它们
互相导入
"""

from dataclasses import dataclass


@dataclass
class Prepared:
    """一个文件在转换前的准备结果。

    @brief 普通音频与视频容器原样返回, 加密容器的还原结果放在临时文件里
    """

    path: str
    extension: str
    temporary: bool


class PlatformError(RuntimeError):
    """加密容器的识别或还原失败, 消息可以直接展示给用户。"""
