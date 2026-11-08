"""Markdown 改造工具的专属常量"""

PAGE_TITLE = "Markdown改造"
SUBTITLE = "把 Markdown 和本地图片整理成可直接导入博客的 ZIP"

FILE_COLUMNS = (
    {"key": "name", "title": "文件名", "weight": 2, "mono": False},
    {"key": "folder", "title": "所在目录", "weight": 5, "mono": True},
)

EMPTY_TEXT = "还没有添加 Markdown 文件, 点击上方按钮开始"
OUTPUT_HINT = "正文和封面中的本地图片会复制到 ZIP 的 images 目录"
ALLOW_MISSING_HINT = "允许忽略不存在的图片"
FORCE_HINT = "覆盖已有 ZIP"
STATUS_IDLE = "添加 Markdown 文件或文件夹后开始改造"
