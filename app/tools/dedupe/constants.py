"""重复图片查找的专属常量。

PAGE_TITLE 是页面标题, 与外壳的 APP_TITLE (程序名) 不是同一个东西。
"""

PAGE_TITLE = "图片查重"

THUMB_SIZE = (150, 150)
HASH_THRESHOLD = 5
SUPPORTED_IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff', '.webp'}
DUP_SUBFOLDER_NAME = "重复项"
