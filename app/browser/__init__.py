"""资源管理器风格的浏览组件, 图片查重与批量重命名共用。

这里只放两个工具都要用的界面部件: 文件视图, 右侧预览窗格, 底部详细信息窗格
以及展示方式 缩略图大小与窗格开关。具体业务 (查重, 改名) 仍留在各自的工具包里
"""

from .details_pane import DetailsPane
from .file_grid import FileGrid
from .preview_pane import PreviewPane
from .view_bar import PaneToggles, ViewSwitch

__all__ = ["DetailsPane", "FileGrid", "PreviewPane", "PaneToggles", "ViewSwitch"]
