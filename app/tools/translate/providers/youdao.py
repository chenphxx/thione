"""有道 AI 体验接口 Provider (https://aidemo.youdao.com/trans)

免凭据的公共接口: `POST /trans` 用 form 参数 `q` / `from` / `to` 提交待翻译
文本, 源语言可以指定也可以交给服务端识别 (`auto`), 译文在 `translation`
数组里, `errorCode` 是 `0` 才算成功

该接口只提供中英日三种语言, 翻译的源语言与目标语言至少一侧须为中文 (中英
中日互译), 单次最多 1000 字符, 并有访问频率限制: 触发频率限制时按提示让
用户稍后再试, 不做自动重试
"""

import logging

import httpx

from ..constants import YOUDAO_MAX_TEXT_LENGTH, YOUDAO_TIMEOUT, YOUDAO_URL
from .provider import TranslationError, TranslationProvider, spec_for

logger = logging.getLogger(__name__)

#: 本服务的元数据, 语言代码表由它提供
SPEC = spec_for("youdao")

#: 响应里的业务返回码字段与成功取值
ERROR_CODE_FIELD = "errorCode"
SUCCESS_CODE = "0"

#: 服务端错误码对应的用户提示
ERROR_MESSAGES = {
    "102": "该服务不支持这笔翻译, 请改选其它语言或其它服务",
    "103": "文本过长, 请缩短后重试",
    "113": "待翻译文本为空",
    "411": "访问过于频繁, 请稍后再试",
}


class YoudaoTranslator(TranslationProvider):
    """有道 AI 体验接口的 /trans 接口

    译文放在 `translation` 数组里, 正常情况下只有一段, 这里全部拼起来
    """

    def __init__(self, url=YOUDAO_URL, timeout=YOUDAO_TIMEOUT):
        self._url = url
        self._timeout = timeout

    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        """调用 /trans 翻译文本

        @param text: 待翻译文本
        @param source_lang: 源语言的领域语言代码, `auto` 交给服务端识别
        @param target_lang: 目标语言的领域语言代码
        @return: 译文
        @raise TranslationError: 文本为空或过长, 语言不受支持, 访问过于频繁,
            或网络与响应格式异常
        """
        text = (text or "").strip()
        if not text:
            raise TranslationError("待翻译文本为空")
        if len(text) > YOUDAO_MAX_TEXT_LENGTH:
            raise TranslationError(
                f"文本过长 (超过 {YOUDAO_MAX_TEXT_LENGTH} 字符)"
            )

        data = {
            "q": text,
            "from": SPEC.source_code_of(source_lang),
            "to": SPEC.code_of(target_lang),
        }

        try:
            response = httpx.post(self._url, data=data, timeout=self._timeout)
        except Exception as exc:
            raise TranslationError(f"调用翻译接口失败: {exc}") from exc

        try:
            payload = response.json()
        except ValueError:
            payload = None
        if not isinstance(payload, dict):
            raise TranslationError(
                f"翻译接口返回异常 (HTTP {response.status_code})"
            )

        error_code = payload.get(ERROR_CODE_FIELD, "")
        error_code = "" if error_code is None else str(error_code)
        if response.status_code != 200 or error_code != SUCCESS_CODE:
            raise TranslationError(
                self._error_message(payload, response.status_code, error_code)
            )

        result = payload.get("translation")
        if isinstance(result, list):
            result = "".join(part for part in result if isinstance(part, str))
        if not result or not result.strip():
            raise TranslationError("翻译接口没有返回译文")
        return result

    @staticmethod
    def _error_message(payload, status_code, error_code):
        """把服务端的错误码与说明转成一句提示

        @param payload: 已解析的响应体
        @param status_code: HTTP 状态码
        @param error_code: 响应里的 errorCode
        @return: 错误提示
        """
        logger.warning("有道翻译返回 %r (HTTP %s)", error_code, status_code)
        if error_code in ERROR_MESSAGES:
            return ERROR_MESSAGES[error_code]
        if error_code:
            return f"翻译接口调用失败 (错误码 {error_code})"
        return f"翻译接口调用失败 (HTTP {status_code})"
