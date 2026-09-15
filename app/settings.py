"""外壳级界面设置的读写。

只保存界面偏好 (主题、上次停留的页面), 与华为云凭据等业务配置分开存放:
文件位于 %APPDATA%\\thione\\settings.ini。设置损坏或缺失时回落到默认值,
不影响程序启动。更名前位于 %APPDATA%\\thpy 的设置只作为兼容读取来源。
"""

import configparser
import logging
import os

from . import paths

logger = logging.getLogger(__name__)

SECTION = "ui"
SETTINGS_FILE = "settings.ini"
DEFAULT_THEME = "dark"
DEFAULT_PAGE = ""
THEMES = ("dark", "light")


def config_path():
    """返回 settings.ini 的完整路径 (不保证文件已存在)。"""
    return os.path.join(paths.user_data_dir(), SETTINGS_FILE)


def legacy_config_path():
    """返回更名前 settings.ini 的路径, 只作为兼容读取来源。"""
    return os.path.join(paths.legacy_user_data_dir(), SETTINGS_FILE)


def _read_section(path):
    """读取设置文件里的 [ui] 段, 返回去掉首尾空白后的键值对。

    @param path: 设置文件路径
    @return: 键值对字典; 文件不存在或没有 [ui] 段时返回 None
    """
    parser = configparser.ConfigParser()
    try:
        # utf-8-sig: 兼容记事本「UTF-8」另存后带 BOM 的文件
        parser.read(path, encoding="utf-8-sig")
    except (configparser.Error, OSError, UnicodeDecodeError):
        logger.warning("界面设置无法读取, 忽略该文件: %s", path)
        return None
    if not parser.has_section(SECTION):
        return None
    return {k: (v or "").strip() for k, v in parser.items(SECTION)}


class AppSettings:
    """界面偏好的内存表示, 修改属性后调用 save() 落盘。"""

    def __init__(self, theme=DEFAULT_THEME, page=DEFAULT_PAGE):
        self.theme = theme
        self.page = page

    @classmethod
    def load(cls):
        """读取界面设置, 新位置没有可用内容时回落到更名前的旧位置。

        @return: AppSettings 实例; 任何异常都回落到默认值
        """
        values = {}
        for path in (config_path(), legacy_config_path()):
            found = _read_section(path)
            if found is not None:
                values = found
                break

        theme = values.get("theme") or DEFAULT_THEME
        if theme not in THEMES:
            theme = DEFAULT_THEME
        return cls(theme=theme, page=values.get("page", DEFAULT_PAGE))

    def save(self):
        """写入设置文件; 失败只记日志, 不打断退出流程。"""
        path = config_path()
        parser = configparser.ConfigParser()
        parser[SECTION] = {"theme": self.theme, "page": self.page or ""}
        try:
            paths.ensure_dir(os.path.dirname(path))
            # 先写临时文件再替换, 避免写一半留下损坏的设置
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                parser.write(f)
            os.replace(tmp, path)
        except OSError:
            logger.warning("界面设置保存失败: %s", path, exc_info=True)
