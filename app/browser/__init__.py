"""资源管理器风格的浏览组件, 图片查重与批量重命名共用"""

from .details_pane import DetailsPane
from .file_grid import FileGrid
from .preview_pane import PreviewPane
from .view_bar import PaneToggles, ViewSwitch

__all__ = ["DetailsPane", "FileGrid", "PreviewPane", "PaneToggles", "ViewSwitch"]
