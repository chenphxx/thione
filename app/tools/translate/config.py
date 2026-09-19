"""运行配置的数据结构。

provider 决定这次翻译交给哪个服务, 取值见 constants.PROVIDERS; 使用免费
接口时凭据字段可以留空。

密钥 (AK/SK/project_id) 的读取优先级与落点由 storage 负责, 见该模块
文档。这里只保留配置对象本身, 避免调用方关心具体来源。

注意: 这里不能再引入 storage, 否则会与 storage 读取 Config 形成循环依赖。
"""

from dataclasses import dataclass

from . import constants

__all__ = ["Config"]


@dataclass
class Config:
    ak: str
    sk: str
    project_id: str
    region: str = constants.REGION
    provider: str = constants.PROVIDER_HUAWEI

    @property
    def endpoint(self):
        return f"https://nlp-ext.{self.region}.myhuaweicloud.com"

    @property
    def label(self):
        """当前服务在界面上的显示名。"""
        return constants.PROVIDER_LABELS.get(self.provider, self.provider)


