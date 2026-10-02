"""腾讯交互翻译 Provider (https://transmart.qq.com)

免凭据的公共接口: `POST /api/imt` 用 JSON 提交待翻译文本, 源语言可以指定也可以
交给服务端识别 (`auto`), 译文在 `auto_translation` 数组里, `header` 里的
`ret_code` 是 `succ` 才算成功

请求体里的 client_key 是网页端固定使用的浏览器标识, 不是账号凭据. 服务端限制
单次 6000 字符, 本地先按同一上限拦一次; 失败原因 (语言不支持 超出长度 等) 由
`ret_code` 与 `message` 给出, 这里转成用户看得懂的提示
"""

import logging

import httpx

from ..constants import (
    TRANSMART_MAX_TEXT_LENGTH,
    TRANSMART_TIMEOUT,
    TRANSMART_URL,
)
from .provider import TranslationError, TranslationProvider, spec_for

logger = logging.getLogger(__name__)

#: 本服务的元数据, 语言代码表由它提供
SPEC = spec_for("transmart")

#: 网页端固定使用的浏览器标识, 不是账号凭据
CLIENT_KEY = "browser-chrome-110.0.0"

#: 译文在响应里的字段
RESULT_FIELD = "auto_translation"

#: 出错时依次尝试从响应里取说明的字段
ERROR_FIELDS = ("message", "error")

#: 服务端返回码对应的用户提示
ERROR_MESSAGES = {
    "Unsupported-Language": "该服务不支持这门语言, 请改选其它语言或其它服务",
    "outOfLimit": "文本过长, 请缩短后重试",
    "Auth-Failed": "翻译接口拒绝了本次请求, 请稍后重试",
}


class TransmartTranslator(TranslationProvider):
    """腾讯交互翻译的 /api/imt 接口

    接口一次可以提交多段文本, 这里只发一段, 再把返回的段落拼回一个字符串
    """

    def __init__(self, url=TRANSMART_URL, timeout=TRANSMART_TIMEOUT):
        self._url = url
        self._timeout = timeout

    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        """调用 /api/imt 翻译文本

        @param text: 待翻译文本
        @param source_lang: 源语言的领域语言代码, `auto` 交给服务端识别
        @param target_lang: 目标语言的领域语言代码
        @return: 译文
        @raise TranslationError: 文本为空或过长, 语言不受支持, 服务端报错,
            或网络与响应格式异常
        """
        text = (text or "").strip()
        if not text:
            raise TranslationError("待翻译文本为空")
        if len(text) > TRANSMART_MAX_TEXT_LENGTH:
            raise TranslationError(
                f"文本过长 (超过 {TRANSMART_MAX_TEXT_LENGTH} 字符)"
            )

        payload = {
            "header": {"fn": "auto_translation", "client_key": CLIENT_KEY},
            "type": "plain",
            "model_category": "normal",
            "source": {
                "lang": SPEC.source_code_of(source_lang),
                "text_list": [text],
            },
            "target": {"lang": SPEC.code_of(target_lang)},
        }

        try:
            response = httpx.post(self._url, json=payload, timeout=self._timeout)
        except Exception as exc:
            raise TranslationError(f"调用翻译接口失败: {exc}") from exc

        try:
            body = response.json()
        except ValueError:
            body = None
        if not isinstance(body, dict):
            raise TranslationError(
                f"翻译接口返回异常 (HTTP {response.status_code})"
            )

        ret_code = (body.get("header") or {}).get("ret_code")
        if response.status_code != 200 or ret_code != "succ":
            raise TranslationError(
                self._error_message(body, response.status_code, ret_code)
            )

        result = body.get(RESULT_FIELD)
        if isinstance(result, list):
            result = "".join(part for part in result if isinstance(part, str))
        if not result or not result.strip():
            raise TranslationError("翻译接口没有返回译文")
        return result

    @staticmethod
    def _error_message(body, status_code, ret_code):
        """把服务端的错误说明转成一句提示

        @param body: 已解析的响应体
        @param status_code: HTTP 状态码
        @param ret_code: 响应头里的业务返回码
        @return: 错误提示
        """
        logger.warning("腾讯交互翻译返回 %r (HTTP %s)", ret_code, status_code)
        for key in ERROR_FIELDS:
            value = body.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        if ret_code in ERROR_MESSAGES:
            return ERROR_MESSAGES[ret_code]
        if ret_code:
            return f"翻译接口调用失败 ({ret_code})"
        return f"翻译接口调用失败 (HTTP {status_code})"
