"""华为云 NLP 文本翻译服务封装, 以及翻译实现的统一入口。

本模块对外提供三样东西:

- `TranslationError`: 各翻译实现共用的异常, uapi_translator 也复用它;
- `Translator`: 华为云 NLP 的实现;
- `build_translator()`: 按配置里的服务名挑一个实现, 调用方不必关心细节。
"""

from huaweicloudsdknlp.v2.model import RunTextTranslationRequest, TextTranslationReq

from .auth import build_client
from .config import Config
from .constants import MAX_TEXT_LENGTH, PROVIDER_UAPI
from .language import detect_language, pick_direction


class TranslationError(RuntimeError):
    """翻译调用失败。"""


def build_translator(config: Config):
    """按配置里选定的服务构建翻译实现。

    免费接口的实现延迟到真正要用时才导入 SDK, 因此这里不会因为缺少
    uapi-sdk-python 而失败。

    @param config: 运行配置, 其中 provider 决定使用哪个服务
    @return: 具有 translate(text) 方法的翻译实现
    """
    if config.provider == PROVIDER_UAPI:
        from .uapi_translator import UapiTranslator

        return UapiTranslator()
    return Translator(config)


class Translator:
    """封装华为云 NLP 文本翻译接口。"""

    def __init__(self, config: Config):
        self.config = config
        self._client = build_client(config)

    def translate(self, text: str) -> str:
        text = (text or "").strip()
        if not text:
            raise TranslationError("待翻译文本为空。")
        if len(text) > MAX_TEXT_LENGTH:
            raise TranslationError(f"文本过长 (超过 {MAX_TEXT_LENGTH} 字符)。")

        source = detect_language(text)
        src_lang, dst_lang = pick_direction(source)

        request = RunTextTranslationRequest(
            body=TextTranslationReq(
                text=text,
                _from=src_lang,
                to=dst_lang,
                scene="common",
            )
        )

        try:
            response = self._client.run_text_translation(request)
        except Exception as exc:
            raise TranslationError(f"调用翻译接口失败: {exc}") from exc

        if getattr(response, "error_code", None):
            raise TranslationError(f"{response.error_code}: {response.error_msg}")
        return response.translated_text
