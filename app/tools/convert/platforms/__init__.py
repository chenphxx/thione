"""音乐平台加密容器的还原子包。

对外只暴露 `prepare()` 与 `PlatformError`: 转换页面在开始处理一个文件之前调用
`prepare()`, 把加密容器换成可以直接交给 ffmpeg 的音频文件。各平台的实现放在
同级模块里, 由注册表按扩展名选用, 因此加载本包不会牵连具体平台的细节。
"""

from .base import PlatformError, Prepared
from .container import prepare

__all__ = ["PlatformError", "Prepared", "prepare"]
