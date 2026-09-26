"""资源路径与运行目录辅助。

统一约定 (集成后各工具共用一套目录):
    用户配置 -> %APPDATA%\\thione
    运行日志 -> %LOCALAPPDATA%\\thione\\logs
    只读资源 -> 打包后的解压目录, 源码运行时为项目根目录

更名前使用的 %APPDATA%\\thpy 只作为兼容读取来源, 不再写入。
"""

import os
import sys

APP_DIR_NAME = "thione"

#: 更名前使用的目录名, 仅用于读取旧位置留下的数据
LEGACY_APP_DIR_NAME = "thpy"


def _project_root():
    """源码运行时的项目根目录 (app 包所在目录的上一级)。"""
    return os.path.abspath(os.path.dirname(os.path.dirname(__file__)))


def resource_path(relative_path):
    """返回随程序分发的只读资源路径。

    打包运行时资源被解压到 sys._MEIPASS (临时目录, 只读), 源码运行时回落到
    项目根目录。注意: 这个目录只适合读取, 不要向其中写入任何用户数据。
    """
    base_path = getattr(sys, "_MEIPASS", None)
    if base_path is None:
        base_path = _project_root()
    return os.path.join(base_path, relative_path)


def app_root():
    """返回「程序所在目录」。

    打包运行: exe 所在目录; 源码运行: 项目根目录。这是便携版放置 .env 或
    华为云 csv 的位置。不能用 __file__ 推算, 因为 onefile 模式下 __file__
    指向临时解压目录。
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return _project_root()


def _appdata_dir():
    """返回漫游应用数据目录 (%APPDATA%), 取不到时回落到用户主目录。"""
    return (
        os.environ.get("APPDATA")
        or os.environ.get("LOCALAPPDATA")
        or os.path.expanduser("~")
    )


def user_data_dir():
    """返回用户级配置目录: %APPDATA%\\thione。"""
    return os.path.join(_appdata_dir(), APP_DIR_NAME)


def legacy_user_data_dir():
    """返回更名前的配置目录 %APPDATA%\\thpy, 只作为兼容读取来源。

    @return: 更名前的用户级配置目录路径
    """
    return os.path.join(_appdata_dir(), LEGACY_APP_DIR_NAME)


def user_log_dir():
    """返回用户级日志目录: %LOCALAPPDATA%\\thione\\logs。"""
    local = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if local:
        return os.path.join(local, APP_DIR_NAME, "logs")
    return os.path.join(os.path.expanduser("~"), "." + APP_DIR_NAME, "logs")


def ensure_dir(path):
    """确保目录存在并返回该路径; 失败时抛出 OSError 由调用方处理。"""
    os.makedirs(path, exist_ok=True)
    return path
