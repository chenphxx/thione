"""进制转换页面: 上方是待转换数字与转换结果, 下方是常用进制对照表

输入框的内容或者任一进制选择发生变化都会立即重新转换, 因此不额外放转换
按钮; 结果框只读, 复制由顶栏之外的按钮完成. 输入不合法时结果清空, 原因写在
状态栏, 不弹窗打断输入
"""

import tkinter as tk

from ... import kit
from ...dpi import scale
from ...shell.page import ToolPage
from ...theme import (
    BODY_GAP,
    SIZE_LABEL,
    SIZE_SECTION,
    SIZE_TITLE,
    SIZE_VALUE,
    tint,
)
from .constants import (
    BASE_CHOICES,
    BASE_LABELS,
    BASES,
    COMMON_BASES,
    COMMON_LABELS,
    DEFAULT_SOURCE_BASE,
    DEFAULT_TARGET_BASE,
    EMPTY_HINT,
    REFERENCE_COLUMNS,
    REFERENCE_LIMIT,
    STATUS_HINT,
    SUBTITLE,
)
from .converter import ConvertError, convert_many, reference_rows

class RadixPage(ToolPage):
    """在 2 到 36 进制之间转换数字的工具页面"""

    key = "radix"
    title = "进制转换"
    icon = "\uE8EF"
    subtitle = SUBTITLE

    def __init__(self, master, shell):
        super().__init__(master, shell)

        self._source_base = DEFAULT_SOURCE_BASE
        self._target_base = DEFAULT_TARGET_BASE
        self._cell_values = {}
        self._cell_tokens = {}

        self._build_panels()
        self.status.set_kind("idle")
        self.status.set_text(STATUS_HINT)

        self._sync_combos()
        self._convert()

    # ---------------- 界面构建 ----------------
    def _build_panels(self):
        """上半部分是转换区, 下半部分是常用进制对照表"""
        panel = self.add_panel(title="进制转换", grow=False)
        row = tk.Frame(panel.body, bd=0, highlightthickness=0)
        tint(row, bg="panel")
        row.configure(bg=self.theme.rgb("panel"))
        row.pack(side="top", fill="x")

        source = self._build_block(row, "待转换数字", accent=False)
        source.pack(side="left", fill="x", expand=True)
        self._build_swap(row).pack(side="left", fill="y", padx=BODY_GAP)
        target = self._build_block(row, "转换结果", accent=True)
        target.pack(side="left", fill="x", expand=True)

        cells = tk.Frame(panel.body, bd=0, highlightthickness=0)
        tint(cells, bg="panel")
        cells.configure(bg=self.theme.rgb("panel"))
        cells.pack(side="top", fill="x", pady=(BODY_GAP, 0))
        for base in COMMON_BASES:
            self._build_common_cell(cells, base).pack(
                side="left", fill="x", expand=True, padx=(0, 10))

        table_panel = self.add_panel(title="进制对照表", body_pad=(14, 0))
        # 一张表 16 行纵向下滑, 不再左右分成两半
        columns = [{"key": key, "title": title, "weight": 1, "mono": True}
                   for key, title, _width in REFERENCE_COLUMNS]
        self.table = kit.Table(
            table_panel.body, self.theme, columns, surface="panel")
        self.table.pack(side="top", fill="both", expand=True,
                        pady=(scale(10), 0))
        self.table.set_rows(self._reference_rows())

    def _build_block(self, parent, caption, accent):
        """建立一个进制输入块: 说明 + 数字框 + 进制选择

        @param parent: 父容器
        @param caption: 块上方的说明文字
        @param accent: True 表示结果块 (文字用强调色, 只读)
        @return: 块控件
        """
        block = tk.Frame(parent, bd=0, highlightthickness=0)
        tint(block, bg="panel")
        block.configure(bg=self.theme.rgb("panel"))
        kit.text(block, self.theme, value=caption, size=SIZE_LABEL,
                 token="muted", surface="panel").pack(anchor="w", pady=(0, 6))
        area = kit.Area(block, self.theme, height=120, surface="panel",
                        size=SIZE_TITLE, token="accent" if accent else "text",
                        editable=not accent,
                        placeholder="" if accent else EMPTY_HINT)
        area.pack(fill="x")
        combo = kit.Dropdown(block, self.theme, values=list(BASE_CHOICES),
                             command=self._on_base_change,
                             surface="panel")
        combo.pack(fill="x", pady=(6, 0))
        if accent:
            self.area_result = area
            self.combo_target = combo
        else:
            self.area_input = area
            self.combo_source = combo
            self.area_input.widget.bind("<KeyRelease>", self._on_input)
            self.area_input.widget.bind("<<Paste>>", self._on_input)
            self.area_input.widget.bind("<<Cut>>", self._on_input)
        return block

    def _build_swap(self, parent):
        """两个进制之间的交换按钮

        @param parent: 父容器
        @return: 按钮控件
        """
        swap = tk.Frame(parent, width=scale(32), bd=0, highlightthickness=1,
                        cursor="hand2")
        tint(swap, bg="fill", hl="hair", hlc="hair")
        swap.configure(bg=self.theme.rgb("fill"),
                       highlightbackground=self.theme.rgb("hair"),
                       highlightcolor=self.theme.rgb("hair"))
        swap.pack_propagate(False)
        glyph = kit.text(swap, self.theme, value="\uE8AB", size=SIZE_VALUE,
                         token="muted", icon_font=True, surface="fill",
                         anchor="center")
        glyph.pack(fill="both", expand=True)
        for widget in (swap, glyph):
            widget.bind("<Button-1>", lambda _e: self._swap_bases())
        return swap

    def _build_common_cell(self, parent, base):
        """建立一个常用进制的小格子

        @param parent: 父容器
        @param base: 进制
        @return: 格子控件
        """
        cell = tk.Frame(parent, bd=0, highlightthickness=1)
        tint(cell, bg="fill", hl="hair", hlc="hair")
        cell.configure(bg=self.theme.rgb("fill"),
                       highlightbackground=self.theme.rgb("hair"),
                       highlightcolor=self.theme.rgb("hair"))
        inner = tk.Frame(cell, bd=0, highlightthickness=0)
        tint(inner, bg="fill")
        inner.configure(bg=self.theme.rgb("fill"))
        inner.pack(fill="both", expand=True, padx=scale(10),
                   pady=scale(7))
        kit.text(inner, self.theme, value=COMMON_LABELS[base],
                 size=SIZE_SECTION, token="muted", surface="fill").pack(
            anchor="w")
        value = kit.text(inner, self.theme, value="", size=SIZE_VALUE,
                         mono_font=True, surface="fill")
        value.pack(anchor="w", pady=(scale(4), 0))
        self._cell_values[base] = value
        return cell

    def _reference_rows(self):
        """对照表的每一行: 十进制/二进制/八进制/十六进制

        @return: 表格数据行
        """
        keys = [key for key, _title, _width in REFERENCE_COLUMNS]
        return [dict(zip(keys, row)) for row in reference_rows(REFERENCE_LIMIT)]

    # ---------------- 转换与提示 ----------------
    def _on_input(self, _event=None):
        self._convert()

    def _on_base_change(self, _label):
        """下拉框换值后重新转换

        @param _label: 下拉框显示的新文本
        """
        self._source_base = self._base_from_label(self.combo_source.value(),
                                                  DEFAULT_SOURCE_BASE)
        self._target_base = self._base_from_label(self.combo_target.value(),
                                                  DEFAULT_TARGET_BASE)
        self._convert()

    def _convert(self):
        """按当前的两个进制重新转换, 并刷新结果 常用进制与状态栏提示"""
        try:
            values = convert_many(
                self.area_input.get(), self._source_base,
                (self._target_base, *COMMON_BASES),
            )
        except ConvertError as exc:
            self.area_result.set("")
            self._clear_common()
            self.status.set_kind("fail")
            self.status.set_text(str(exc))
            return
        self.area_result.set(values[0])
        for base, value in zip(COMMON_BASES, values[1:]):
            self._cell_values[base].configure(text=value)
            token = "accent" if base == self._target_base else "text"
            tint(self._cell_values[base], bg="fill", fg=token)
            self._cell_values[base].configure(fg=self.theme.rgb(token))
        self.status.set_kind("idle")
        self.status.set_text(STATUS_HINT)

    def _clear_common(self):
        """清空常用进制的结果, 输入不合法时与主结果一起清掉"""
        for label in self._cell_values.values():
            label.configure(text="")

    def _sync_combos(self):
        """把两个下拉框的显示对齐到当前进制"""
        self.combo_source.set(BASE_LABELS[self._source_base])
        self.combo_target.set(BASE_LABELS[self._target_base])

    @staticmethod
    def _base_from_label(label, fallback):
        """把下拉框里的显示名换回进制数字

        @param label: 下拉框当前显示的文本
        @param fallback: 显示名不是已知取值时使用的进制
        @return: 进制数字
        """
        if label in BASE_CHOICES:
            return BASES[BASE_CHOICES.index(label)]
        return fallback

    # ---------------- 交互 ----------------
    def _swap_bases(self):
        """交换两个进制, 并把上一次的结果放进输入框接着转换"""
        previous = self.area_result.get()
        self._source_base, self._target_base = self._target_base, \
            self._source_base
        self._sync_combos()
        if previous:
            self.area_input.set(previous)
            self._convert()
        else:
            self._convert()
        self.area_input.focus_set()

    def on_show(self):
        """切到本页时把光标放进输入框, 打开就能输入"""
        self.area_input.focus_set()

    def on_theme_changed(self):
        """主题切换后重画常用进制的取值颜色"""
        self._convert()
