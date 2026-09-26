"""进制转换页面: 上方是待转换数字与转换结果, 下方是常用进制对照表。

输入框的内容或者任一进制选择发生变化都会立即重新转换, 因此不额外放转换
按钮; 结果框只读, 复制由相邻的按钮完成。输入不合法时结果清空, 原因写在
输入框下方, 不弹窗打断输入。
"""

import tkinter as tk
from tkinter import ttk

import pyperclip

from ...shell.page import ToolPage
from ...theme import mono
from .constants import (
    BASE_CHOICES,
    BASE_COMBO_WIDTH,
    BASE_LABELS,
    BASES,
    COMMON_BASES,
    COMMON_LABELS,
    DEFAULT_SOURCE_BASE,
    DEFAULT_TARGET_BASE,
    EMPTY_HINT,
    NUMBER_FONT_SIZE,
    PAGE_TITLE,
    REFERENCE_COLUMNS,
    REFERENCE_LIMIT,
    SUBTITLE,
)
from .converter import ConvertError, convert_many, reference_rows

# 状态栏里回显结果时的最大长度, 二进制结果可能很长
STATUS_MAX_CHARS = 48

#: 常用进制一栏的标题
COMMON_TITLE = "常用进制"

#: 常用进制分左右两侧展示, 每侧两项
COMMON_SIDES = (COMMON_BASES[:2], COMMON_BASES[2:])


