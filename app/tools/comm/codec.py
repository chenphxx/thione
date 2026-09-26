"""收发数据的编解码: 展示格式化与发送内容解析

展示侧把字节流按 HEX DEC OCT BIN 文本四种方式格式化 文本与自动识别走增量解码器
因此多字节字符被拆到两个数据包时也不会显示成乱码 发送侧把输入框里的文本解析成
字节 解析失败会给出能直接展示给用户的原因
"""

import codecs

from .constants import (
    AUTO_TEXT_RATIO,
    BYTES_PER_LINE,
    DISPLAY_AUTO,
    DISPLAY_BIN,
    DISPLAY_DEC,
    DISPLAY_HEX,
    DISPLAY_OCT,
    DISPLAY_TEXT,
    SEND_BIN,
    SEND_DEC,
    SEND_HEX,
    SEND_OCT,
    SEND_TEXT,
)

#: 解析发送内容时当作分隔符的字符
_SEPARATORS = " \t\r\n,;|"

_BASE_BY_MODE = {
    SEND_HEX: 16,
    SEND_DEC: 10,
    SEND_OCT: 8,
    SEND_BIN: 2,
}

#: 进制到中文说明, 用于拼解析失败的原因
_BASE_LABEL = {
    16: "十六进制",
    10: "十进制",
    8: "八进制",
    2: "二进制",
}

#: 展示模式对应的进制, 0 表示文本
_DISPLAY_BASE = {
    DISPLAY_HEX: 16,
    DISPLAY_DEC: 10,
    DISPLAY_OCT: 8,
    DISPLAY_BIN: 2,
}

_DIGITS = {
    16: "0123456789abcdefABCDEF",
    10: "0123456789",
    8: "01234567",
    2: "01",
}


class ParseError(ValueError):
    """发送内容无法解析成字节"""


def parse_payload(text, mode, encoding):
    """把输入框里的内容解析成要发送的字节

    @param text: 输入框内容
    @param mode: 发送模式, 见 SEND_MODES
    @param encoding: 文本模式使用的编码名
    @return: 字节串
    @throws ParseError: 内容与模式不匹配时
    """
    if mode == SEND_TEXT:
        if not text:
            return b""
        try:
            return text.encode(encoding)
        except (UnicodeEncodeError, LookupError) as exc:
            raise ParseError("当前编码无法表示输入的内容: %s" % exc) from exc
    base = _BASE_BY_MODE.get(mode)
    if base is None:
        raise ParseError("未知的发送模式: %s" % mode)
    return _parse_digits(text, base)


def _parse_digits(text, base):
    """按进制解析以分隔符隔开的数据

    @param text: 输入内容
    @param base: 2 8 10 16
    @return: 字节串
    @throws ParseError: 出现非本进制的字符或者数值超出 0 到 255 时
    """
    label = _BASE_LABEL[base]
    body = text.strip()
    if not body:
        return b""
    if base == 16:
        body = _strip_hex_prefix(body)
        body = "".join(_SEPARATORS_FREE(body))
        if len(body) % 2:
            raise ParseError("十六进制需要成对出现, 当前有 %d 个字符" % len(body))
        tokens = [body[index:index + 2] for index in range(0, len(body), 2)]
    else:
        tokens = [token for token in _split(body) if token]
        if base == 2 and len(tokens) == 1 and len(tokens[0]) > 8:
            body = tokens[0]
            if len(body) % 8:
                raise ParseError("二进制需要 8 位一组, 当前有 %d 位" % len(body))
            tokens = [body[index:index + 8] for index in range(0, len(body), 8)]

    values = []
    for index, token in enumerate(tokens, 1):
        digits = _check_digits(token, base)
        value = int(digits, base)
        if value > 255:
            raise ParseError("第 %d 个数据 %s 超出 0 到 255" % (index, digits))
        values.append(value)
    return bytes(values)


