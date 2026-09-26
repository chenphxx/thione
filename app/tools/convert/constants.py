"""文件格式转换的专属常量"""

PAGE_TITLE = "文件格式转换"

# 可选的输出格式: 扩展名 显示名 有损编码器 是否有损码率可选
# 无损选项的编码器见 LOSSLESS_QUALITY; 一期只做音频, 之后加视频时在这里补一组格式
AUDIO_FORMATS = (
    ("mp3", "MP3", "libmp3lame", True),
    ("wav", "WAV", "pcm_s16le", False),
    ("flac", "FLAC", "flac", False),
    ("m4a", "M4A", "aac", True),
    ("ogg", "OGG", "libvorbis", True),
    ("opus", "OPUS", "libopus", True),
    ("wma", "WMA", "wmav2", True),
    ("aiff", "AIFF", "pcm_s16be", False),
)

#: 输出格式的显示名, 与扩展名一一对应
FORMAT_LABELS = {ext: label for ext, label, _codec, _by_rate in AUDIO_FORMATS}
#: 扩展名到有损编码时使用的 ffmpeg 音频编码器
FORMAT_CODECS = {ext: codec for ext, _label, codec, _by_rate in AUDIO_FORMATS}
#: 下拉框的取值, 顺序与 AUDIO_FORMATS 一致
FORMAT_CHOICES = tuple(FORMAT_LABELS[ext]
                       for ext, _label, _codec, _by_rate in AUDIO_FORMATS)
#: 只有无损编码的容器: 音质下拉框里只有无损一项, 没有码率可选
LOSSLESS_ONLY_FORMATS = frozenset(ext for ext, _label, _codec, by_rate in AUDIO_FORMATS
                                  if not by_rate)

DEFAULT_FORMAT = "mp3"

# 有损编码的码率档 (kbps), 所有支持有损编码的格式共用同一套
BITRATES = (128, 192, 256, 320)
BITRATE_LABELS = tuple(f"{rate} kbps" for rate in BITRATES)
DEFAULT_BITRATE = 192

#: 容器里的无损编码器与音质显示名
#  无损选项排在音质下拉框最前面, 不传码率; MP3 OPUS WMA 只有有损编码, 不在这里
LOSSLESS_QUALITY = {
    "wav": ("无损 (PCM)", "pcm_s16le"),
    "flac": ("无损 (FLAC)", "flac"),
    "aiff": ("无损 (PCM)", "pcm_s16be"),
    "m4a": ("无损 (ALAC)", "alac"),
    "ogg": ("无损 (FLAC)", "flac"),
}

#: 自动码率的标记: 用 每声道上限 x 源文件声道数 算出编码器能给出的最高码率
AUTO_BITRATE = -1

# 最高音质档: 显示名 额外编码参数 是否按声道数自动算码率
# 有损格式的档位里排在最前; 参数取该编码器质量优先的那一档
# opus 的编码复杂度默认就是最高, 因此不需要额外参数, 只把码率提到每声道上限
TOP_QUALITY = {
    "mp3": ("最高音质 (自动)", ("-b:a", "320k", "-compression_level", "0"), False),
    "m4a": ("最高音质 (自动)", ("-b:a", "320k"), False),
    "ogg": ("最高音质 (自动)", ("-q:a", "10"), False),
    "opus": ("最高音质 (自动)", (), True),
    "wma": ("最高音质 (自动)", ("-b:a", "320k"), False),
}

#: 编码器每声道的码率上限 (kbps): 手动选的码率超过上限时按源文件声道数下调
#  opus 单声道 256 立体声 512, vorbis 单声道 224 立体声 448; 最高音质档按同一张表换算
BITRATE_LIMIT_PER_CHANNEL = {"libopus": 256, "libvorbis": 224}

#: 音质下拉框后面的说明, 解释可选项为什么与别的格式不同
#  文案要短: 最小窗口宽度下说明标签只有一百来像素
QUALITY_HINTS = {
    "mp3": "需无损请选 FLAC",
    "opus": "需无损请选 FLAC",
    "wma": "需无损请选 FLAC",
    "m4a": "可选无损 (ALAC)",
    "ogg": "可选无损 (FLAC)",
    "wav": "按源采样率编码",
    "flac": "按源采样率编码",
    "aiff": "按源采样率编码",
}

#: 可以把封面写进输出文件的容器: 其余格式 (wav ogg opus) 不支持附加图片
COVER_FORMATS = frozenset({"mp3", "flac", "m4a", "wma", "aiff"})

#: 写标签与封面时要额外传给 ffmpeg 的参数: aiff 不打开 ID3v2 只会写入标题
FORMAT_TAG_ARGS = {"aiff": ("-write_id3v2", "1")}

# 可以直接交给 ffmpeg 解码的音频扩展名
AUDIO_EXTENSIONS = (".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".oga",
                    ".opus", ".wma", ".aiff", ".aif", ".ape", ".amr", ".ac3",
                    ".mp2", ".mka", ".wv", ".m4b", ".caf", ".au")

