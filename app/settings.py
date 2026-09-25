"""读取和保存上次选择的工具页面偏好。"""

import configparser
import logging
import os

from . import paths

logger = logging.getLogger(__name__)

SECTION = "ui"
SETTINGS_FILE = "settings.ini"
DEFAULT_PAGE = ""


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

    def __init__(self, page=DEFAULT_PAGE):
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

        # 旧版本保存过可选主题设置; 新界面统一使用浅色主题。
        return cls(page=values.get("page", DEFAULT_PAGE))

    def save(self):
        """写入设置文件; 失败只记日志, 不打断退出流程。"""
        path = config_path()
        parser = configparser.ConfigParser()
        parser[SECTION] = {"page": self.page or ""}
        try:
            paths.ensure_dir(os.path.dirname(path))
            # 先写临时文件再替换, 避免写一半留下损坏的设置
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                parser.write(f)
            os.replace(tmp, path)
        except OSError:
            logger.warning("界面设置保存失败: %s", path, exc_info=True)
