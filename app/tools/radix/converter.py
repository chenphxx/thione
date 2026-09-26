"""进制转换的数字解析与格式化。

约定与常见计算器一致: 输入可以带正负号, 可以带与所选进制匹配的 0b / 0o / 0x
前缀; 空格 逗号与下划线只作为分隔符被忽略, 全角字符先按 NFKC 归一化成半角
因此从别处复制过来的数字可以直接粘贴。

这里只依赖标准库, 不引入 tkinter, 页面只负责取值与展示。
"""

import unicodedata

# 各进制可用的数字字符, 超过十的部分统一用大写字母
DIGITS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

#: 支持的最小与最大进制, 与 int() 的上限一致
MIN_BASE = 2
MAX_BASE = 36

# 只有与所选进制匹配时才允许出现的前缀
PREFIXES = {2: "0b", 8: "0o", 16: "0x"}

# format() 直接支持的进制, 这几个走内置的快速路径
FORMAT_CODES = {2: "b", 8: "o", 10: "d", 16: "X"}

# 解析前忽略的分隔符
SEPARATORS = "_, "

#: 中文数字, 用于拼出进制名
_CN_DIGITS = "零一二三四五六七八九"


class ConvertError(ValueError):
    """输入无法解析为该进制的数字, 消息可以直接展示给用户。"""


def base_name(base):
    """取进制的名字。

    @param base: 2 到 36 之间的进制
    @return: 例如 2 对应 二进制, 16 对应 十六进制, 36 对应 三十六进制
    """
    if base < 10:
        return f"{_CN_DIGITS[base]}进制"
    tens, ones = divmod(base, 10)
    name = "" if tens == 1 else _CN_DIGITS[tens]
    name += "十"
    if ones:
        name += _CN_DIGITS[ones]
    return name + "进制"


def digit_hint(base):
    """描述该进制可以使用的数字字符, 用于错误消息。

    @param base: 2 到 36 之间的进制
    @return: 例如 16 对应 0-9 与 A-F
    """
    if base == 2:
        return "0 和 1"
    if base <= 10:
        return f"0-{base - 1}"
    return f"0-9 与 A-{DIGITS[base - 1]}"


def normalize(text):
    """把输入整理成只含符号 前缀与数字字符的形式。

    @param text: 界面输入框里的原始内容
    @return: 去掉全角字符与分隔符之后的字符串
    """
    cleaned = unicodedata.normalize("NFKC", text)
    for char in SEPARATORS:
        cleaned = cleaned.replace(char, "")
    return cleaned


def parse_number(text, base):
    """把输入按 base 解析成整数。

    @param text: 界面输入框里的原始内容
    @param base: 2 到 36 之间的进制
    @return: 解析出的整数, 负数带负号
    @throws ConvertError: 输入为空或者含有该进制不认识的字符
    """
    cleaned = normalize(text)
    sign = 1
    if cleaned[:1] in ("+", "-"):
        sign = -1 if cleaned[0] == "-" else 1
        cleaned = cleaned[1:]
    prefix = PREFIXES.get(base)
    if prefix is not None and cleaned[:2].lower() == prefix:
        cleaned = cleaned[2:]
    if not cleaned:
        raise ConvertError("请输入要转换的数字")
    allowed = DIGITS[:base]
    invalid = next((char for char in cleaned.upper() if char not in allowed),
                   None)
    if invalid is not None:
        raise ConvertError(
            f"{base_name(base)}只能使用 {digit_hint(base)}, 无法识别 {invalid}"
        )
    return sign * int(cleaned, base)


def format_number(value, base):
    """把整数按 base 输出成字符串。

    @param value: 待输出的整数
    @param base: 2 到 36 之间的进制
    @return: 负数带负号, 十以上的进制用大写字母
    """
    if value < 0:
        return "-" + format_number(-value, base)
    code = FORMAT_CODES.get(base)
    if code is not None:
        return format(value, code)
    # 其余进制没有内置的格式化, 用短除法逐位取余
    digits = []
    while value:
        value, remainder = divmod(value, base)
        digits.append(DIGITS[remainder])
    return "".join(reversed(digits)) if digits else "0"


def convert(text, source_base, target_base):
    """按输入进制解析后, 再按目标进制输出。

    @param text: 界面输入框里的原始内容
    @param source_base: 输入的进制
    @param target_base: 输出的进制
    @return: 目标进制的字符串, 输入为空时返回空串
    @throws ConvertError: 输入不是该进制的合法数字
    """
    return convert_many(text, source_base, (target_base,))[0]


def convert_many(text, source_base, target_bases):
    """解析一次, 同时给出多个进制下的结果。

    @param text: 界面输入框里的原始内容
    @param source_base: 输入的进制
    @param target_bases: 需要输出的进制序列
    @return: 与 target_bases 一一对应的列表, 输入为空时每项都是空串
    @throws ConvertError: 输入不是该进制的合法数字
    """
    if not normalize(text):
        return ["" for _base in target_bases]
    value = parse_number(text, source_base)
    return [format_number(value, base) for base in target_bases]


def reference_rows(limit):
    """生成对照表的数据行, 每行的四列与 REFERENCE_COLUMNS 对应。

    @param limit: 生成 [0, limit) 范围内的整数
    @return: 每行一个 (十进制, 二进制, 八进制, 十六进制) 元组的列表
    """
    return [
        (str(value), format_number(value, 2), format_number(value, 8),
         format_number(value, 16))
        for value in range(limit)
    ]
