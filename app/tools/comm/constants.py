"""串口助手的专属常量"""

PAGE_TITLE = "串口助手"

SUBTITLE = "通过串口或者网络收发数据, 支持 TCP Client TCP Server 与 UDP"

#: 接收区可以选择的展示模式: 自动识别会按数据内容在文本与 HEX 之间切换
DISPLAY_AUTO = "auto"
DISPLAY_TEXT = "text"
DISPLAY_HEX = "hex"
DISPLAY_DEC = "dec"
DISPLAY_OCT = "oct"
DISPLAY_BIN = "bin"
DISPLAY_MODES = (
    (DISPLAY_AUTO, "自动识别"),
    (DISPLAY_TEXT, "文本"),
    (DISPLAY_HEX, "HEX"),
    (DISPLAY_DEC, "DEC"),
    (DISPLAY_OCT, "OCT"),
    (DISPLAY_BIN, "BIN"),
)

#: 发送区可以选择的模式, 没有自动识别
SEND_TEXT = "text"
SEND_HEX = "hex"
SEND_DEC = "dec"
SEND_OCT = "oct"
SEND_BIN = "bin"
SEND_MODES = (
    (SEND_TEXT, "文本"),
    (SEND_HEX, "HEX"),
    (SEND_DEC, "DEC"),
    (SEND_OCT, "OCT"),
    (SEND_BIN, "BIN"),
)
DEFAULT_SEND_MODE = SEND_TEXT

#: 文本模式下可以选择的编码, 与下拉框顺序一致
ENCODINGS = ("UTF-8", "GBK")
DEFAULT_ENCODING = "UTF-8"

#: 每行展示多少个字节, HEX DEC OCT BIN 四种模式按此换行
BYTES_PER_LINE = 16

#: 自动识别判定为文本的比例下限: 可打印字节占比不低于该值时按文本展示
AUTO_TEXT_RATIO = 0.85

#: 串口的常用取值, 下拉框可编辑因此也能手填其它值
BAUD_RATES = (1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600)
DEFAULT_BAUD = 9600
PARITY_LABELS = ("NONE", "EVEN", "ODD", "MARK", "SPACE")
DEFAULT_PARITY = "NONE"
DATA_BITS = (5, 6, 7, 8)
DEFAULT_DATA_BITS = 8
STOP_BITS = ("1", "1.5", "2")
DEFAULT_STOP_BITS = "1"

#: 网络协议: 键 显示名
PROTO_TCP_CLIENT = "tcp_client"
PROTO_TCP_SERVER = "tcp_server"
PROTO_UDP = "udp"
PROTOCOLS = (
    (PROTO_TCP_CLIENT, "TCP Client"),
    (PROTO_TCP_SERVER, "TCP Server"),
    (PROTO_UDP, "UDP"),
)
DEFAULT_PROTO = PROTO_TCP_CLIENT

#: 发送后缀的预设, 自定义一项按当前发送模式解析输入框内容
SUFFIX_NONE = "none"
SUFFIX_CRLF = "crlf"
SUFFIX_LF = "lf"
SUFFIX_CR = "cr"
SUFFIX_CUSTOM = "custom"
SUFFIX_CHOICES = (
    (SUFFIX_NONE, "无"),
    (SUFFIX_CRLF, "CRLF"),
    (SUFFIX_LF, "LF"),
    (SUFFIX_CR, "CR"),
    (SUFFIX_CUSTOM, "自定义"),
)
SUFFIX_BYTES = {
    SUFFIX_NONE: b"",
    SUFFIX_CRLF: b"\r\n",
    SUFFIX_LF: b"\n",
    SUFFIX_CR: b"\r",
}
DEFAULT_SUFFIX = SUFFIX_NONE

#: 循环发送的默认间隔与下限 (毫秒), 下限用来避免把界面拖死
DEFAULT_INTERVAL_MS = 1000
MIN_INTERVAL_MS = 10

#: 接收视图里最多保留的字符数, 超出后从头部丢弃, 避免长时间运行吃满内存
MAX_VIEW_CHARS = 400000

#: 后台线程收尾的等待时间 (秒)
CLOSE_JOIN_TIMEOUT = 2.0
#: TCP 连接测试与 UDP 绑定测试的超时 (秒)
CONNECT_TIMEOUT = 2.0

#: 配置列里提示文字的折行宽度 (像素)
CONTROL_HINT_WRAP = 230

#: 控件宽度 (字符数): 配置区一行要放下当前链路的全部控件, 收发卡的配置列要放下
#: 每条控制项, 因此取值按实际内容压到最小, 串口号按常见名称取 17 个字符
PORT_COMBO_WIDTH = 17
BAUD_COMBO_WIDTH = 7
PARITY_COMBO_WIDTH = 8
BITS_COMBO_WIDTH = 3
HOST_ENTRY_WIDTH = 11
PORT_ENTRY_WIDTH = 5
IP_COMBO_WIDTH = 11
MODE_COMBO_WIDTH = 7
ENCODING_COMBO_WIDTH = 6
SUFFIX_COMBO_WIDTH = 5
SUFFIX_TEXT_WIDTH = 6
INTERVAL_ENTRY_WIDTH = 5
PROTO_COMBO_WIDTH = 10
TARGET_COMBO_WIDTH = 14

#: 页面轮询后台消息的间隔 (毫秒)
POLL_INTERVAL_MS = 60

#: 串口列表里对可用状态的说明
PORT_AVAILABLE = "可用"
PORT_BUSY = "占用中"
PORT_IN_USE_BY_US = "本程序使用中"

#: 配置检查的结果前缀
CHECK_OK = "配置可用"
CHECK_FAIL = "配置有问题"


#: 四个数据面板的标题
PANEL_SERIAL_RECEIVE = "串口接收"
PANEL_SERIAL_SEND = "串口发送"
PANEL_NET_RECEIVE = "网络接收"
PANEL_NET_SEND = "网络发送"

#: 页面内部区分两条链路的标识, 同时用来归类会话回调
LINK_SERIAL = "serial"
LINK_NET = "net"

#: 顶部切换当前链路的分段按钮
LINK_CHOICES = (
    (LINK_SERIAL, "串口通信"),
    (LINK_NET, "网络通信"),
)

#: 配置区的按钮文字
BTN_OPEN_PORT = "打开串口"
BTN_CLOSE_PORT = "关闭串口"
BTN_REFRESH_PORTS = "刷新串口"
BTN_LOAD_CONFIG = "载入配置"
BTN_CLOSE_NET = "关闭网络"
BTN_TEST_CONNECT = "测试连接"

#: 本机地址下拉框里代表所有网卡的取值
ALL_ADDRESSES = "0.0.0.0"

#: 协议切换时配置区下方的说明
PROTO_HINTS = {
    PROTO_TCP_CLIENT: "TCP Client: 目的地址与端口是连接目标, 本机地址与接收端口可以不填",
    PROTO_TCP_SERVER: "TCP Server: 本机地址与接收端口是监听地址与端口",
    PROTO_UDP: "UDP: 目的地址与端口必填, 接收端口与发送端口可以留空由系统分配",
}

#: 配置区下方的常驻提示, 按链路区分
HINT_SERIAL_IDLE = "选好串口与参数后点「打开串口」"
HINT_NET_IDLE = "填好地址与端口后点「载入配置」"
HINT_NO_PORTS = "没有检测到串口, 插好设备后点「刷新串口」"
HINT_NEED_PORT = "先选择要打开的串口"

#: 单次轮询最多处理多少条后台消息, 数据量大时也要留出刷新界面的时间
MAX_MESSAGES_PER_POLL = 400
