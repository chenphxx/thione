"""Google 翻译免费端点 Provider (https://translate.googleapis.com)

免凭据的公共端点: `POST /translate_a/single` 用 form 参数 `q` 提交待翻译文本,
语言代码放在 query 里 (`sl` 源语言, `tl` 目标语言), `sl=auto` 交给服务端识别

响应是嵌套数组, 译文按句拆成多段放在第一项里, 每段的第一项才是译文, 这里按
原文顺序把各段拼回一个字符串. 端点没有公开的字符上限, 长文本由服务端自行拆句,
本地不做长度校验
"""

import logging

import httpx

from ..constants import GOOGLE_TIMEOUT, GOOGLE_URL
from .provider import TranslationError, TranslationProvider, spec_for

logger = logging.getLogger(__name__)

#: 本服务的元数据, 语言代码表由它提供
SPEC = spec_for("google")


class GoogleTranslator(TranslationProvider):
    """Google 翻译网页端免费端点

    一次提交一整段文本, 服务端会拆成多句, 返回的译文也是多段, 这里按段拼接
    """

    def __init__(self, url=GOOGLE_URL, timeout=GOOGLE_TIMEOUT):
        self._url = url
        self._timeout = timeout

    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        """调用 /translate_a/single 翻译文本

        @param text: 待翻译文本
        @param source_lang: 源语言的领域语言代码, `auto` 交给服务端识别
        @param target_lang: 目标语言的领域语言代码
        @return: 译文
        @raise TranslationError: 文本为空, 语言不受支持, 服务端报错, 或网络
            与响应格式异常
        """
        text = (text or "").strip()
        if not text:
            raise TranslationError("待翻译文本为空")

        params = {
            "client": "gtx",
            "sl": SPEC.source_code_of(source_lang),
            "tl": SPEC.code_of(target_lang),
            "dt": "t",
        }

        try:
            response = httpx.post(
                self._url, params=params, data={"q": text},
                timeout=self._timeout,
            )
        except Exception as exc:
            raise TranslationError(f"调用翻译接口失败: {exc}") from exc

        try:
            body = response.json()
        except ValueError:
            body = None
        if response.status_code != 200 or not isinstance(body, list):
            logger.warning("Google 翻译返回异常 (HTTP %s)", response.status_code)
            raise TranslationError(
                f"翻译接口返回异常 (HTTP {response.status_code})"
            )

        segments = body[0] if body and isinstance(body[0], list) else []
        result = "".join(
            segment[0] for segment in segments
            if isinstance(segment, list) and segment
            and isinstance(segment[0], str)
        )
        if not result.strip():
            raise TranslationError("翻译接口没有返回译文")
        return result
