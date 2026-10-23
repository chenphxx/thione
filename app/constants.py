"""外壳级全局常量"""

from . import __version__
from .dpi import scale

APP_TITLE = "thione"
APP_VERSION = __version__

#: 窗口与任务栏图标 (相对项目根目录; 打包后由 resource_path 解到临时目录)
APP_ICON = "assets/images/logo.ico"

# 主窗口尺寸
APP_SIZE = f"{scale(1280)}x{scale(780)}"
APP_MIN_SIZE = (scale(1000), scale(620))

# 外壳投递队列的轮询间隔 (毫秒)
QUEUE_POLL_MS = 200
