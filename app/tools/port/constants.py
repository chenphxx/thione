"""端口与文件占用的专属常量"""

PAGE_TITLE = "端口与占用"

# 两种查询视图, 顺序即分段按钮的顺序
VIEW_PORTS = "ports"
VIEW_FILES = "files"
VIEW_LABELS = ((VIEW_PORTS, "端口占用"), (VIEW_FILES, "文件占用"))

# 表格的列: 列标识 标题 初始宽度 对齐方式
# 宽度之和控制在默认布局的列表宽度以内, 超宽时表格会被裁掉右侧的列
PORT_COLUMNS = (
    ("proto", "协议", 54, "center"),
    ("local", "本地地址", 112, "center"),
    ("port", "端口", 54, "center"),
    ("state", "状态", 74, "center"),
    ("remote", "远程地址", 112, "center"),
    ("pid", "PID", 60, "center"),
    ("process", "进程", 140, "w"),
)

FILE_COLUMNS = (
    ("pid", "PID", 60, "center"),
    ("process", "进程", 146, "w"),
    ("type", "类型", 92, "center"),
    ("path", "路径", 308, "w"),
)

# 进程详情的字段: 键 标题
DETAIL_FIELDS = (
    ("process", "进程"),
    ("path", "路径"),
    ("cmdline", "命令行"),
    ("started", "启动"),
    ("memory", "内存"),
    ("parent", "父进程"),
)

#: 详情里缺省显示的占位符
EMPTY_VALUE = "-"

# 端口输入框宽度 (字符数)
PORT_ENTRY_WIDTH = 10

# 详情栏的初始宽度 (像素), 之后可以由分隔条拖动调整
DETAIL_WIDTH = 330

# 空状态文案: 标题 与 下一步动作
EMPTY_STATES = {
    VIEW_PORTS: ("还没有扫描本机端口", "点击右上角的「扫描本机端口」开始"),
    VIEW_FILES: ("还没有查询文件占用", "在上方选择文件后点击「查询占用」"),
}

# 端口号范围
MIN_PORT = 0
MAX_PORT = 65535
