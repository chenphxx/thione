"""内置工具集合。

新增工具时只需要在这里追加一个 ToolPage 子类, 外壳会自动为它生成侧栏入口
与内容区页面。
"""

from .comm import CommPage
from .convert import ConvertPage
from .dedupe import DedupePage
from .port import PortPage
from .radix import RadixPage
from .rename import RenamePage
from .translate import TranslatePage

#: 外壳按此顺序装载页面, 顺序即侧栏顺序
TOOL_PAGES = (
    DedupePage,
    RenamePage,
    TranslatePage,
    RadixPage,
    PortPage,
    ConvertPage,
    CommPage,
)

__all__ = ["TOOL_PAGES", "DedupePage", "RenamePage", "TranslatePage",
           "RadixPage", "PortPage", "ConvertPage", "CommPage"]
