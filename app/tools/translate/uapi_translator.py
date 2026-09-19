"""uapipro 免费翻译接口封装 (https://uapis.cn)。

与华为云实现的区别只有两点: 不需要凭据, 以及目标语言放在 query 里给出,
源语言交给服务端自动识别。

调用示例见仓库根目录的 test.py:

    client = UapiClient("https://uapis.cn")
    client.translate.post_translate_text(to_lang="zh", text="hello world")
"""

import logging

from .constants import UAPI_BASE_URL, UAPI_MAX_TEXT_LENGTH, UAPI_TIMEOUT
from .language import detect_language, pick_direction
from .translator import TranslationError

logger = logging.getLogger(__name__)

#: 响应里存放译文的字段
RESULT_FIELD = "translate"


class UapiTranslator:
    """uapipro 的 /api/v1/translate/text 接口。

    免费接口没有凭据可配置, 因此构造时不连接任何东西; SDK 也推迟到第一次
    翻译时才导入, 未安装时只影响这一个服务, 不会波及华为云那条路径。
    """

    def __init__(self, base_url=UAPI_BASE_URL, timeout=UAPI_TIMEOUT):
        self._base_url = base_url
        self._timeout = timeout
        self._client = None

    def translate(self, text: str) -> str:
        """把文本翻译成中文或英文, 返回译文。

        @param text: 待翻译文本
        @return: 译文
        @raise TranslationError: 文本为空或过长, 缺少 SDK, 或接口调用失败
        """
        text = (text or "").strip()
        if not text:
            raise TranslationError("待翻译文本为空。")
        if len(text) > UAPI_MAX_TEXT_LENGTH:
            raise TranslationError(
                f"文本过长 (超过 {UAPI_MAX_TEXT_LENGTH} 字符)。"
            )

        # 源语言由服务端识别, 这里只取翻译方向里的目标语言
        to_lang = pick_direction(detect_language(text))[1]

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
