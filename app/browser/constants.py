"""资源管理器风格浏览组件的常量。

图片查重与批量重命名共用同一套文件视图 (列表与缩略图两种展示方式), 因此
展示方式 档位 缩略图缓存尺寸与可预览的文件类型都在这里定义, 两个页面不各自
维护一份
"""

#: 展示方式, 顺序即界面上的排列顺序
VIEWS = ("list", "icons")

#: 列表展示在界面上的按钮文案; 缩略图一侧由档位按钮 小 中 大 表示
LIST_LABEL = "列表"

#: 默认展示方式
DEFAULT_VIEW = "icons"

#: 缩略图大小档位, 顺序即界面上的排列顺序 (同时作为缩略图展示的入口)
TIERS = ("small", "medium", "large")

#: 档位在界面上的显示名
TIER_LABELS = {"small": "小", "medium": "中", "large": "大"}

#: 默认档位
DEFAULT_TIER = "medium"

#: 每档的 (图标框边长, 名称字号, 单元格内边距)
TIER_SPECS = {
    "small": (64, 8, 6),
    "medium": (128, 9, 8),
    "large": (192, 10, 10),
}

#: 图标与名称之间的间距, 以及网格四周的留白
LABEL_GAP = 6
GRID_PAD = 4

#: 列表视图的图标边长, 行高与名称字号; 列表视图不随缩略图档位变化
LIST_ICON = 20
LIST_ROW_HEIGHT = 26
LIST_FONT_SIZE = 10

#: 后台线程读入时的缓存尺寸, 比最大展示尺寸大一圈以便放大档位后仍然清晰
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
PREVIEW_WIDTH = 360
DETAILS_HEIGHT = 88

#: 预览支持的文件类型, 与 Windows 资源管理器能直接预览的范围一致
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".jfif", ".gif", ".bmp", ".webp",
              ".ico", ".tif", ".tiff"}
TEXT_EXTS = {".txt", ".md", ".log", ".py", ".json", ".xml", ".yml", ".yaml", ".ini", ".cfg", ".conf", ".html", ".css", ".js", ".srt"}
TABLE_EXTS = {".csv", ".tsv", ".xlsx"}
MAX_PREVIEW_ROWS = 100
MAX_PREVIEW_BYTES = 200 * 1024
