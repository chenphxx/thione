"""翻译服务 Provider 子包。

对外只暴露统一接口, 元数据与注册表: 业务层通过 `build_provider()` 取得当前
配置选定的实现, 或通过 `spec_for()` 读取某家服务的显示名与可选语言。各具体
实现由注册表在真正用到时才导入, 因此加载本包不会牵连任何第三方 SDK。
"""

from .provider import (
    DEFAULT_PROVIDER,
    PROVIDER_NAMES,
    PROVIDER_SPECS,
    ProviderSpec,
    TranslationError,
    TranslationProvider,
    build_provider,
    spec_for,
)

__all__ = [
    "DEFAULT_PROVIDER",
    "PROVIDER_NAMES",
    "PROVIDER_SPECS",
    "ProviderSpec",
    "TranslationError",
    "TranslationProvider",
    "build_provider",
    "spec_for",
]