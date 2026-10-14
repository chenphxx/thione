"""资源管理器风格浏览组件的常量"""

#: 展示方式, 顺序即界面上的排列顺序
VIEWS = ("list", "icons")

#: 列表展示在界面上的按钮文案; 缩略图一侧由档位按钮 小 中 大 表示
LIST_LABEL = "列表"

#: 只需要区分 列表 与 平铺 时, 缩略图一侧的按钮文案
TILE_LABEL = "平铺"

#: 默认展示方式
DEFAULT_VIEW = "icons"

#: 缩略图大小档位, 顺序即界面上的排列顺序 (同时作为缩略图展示的入口)
TIERS = ("small", "medium", "large")

#: 档位在界面上的显示名
TIER_LABELS = {"small": "小", "medium": "中", "large": "大"}

#: 默认档位
DEFAULT_TIER = "medium"

#: 每档的 (缩略图框宽, 缩略图框高, 名称字号)
#: 中档与设计稿一致 (148 x 98), 小档与大档按同一比例缩放
TIER_SPECS = {
    "small": (89, 59, 11),
    "medium": (148, 98, 12),
    "large": (207, 137, 13),
}

#: 缩略图与名称之间的间距
LABEL_GAP = 6

#: 网格里各格子之间的间距, 与设计稿的 gap 一致
CELL_GAP = 12

#: 网格四周留出的空白
GRID_PAD = 0

#: 列表视图的行高与名称字号; 列表视图不随缩略图档位变化
LIST_ROW_HEIGHT = 30
LIST_FONT_SIZE = 13

#: 后端线程读入时的缓存尺寸, 比最大展示尺寸大一圈以便放大档位后仍然清晰
CACHE_SIZE = (512, 512)

#: 主线程每次贴上几张, 避免一次性重建几百张时卡住界面
BATCH = 25

#: 队列轮询间隔 (毫秒)
POLL_MS = 60

#: 内容宽度变化后延迟重排的时间 (毫秒)
RELAYOUT_MS = 40

#: 滚动停下后延迟补载缩略图的时间 (毫秒)
SCROLL_MS = 50

#: 视口上下各多读几行缩略图, 滚动时不至于出现空白
OVERSCAN_ROWS = 2

#: 已解码缩略图的保留张数上限, 超出后按最近使用顺序淘汰
CACHE_LIMIT = 240

#: 右侧预览窗格宽度与底部详细信息窗格高度
PREVIEW_WIDTH = 276
DETAILS_HEIGHT = 88

#: 缩略图右下角标记的内边距与字号
BADGE_INSET = 6
BADGE_FONT_SIZE = 11

#: 预览支持的文件类型, 与 Windows 资源管理器能直接预览的范围一致
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".jfif", ".gif", ".bmp", ".webp",
              ".ico", ".tif", ".tiff"}
TEXT_EXTS = {".txt", ".md", ".log", ".py", ".json", ".xml", ".yml", ".yaml", ".ini", ".cfg", ".conf", ".html", ".css", ".js", ".srt"}
TABLE_EXTS = {".csv", ".tsv", ".xlsx"}
MAX_PREVIEW_ROWS = 100
MAX_PREVIEW_BYTES = 200 * 1024