def _check_digits(token, base):
    """确认这一段只包含本进制的字符, 并去掉常见的进制前缀

    @param token: 一段数据
    @param base: 2 8 10 16
    @return: 去掉前缀后的数字文本
    @throws ParseError: 出现本进制之外的字符时
    """
    digits = token
    lowered = digits.lower()
    if base == 16 and lowered.startswith("0x"):
        digits = digits[2:]
    elif base == 8 and lowered.startswith("0o"):
        digits = digits[2:]
    elif base == 2 and lowered.startswith("0b"):
        digits = digits[2:]
    if not digits:
        raise ParseError("有一段数据是空的")
    allowed = _DIGITS[base]
    for char in digits:
        if char not in allowed:
            raise ParseError("字符 %s 不属于%s" % (char, _BASE_LABEL[base]))
    return digits


def _split(text):
    """按分隔符切开, 兼容连续分隔符

    @param text: 输入内容
    @return: 分段列表, 空段已经去掉
    """
    parts = []
    current = []
    for char in text:
        if char in _SEPARATORS:
            if current:
                parts.append("".join(current))
                current = []
        else:
            current.append(char)
    if current:
        parts.append("".join(current))
    return parts


def _strip_hex_prefix(text):
    """把 0x 前缀当作分隔符处理, 便于直接粘贴 0xAA 0xBB 形式的报文

    @param text: 输入内容
    @return: 去掉前缀后的内容
    """
    lowered = text.lower()
    if "0x" not in lowered:
        return text
    result = []
    index = 0
    while index < len(text):
        if lowered.startswith("0x", index):
            result.append(" ")
            index += 2
            continue
        result.append(text[index])
        index += 1
    return "".join(result)


def _SEPARATORS_FREE(text):
    """去掉十六进制输入里的分隔符, 只留下数字

    @param text: 输入内容
    @return: 逐个数字组成的迭代
    """
    for char in text:
        if char not in _SEPARATORS:
            yield char


def format_bytes(data, mode, encoding):
    """把一段字节格式化成可以展示的文本

    @param data: 字节串
    @param mode: 展示模式, 见 DISPLAY_MODES
    @param encoding: 文本模式使用的编码名
    @return: 展示文本
    """
    if not data:
        return ""
    base = _DISPLAY_BASE.get(mode)
    if base is None:
        return _decode(data, encoding)
    return _format_base(data, base)


def _decode(data, encoding):
    """按编码解码, 编码名不合法或者字节无效时用替换字符兜底

    @param data: 字节串
    @param encoding: 编码名
    @return: 文本
    """
    try:
        return data.decode(encoding, errors="replace")
    except LookupError:
        return data.decode("utf-8", errors="replace")


def _format_base(data, base):
    """按进制把字节排成每行 BYTES_PER_LINE 个

    @param data: 字节串
    @param base: 2 8 10 16
    @return: 展示文本, 末尾不带换行
    """
    width = {16: 2, 10: 3, 8: 3, 2: 8}[base]
    lines = []
    for start in range(0, len(data), BYTES_PER_LINE):
        chunk = data[start:start + BYTES_PER_LINE]
        lines.append(" ".join(_token(value, base, width) for value in chunk))
    return "\n".join(lines)


def _token(value, base, width):
    """单个字节在当前进制下的展示文本

    @param value: 0 到 255
    @param base: 2 8 10 16
    @param width: 对齐用的最小宽度
    @return: 展示文本
    """
    if base == 16:
        return "%02X" % value
    if base == 10:
        return "%3d" % value
    if base == 8:
        return "%3o" % value
    return format(value, "08b")


def looks_like_text(data, encoding):
    """判断这段字节更像文本还是二进制

    判定依据是能否按编码解码, 以及可打印字节的占比

    @param data: 字节串
    @param encoding: 编码名
    @return: True 表示按文本展示
    """
    if not data:
        return True
    printable = 0
    for value in data:
        if value in (9, 10, 13) or 32 <= value < 127 or value >= 128:
            printable += 1
    if printable / len(data) < AUTO_TEXT_RATIO:
        return False
    try:
        text = data.decode(encoding)
    except (UnicodeDecodeError, LookupError):
        return False
    return not any(ord(char) < 32 and char not in "\t\r\n" for char in text)


