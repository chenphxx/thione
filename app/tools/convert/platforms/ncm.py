"""网易云音乐 ncm 容器的还原。

ncm 由文件头 元数据 封面 与音频数据组成: 音频密钥存在文件头里, 用固定的 AES-128
密钥加密; 音频本体用密钥调度的密钥流循环异或还原。还原只用本机计算, 不需要联网,
也不需要额外的加密库或者可执行文件。

这里只还原音频本体, 元数据与封面不参与格式转换, 因此直接跳过。
"""

import contextlib
import os
import tempfile

from .. import constants
from . import aes, sniff
from .base import PlatformError, Prepared

#: 文件头魔数
MAGIC = b"CTENFDAM"
#: 文件头魔数之后的间隔字节数
GAP = 2
#: 音频密钥在写入前按字节异或的值
KEY_XOR = 0x64
#: 解密音频密钥用的固定密钥
CORE_KEY = bytes.fromhex("687A4852416D736F356B496E62617857")
#: 密钥明文里位于音频密钥之前的固定前缀
KEY_PREFIX = b"neteasecloudmusic"
#: 元数据之后的间隔字节数 (校验码与一个填充字节)
META_GAP = 5
#: 长度字段占用的字节数
LENGTH_SIZE = 4
#: 密钥流的长度, 也是异或的周期
STREAM_SIZE = 256
#: 每次读写的数据量, 取密钥流长度的整数倍以便对齐
CHUNK_SIZE = STREAM_SIZE * 4096
#: 解密结果写进临时文件时用的前缀
TEMP_PREFIX = "thione-ncm-"


def is_container(path):
    """判断文件是不是 ncm 容器。

    @param path: 文件路径
    @return: 开头是 ncm 魔数时为 True
    """
    try:
        with open(path, "rb") as handle:
            return handle.read(len(MAGIC)) == MAGIC
    except OSError:
        return False


def decrypt(source):
    """把 ncm 还原成常见音频文件。

    还原结果写在系统临时目录里, 由调用方负责删除

    @param source: ncm 文件路径
    @return: Prepared, temporary 恒为 True
    @throws PlatformError: 文件结构损坏, 或者还原出来的不是已知音频
    """
    try:
        with open(source, "rb") as handle:
            stream = _key_stream(_audio_key(handle))
            _skip_to_audio(handle)
            first = _xor(handle.read(CHUNK_SIZE), stream)
            extension = sniff.sniff_bytes(first)
            if not extension:
                raise PlatformError(f"{constants.DECRYPT_FAILED}: "
                                    f"{constants.PLATFORM_NO_AUDIO}")
            path = _write_output(handle, stream, first, extension)
    except OSError as exc:
        raise PlatformError(f"{constants.DECRYPT_FAILED}: {exc}") from exc
    return Prepared(path, extension, True)


def _audio_key(handle):
    """读文件头里的音频密钥。

    @param handle: 已打开的 ncm 文件
    @return: 音频密钥
    @throws PlatformError: 密钥解不开, 或者密钥长度不对
    """
    handle.seek(len(MAGIC) + GAP)
    length = int.from_bytes(handle.read(LENGTH_SIZE), "little")
    blob = bytes(byte ^ KEY_XOR for byte in handle.read(length))
    plain = _unpad(aes.decrypt(CORE_KEY, blob))
    if not plain.startswith(KEY_PREFIX) or len(plain) <= len(KEY_PREFIX):
        raise PlatformError(f"{constants.DECRYPT_FAILED}: "
                            f"{constants.PLATFORM_KEY_BROKEN}")
    return plain[len(KEY_PREFIX):]


def _unpad(data):
    """去掉 AES 分组用的 PKCS#7 填充。

    @param data: 解密后的数据
    @return: 去掉填充的数据; 填充不合法时原样返回
    """
    if not data:
        return data
    padding = data[-1]
    if padding < 1 or padding > aes.BLOCK_SIZE or padding > len(data):
        return data
    if data[-padding:] != bytes([padding]) * padding:
        return data
    return data[:-padding]


def _key_stream(key):
    """按 RC4 的密钥调度算法生成循环密钥流。

    @param key: 音频密钥
    @return: STREAM_SIZE 字节密钥流, 音频的第一个字节从表的第二项开始取用
    """
    box = bytearray(range(STREAM_SIZE))
    position = 0
    for index in range(STREAM_SIZE):
        position = (position + box[index] + key[index % len(key)]) & 0xff
        box[index], box[position] = box[position], box[index]
    table = bytes(box[(box[index] + box[(index + box[index]) & 0xff]) & 0xff]
                  for index in range(STREAM_SIZE))
    return table[1:] + table[:1]


def _skip_to_audio(handle):
    """跳过元数据与封面, 把文件位置移到音频数据。

    @param handle: 已打开的 ncm 文件, 位置在音频密钥之后
    """
    meta_length = int.from_bytes(handle.read(LENGTH_SIZE), "little")
    handle.seek(meta_length + META_GAP, os.SEEK_CUR)
    cover_space = int.from_bytes(handle.read(LENGTH_SIZE), "little")
    cover_size = int.from_bytes(handle.read(LENGTH_SIZE), "little")
    handle.seek(max(cover_space, cover_size), os.SEEK_CUR)


def _write_output(handle, stream, first, extension):
    """把还原出来的音频写进临时文件。

    @param handle: 已打开的 ncm 文件, 位置在第一块之后
    @param stream: 循环密钥流
    @param first: 已经还原出来的第一块音频
    @param extension: 真实格式的扩展名
    @return: 临时文件路径
    """
    descriptor, path = tempfile.mkstemp(prefix=TEMP_PREFIX,
                                        suffix=f".{extension}")
    try:
        with os.fdopen(descriptor, "wb") as target:
            target.write(first)
            while True:
                chunk = handle.read(CHUNK_SIZE)
                if not chunk:
                    break
                target.write(_xor(chunk, stream))
    except OSError:
        # 删除失败也不能盖掉真正的错误原因
        with contextlib.suppress(OSError):
            os.remove(path)
        raise
    return path


def _xor(data, stream):
    """用循环密钥流异或一块数据。

    异或按整数一次算完, 比逐字节循环快得多

    @param data: 音频密文
    @param stream: 循环密钥流
    @return: 明文
    """
    if not data:
        return data
    mask = (stream * (len(data) // len(stream) + 1))[:len(data)]
    return (int.from_bytes(data, "big")
            ^ int.from_bytes(mask, "big")).to_bytes(len(data), "big")
