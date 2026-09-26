"""按文件内容判断真实音频格式。

源文件的扩展名可能与内容不一致, 例如已经还原过却仍然叫 .ncm 的文件, 因此加密
容器的入口和转换前的判断都要看文件头而不是扩展名。
"""

#: 开头的魔数与对应的格式扩展名
HEAD_SIGNATURES = (
    (b"fLaC", "flac"),
    (b"OggS", "ogg"),
    (b"ID3", "mp3"),
    (b"RIFF", "wav"),
    (b"\xff\xfb", "mp3"),
    (b"\xff\xf3", "mp3"),
    (b"\xff\xf2", "mp3"),
    (b"\xff\xfa", "mp3"),
)
#: MP4 家族的格式标识在第 4 个字节起的 ftyp 盒子里
MP4_SIGNATURE = b"ftyp"
MP4_OFFSET = 4
#: MP4 家族的扩展名
MP4_EXTENSION = "m4a"
#: 判断格式需要的字节数
HEAD_SIZE = 16


def sniff_bytes(head):
    """按文件开头的字节判断真实格式。

    @param head: 文件开头的若干字节
    @return: 格式扩展名; 识别不出来时返回空串
    """
    for signature, extension in HEAD_SIGNATURES:
        if head.startswith(signature):
            return extension
    if head[MP4_OFFSET:MP4_OFFSET + len(MP4_SIGNATURE)] == MP4_SIGNATURE:
        return MP4_EXTENSION
    return ""


def sniff_format(path):
    """读文件开头判断真实格式。

    @param path: 文件路径
    @return: 格式扩展名; 文件读不到或者识别不出来时返回空串
    """
    try:
        with open(path, "rb") as handle:
            head = handle.read(HEAD_SIZE)
    except OSError:
        return ""
    return sniff_bytes(head)