class RadixPage(ToolPage):
    """在 2 到 36 进制之间转换数字的工具页面。"""

    key = "radix"
    title = PAGE_TITLE
    icon = "🔢"
    subtitle = SUBTITLE

    def __init__(self, master, shell):
        super().__init__(master, shell)

        self._source_base = DEFAULT_SOURCE_BASE
        self._target_base = DEFAULT_TARGET_BASE
        # 主题管理器按系统可用字体解析字体族, 因此在这里取而不是在模块级取
        self._number_font = mono(NUMBER_FONT_SIZE)
        self._input_var = tk.StringVar()
        self._result_var = tk.StringVar()
        self._hint_var = tk.StringVar(value=EMPTY_HINT)
        self._common_vars = {base: tk.StringVar() for base in COMMON_BASES}

        self._build_toolbar()
        self.add_divider()
        self._build_convert_area()
        self._build_reference_table()

        # 换进制与改输入都走同一条转换路径, 下拉框的显示在这里对齐
        self._input_var.trace_add("write", lambda *_args: self._convert())
        self._sync_combos()
        self._convert()

    # ---------------- 界面构建 ----------------
    def _build_toolbar(self):
        _bar, head, _actions = self.build_toolbar()
        ttk.Label(head, text=PAGE_TITLE,
                  style="PanelHeader.TLabel").pack(side="left")
        ttk.Label(head, text="输入数字即可转换, 结果随输入与进制实时刷新",
                  style="PanelHint.TLabel").pack(side="left", padx=(12, 0))

    def _build_convert_area(self):
        """页面上半部分: 左侧待转换的数字, 右侧转换结果, 中间是交换按钮。

        常用进制分在两侧, 与上方的两栏共用同一列, 因此左右两块自然对齐。
        """
        card = ttk.LabelFrame(self, text="进制转换", padding=(16, 12))
        card.pack(side="top", fill="x")
        card.columnconfigure(0, weight=1)
        card.columnconfigure(2, weight=1)

        self._build_source_area(card)
        self._build_result_area(card)
        self._build_common_bases(card)

        ttk.Button(card, text="⇄", width=3, style="Secondary.TButton",
                   command=self._swap_bases).grid(row=0, column=1, padx=14)

    def _build_source_area(self, card):
        """左侧区域: 待转换的数字与它的进制选择。

        @param card: 放置该区域的卡片
        """
        area = ttk.Frame(card, style="CardFlat.TFrame")
        area.grid(row=0, column=0, sticky="nsew")
        area.columnconfigure(0, weight=1)

        ttk.Label(area, text="待转换数字",
                  style="Card.TLabel").grid(row=0, column=0, sticky="w")
        self.combo_source = ttk.Combobox(
            area, state="readonly", width=BASE_COMBO_WIDTH, values=list(BASE_CHOICES)
        )
        self.combo_source.grid(row=0, column=1, sticky="e", padx=(10, 0))
        self.combo_source.bind("<<ComboboxSelected>>", self._on_source_base_change)

        self.entry_input = ttk.Entry(area, textvariable=self._input_var,
                                     font=self._number_font)
        self.entry_input.grid(row=1, column=0, columnspan=2, sticky="we",
                              pady=(8, 0))

        self.lbl_hint = ttk.Label(area, textvariable=self._hint_var, anchor="w",
                                  style="CardMuted.TLabel")
        self.lbl_hint.grid(row=2, column=0, columnspan=2, sticky="we", pady=(6, 0))

    def _build_result_area(self, card):
        """右侧区域: 转换结果与它的进制选择。

        @param card: 放置该区域的卡片
        """
        area = ttk.Frame(card, style="CardFlat.TFrame")
        area.grid(row=0, column=2, sticky="nsew")
        # 第 0 列放标题与常用进制的名称, 第 1 列放取值的输入框
        area.columnconfigure(1, weight=1)

        ttk.Label(area, text="转换结果",
                  style="Card.TLabel").grid(row=0, column=0, sticky="w")
        self.combo_target = ttk.Combobox(
            area, state="readonly", width=BASE_COMBO_WIDTH, values=list(BASE_CHOICES)
        )
        self.combo_target.grid(row=0, column=1, sticky="e", padx=(10, 0))
        self.combo_target.bind("<<ComboboxSelected>>", self._on_target_base_change)

        self.entry_result = ttk.Entry(area, textvariable=self._result_var,
                                      font=self._number_font, state="readonly")
        self.entry_result.grid(row=1, column=0, columnspan=2, sticky="we",
                               pady=(8, 0))

        ttk.Button(area, text="复制结果", style="Secondary.TButton",
                   command=self._copy_result).grid(row=2, column=0, columnspan=2,
                                                   sticky="e", pady=(6, 0))

    def _build_common_bases(self, card):
        """目标进制之外的四种常用进制: 左侧两种, 右侧两种。

        @param card: 放置该区块的卡片
        """
        for column, bases in ((0, COMMON_SIDES[0]), (2, COMMON_SIDES[1])):
            area = ttk.Frame(card, style="CardFlat.TFrame")
            area.grid(row=1, column=column, sticky="nsew", pady=(12, 0))
            area.columnconfigure(1, weight=1)

            ttk.Separator(area, orient="horizontal").grid(
                row=0, column=0, columnspan=2, sticky="we")
            ttk.Label(area, text=COMMON_TITLE,
                      style="CardMuted.TLabel").grid(row=1, column=0,
                                                     columnspan=2, sticky="w",
                                                     pady=(10, 0))
            for index, base in enumerate(bases):
                row = index + 2
                ttk.Label(area, text=COMMON_LABELS[base],
                          style="Card.TLabel").grid(row=row, column=0,
                                                    sticky="w", pady=2)
                ttk.Entry(area, textvariable=self._common_vars[base],
                          font=self._number_font, state="readonly").grid(
                    row=row, column=1, sticky="we", padx=(10, 0), pady=2)

    def _build_reference_table(self):
        """页面下半部分: 0 到 15 的四种进制对照, 高度不够时自己滚动。"""
        card = ttk.LabelFrame(self, text="进制对照表", padding=(16, 12))
        card.pack(side="top", fill="both", expand=True, pady=(12, 0))

        self.table = ttk.Treeview(
            card, show="headings", style="Card.Treeview",
            columns=[key for key, _title, _width in REFERENCE_COLUMNS],
        )
        for key, title, width in REFERENCE_COLUMNS:
            self.table.heading(key, text=title, anchor="center")
            self.table.column(key, width=width, minwidth=80, anchor="center",
                              stretch=True)
        # 四列都是数字, 统一用等宽字体便于逐位比对
        self.table.tag_configure("value", font=self._number_font)
        for row in reference_rows(REFERENCE_LIMIT):
            self.table.insert("", "end", values=row, tags=("value",))

        scroll = ttk.Scrollbar(card, orient="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=scroll.set)
        self.table.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

    # ---------------- 转换与提示 ----------------
    def _on_source_base_change(self, _event=None):
        self._source_base = self._base_from_label(self.combo_source.get(),
                                                  DEFAULT_SOURCE_BASE)
        self._convert()

    def _on_target_base_change(self, _event=None):
        self._target_base = self._base_from_label(self.combo_target.get(),
                                                  DEFAULT_TARGET_BASE)
        self._convert()

    def _convert(self):
        """按当前的两个进制重新转换, 并刷新结果 常用进制与输入框下方的说明。"""
        try:
            values = convert_many(
                self._input_var.get(), self._source_base,
                (self._target_base, *COMMON_BASES),
            )
        except ConvertError as exc:
            self._result_var.set("")
            self._clear_common()
            self._set_hint(str(exc), error=True)
            return
        self._result_var.set(values[0])
        for base, value in zip(COMMON_BASES, values[1:]):
            self._common_vars[base].set(value)
        # 还没输入时给引导, 转换成功就不用再解释
        self._set_hint("" if values[0] else EMPTY_HINT)

    def _clear_common(self):
        """清空常用进制的结果, 输入不合法时与主结果一起清掉。"""
        for var in self._common_vars.values():
            var.set("")

    def _set_hint(self, text, error=False):
        """更新输入框下方的说明。

        @param text: 要显示的内容
        @param error: True 时改用危险色, 说明输入不合法
        """
        self._hint_var.set(text)
        style = "CardError.TLabel" if error else "CardMuted.TLabel"
        if self.lbl_hint.cget("style") != style:
            self.lbl_hint.configure(style=style)

    def _sync_combos(self):
        """把两个下拉框的显示对齐到当前进制。"""
        self.combo_source.set(BASE_LABELS[self._source_base])
        self.combo_target.set(BASE_LABELS[self._target_base])

    @staticmethod
    def _base_from_label(label, fallback):
        """把下拉框里的显示名换回进制数字。

        @param label: 下拉框当前显示的文本
        @param fallback: 显示名不是已知取值时使用的进制
        @return: 进制数字
        """
        if label in BASE_CHOICES:
            return BASES[BASE_CHOICES.index(label)]
        return fallback

    # ---------------- 交互 ----------------
    def _swap_bases(self):
        """交换两个进制, 并把上一次的结果放进输入框接着转换。"""
        previous = self._result_var.get()
        self._source_base, self._target_base = self._target_base, self._source_base
        self._sync_combos()
        if previous:
            # 写回输入框会触发一次重新转换
            self._input_var.set(previous)
        else:
            self._convert()
        self.entry_input.focus_set()

    def _copy_result(self):
        """把结果写进系统剪贴板, 供其它程序粘贴。"""
        result = self._result_var.get()
        if not result:
            return
        pyperclip.copy(result)
        self.set_status(f"已复制转换结果: {_shorten(result)}")

    def on_show(self):
        """切到本页时把光标放进输入框, 打开就能输入。"""
        self.entry_input.focus_set()


def _shorten(text):
    """状态栏里的回显不要过长。

    @param text: 转换结果
    @return: 超过 STATUS_MAX_CHARS 时截断并加省略标记
    """
    if len(text) <= STATUS_MAX_CHARS:
        return text
    return text[:STATUS_MAX_CHARS] + "..."
