"""提供虚拟滚动和后台缩略图加载的文件视图。

仅读取和解码可见文件, 用户切换视图或缩放档位时仍可复用已缓存的缩略图。
"""

import os
import queue
import threading
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

from PIL import ImageTk

from ..imaging import load_thumbnail, make_placeholder
from ..theme import sans
from ..widgets import bind_mousewheel, unbind_mousewheel
from .constants import (
    BATCH,
    CACHE_LIMIT,
    CACHE_SIZE,
    DEFAULT_TIER,
    DEFAULT_VIEW,
    GRID_PAD,
    IMAGE_EXTS,
    LABEL_GAP,
    LIST_FONT_SIZE,
    LIST_ICON,
    LIST_ROW_HEIGHT,
    OVERSCAN_ROWS,
    POLL_MS,
    RELAYOUT_MS,
    SCROLL_MS,
    TIER_SPECS,
    VIEWS,
)


def _fit_text(font, name, max_width):
    """按像素宽度截断文件名, 超长时补省略号。"""
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
    """按扩展名判断是否真的去读图; 其余类型直接给占位图。

    这一步避开了对文本与表格文件的读取, 也不会在额外的
    类型上占用文件句柄
    """
    return os.path.splitext(path)[1].lower() in IMAGE_EXTS


class FileGrid(ttk.Frame):
    """把一组文件按列表或缩略图排列, 支持选中, 双击与右键。

    参数:
        master:      父容器
        theme:       ThemeManager
        on_select:   callable(path), 选中项变化时调用, 未选中时 path 为 None
        on_activate: callable(path), 双击某一项时调用
        on_context:  callable(path, event), 右键某一项时调用
        tier:        初始档位, 见 constants.TIERS
        view:        初始展示方式, 见 constants.VIEWS
        surface:     所在的表面层, bg 表示页面底色, card 表示卡片
    """

    def __init__(self, master, theme, on_select=None, on_activate=None,
                 on_context=None, tier=DEFAULT_TIER,
                 view=DEFAULT_VIEW, surface="bg"):
        super().__init__(master,
                         style="Card.TFrame" if surface == "card" else "TFrame")
        self.theme = theme
        self._surface = surface
        self._on_select = on_select
        self._on_activate = on_activate
        self._on_context = on_context

        self._paths = []
        self._cells = {}
        self._pil_cache = {}
        self._photo_cache = {}
        self._selected = None
        self._tier = tier
        self._view = view
        self._icon = (LIST_ICON if view == "list"
                      else TIER_SPECS[tier][0])
        self._font = None
        self._cols = 1

        #: 已经排给后台线程但还没拿到结果的路径
        self._requested = set()
        self._queue = queue.Queue()
        self._loading = False
        self._pump_job = None
        self._layout_job = None
        self._visible_job = None

        self.canvas = tk.Canvas(self, highlightthickness=0, bd=0)
        self.canvas._thione_surface = surface
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scroll = ttk.Scrollbar(self, orient="vertical",
                                    command=self.canvas.yview)
        self.scroll.pack(side="right", fill="y")
        self.canvas.configure(yscrollcommand=self._on_yscroll)

        bind_mousewheel(self.canvas, self.canvas)
        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<Double-1>", self._on_double_click)
        self.canvas.bind("<Button-3>", self._on_right_click)
        self.canvas.bind("<Configure>", self._on_resize)
        self.bind("<Destroy>", self._on_destroy)
        self._apply_palette()

    # ---------------- 对外接口 ----------------
    @property
    def tier(self):
        """当前档位。"""
        return self._tier

    @property
    def view(self):
        """当前展示方式。"""
        return self._view

    @property
    def loading(self):
        """是否仍在后台读取缩略图。"""
        return self._loading

    def selected_path(self):
        """当前选中的文件路径, 未选中时返回 None。"""
        return self._selected

    def set_files(self, paths):
        """重新加载一组文件, 清空缓存与选中; 不触发 on_select。"""
        self._stop_pump()
        self._paths = list(paths)
        self._pil_cache.clear()
        self._photo_cache.clear()
        self._selected = None
        self._requested.clear()
        self._rebuild_cells()

    def clear(self):
        """清空内容。"""
        self.set_files([])

    def set_tier(self, tier):
        """切换缩略图大小档位; 已缓存的图片直接按新尺寸重画。"""
        if tier not in TIER_SPECS or tier == self._tier:
            return
        self._tier = tier
        if self._view == "list":
            return  # 列表视图不随档位变化, 只记住这次选择
        self._icon = TIER_SPECS[tier][0]
        self._font = None
        self._photo_cache.clear()
        self._rebuild_cells()

    def set_view(self, view):
        """切换列表视图与缩略图视图; 已缓存的图片直接按新布局重画。"""
        if view not in VIEWS or view == self._view:
            return
        self._view = view
        self._icon = (LIST_ICON if view == "list"
                      else TIER_SPECS[self._tier][0])
        self._font = None
        self._photo_cache.clear()
        self._rebuild_cells()

    def select(self, path):
        """设置选中项并触发 on_select; path 为 None 表示取消选中。"""
        if path == self._selected:
            return
        previous, self._selected = self._selected, path
        self._paint_selection(previous)
        self._paint_selection(path)
        if self._on_select is not None:
            self._on_select(path)

    def _apply_palette(self):
        """初始化画布背景和选中项颜色。"""
        p = self.theme.palette
        try:
            self.canvas.configure(bg=p[self._surface])
        except tk.TclError:
            return
        for path in self._cells:
            self._paint_selection(path)

    # ---------------- 单元格 ----------------
    def _label_size(self):
        """名称字号; 列表视图固定, 缩略图视图随档位变化。"""
        if self._view == "list":
            return LIST_FONT_SIZE
        return TIER_SPECS[self._tier][1]

    def _label_font(self):
        if self._font is None:
            self._font = tkfont.Font(font=sans(self._label_size()))
        return self._font

    def _cell_size(self):
        icon, _, pad = TIER_SPECS[self._tier]
        line = self._label_font().metrics("linespace")
        return icon + pad * 2, icon + LABEL_GAP + line + pad * 2

    def _rebuild_cells(self):
        self.canvas.delete("cell")
        self._cells = {}
        font = self._label_font()
        for path in self._paths:
            self._cells[path] = {
                "rect": self.canvas.create_rectangle(0, 0, 0, 0, fill="",
                                                     outline="", tags="cell"),
                "image": self.canvas.create_image(0, 0, anchor="center",
                                                  tags="cell"),
                "text": self.canvas.create_text(0, 0, anchor="n", text="",
                                                font=font, tags="cell"),
            }
        self._relayout()

    def _relayout(self):
        if self._view == "list":
            self._relayout_list()
        else:
            self._relayout_icons()
        self._ensure_visible()

    def _relayout_icons(self):
        icon, _, pad = TIER_SPECS[self._tier]
        cell_w, cell_h = self._cell_size()
        width = max(1, self.canvas.winfo_width())
        cols = max(1, (width - GRID_PAD * 2) // cell_w)
        self._cols = cols
        font = self._label_font()
        for index, path in enumerate(self._paths):
            cell = self._cells.get(path)
            if cell is None:
                continue
            row, col = divmod(index, cols)
            left = GRID_PAD + col * cell_w
            top = GRID_PAD + row * cell_h
            center = left + cell_w / 2
            self.canvas.coords(cell["rect"], left + 3, top + 3,
                               left + cell_w - 3, top + cell_h - 3)
            self.canvas.coords(cell["image"], center, top + pad + icon / 2)
            self.canvas.coords(cell["text"], center,
                               top + pad + icon + LABEL_GAP)
            self.canvas.itemconfigure(
                cell["text"], anchor="n",
                text=_fit_text(font, os.path.basename(path), cell_w - 10))
        rows = (len(self._paths) + cols - 1) // cols
        content = max(cell_h * rows + GRID_PAD * 2,
                      self.canvas.winfo_height())
        self.canvas.configure(scrollregion=(0, 0, width, content))
        for path in self._cells:
            self._paint_selection(path)

    def _relayout_list(self):
        """列表视图: 每行一项, 小图标在左 名称在右。"""
        width = max(1, self.canvas.winfo_width())
        row_width = max(LIST_ICON * 2, width - GRID_PAD * 2)
        font = self._label_font()
        for index, path in enumerate(self._paths):
            cell = self._cells.get(path)
            if cell is None:
                continue
            top = GRID_PAD + index * LIST_ROW_HEIGHT
            center = top + LIST_ROW_HEIGHT / 2
            self.canvas.coords(cell["rect"], GRID_PAD + 2, top + 1,
                               GRID_PAD + row_width - 2,
                               top + LIST_ROW_HEIGHT - 1)
            self.canvas.coords(cell["image"],
                               GRID_PAD + 6 + LIST_ICON / 2, center)
            self.canvas.coords(cell["text"], GRID_PAD + 12 + LIST_ICON, center)
            self.canvas.itemconfigure(
                cell["text"], anchor="w",
                text=_fit_text(font, os.path.basename(path),
                               row_width - LIST_ICON - 26))
        content = max(len(self._paths) * LIST_ROW_HEIGHT + GRID_PAD * 2,
                      self.canvas.winfo_height())
        self.canvas.configure(scrollregion=(0, 0, width, content))
        for path in self._cells:
            self._paint_selection(path)

    def _paint_selection(self, path):
        cell = self._cells.get(path)
        if cell is None:
            return
        p = self.theme.palette
        selected = path == self._selected
        self.canvas.itemconfigure(
            cell["rect"],
            fill=p["accent_weak"] if selected else "",
            outline=p["accent"] if selected else "",
        )
        self.canvas.itemconfigure(
            cell["text"], fill=p["link"] if selected else p["muted"])

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
        """当前视口覆盖到的下标范围, 上下各多留 OVERSCAN_ROWS 行。

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
        """补齐视口内的缩略图: 已缓存的直接贴, 没读过的排给后台线程。

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
        """把补载推迟到滚动停下来之后, 连续滚动时不必反复算可见范围。"""
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
        """缓存超出上限时丢掉视口之外最久没贴过的缩略图, 免得内存一直涨。

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
        """把缩略图贴到格子; 用到就重新插到缓存尾部, 字典顺序即最近使用顺序。"""
        cell = self._cells.get(path)
        if cell is None:
            return
        photo = self._photo_cache.pop(path, None)
        if photo is None:
            photo = self._make_photo(path)
        self._photo_cache[path] = photo
        if path in self._pil_cache:
            self._pil_cache[path] = self._pil_cache.pop(path)
        self.canvas.itemconfigure(cell["image"], image=photo)

    def _make_photo(self, path):
        img = self._pil_cache.get(path)
        if img is None:
            img = make_placeholder((self._icon, self._icon),
                                   self.theme.palette["placeholder"])
        else:
            img = img.copy()
            img.thumbnail((self._icon, self._icon))
        return ImageTk.PhotoImage(img)

    def _stop_pump(self):
        if self._pump_job is not None:
            try:
                self.after_cancel(self._pump_job)
            except tk.TclError:
                pass
            self._pump_job = None
        if self._layout_job is not None:
            try:
                self.after_cancel(self._layout_job)
            except tk.TclError:
                pass
            self._layout_job = None
        if self._visible_job is not None:
            try:
                self.after_cancel(self._visible_job)
            except tk.TclError:
                pass
            self._visible_job = None
        self._loading = False

    # ---------------- 交互 ----------------
    def _hit(self, x, y):
        """把控件坐标换算成画布坐标后判断点到了哪一项。

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
        cell_w, cell_h = self._cell_size()
        col = int((x - GRID_PAD) // cell_w)
        row = int((y - GRID_PAD) // cell_h)
        if col < 0 or row < 0 or col >= self._cols:
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

    def _on_yscroll(self, first, last):
        """滚动条位置变化时同步滑块, 并安排补载新进入视口的缩略图。"""
        self.scroll.set(first, last)
        self._schedule_visible()

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
