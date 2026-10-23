"""提供虚拟滚动和后台缩略图加载的文件视图

仅读取和解码可见文件, 用户切换视图或缩放档位时仍可复用已缓存的缩略图

缩略图的外观与设计稿一致: 148 x 98 的方框图 (没有图片时用 ph1 -> ph2 的 140 度
渐变占位), 名称在框下方 6 像素处, 选中项的方框描 2 像素强调色且名称改用强调色
"""

import os
import queue
import threading
import tkinter as tk
import tkinter.font as tkfont

from PIL import ImageTk

from ..dpi import scale
from ..imaging import load_thumbnail, make_gradient
from ..theme import (
    ICON_ARROW,
    ICON_CHECK,
    SIZE_SECTION,
    icon,
    mono,
    sans,
    tint,
)
from ..widgets import bind_mousewheel, unbind_mousewheel
from .constants import (
    BADGE_FONT_SIZE,
    BADGE_INSET,
    BATCH,
    CACHE_LIMIT,
    CACHE_SIZE,
    CELL_GAP,
    DEFAULT_TIER,
    DEFAULT_VIEW,
    GRID_PAD,
    IMAGE_EXTS,
    LABEL_GAP,
    LIST_FONT_SIZE,
    LIST_ROW_HEIGHT,
    OVERSCAN_ROWS,
    POLL_MS,
    RELAYOUT_MS,
    SCROLL_MS,
    TIER_SPECS,
    VIEWS,
)

#: 列表视图里勾选字形占用的宽度
LIST_MARK_WIDTH = scale(19)


def _fit_text(font, name, max_width):
    """按像素宽度截断文件名, 超长时补省略号

    @param font: 用于测量的字体对象
    @param name: 原始文件名
    @param max_width: 允许的最大像素宽度
    @return: 截断后的文件名
    """
    if max_width <= 0 or font.measure(name) <= max_width:
        return name
    low, high = 0, len(name)
    while low < high:
        middle = (low + high + 1) // 2
        if font.measure(name[:middle] + "...") <= max_width:
            low = middle
        else:
            high = middle - 1
    return name[:low] + "..."


def _is_image(path):
    """按扩展名判断是否真的去读图; 其余类型直接给占位图

    这一步避开了对文本与表格文件的读取, 也不会在额外的
    类型上占用文件句柄

    @param path: 文件路径
    @return: 是否按图片读取
    """
    return os.path.splitext(path)[1].lower() in IMAGE_EXTS


def _rgb(text):
    """把 #RRGGBB 换成 (r, g, b) 三元组

    @param text: 颜色字符串
    @return: 三元组
    """
    return (int(text[1:3], 16), int(text[3:5], 16), int(text[5:7], 16))


