"""读取和保存界面偏好与工具级缓存"""

import configparser
import logging
import os

from . import paths

logger = logging.getLogger(__name__)

SECTION = "ui"
#: 工具级缓存所在的段, 例如文件格式转换上次用过的 ffmpeg 路径
TOOLS_SECTION = "tools"
SETTINGS_FILE = "settings.ini"
DEFAULT_THEME = "light"
THEMES = ("light", "dark")
DEFAULT_PAGE = ""


def config_path():
    """返回 settings.ini 的完整路径 (不保证文件已存在)"""
    return os.path.join(paths.user_data_dir(), SETTINGS_FILE)


def legacy_config_path():
    """返回更名前 settings.ini 的路径, 只作为兼容读取来源"""
    return os.path.join(paths.legacy_user_data_dir(), SETTINGS_FILE)


def _read_section(path, section=SECTION):
    """读取设置文件里的一个段, 返回去掉首尾空白后的键值对

    @param path: 设置文件路径
    @param section: 段名, 默认是 [ui]
    @return: 键值对字典; 文件不存在或没有该段时返回 None
    """
    parser = configparser.ConfigParser()
    try:
        # utf-8-sig: 兼容记事本'UTF-8'另存后带 BOM 的文件
        parser.read(path, encoding="utf-8-sig")
    except (configparser.Error, OSError, UnicodeDecodeError):
        logger.warning("界面设置无法读取, 忽略该文件: %s", path)
        return None
    if not parser.has_section(section):
        return None
    return {k: (v or "").strip() for k, v in parser.items(section)}


class AppSettings:
    """界面偏好的内存表示, 修改属性后调用 save() 落盘"""

    def __init__(self, theme=DEFAULT_THEME, page=DEFAULT_PAGE,
                 ffmpeg_path=""):
        self.theme = theme if theme in THEMES else DEFAULT_THEME
        self.page = page
        #: 文件格式转换上次用过的 ffmpeg 路径, 空串表示还没有缓存
        self.ffmpeg_path = ffmpeg_path

    @classmethod
    def load(cls):
        """读取界面设置, 新位置没有可用内容时回落到更名前的旧位置

        @return: AppSettings 实例; 任何异常都回落到默认值
        """
        values = {}
        tools = {}
        for path in (config_path(), legacy_config_path()):
            found = _read_section(path)
            if found is None:
                continue
            values = found
            tools = _read_section(path, TOOLS_SECTION) or {}
            break

        theme = values.get("theme", DEFAULT_THEME)
        return cls(theme=theme, page=values.get("page", DEFAULT_PAGE),
                   ffmpeg_path=tools.get("ffmpeg", ""))

    def save(self):
        """写入设置文件; 失败只记日志, 不打断退出流程"""
        path = config_path()
        parser = configparser.ConfigParser()
        parser[SECTION] = {
            "theme": self.theme,
            "page": self.page or "",
        }
        parser[TOOLS_SECTION] = {
            "ffmpeg": self.ffmpeg_path or "",
        }
        try:
            paths.ensure_dir(os.path.dirname(path))
            # 先写临时文件再替换, 避免写一半留下损坏的设置
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                parser.write(f)
            os.replace(tmp, path)
        except OSError:
            logger.warning("界面设置保存失败: %s", path, exc_info=True)
