"""60s API 在线翻译 Provider (https://docs.60s-api.viki.moe/254700383e0)。

免凭据的公共接口, 数据来自有道翻译: `GET /v2/fanyi` 带 text / from / to 三个
query 参数, 语言代码用有道的取值 (中文是 `zh-CHS`), 译文在 `data.target.text`。

源语言与目标语言都可以指定, 因此不必依赖服务端的自动规则。公共实例有频率
限制 (实测触发过 429), 所以这里不做自动重试, 只把服务端给出的说明转成
TranslationError 交给用户决定。
"""

import logging

import httpx

from ..constants import SIXTY_BASE_URL, SIXTY_TIMEOUT
from .provider import TranslationError, TranslationProvider, spec_for

logger = logging.getLogger(__name__)

#: 本服务的元数据, 语言代码表由它提供
SPEC = spec_for("sixty")

#: 译文在响应里的路径
RESULT_PATH = ("data", "target", "text")

#: 出错时依次尝试从响应里取说明的字段
ERROR_FIELDS = ("message", "title", "detail", "error")


class SixtyTranslator(TranslationProvider):
    """60s API 的 /v2/fanyi 接口。"""

    def __init__(self, base_url=SIXTY_BASE_URL, timeout=SIXTY_TIMEOUT):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        """调用 /v2/fanyi 翻译文本。

        @param text: 待翻译文本
        @param source_lang: 源语言的领域语言代码, `auto` 交给服务端识别
        @param target_lang: 目标语言的领域语言代码
        @return: 译文
        @raise TranslationError: 文本为空, 语言不受支持, 服务端报错, 或网络
            与响应格式异常
        """
        text = (text or "").strip()
        if not text:
            raise TranslationError("待翻译文本为空。")

        params = {
            "text": text,
            "from": SPEC.source_code_of(source_lang),
            "to": SPEC.code_of(target_lang),
        }

        try:
            response = httpx.get(
                f"{self._base_url}/v2/fanyi", params=params,
                timeout=self._timeout,
            )
        except Exception as exc:
            raise TranslationError(f"调用翻译接口失败: {exc}") from exc

        try:
            payload = response.json()
        except ValueError:
            payload = None
        if not isinstance(payload, dict):
            raise TranslationError(
                f"翻译接口返回异常 (HTTP {response.status_code})。"
            )

        if response.status_code != 200 or payload.get("code") != 200:
            raise TranslationError(
                self._error_message(payload, response.status_code)
            )

        result = payload
        for key in RESULT_PATH:
            result = result.get(key) if isinstance(result, dict) else None
        if not result:
            raise TranslationError("翻译接口没有返回译文。")
        return result

    @staticmethod
    def _error_message(payload, status_code):
        """把服务端的错误说明转成一句提示, 限流与网关错误也能看懂。

        @param payload: 已解析的响应体
        @param status_code: HTTP 状态码
        @return: 错误提示
        """
        for key in ERROR_FIELDS:
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return f"翻译接口调用失败 (HTTP {status_code})。"