class FileGrid(tk.Frame):
    """把一组文件按列表或缩略图排列, 支持选中, 双击与右键

    参数:
        master:      父容器
        theme:       ThemeManager
        on_select:   callable(path), 选中项变化时调用, 未选中时 path 为 None
        on_activate: callable(path), 双击某一项时调用
        on_context:  callable(path, event), 右键某一项时调用
        tier:        初始档位, 见 constants.TIERS
        view:        初始展示方式, 见 constants.VIEWS
        surface:     所在的表面层, canvas 表示页面底色, panel 表示面板
    """

    def __init__(self, master, theme, on_select=None, on_activate=None,
                 on_context=None, tier=DEFAULT_TIER,
                 view=DEFAULT_VIEW, surface="canvas"):
        super().__init__(master, bd=0, highlightthickness=0)
        self.theme = theme
        self._surface = surface
        self._on_select = on_select
        self._on_activate = on_activate
        self._on_context = on_context

        self._paths = []
        self._cells = {}
        self._badges = {}
        self._secondary = None
        self._pil_cache = {}
        self._photo_cache = {}
        self._selected = None
        self._tier = tier
        self._view = view
        self._font = None
        self._cols = 1
        self._placeholder_cache = None

        #: 已经排给后台线程但还没拿到结果的路径
        self._requested = set()
        self._queue = queue.Queue()
        self._loading = False
        self._pump_job = None
        self._layout_job = None
        self._visible_job = None

        tint(self, bg=surface)
        self.configure(bg=theme.rgb(surface))
        self.canvas = tk.Canvas(self, highlightthickness=0, bd=0)
        tint(self.canvas, bg=surface)
        self.canvas.configure(bg=theme.rgb(surface))
        self.canvas.pack(side="left", fill="both", expand=True)

        bind_mousewheel(self.canvas, self.canvas)
        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<Double-1>", self._on_double_click)
        self.canvas.bind("<Button-3>", self._on_right_click)
        self.canvas.bind("<Configure>", self._on_resize)
        self.bind("<Destroy>", self._on_destroy)

    # ---------------- 对外接口 ----------------
    @property
    def tier(self):
        """当前档位"""
        return self._tier

    @property
    def view(self):
        """当前展示方式"""
        return self._view

    @property
    def loading(self):
        """是否仍在后台读取缩略图"""
        return self._loading

    def selected_path(self):
        """当前选中的文件路径, 未选中时返回 None"""
        return self._selected

    def set_files(self, paths):
        """重新加载一组文件, 清空缓存与选中; 不触发 on_select

        @param paths: 文件路径序列
        """
        self._stop_pump()
        self._paths = list(paths)
        self._pil_cache.clear()
        self._photo_cache.clear()
        self._selected = None
        self._requested.clear()
        self._badges = {path: text for path, text in self._badges.items()
                        if path in set(self._paths)}
        self._rebuild_cells()

    def clear(self):
        """清空内容"""
        self.set_files([])

    def set_tier(self, tier):
        """切换缩略图大小档位; 已缓存的图片直接按新尺寸重画

        @param tier: 档位名
        """
        if tier not in TIER_SPECS or tier == self._tier:
            return
        self._tier = tier
        if self._view == "list":
            return  # 列表视图不随档位变化, 只记住这次选择
        self._font = None
        self._photo_cache.clear()
        self._placeholder_cache = None
        self._rebuild_cells()

    def set_view(self, view):
        """切换列表视图与缩略图视图; 已缓存的图片直接按新布局重画

        @param view: 展示方式
        """
        if view not in VIEWS or view == self._view:
            return
        self._view = view
        self._font = None
        self._photo_cache.clear()
        self._placeholder_cache = None
        self._rebuild_cells()

    def set_badges(self, badges):
        """给部分文件加右下角标记 (查重结果里的 保留 / 重复)

        @param badges: {路径: 标记文本}
        """
        self._badges = dict(badges)
        self._relayout()

    def set_secondary_text(self, provider):
        """列表视图里在名称右侧补一列次要文字

        批量重命名用它显示改后的文件名, 行内同时画出 源名称 -> 新名称

        @param provider: callable(path) -> 文本, 传 None 时恢复普通列表
        """
        self._secondary = provider
        self._relayout()

    def content_height(self):
        """把全部内容画出来需要的高度

        页面用它把宿主容器撑到刚好放下所有行, 是否滚动交给外层决定

        @return: 像素高度
        """
        if self._view == "list":
            return max(len(self._paths), 1) * LIST_ROW_HEIGHT
        cell_width, cell_height = self._cell_size()
        width = max(self.canvas.winfo_width(), 1)
        cols = max(1, int((width - GRID_PAD * 2 + CELL_GAP) // cell_width))
        rows = (len(self._paths) + cols - 1) // cols
        return max(rows, 1) * cell_height

    def select(self, path):
        """设置选中项并触发 on_select; path 为 None 表示取消选中

        @param path: 文件路径
        """
        if path == self._selected:
            return
        previous, self._selected = self._selected, path
        self._paint_selection(previous)
        self._paint_selection(path)
        if self._on_select is not None:
            self._on_select(path)

    def apply_palette(self):
        """按当前主题刷新画布背景, 文件文字与占位缩略图"""
        color = self.theme.rgb(self._surface)
        try:
            self.configure(bg=color)
            self.canvas.configure(bg=color)
        except tk.TclError:
            return
        self._photo_cache.clear()
        self._placeholder_cache = None
        self._relayout()

    # ---------------- 尺寸与字体 ----------------
    def _label_size(self):
        """名称字号; 列表视图固定, 缩略图视图随档位变化

        @return: 字号 (像素)
        """
        if self._view == "list":
            return LIST_FONT_SIZE
        return TIER_SPECS[self._tier][2]

    def _label_font(self):
        """测量用的字体对象

        @return: tkfont.Font
        """
        if self._font is None:
            self._font = tkfont.Font(font=sans(self._label_size()))
        return self._font

    def _display_font(self, selected):
        """名称使用的字体配置

        @param selected: 是否选中
        @return: 字体元组
        """
        return sans(self._label_size(), selected)

    def _box_size(self):
        """缩略图方框的尺寸

        @return: (宽, 高)
        """
        spec = TIER_SPECS[self._tier]
        return spec[0], spec[1]

    def _cell_size(self):
        """单个格子的尺寸 (含名称与行间距)

        @return: (宽, 高)
        """
        box_width, box_height = self._box_size()
        if self._view == "list":
            return 1, LIST_ROW_HEIGHT
        line = self._label_font().metrics("linespace")
        return (box_width + CELL_GAP,
                box_height + LABEL_GAP + line + CELL_GAP)

    # ---------------- 单元格 ----------------
    def _rebuild_cells(self):
        """按当前文件列表重建画布上的元素"""
        self.canvas.delete("cell")
        self._cells = {}
        for path in self._paths:
            self._cells[path] = {
                "ring": self.canvas.create_rectangle(0, 0, 0, 0, fill="",
                                                     outline="", tags="cell"),
                "placeholder": self.canvas.create_image(0, 0, anchor="center",
                                                        tags="cell"),
                "image": self.canvas.create_image(0, 0, anchor="center",
                                                  tags="cell"),
                "text": self.canvas.create_text(0, 0, anchor="n", text="",
                                                font=self._label_font(),
                                                tags="cell"),
                "badge_bg": self.canvas.create_rectangle(0, 0, 0, 0, fill="",
                                                         outline="",
                                                         state="hidden",
                                                         tags="cell"),
                "badge": self.canvas.create_text(0, 0, anchor="se", text="",
                                                 font=sans(BADGE_FONT_SIZE),
                                                 state="hidden", tags="cell"),
                "line": self.canvas.create_rectangle(0, 0, 0, 0, fill="",
                                                    outline="",
                                                    state="hidden",
                                                    tags="cell"),
                "bar": self.canvas.create_rectangle(0, 0, 0, 0, fill="",
                                                    outline="",
                                                    state="hidden",
                                                    tags="cell"),
                "mark": self.canvas.create_text(0, 0, anchor="w", text="",
                                                state="hidden", tags="cell"),
                "arrow": self.canvas.create_text(0, 0, anchor="e", text="",
                                                 state="hidden", tags="cell"),
                "secondary": self.canvas.create_text(0, 0, anchor="w", text="",
                                                     state="hidden",
                                                     tags="cell"),
            }
        self._relayout()

    def _relayout(self):
        if self._view == "list":
            self._relayout_list()
        else:
            self._relayout_icons()
        self._ensure_visible()

    def _relayout_icons(self):
        """缩略图视图: 每个格子是方框图 + 下方名称"""
        box_width, box_height = self._box_size()
        cell_width, cell_height = self._cell_size()
        width = max(1, self.canvas.winfo_width())
        cols = max(1, int((width - GRID_PAD * 2 + CELL_GAP) // cell_width))
        self._cols = cols
        font = self._label_font()
        for index, path in enumerate(self._paths):
            cell = self._cells.get(path)
            if cell is None:
                continue
            row, col = divmod(index, cols)
            left = GRID_PAD + col * cell_width
            top = GRID_PAD + row * cell_height
            center_x = left + box_width / 2
            self._place_box(cell, left, top, box_width, box_height)
            self.canvas.coords(cell["text"], center_x,
                               top + box_height + LABEL_GAP)
            self.canvas.itemconfigure(
                cell["text"], anchor="n",
                text=_fit_text(font, os.path.basename(path), box_width))
            self._place_badge(cell, left, top, box_width, box_height, path)
        rows = (len(self._paths) + cols - 1) // cols
        content = max(cell_height * rows + GRID_PAD * 2,
                      self.canvas.winfo_height())
        self.canvas.configure(scrollregion=(0, 0, width, content))
        for path in self._cells:
            self._paint_selection(path)

    def _place_box(self, cell, left, top, box_width, box_height):
        """摆放一个格子的方框图与缩略图

        @param cell: 格子元素字典
        @param left: 方框左边界
        @param top: 方框上边界
        @param box_width: 方框宽度
        @param box_height: 方框高度
        """
        self.canvas.coords(cell["ring"], left, top, left + box_width,
                           top + box_height)
        center_x = left + box_width / 2
        center_y = top + box_height / 2
        self.canvas.coords(cell["placeholder"], center_x, center_y)
        self.canvas.coords(cell["image"], center_x, center_y)

    def _place_badge(self, cell, left, top, box_width, box_height, path):
        """摆放右下角的标记块

        @param cell: 格子元素字典
        @param left: 方框左边界
        @param top: 方框上边界
        @param box_width: 方框宽度
        @param box_height: 方框高度
        @param path: 文件路径
        """
        text = self._badges.get(path, "")
        if not text:
            self.canvas.itemconfigure(cell["badge"], state="hidden")
            self.canvas.itemconfigure(cell["badge_bg"], state="hidden")
            return
        font = tkfont.Font(font=sans(BADGE_FONT_SIZE))
        text_width = font.measure(text)
        line = font.metrics("linespace")
        right = left + box_width - BADGE_INSET
        bottom = top + box_height - BADGE_INSET
        self.canvas.itemconfigure(cell["badge"], state="normal", text=text)
        self.canvas.coords(cell["badge"], right - scale(5), bottom - 1)
        self.canvas.coords(cell["badge_bg"], right - text_width - scale(10),
                           bottom - line - scale(2), right, bottom)
        self.canvas.itemconfigure(cell["badge_bg"], state="normal")

    def _relayout_list(self):
        """列表视图: 每行一项, 名称在左 行间 1 像素分隔线"""
        width = max(1, self.canvas.winfo_width())
        font = self._label_font()
        middle = width / 2
        for index, path in enumerate(self._paths):
            cell = self._cells.get(path)
            if cell is None:
                continue
            top = GRID_PAD + index * LIST_ROW_HEIGHT
            center = top + LIST_ROW_HEIGHT / 2
            self.canvas.coords(cell["ring"], 0, top, width,
                               top + LIST_ROW_HEIGHT)
            self.canvas.coords(cell["placeholder"], -100, -100)
            self.canvas.coords(cell["image"], -100, -100)
            if self._secondary is None:
                self.canvas.coords(cell["text"], scale(12), center)
                self.canvas.itemconfigure(
                    cell["text"], anchor="w",
                    text=_fit_text(font, os.path.basename(path),
                                   width - scale(40)))
            else:
                self.canvas.coords(cell["text"], scale(12) + LIST_MARK_WIDTH,
                                   center)
                self.canvas.itemconfigure(
                    cell["text"], anchor="w",
                    text=_fit_text(font, os.path.basename(path),
                                   middle - scale(40) - LIST_MARK_WIDTH))
                self._draw_secondary(cell, path, middle, center, width)
            if self._secondary is None:
                for name in ("mark", "arrow", "secondary"):
                    self.canvas.itemconfigure(cell[name], state="hidden")
            self.canvas.itemconfigure(cell["badge"], state="hidden")
            self.canvas.itemconfigure(cell["badge_bg"], state="hidden")
            self.canvas.coords(cell["line"], 0, top + LIST_ROW_HEIGHT - 1,
                               width, top + LIST_ROW_HEIGHT)
            self.canvas.itemconfigure(
                cell["line"], state="normal" if index < len(self._paths) - 1
                else "hidden", fill=self.theme.rgb("hair"))
            self.canvas.coords(cell["bar"], 0, top, scale(2),
                               top + LIST_ROW_HEIGHT)
        content = max(len(self._paths) * LIST_ROW_HEIGHT + GRID_PAD * 2,
                      self.canvas.winfo_height())
        self.canvas.configure(scrollregion=(0, 0, width, content))
        for path in self._cells:
            self._paint_selection(path)

    def _draw_secondary(self, cell, path, middle, center, width):
        """画出 勾选字形 箭头 与新名称三样东西

        @param cell: 格子元素字典
        @param path: 文件路径
        @param middle: 行的水平中点
        @param center: 行的垂直中点
        @param width: 行宽
        """
        self.canvas.coords(cell["mark"], scale(12), center)
        self.canvas.itemconfigure(
            cell["mark"], state="normal", font=icon(SIZE_SECTION),
            text=ICON_CHECK, fill=self.theme.rgb("muted"))
        self.canvas.coords(cell["arrow"], middle - scale(10), center)
        self.canvas.itemconfigure(
            cell["arrow"], state="normal", font=icon(SIZE_SECTION),
            text=ICON_ARROW, fill=self.theme.rgb("muted"))
        self.canvas.coords(cell["secondary"], middle + scale(23), center)
        self.canvas.itemconfigure(
            cell["secondary"], state="normal", anchor="w",
            text=_fit_text(self._label_font(), self._secondary(path) or "",
                           width - middle - scale(40)),
            font=mono(self._label_size()),
            fill=self.theme.rgb("accent"))

    def _paint_selection(self, path):
        """刷新一个格子的选中态

        @param path: 文件路径
        """
        cell = self._cells.get(path)
        if cell is None:
            return
        selected = path == self._selected
        if self._view == "list":
            if self._secondary is None:
                for name in ("mark", "arrow", "secondary"):
                    self.canvas.itemconfigure(cell[name], state="hidden")
            self.canvas.itemconfigure(cell["placeholder"], state="hidden")
            self.canvas.itemconfigure(cell["image"], state="hidden")
            self.canvas.itemconfigure(cell["ring"], state="hidden")
            self.canvas.itemconfigure(
                cell["bar"], state="normal" if selected else "hidden",
                fill=self.theme.rgb("accent"))
            self.canvas.itemconfigure(
                cell["text"], anchor="w",
                fill=self.theme.rgb("accent" if selected else "text"),
                font=self._display_font(selected))
            return
        self.canvas.itemconfigure(cell["line"], state="hidden")
        self.canvas.itemconfigure(cell["bar"], state="hidden")
        self.canvas.itemconfigure(cell["ring"], state="normal")
        self.canvas.itemconfigure(
            cell["ring"], fill="", width=scale(2) if selected else 1,
            outline=self.theme.rgb("accent" if selected
                                   else "thumb_edge"))
        self.canvas.itemconfigure(
            cell["text"],
            fill=self.theme.rgb("accent" if selected else "muted"),
            font=self._display_font(selected))

    # ---------------- 缩略图加载 ----------------
    def _load_worker(self, paths):
        for path in paths:
            img = load_thumbnail(path, CACHE_SIZE) if _is_image(path) else None
            self._queue.put((path, img))
        self._queue.put(None)

    def _pump(self):
        self._pump_job = None
        finished = False
        for _ in range(BATCH):
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                break
            if item is None:
                finished = True
                break
            path, img = item
            self._pil_cache[path] = img
            self._paint(path)

        if finished:
            self._loading = False
            self._requested.clear()
            self._prune_cache()
            self._ensure_visible()  # 读取期间可能又滚到了别处
            return
        if self._loading:
            self._pump_job = self.after(POLL_MS, self._pump)

    def _visible_range(self):
        """当前视口覆盖到的下标范围, 上下各多留 OVERSCAN_ROWS 行

        @return: (起始下标, 结束下标), 结束下标不包含在内
        """
        if not self._paths:
            return 0, 0
        if self._view == "list":
            row_height, cols = LIST_ROW_HEIGHT, 1
        else:
            _, cell_height = self._cell_size()
            row_height, cols = cell_height, self._cols
        top = self.canvas.canvasy(0)
        bottom = top + max(1, self.canvas.winfo_height())
        first_row = max(0, int((top - GRID_PAD) // row_height) - OVERSCAN_ROWS)
        last_row = int((bottom - GRID_PAD) // row_height) + OVERSCAN_ROWS
        return (min(first_row * cols, len(self._paths)),
                min((last_row + 1) * cols, len(self._paths)))

    def _ensure_visible(self):
        """补齐视口内的缩略图: 已缓存的直接贴, 没读过的排给后台线程

        滚动 换档 换展示方式与容器尺寸变化都走这里, 因此只有看得见的图会去读盘;
        已经有一批在读取时先不急, 等它读完会再走一次本方法
        """
        first, last = self._visible_range()
        missing = []
        for path in self._paths[first:last]:
            if path in self._pil_cache:
                if path not in self._photo_cache:
                    self._paint(path)
            elif path not in self._requested:
                missing.append(path)
        if not missing or self._loading:
            return
        self._requested.update(missing)
        self._queue = queue.Queue()
        self._loading = True
        threading.Thread(target=self._load_worker, args=(missing,),
                         daemon=True).start()
        if self._pump_job is None:
            self._pump_job = self.after(POLL_MS, self._pump)

    def _schedule_visible(self):
        """把补载推迟到滚动停下来之后, 连续滚动时不必反复算可见范围"""
        if self._visible_job is not None:
            try:
                self.after_cancel(self._visible_job)
            except tk.TclError:
                pass
        self._visible_job = self.after(SCROLL_MS, self._do_ensure_visible)

    def _do_ensure_visible(self):
        self._visible_job = None
        self._ensure_visible()

    def _prune_cache(self):
        """缓存超出上限时丢掉视口之外最久没贴过的缩略图, 免得内存一直涨

        视口内的不淘汰: 否则刚贴上的图会被丢掉又立刻重排一次, 来回读盘
        """
        first, last = self._visible_range()
        keep = set(self._paths[first:last])
        limit = max(CACHE_LIMIT, len(keep))
        for path in list(self._pil_cache):
            if len(self._pil_cache) <= limit:
                break
            if path in keep:
                continue
            del self._pil_cache[path]
            self._photo_cache.pop(path, None)

    def _paint(self, path):
        """把缩略图贴到格子; 用到就重新插到缓存尾部, 字典顺序即最近使用顺序

        @param path: 文件路径
        """
        cell = self._cells.get(path)
        if cell is None:
            return
        photo = self._photo_cache.pop(path, None)
        if photo is None:
            photo, placeholder = self._make_photo(path)
        else:
            placeholder = self._placeholder_photo()
        self._photo_cache[path] = photo
        if path in self._pil_cache:
            self._pil_cache[path] = self._pil_cache.pop(path)
        self.canvas.itemconfigure(cell["image"], image=photo,
                                  state="normal" if photo is not None
                                  else "hidden")
        self.canvas.itemconfigure(cell["placeholder"], image=placeholder,
                                  state="hidden" if photo is not None
                                  else "normal")

    def _make_photo(self, path):
        """按缩略图方框尺寸生成要贴的图

        @param path: 文件路径
        @return: (缩略图 PhotoImage 或 None, 占位渐变 PhotoImage)
        """
        box_width, box_height = self._box_size()
        img = self._pil_cache.get(path)
        photo = None
        if img is not None:
            scaled = img.copy()
            scaled.thumbnail((box_width, box_height))
            photo = ImageTk.PhotoImage(scaled)
        return photo, self._placeholder_photo()

    def _placeholder_photo(self):
        """占位用的渐变图, 按当前档位缓存一份

        @return: PhotoImage
        """
        if self._placeholder_cache is not None:
            return self._placeholder_cache
        palette = self.theme.palette
        image = make_gradient(self._box_size(), _rgb(palette["ph1"]),
                              _rgb(palette["ph2"]))
        self._placeholder_cache = ImageTk.PhotoImage(image)
        return self._placeholder_cache

    def _stop_pump(self):
        """页面切走或销毁时停掉所有定时器"""
        for name in ("_pump_job", "_layout_job", "_visible_job"):
            job = getattr(self, name)
            if job is not None:
                try:
                    self.after_cancel(job)
                except tk.TclError:
                    pass
                setattr(self, name, None)
        self._loading = False

    # ---------------- 交互 ----------------
    def _hit(self, x, y):
        """把控件坐标换算成画布坐标后判断点到了哪一项

        event.x/y 是相对控件的坐标, 画布滚动过之后与画布坐标相差一个偏移量,
        不换算就会点中另一项

        @param x: 相对控件的横坐标
        @param y: 相对控件的纵坐标
        @return: 命中的文件路径, 没有命中时返回 None
        """
        x = self.canvas.canvasx(x)
        y = self.canvas.canvasy(y)
        if self._view == "list":
            row = int((y - GRID_PAD) // LIST_ROW_HEIGHT)
            if 0 <= row < len(self._paths):
                return self._paths[row]
            return None
        cell_width, cell_height = self._cell_size()
        col = int((x - GRID_PAD) // cell_width)
        row = int((y - GRID_PAD) // cell_height)
        # 每一行的右侧与下方间距不属于任何格子
        if (col < 0 or row < 0 or col >= self._cols
                or x - GRID_PAD - col * cell_width > self._box_size()[0]):
            return None
        index = row * self._cols + col
        if 0 <= index < len(self._paths):
            return self._paths[index]
        return None

    def _on_click(self, event):
        self.select(self._hit(event.x, event.y))

    def _on_double_click(self, event):
        path = self._hit(event.x, event.y)
        if path is None:
            return
        self.select(path)
        if self._on_activate is not None:
            self._on_activate(path)

    def _on_right_click(self, event):
        path = self._hit(event.x, event.y)
        if path is None:
            return
        self.select(path)
        if self._on_context is not None:
            self._on_context(path, event)

    def _on_resize(self, _event):
        if self._layout_job is not None:
            try:
                self.after_cancel(self._layout_job)
            except tk.TclError:
                pass
        self._layout_job = self.after(RELAYOUT_MS, self._do_relayout)

    def _do_relayout(self):
        self._layout_job = None
        self._relayout()

    def _on_destroy(self, event):
        if event.widget is not self:
            return
        self._stop_pump()
        unbind_mousewheel(self.canvas)
