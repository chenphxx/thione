"""批量重命名的多选文件类型筛选"""

import os
import tkinter as tk
from tkinter import ttk

from ... import kit
from ...dpi import scale
from ...theme import tint
from ...widgets import bind_mousewheel, unbind_mousewheel

#: 弹出列表一次最多展示的类型数
MAX_VISIBLE_TYPES = 10

#: 一行类型选项的高度
ROW_HEIGHT = scale(28)

#: 弹出列表的最小宽度
MIN_POPUP_WIDTH = scale(180)


def file_type(name):
    """取文件名对应的扩展名

    @param name: 文件名或完整路径
    @return: 小写扩展名, 没有扩展名时返回空串
    """
    return os.path.splitext(name)[1].lower()


def type_label(extension):
    """把扩展名转成界面上显示的文字

    @param extension: 扩展名
    @return: 用于展示的类型名称
    """
    return extension or "无扩展名"


class TypeFilter(kit.Field):
    """可多选文件类型的筛选框

    内部始终保留全部类型列表; 全部选中时 selected_values 返回 None,
    子集选中时返回小写扩展名集合, 空集合表示不显示任何文件
    """

    def __init__(self, master, theme, command=None, width=170,
                 surface="canvas"):
        super().__init__(master, theme, value="全部类型", surface=surface,
                         token="text", mono_font=False, width=width,
                         chevron=True)
        self._command = command
        self._values = []
        self._all = True
        self._selected = set()
        self._popup = None
        for widget in (self, self.label, self.chevron):
            widget.configure(cursor="hand2")
            widget.bind("<Button-1>", self._on_click)
        self.bind("<Destroy>", self._on_destroy)

    def set_values(self, values):
        """替换可筛选的文件类型

        如果当前选中的类型在新列表中全部消失, 自动回到全部类型;
        用户主动取消全部勾选时不会被这里改回全部类型

        @param values: 扩展名序列
        """
        self._values = sorted(set(values), key=lambda value: (value != "", value))
        if self._all:
            self._selected = set(self._values)
        else:
            requested = set(self._selected)
            self._selected.intersection_update(self._values)
            if requested and not self._selected:
                self._all = True
                self._selected = set(self._values)
        self.close_popup()
        self._update_text()

    def selected_values(self):
        """当前筛选结果

        @return: 全部类型时返回 None, 否则返回扩展名集合
        """
        if self._all:
            return None
        return set(self._selected)

    def _on_click(self, _event=None):
        if self._popup is not None:
            self.close_popup()
            return "break"
        if not self._values:
            return "break"
        self._popup = _TypeFilterPopup(self)
        self._popup.open()
        return "break"

    def close_popup(self):
        """关闭已经打开的类型列表"""
        popup, self._popup = self._popup, None
        if popup is not None:
            popup.close()

    def _toggle_all(self, checked):
        """切换全部类型"""
        self._all = bool(checked)
        self._selected = set(self._values) if self._all else set()
        self._changed()

    def _toggle_type(self, extension, checked):
        """切换单个类型"""
        if self._all:
            self._all = False
            self._selected = set(self._values)
        if checked:
            self._selected.add(extension)
        else:
            self._selected.discard(extension)
        self._changed()

    def _changed(self):
        self._update_text()
        if self._popup is not None:
            self._popup.sync()
        kit.invoke(self._command, self.selected_values())

    def _update_text(self):
        """按当前选择更新控件框里的摘要"""
        if self._all:
            text, token = "全部类型", "text"
        elif not self._selected:
            text, token = "未选择类型", "muted"
        elif len(self._selected) == 1:
            text, token = type_label(next(iter(self._selected))), "text"
        elif len(self._selected) == 2:
            text = ", ".join(type_label(value)
                             for value in sorted(self._selected))
            token = "text"
        else:
            text, token = f"{len(self._selected)} 种类型", "text"
        self.set(text, token=token)

    def _on_destroy(self, event):
        if event.widget is self:
            self.close_popup()


