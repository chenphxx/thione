"""加密容器的统一入口与注册表。

各平台的容器实现放在同级模块里, 本模块按扩展名选用实现: 转换页面只调用
`prepare()`, 因此新增平台不需要改动页面里的流程。
"""

import os

from .. import constants
from . import ncm, sniff
from .base import PlatformError, Prepared

#: 加密容器的扩展名到实现的映射
DECODERS = {".ncm": ncm}


def prepare(source):
    """把音乐平台的加密容器还原成可以直接处理的音频文件。

    普通音频与视频容器原样返回; 扩展名像加密容器而内容不是时按文件头识别真实
    格式, 因此已经还原过或者只是改了扩展名的文件同样能参与转换

    @param source: 源文件路径
    @return: Prepared
    @throws PlatformError: 容器损坏, 或者文件内容无法识别
    """
    extension = os.path.splitext(source)[1].lstrip(".").lower()
    decoder = DECODERS.get(f".{extension}")
    if decoder is None:
        return Prepared(source, extension, False)
    if decoder.is_container(source):
        return decoder.decrypt(source)
    real = sniff.sniff_format(source)
    if not real:
        raise PlatformError(f"{constants.DECRYPT_FAILED}: "
                            f"{constants.PLATFORM_UNKNOWN}")
    return Prepared(source, real, False)
