"""华为云 NLP 文本翻译 Provider。

与另外两家服务的区别: 需要 AK / SK / Project ID 凭据, 单次最多 2000 字符,
繁体中文的语言代码是 `zh-tw`。
"""

from huaweicloudsdknlp.v2.model import RunTextTranslationRequest, TextTranslationReq

from ..auth import build_client
from ..config import Config
from ..constants import MAX_TEXT_LENGTH
from .provider import TranslationError, TranslationProvider, spec_for

#: 本服务的元数据, 语言代码表由它提供
SPEC = spec_for("huawei")


class HuaweiTranslator(TranslationProvider):
    """封装华为云 NLP 文本翻译接口。"""

    def __init__(self, config: Config):
        self.config = config
        self._client = build_client(config)

    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        """调用 run_text_translation 翻译文本。

        @param text: 待翻译文本
        @param source_lang: 源语言的领域语言代码, `auto` 交给服务端识别
        @param target_lang: 目标语言的领域语言代码
        @return: 译文
        @raise TranslationError: 文本为空或过长, 语言不受支持, 或接口调用失败
        """
        text = (text or "").strip()
        if not text:
            raise TranslationError("待翻译文本为空。")
        if len(text) > MAX_TEXT_LENGTH:
            raise TranslationError(f"文本过长 (超过 {MAX_TEXT_LENGTH} 字符)。")

        request = RunTextTranslationRequest(
            body=TextTranslationReq(
                text=text,
                _from=SPEC.source_code_of(source_lang),
                to=SPEC.code_of(target_lang),
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