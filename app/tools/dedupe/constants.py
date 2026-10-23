"""重复图片查找的专属常量"""

from ...dpi import scale

PAGE_TITLE = "图片查重"

# 顶栏里工具名下方的说明
SUBTITLE = "扫描文件夹, 找出视觉上重复的图片"

THUMB_SIZE = (scale(150), scale(150))
HASH_THRESHOLD = 5
SUPPORTED_IMAGE_EXTS = {'.jpg', '.jpeg', '.jfif', '.png', '.bmp', '.gif',
                        '.tiff', '.webp'}
DUP_SUBFOLDER_NAME = "重复项"
