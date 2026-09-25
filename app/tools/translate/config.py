"""运行配置的数据结构。

provider 决定这次翻译交给哪个服务, 取值见 providers.PROVIDER_NAMES; 使用免费
接口时凭据字段可以留空。source_lang / target_lang 是本项目的领域语言代码,
取值见 language.LANGUAGE_LABELS, 由各 Provider 自己转换成服务的语言代码。

密钥 (AK/SK/project_id) 的读取优先级与落点由 storage 负责, 见该模块
文档。这里只保留配置对象本身, 避免调用方关心具体来源。

注意: 这里不能再引入 storage, 否则会与 storage 读取 Config 形成循环依赖。
"""

from dataclasses import dataclass

from . import constants
from .language import AUTO_LANG, DEFAULT_TARGET_LANG
from .providers import DEFAULT_PROVIDER, spec_for

__all__ = ["Config"]


@dataclass
class Config:
    ak: str
    sk: str
    project_id: str
    region: str = constants.REGION
    provider: str = DEFAULT_PROVIDER
    source_lang: str = AUTO_LANG
    target_lang: str = DEFAULT_TARGET_LANG

    @property
    def endpoint(self):
        return f"https://nlp-ext.{self.region}.myhuaweicloud.com"

    @property
    def label(self):
        """当前服务在界面上的显示名。"""
        return spec_for(self.provider).label