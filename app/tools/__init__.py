"""内置工具集合。

新增工具时只需要在这里追加一个 ToolPage 子类, 外壳会自动为它生成侧栏入口
与内容区页面。
"""

from .dedupe import DedupePage
from .rename import RenamePage
from .translate import TranslatePage

#: 外壳按此顺序装载页面, 顺序即侧栏顺序
TOOL_PAGES = (
    DedupePage,
    RenamePage,
    TranslatePage,
)

__all__ = ["TOOL_PAGES", "DedupePage", "RenamePage", "TranslatePage"]