class StreamDecoder:
    """把连续到达的数据包转成展示文本

    文本模式与自动识别模式会缓存不完整的字符, 因此一个汉字被拆到两个包里也不会
    显示成乱码; HEX DEC OCT BIN 四种模式按 BYTES_PER_LINE 对齐换行, 行内位置
    在多次数据包之间保持连续

    @brief 接收视图的增量格式化器
    """

    def __init__(self, mode, encoding):
        self.mode = mode
        self.encoding = encoding
        self._pending = bytearray()
        self._column = 0
        self._decoder = None

    def set_mode(self, mode):
        """切换展示模式, 未消费的缓存按新格式重新排版

        @param mode: 展示模式
        """
        if mode == self.mode:
            return None
        leftover = bytes(self._pending)
        self.mode = mode
        self._pending.clear()
        self._column = 0
        return self._format(leftover) if leftover else None

    def set_encoding(self, encoding):
        """切换编码, 缓存里的字节按新编码重新解码

        @param encoding: 编码名
        """
        if encoding == self.encoding:
            return None
        self.encoding = encoding
        self._decoder = None
        leftover = bytes(self._pending)
        self._pending.clear()
        return self._format(leftover) if leftover else None

    def reset_line(self):
        """外部往视图里写过别的文字后调用, 让下一个数据包从新的一行开始"""
        self._column = 0

    def reset(self):
        """清屏时调用, 丢掉没有解码完的缓存与解码器状态"""
        self._pending.clear()
        self._column = 0
        self._decoder = None

    def feed(self, data):
        """喂入一段数据

        @param data: 字节串
        @return: 要追加到视图的文本, 没有可展示内容时为空串
        """
        if not data:
            return ""
        self._pending.extend(data)
        if self.mode in (DISPLAY_TEXT, DISPLAY_AUTO):
            return self._feed_text()
        return self._format(bytes(self._pending), consume=True)

    def flush(self):
        """把缓存里剩下的内容按当前模式展示出来

        @return: 要追加到视图的文本
        """
        if not self._pending:
            return ""
        return self._format(bytes(self._pending), consume=True)

    def _feed_text(self):
        """文本与自动识别模式的取词与解码"""
        if self.mode == DISPLAY_AUTO:
            if len(self._pending) < 4 and not self._is_break():
                return ""
            if not looks_like_text(bytes(self._pending), self.encoding):
                return self._format(bytes(self._pending), consume=True)
        data = bytes(self._pending)
        self._pending.clear()
        return self._decode_stream(data)

    def _is_break(self):
        """自动识别模式下, 小段落里已经出现换行就可以先判定

        @return: 是否需要立即判定
        """
        return b"\n" in self._pending or b"\r" in self._pending

    def _decode_stream(self, data):
        """用增量解码器解码, 保证不完整的多字节字符留在缓存里

        解码器实例缓存在对象上, 因此被拆成两半的字符会在下一个数据包到达时补齐

        @param data: 字节串
        @return: 解码文本
        """
        if self._decoder is None:
            try:
                self._decoder = codecs.getincrementaldecoder(self.encoding)(
                    errors="replace")
            except LookupError:
                self._decoder = codecs.getincrementaldecoder("utf-8")(
                    errors="replace")
        return self._decoder.decode(data, False)

    def _format(self, data, consume=False):
        """按进制格式化, 行内位置跨数据包连续

        @param data: 字节串
        @param consume: True 表示这段数据已经取走
        @return: 展示文本
        """
        if consume:
            self._pending.clear()
        if not data:
            return ""
        base = _DISPLAY_BASE.get(self.mode)
        if base is None and self.mode == DISPLAY_AUTO:
            # 自动识别判定为二进制时按 HEX 展示
            base = 16
        if base is None:
            return self._decode_stream(data)
        parts = []
        for value in data:
            if self._column == 0 and parts:
                parts.append("\n")
            elif self._column:
                parts.append(" ")
            parts.append(_token(value, base, 0))
            self._column = (self._column + 1) % BYTES_PER_LINE
        text = "".join(parts)
        return text
