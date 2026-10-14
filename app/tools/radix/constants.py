"""进制转换的专属常量"""

from .converter import MAX_BASE, MIN_BASE, base_name

PAGE_TITLE = "进制转换"

# 支持的进制, 顺序即两个下拉框里的顺序
BASES = tuple(range(MIN_BASE, MAX_BASE + 1))

# 结果区固定给出的常用进制, 顺序即展示顺序
COMMON_BASES = (2, 8, 10, 16)

# 下拉框里的显示名, 直接带上进制对应的中文名与数字
BASE_LABELS = {base: f"{base_name(base)} ({base})" for base in BASES}

# 下拉框的取值, 与 BASES 一一对应
BASE_CHOICES = tuple(BASE_LABELS[base] for base in BASES)

# 结果区里常用进制的行标题
COMMON_LABELS = {base: base_name(base) for base in COMMON_BASES}

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

# 对照表把 0 到 REFERENCE_LIMIT - 1 分成左右两半并排展示
REFERENCE_HALVES = 2

# 输入框为空时显示的占位文案
EMPTY_HINT = "输入数字"

# 状态栏默认给出的能力说明
STATUS_HINT = "支持负数与超大整数"

# 页面标题下的说明
SUBTITLE = "输入数字即可转换, 结果随输入与进制实时刷新"
