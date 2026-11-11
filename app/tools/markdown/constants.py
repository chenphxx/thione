"""Markdown 改造工具的专属常量"""

PAGE_TITLE = "Markdown改造"
SUBTITLE = "把 Markdown 和本地图片整理成导入包或原始目录文档"

DEFAULT_IMAGE_FOLDER = "assets/images"

FILE_COLUMNS = (
    {"key": "name", "title": "文件名", "weight": 2, "mono": False},
    {"key": "folder", "title": "所在目录", "weight": 5, "mono": True},
)

EMPTY_TEXT = "还没有添加 Markdown 文件, 点击上方按钮开始"
GENERATE_ZIP_HINT = "生成压缩包"
ZIP_IMAGE_FOLDER_HINT = "图片目录使用 ZIP 内的相对路径"
DOCUMENT_IMAGE_FOLDER_HINT = "图片目录相对每篇 Markdown 所在目录"
ZIP_OUTPUT_HINT = "本地图片会复制到指定目录并改写为相对路径"
DOCUMENT_OUTPUT_HINT = "输出到原目录, 文件名追加 -改造后"
ALLOW_MISSING_HINT = "允许忽略不存在的图片"
ZIP_FORCE_HINT = "覆盖已有 ZIP"
DOCUMENT_FORCE_HINT = "覆盖已有文件"
STATUS_IDLE = "添加 Markdown 文件或文件夹后开始改造"
