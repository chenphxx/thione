"""外壳级全局常量。

各工具的专属常量放在各自包的 constants.py 中, 这里只保留外壳自身以及
跨工具共享的取值。
"""

from . import __version__

APP_TITLE = "thione"
APP_TAGLINE = "图片查重 · 批量重命名 · 划词翻译"
APP_VERSION = __version__

# 主窗口尺寸
APP_SIZE = "1280x780"
APP_MIN_SIZE = (1000, 620)

# 外壳投递队列的轮询间隔 (毫秒)
QUEUE_POLL_MS = 200
