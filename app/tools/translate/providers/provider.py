"""翻译服务 Provider 的统一接口, 元数据与注册表。

每个 Provider 只负责自己那一家服务的细节: 接口地址, 请求方式, 认证, 参数
转换, 响应解析与第三方异常转换。业务层只通过本模块的元数据与
`TranslationProvider.translate()` 使用翻译能力, 不出现具体供应商的判断。

`translate()` 的语言参数一律是本项目的领域语言代码 (见 `language.LANGUAGE_LABELS`)
例如中文是 `zh`; 各服务自己的语言代码 (华为云 `zh-tw`, 60s API `zh-CHT`,
uapipro `zh-TW`) 由 Provider 内部转换, 不向业务层暴露。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Mapping

from ..constants import MAX_TEXT_LENGTH, UAPI_MAX_TEXT_LENGTH
from ..language import AUTO_LANG, language_label

if TYPE_CHECKING:  # 仅用于类型标注, 避免与 config 形成循环导入
    from ..config import Config


#: 没有任何配置或配置值未知时使用的翻译服务
DEFAULT_PROVIDER = "huawei"

#: 华为云 NLP 支持的语言, 取值见 SDK 里 TextTranslationReq 的语言列表
HUAWEI_LANGUAGES = {
    "zh": "zh",
    "zh-Hant": "zh-tw",
    "en": "en",
    "ja": "ja",
    "ko": "ko",
    "fr": "fr",
    "de": "de",
    "es": "es",
    "pt": "pt",
    "ru": "ru",
    "ar": "ar",
    "th": "th",
    "vi": "vi",
    "tr": "tr",
}

#: 60s API 支持的语言, 取值见 https://docs.60s-api.viki.moe/254700383e0
SIXTY_LANGUAGES = {
    "zh": "zh-CHS",
    "zh-Hant": "zh-CHT",
    "en": "en",
    "ja": "ja",
    "ko": "ko",
    "fr": "fr",
    "de": "de",
    "es": "es",
    "pt": "pt",
    "ru": "ru",
    "ar": "ar",
    "th": "th",
    "vi": "vi",
    "tr": "tr",
    "it": "it",
    "id": "id",
    "nl": "nl",
    "pl": "pl",
    "hi": "hi",
}

#: uapipro 支持的语言, 取值见 https://uapis.cn/openapi.json 的 to_lang 枚举
UAPI_LANGUAGES = {
    "zh": "zh",
    "zh-Hant": "zh-TW",
    "en": "en",
    "ja": "ja",
    "ko": "ko",
    "fr": "fr",
    "de": "de",
    "es": "es",
    "pt": "pt",
    "ru": "ru",
    "ar": "ar",
    "th": "th",
    "vi": "vi",
    "tr": "tr",
    "it": "it",
    "id": "id",
    "nl": "nl",
    "pl": "pl",
    "hi": "hi",
}

#: 可作为源语言的领域语言代码, 一律包含 auto (自动识别); uapipro 的接口由
#: 服务端识别源语言, 因此只支持 auto
HUAWEI_SOURCE_LANGUAGES = frozenset(HUAWEI_LANGUAGES) | {AUTO_LANG}
SIXTY_SOURCE_LANGUAGES = frozenset(SIXTY_LANGUAGES) | {AUTO_LANG}
UAPI_SOURCE_LANGUAGES = frozenset({AUTO_LANG})


class TranslationError(RuntimeError):
    """翻译调用失败, 各 Provider 共用的异常。"""


class TranslationProvider(ABC):
    """翻译能力的统一接口, 业务层只依赖这个抽象。"""

    @abstractmethod
    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        """把文本翻译成目标语言。

        @param text: 待翻译文本
        @param source_lang: 源语言的领域语言代码, `auto` 表示交给服务端识别
        @param target_lang: 目标语言的领域语言代码, 不接受 `auto`
        @return: 译文
        @raise TranslationError: 文本为空或过长, 语言不受支持, 或接口调用失败
        """


@dataclass(frozen=True)
class ProviderSpec:
    """一家翻译服务对外的元数据与构造方式。"""

    name: str
    label: str
    hint: str
    requires_credentials: bool
    languages: Mapping[str, str]
    source_languages: frozenset[str]
    factory: "Callable[[Config], TranslationProvider]"

    def code_of(self, lang: str) -> str:
        """把领域语言代码换成该服务的语言代码。

        @param lang: 目标语言的领域语言代码
        @return: 该服务自己的语言代码
        @raise TranslationError: 该服务不支持这门语言
        """
        code = self.languages.get(lang or "")
        if code is None:
            raise TranslationError(
                f"{self.label} 不支持{language_label(lang)}, "
                "请改选其它语言或其它服务。"
            )
        return code

    def source_code_of(self, lang: str) -> str:
        """源语言的领域语言代码换成该服务的语言代码。

        @param lang: 源语言的领域语言代码
        @return: 该服务自己的语言代码, `auto` 原样返回
        @raise TranslationError: 该服务不能把这门语言指定为源语言
        """
        if not lang or lang == AUTO_LANG:
            return AUTO_LANG
        if lang not in self.source_languages:
            raise TranslationError(
                f"{self.label} 不支持指定{language_label(lang)}为源语言, "
                "请改用自动识别或其它服务。"
            )
        return self.languages[lang]


def _build_huawei(config: "Config") -> TranslationProvider:
    """构建华为云实现; 延迟导入, 没选它时不必加载 SDK。"""
    from .huawei import HuaweiTranslator

    return HuaweiTranslator(config)


def _build_uapi(config: "Config") -> TranslationProvider:
    """构建 uapipro 实现; SDK 由实现自己在第一次翻译时导入。"""
    from .uapi import UapiTranslator

    return UapiTranslator()


def _build_sixty(config: "Config") -> TranslationProvider:
    """构建 60s API 实现。"""
    from .sixty import SixtyTranslator

    return SixtyTranslator()


#: 界面上按此顺序给出可选服务
PROVIDER_SPECS = (
    ProviderSpec(
        name=DEFAULT_PROVIDER,
        label="华为云 NLP",
        hint=f"需要 AK / SK / Project ID, 单次最多 {MAX_TEXT_LENGTH} 字符",
        requires_credentials=True,
        languages=HUAWEI_LANGUAGES,
        source_languages=HUAWEI_SOURCE_LANGUAGES,
        factory=_build_huawei,
    ),
    ProviderSpec(
        name="uapi",
        label="uapipro 免费接口",
        hint=(f"公共免费接口, 无需凭据, 单次最多 {UAPI_MAX_TEXT_LENGTH} 字符, "
              "源语言由服务端识别"),
        requires_credentials=False,
        languages=UAPI_LANGUAGES,
        source_languages=UAPI_SOURCE_LANGUAGES,
        factory=_build_uapi,
    ),
    ProviderSpec(
        name="sixty",
        label="60s API 在线翻译",
        hint="公共免费接口, 无需凭据, 数据来自有道翻译, 源语言与目标语言均可指定",
        requires_credentials=False,
        languages=SIXTY_LANGUAGES,
        source_languages=SIXTY_SOURCE_LANGUAGES,
        factory=_build_sixty,
    ),
)

#: 全部可选服务名
PROVIDER_NAMES = tuple(spec.name for spec in PROVIDER_SPECS)

_SPECS_BY_NAME = {spec.name: spec for spec in PROVIDER_SPECS}


def spec_for(name: str) -> ProviderSpec:
    """取某个服务的元数据, 未知或缺失的服务名回落到默认服务。

    @param name: 服务名, 取值见 PROVIDER_NAMES
    @return: 对应的元数据
    """
    key = (name or "").strip().lower()
    return _SPECS_BY_NAME.get(key, _SPECS_BY_NAME[DEFAULT_PROVIDER])


def build_provider(config: "Config") -> TranslationProvider:
    """按配置里选定的服务构建翻译实现。

    @param config: 运行配置, 其中 provider 决定使用哪个服务
    @return: 具有 translate(text, source_lang, target_lang) 的实现
    """
    return spec_for(config.provider).factory(config)