"""文本语言检测, 可选语言目录与翻译方向决策。

领域语言代码是本项目对外的统一语言标识, 与任何一家服务的取值无关: 中文是
`zh`, 繁体中文是 `zh-Hant`, `auto` 表示交给服务端识别或按规则自动选择;
各服务自己的语言代码 (华为云 `zh-tw`, 60s API `zh-CHT`, uapipro `zh-TW`) 由
`providers` 内部转换。

`LANGUAGE_LABELS` 只收录常用语言, 华为云 NLP 支持其中的一部分; 需要新增语言
时在这里补一项, 再到 `providers.provider` 里各服务的语言代码表补上取值。
"""

import re

#: 源语言交给服务端识别, 目标语言按规则自动选择
AUTO_LANG = "auto"

#: 中文的领域语言代码
ZH_LANG = "zh"

#: 默认不指定目标语言, 交给文本内容决定译成哪种语言
DEFAULT_TARGET_LANG = AUTO_LANG

#: 目标语言选 auto 时: 中文译成英文, 其它语言译成中文
TARGET_WHEN_ZH = "en"
TARGET_OTHERWISE = "zh"

#: 目标语言下拉框里 auto 选项的显示名
AUTO_TARGET_LABEL = "自动 (中→英, 其它→中)"

#: 界面上按此顺序给出可选语言: 领域语言代码 -> 中文显示名
LANGUAGE_LABELS = {
    "zh": "中文",
    "zh-Hant": "中文(繁体)",
    "en": "英语",
    "ja": "日语",
    "ko": "韩语",
    "fr": "法语",
    "de": "德语",
    "es": "西班牙语",
    "pt": "葡萄牙语",
    "ru": "俄语",
    "ar": "阿拉伯语",
    "th": "泰语",
    "vi": "越南语",
    "tr": "土耳其语",
    "it": "意大利语",
    "id": "印度尼西亚语",
    "nl": "荷兰语",
    "pl": "波兰语",
    "hi": "印地语",
}

_JAPANESE_RE = re.compile(r"[\u3040-\u309F\u30A0-\u30FF]+")
_CJK_RE = re.compile(r"[\u4E00-\u9FFF]")


def language_label(code: str) -> str:
    """取语言代码的显示名, 未知代码原样返回。

    @param code: 领域语言代码
    @return: 显示名, `auto` 返回「自动识别」
    """
    if not code:
        return "未知语言"
    if code == AUTO_LANG:
        return "自动识别"
    return LANGUAGE_LABELS.get(code, code)


def detect_language(text: str) -> str:
    """粗略判断源语言, 返回 'zh' 或 'auto'。

    日语常包含汉字, 为避免被误判为中文, 只要出现假名就返回 'auto',
    交由服务端自动识别语种。
    """
    if not text:
        return "auto"
    if _JAPANESE_RE.search(text):
        return "auto"
    if _CJK_RE.search(text):
        return "zh"
    return "auto"


def preferred_target(source_lang: str, target_lang: str) -> str:
    """源语言与目标语言都选了中文时, 实际改译英文。

    中文再译成中文没有意义, 因此两者都是中文时按译成英文处理; 目标语言选了
    中文繁体 (zh-Hant) 或其它语言时不受影响。

    @param source_lang: 源语言的领域语言代码
    @param target_lang: 目标语言的领域语言代码
    @return: 实际使用的目标语言领域语言代码
    """
    if source_lang == ZH_LANG and target_lang == ZH_LANG:
        return TARGET_WHEN_ZH
    return target_lang


def resolve_direction(text: str, source_lang: str, target_lang: str):
    """把界面上的语言选择解析成实际交给 Provider 的 (源语言, 目标语言)。

    默认目标语言是 auto, 此时按文本判断方向: 中文译成英文, 其它语言译成中文;
    目标语言明确选了中文而源语言本身就是中文时同样改译英文, 避免译出来还是
    中文; 源语言选 auto 或留空时交给服务端识别。

    @param text: 待翻译文本
    @param source_lang: 源语言的领域语言代码
    @param target_lang: 目标语言的领域语言代码, `auto` 表示按源语言自动选择
    @return: (源语言, 目标语言) 领域语言代码
    """
    source = source_lang or AUTO_LANG
    target = target_lang or DEFAULT_TARGET_LANG
    if target == AUTO_LANG:
        # 默认方向: 中文译成英文, 其它语言译成中文
        target = (
            TARGET_WHEN_ZH if detect_language(text) == "zh" else TARGET_OTHERWISE
        )
    elif target == ZH_LANG:
        # 源语言明确是中文, 或者交给服务端识别出的就是中文
        source_now = detect_language(text) if source == AUTO_LANG else source
        target = preferred_target(source_now, target)
    return source, target
