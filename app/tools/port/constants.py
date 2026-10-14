"""端口与文件占用的专属常量"""

PAGE_TITLE = "端口与占用"

# 顶栏里工具名下方的说明
SUBTITLE = "查看端口被哪个程序占用, 也可以反过来查文件"

# 两种查询视图, 顺序即分段控件的顺序
VIEW_PORTS = "ports"
VIEW_FILES = "files"
VIEW_LABELS = ((VIEW_PORTS, "端口"), (VIEW_FILES, "文件"))

# 占用列表的列: 键 标题 权重 对齐 等宽 颜色
# 列与设计稿一致: 协议 本地地址 状态 PID 程序
PORT_COLUMNS = (
    {"key": "proto", "title": "协议", "weight": 0.7},
    {"key": "local", "title": "本地地址", "weight": 2.4, "mono": True},
    {"key": "state", "title": "状态", "weight": 2.1},
    {"key": "pid", "title": "PID", "weight": 0.9, "mono": True},
    {"key": "process", "title": "程序", "weight": 4.0},
)

# 占用文件的进程列表的列
FILE_COLUMNS = (
    {"key": "pid", "title": "PID", "weight": 1.0, "mono": True},
    {"key": "process", "title": "进程", "weight": 2.4},
    {"key": "type", "title": "类型", "weight": 1.8},
    {"key": "path", "title": "路径", "weight": 6.0},
)

# 进程详情的字段: 键 标题
# 前 5 项与设计稿一致, 命令行与父进程是设计稿没有画到的既有信息
DETAIL_FIELDS = (
    ("process", "进程名"),
    ("pid", "PID"),
    ("started", "启动时间"),
    ("memory", "内存"),
    ("path", "路径"),
    ("cmdline", "命令行"),
    ("parent", "父进程"),
)

#: 详情里缺省显示的占位符
EMPTY_VALUE = "-"

# 端口输入框宽度 (像素)
PORT_ENTRY_WIDTH = 96

# 详情栏的宽度 (像素), 与设计稿一致; 拖动分隔条时可在这个范围内调整
DETAIL_WIDTH = 304
DETAIL_MIN_WIDTH = 240
DETAIL_MAX_WIDTH = 560

# 详情字段标签列的宽度 (像素)
DETAIL_LABEL_WIDTH = 74

# 空状态文案: 标题 与 下一步动作
EMPTY_STATES = {
    VIEW_PORTS: ("还没有扫描本机端口", "点击右上角的'扫描本机端口'开始"),
    VIEW_FILES: ("还没有查询文件占用", "在上方选择文件后点击'查询占用'"),
}

# 端口号范围
MIN_PORT = 0
MAX_PORT = 65535