class _TypeFilterPopup:
    """文件类型多选弹出列表"""

    def __init__(self, field):
        self.field = field
        self.theme = field.theme
        self.window = None
        self.canvas = None
        self.items = None
        self.all_var = None
        self.type_vars = {}

    def open(self):
        """在筛选框下方弹出类型列表"""
        field = self.field
        field.update_idletasks()
        values = list(field._values)
        width = max(field.winfo_width(), MIN_POPUP_WIDTH)
        visible = min(len(values), MAX_VISIBLE_TYPES)
        list_height = max(1, visible) * ROW_HEIGHT
        padding = scale(6)

        self.window = tk.Toplevel(field)
        self.window.withdraw()
        self.window.overrideredirect(True)
        self.window.transient(field.winfo_toplevel())
        self.window.configure(bg=self.theme.rgb("hair"))

        inner = tk.Frame(self.window, bd=0, highlightthickness=0)
        tint(inner, bg="panel")
        inner.configure(bg=self.theme.rgb("panel"))
        inner.pack(fill="both", expand=True, padx=1, pady=1)

        body = tk.Frame(inner, bd=0, highlightthickness=0)
        tint(body, bg="panel")
        body.configure(bg=self.theme.rgb("panel"))
        body.pack(fill="both", expand=True, padx=padding, pady=padding)

        all_row = self._row(body)
        self.all_var = tk.BooleanVar(value=field._all)
        all_check = kit.Check(all_row, self.theme, value="全部类型",
                              variable=self.all_var,
                              command=field._toggle_all, surface="panel")
        all_check.pack(fill="both", expand=True)

        kit.hairline(body, self.theme).pack(fill="x", pady=(scale(3), scale(3)))

        self.canvas = tk.Canvas(body, width=width - padding * 2 - 1,
                                height=list_height, bd=0,
                                highlightthickness=0)
        tint(self.canvas, bg="panel")
        self.canvas.configure(bg=self.theme.rgb("panel"))
        self.canvas.pack(side="left", fill="both", expand=True)
        if len(values) > MAX_VISIBLE_TYPES:
            scroll = ttk.Scrollbar(
                body, orient="vertical", command=self.canvas.yview,
                style="Thin.Vertical.TScrollbar")
            self.canvas.configure(yscrollcommand=scroll.set)
            scroll.pack(side="right", fill="y", padx=(scale(3), 0))

        self.items = tk.Frame(self.canvas, bd=0, highlightthickness=0)
        tint(self.items, bg="panel")
        self.items.configure(bg=self.theme.rgb("panel"))
        self.canvas.create_window(
            (0, 0), window=self.items, anchor="nw",
            width=width - padding * 2 - scale(12))
        for value in values:
            row = self._row(self.items)
            variable = tk.BooleanVar(
                value=field._all or value in field._selected)
            check = kit.Check(
                row, self.theme, value=type_label(value), variable=variable,
                command=lambda checked, item=value:
                field._toggle_type(item, checked),
                surface="panel")
            check.pack(fill="both", expand=True)
            self.type_vars[value] = variable
        self.items.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        bind_mousewheel((self.items, self.canvas), self.canvas,
                        recursive=True)

        self.window.update_idletasks()
        height = self.window.winfo_reqheight()
        x = field.winfo_rootx()
        y = field.winfo_rooty() + field.winfo_height()
        screen_height = field.winfo_screenheight()
        margin = scale(8)
        if y + height > screen_height - margin:
            above = field.winfo_rooty() - height - scale(2)
            y = above if above > margin else max(
                margin, screen_height - height - margin)
        self.window.geometry("%dx%d+%d+%d" % (width + 2, height + 2, x, y))
        self.window.deiconify()
        self.window.lift()
        try:
            self.window.attributes("-topmost", True)
        except tk.TclError:
            pass
        self.window.grab_set()
        for widget in (self.window, inner, body, self.canvas, self.items):
            widget.bind("<Button-1>", self._on_background_click)
        self.window.bind("<Escape>", lambda _event: self.field.close_popup())

    def sync(self):
        """把筛选框的选择状态同步到全部勾选项"""
        self.all_var.set(self.field._all)
        for value, variable in self.type_vars.items():
            variable.set(self.field._all or value in self.field._selected)

    def close(self):
        """关闭弹出列表并清理滚轮绑定"""
        window, self.window = self.window, None
        if window is None:
            return
        unbind_mousewheel(self.canvas)
        try:
            window.grab_release()
            window.destroy()
        except tk.TclError:
            pass

    def _row(self, parent):
        """建立固定高度的类型行"""
        row = tk.Frame(parent, height=ROW_HEIGHT, bd=0,
                       highlightthickness=0)
        tint(row, bg="panel")
        row.configure(bg=self.theme.rgb("panel"))
        row.pack(side="top", fill="x")
        row.pack_propagate(False)
        return row

    def _on_background_click(self, event):
        """点击弹出列表的空白处时收起"""
        if event.widget in (self.window, self.canvas, self.items):
            self.field.close_popup()
