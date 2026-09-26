"""进制转换的专属常量"""

PAGE_TITLE = "进制转换"

# 支持的进制, 顺序即两个下拉框里的顺序
BASES = (2, 8, 10, 16)

# 下拉框里的显示名, 直接带上进制对应的数字
BASE_LABELS = {
    2: "二进制 (2)",
    8: "八进制 (8)",
    10: "十进制 (10)",
    16: "十六进制 (16)",
}

# 下拉框的取值, 与 BASES 一一对应
BASE_CHOICES = tuple(BASE_LABELS[base] for base in BASES)

# 打开页面时的默认方向
DEFAULT_SOURCE_BASE = 10
DEFAULT_TARGET_BASE = 16

# 对照表覆盖 0 到 REFERENCE_LIMIT - 1
REFERENCE_LIMIT = 16

# 对照表的列: 列标识 标题 初始宽度
REFERENCE_COLUMNS = (
    ("dec", "十进制", 110),
    ("bin", "二进制", 200),
    ("oct", "八进制", 130),
    ("hex", "十六进制", 150),
)

# 数字框与对照表使用的等宽字号
NUMBER_FONT_SIZE = 12

# 进制下拉框的宽度 (字符数)
BASE_COMBO_WIDTH = 14

# 输入框为空时下方的引导文案
EMPTY_HINT = "输入数字后立即转换, 支持 0b / 0o / 0x 前缀"