#: 视频容器的扩展名: 转换时只取其中的音频轨
VIDEO_EXTENSIONS = (".mp4", ".m4v", ".mov", ".mkv", ".webm", ".avi", ".flv",
                    ".wmv", ".mpg", ".mpeg")

#: 音乐平台加密容器的扩展名: 转换前先还原成常见音频
ENCRYPTED_EXTENSIONS = (".ncm",)

#: 可以加进列表参与转换的全部扩展名
INPUT_EXTENSIONS = AUDIO_EXTENSIONS + VIDEO_EXTENSIONS + ENCRYPTED_EXTENSIONS

#: 同一编码格式的其它扩展名: 命中时与目标格式视为相同 直接复制而不再编码
#  没有列出的扩展名只与自身相同
FORMAT_ALIASES = {
    "ogg": ("oga",),
    "aiff": ("aif",),
    "m4a": ("m4b",),
}

# 文件列表的列: 列标识 标题 初始宽度 对齐方式
FILE_COLUMNS = (
    ("name", "文件名", 320, "w"),
    ("format", "格式", 70, "center"),
    ("size", "大小", 90, "e"),
    ("status", "状态", 200, "w"),
)

#: 状态列的文字
STATUS_WAITING = "等待转换"
STATUS_RUNNING = "转换中"
STATUS_DONE = "已完成"
STATUS_SKIPPED = "已跳过"
STATUS_CANCELLED = "已终止"
#: 源文件已经是目标格式时只复制文件, 状态列里的文字
STATUS_COPIED = "已复制"
#: 加密容器还原出来的音频就是目标格式时, 状态列里的文字
STATUS_DECODED = "已解密"

#: 状态列里转换失败时的前缀
STATUS_FAILED = "失败"

#: 输出位置: 与源文件同目录 或者 指定的文件夹
DEST_SOURCE = "source"
DEST_CUSTOM = "custom"

#: 输出位置的两个单选项: 取值 显示名
DEST_LABELS = ((DEST_SOURCE, "源文件夹"), (DEST_CUSTOM, "指定文件夹"))

#: 表格里缺省显示的占位符
EMPTY_VALUE = "-"

# 列表为空时的占位文案: 标题 与 下一步动作
EMPTY_TITLE = "还没有要转换的文件"
EMPTY_HINT = "点击左上角的「添加文件」或者「添加文件夹」开始"

#: 列表卡片的标题与工具条上的说明
CARD_TITLE = "待转换文件"
PAGE_HINT = "添加音频 视频或加密文件, 选好输出格式后点「开始转换」"
#: 选好指定文件夹之后的提示
CUSTOM_DEST_HINT = "输出到 {path}"
#: 输出位置一行: 源文件夹时路径框里的说明 与 刷新扫描按钮
DEST_SOURCE_HINT = "输出到与源文件相同的文件夹"
RESCAN_LABEL = "刷新扫描"
#: 指定的输出文件夹在开始转换时已经不存在
DEST_MISSING = "输出文件夹不存在, 请点路径框重新选择"

#: 没有任务时进度区的文字
PROGRESS_IDLE = "等待开始"

# 进度条右侧的文字
PROGRESS_RUNNING = "正在转换 {index}/{total}"
PROGRESS_STOPPING = "正在终止"

#: 同格式同目录时不做无意义的重复转换
SKIP_SAME_FORMAT = "与源文件同格式同目录, 已跳过"

#: 失败消息的前缀: 状态列只显示去掉前缀之后的原因
CONVERT_FAILED = "转换失败"
COPY_FAILED = "复制失败"
DECRYPT_FAILED = "解密失败"
#: 加密容器还原失败的原因
PLATFORM_KEY_BROKEN = "文件结构损坏, 解不出音频密钥"
PLATFORM_NO_AUDIO = "还原出来的数据不是已知的音频格式"
PLATFORM_UNKNOWN = "文件既不是加密容器, 也不是已知的音频"

#: 找不到 ffmpeg 时的提示
FFMPEG_MISSING = "没有找到 ffmpeg, 请手动选择 ffmpeg.exe, 或者把它加入 PATH"

# 工具条上下拉框的宽度 (字符数): 格式名最长 4 个字符, 音质最长 11 个字符
# 留出余量的同时把宽度压到刚好, 让音质说明在最小窗口宽度下也能完整显示
FORMAT_COMBO_WIDTH = 8
QUALITY_COMBO_WIDTH = 14

# 状态栏左侧的引擎说明
ENGINE_LABEL = "引擎"
ENGINE_DETECTING = "正在检测"
ENGINE_MISSING = "未找到 ffmpeg"
ENGINE_CHOOSE = "选择 ffmpeg"

# 转换结束后的总结: 状态栏 与 页面底部
SUMMARY_DONE = "转换完成: 成功 {ok} 个, 跳过 {skip} 个, 失败 {fail} 个"
SUMMARY_STOPPED = "转换已终止: 成功 {ok} 个, 跳过 {skip} 个, 失败 {fail} 个"
SUMMARY_SHORT = "成功 {ok} · 跳过 {skip} · 失败 {fail}"
