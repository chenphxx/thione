"""uapipro 免费翻译接口 Provider (https://uapis.cn)。

与另外两家服务的区别: 不需要凭据, 目标语言放在 query 里给出, 接口没有源语言
参数, 一律由服务端识别, 因此该服务下只有 `auto` 能作为源语言。

"""

import logging

from ..constants import UAPI_BASE_URL, UAPI_MAX_TEXT_LENGTH, UAPI_TIMEOUT
from ..language import AUTO_LANG
from .provider import TranslationError, TranslationProvider, spec_for

logger = logging.getLogger(__name__)

#: 本服务的元数据, 语言代码表由它提供
SPEC = spec_for("uapi")

#: 响应里存放译文的字段
RESULT_FIELD = "translate"


class UapiTranslator(TranslationProvider):
    """uapipro 的 /api/v1/translate/text 接口。

    免费接口没有凭据可配置, 因此构造时不连接任何东西; SDK 也推迟到第一次
    翻译时才导入, 未安装时只影响这一个服务, 不会波及其它服务。
    """

    def __init__(self, base_url=UAPI_BASE_URL, timeout=UAPI_TIMEOUT):
        self._base_url = base_url
        self._timeout = timeout
        self._client = None

    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        """调用 post_translate_text 翻译文本。

        @param text: 待翻译文本
        @param source_lang: 源语言的领域语言代码, 该服务只接受 `auto`
        @param target_lang: 目标语言的领域语言代码
        @return: 译文
        @raise TranslationError: 文本为空或过长, 语言不受支持, 缺少 SDK,
            或接口调用失败
        """
        text = (text or "").strip()
        if not text:
            raise TranslationError("待翻译文本为空。")
        if len(text) > UAPI_MAX_TEXT_LENGTH:
            raise TranslationError(
                f"文本过长 (超过 {UAPI_MAX_TEXT_LENGTH} 字符)。"
            )

        if source_lang and source_lang != AUTO_LANG:
            # 界面在该服务下只提供自动识别, 手改配置带来的其它语言按 auto 处理
            logger.info(
                "uapipro 免费接口由服务端识别源语言, 忽略 source_lang=%s",
                source_lang,
            )
        to_lang = SPEC.code_of(target_lang)

        try:
            client = self._client or self._connect()
            response = client.translate.post_translate_text(
                to_lang=to_lang, text=text
            )
        except TranslationError:
            raise
        except Exception as exc:
            raise TranslationError(f"调用翻译接口失败: {exc}") from exc

        result = response.get(RESULT_FIELD) if isinstance(response, dict) else None
        if not result:
            raise TranslationError("翻译接口没有返回译文。")
        return result

    def _connect(self):
        """导入 SDK 并建立客户端; 缺少依赖时转成用户看得懂的提示。"""
        try:
            from uapi import UapiClient
        except ImportError as exc:
            raise TranslationError(
                "未安装 uapi-sdk-python, 无法使用 uapipro 免费接口; "
                "执行 pip install -r requirements.txt 后重试。"
            ) from exc
        self._client = UapiClient(self._base_url, timeout=self._timeout)
        logger.info("uapipro 翻译客户端已建立: %s", self._base_url)
        return self._client