"""进制转换的数字解析与格式化。

约定与常见计算器一致: 输入可以带正负号, 可以带与所选进制匹配的 0b / 0o / 0x
前缀; 空格 逗号与下划线只作为分隔符被忽略, 全角字符先按 NFKC 归一化成半角
因此从别处复制过来的数字可以直接粘贴。

这里只依赖标准库, 不引入 tkinter, 页面只负责取值与展示。
"""

import unicodedata

# 各进制可用的数字字符, 十六进制统一用大写
DIGITS = {
    2: "01",
    8: "01234567",
    10: "0123456789",
    16: "0123456789ABCDEF",
}

# 错误消息里用到的进制名称与数字写法
BASE_NAMES = {2: "二进制", 8: "八进制", 10: "十进制", 16: "十六进制"}
DIGIT_HINTS = {2: "0 和 1", 8: "0-7", 10: "0-9", 16: "0-9 与 A-F"}

# 只有与所选进制匹配时才允许出现的前缀
PREFIXES = {2: "0b", 8: "0o", 16: "0x"}

# format() 对应的进制字符, 十六进制用大写
FORMAT_CODES = {2: "b", 8: "o", 10: "d", 16: "X"}

# 解析前忽略的分隔符
SEPARATORS = "_, "


class ConvertError(ValueError):
    """输入无法解析为该进制的数字, 消息可以直接展示给用户。"""


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
    @param base: 2 / 8 / 10 / 16 之一
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
    invalid = next((char for char in cleaned.upper()
                    if char not in DIGITS[base]), None)
    if invalid is not None:
        raise ConvertError(
            f"{BASE_NAMES[base]}只能使用 {DIGIT_HINTS[base]}, 无法识别 {invalid}"
        )
    return sign * int(cleaned, base)


def format_number(value, base):
    """把整数按 base 输出成字符串。

    @param value: 待输出的整数
    @param base: 2 / 8 / 10 / 16 之一
    @return: 负数带负号, 十六进制大写
    """
    if value < 0:
        return "-" + format_number(-value, base)
    return format(value, FORMAT_CODES[base])


def convert(text, source_base, target_base):
    """按输入进制解析后, 再按目标进制输出。

    @param text: 界面输入框里的原始内容
    @param source_base: 输入的进制
    @param target_base: 输出的进制
    @return: 目标进制的字符串, 输入为空时返回空串
    @throws ConvertError: 输入不是该进制的合法数字
    """
    if not normalize(text):
        return ""
    return format_number(parse_number(text, source_base), target_base)


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
