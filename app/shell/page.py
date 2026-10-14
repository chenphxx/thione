"""工具页面基类"""

import tkinter as tk
from tkinter import ttk

from .. import kit
from ..theme import (
    BODY_GAP,
    BODY_PAD_TOP,
    BODY_PAD_X,
    SIZE_LABEL,
    SIZE_TITLE,
    TOPBAR_HEIGHT,
    tint,
)


class ToolPage(tk.Frame):
    """外壳中一个工具页面的公共父类

    子类通过类属性声明在侧栏中的呈现方式, 并按需实现生命周期回调

    页面自上而下分两部分: 顶栏 (62 像素高, 左侧是工具名与说明, 右侧是操作按钮,
    底部一条 1 像素分隔线) 与内容区 (左右各留 20 像素, 顶部留 18 像素) 页面
    最底部的状态栏由外壳统一提供, 内容通过 self.status 填充

    注意: 页面只是外壳内容区里的一个 Frame, 因此不要在构造里创建 Tk 根窗口
    或调用 mainloop - 根窗口与事件循环都由外壳持有
    """

    #: 侧栏唯一标识, 同时也用于记录上次停留的页面
    key = ""
    #: 侧栏显示名
    title = ""
    #: 侧栏图标 (`Segoe Fluent Icons` 里的一个字形)
    icon = ""
    #: 顶栏里工具名下方的说明
    subtitle = ""

    def __init__(self, master, shell):
        super().__init__(master, bd=0, highlightthickness=0)
        self.shell = shell
        self.theme = shell.theme
        tint(self, bg="canvas")
        self.configure(bg=self.theme.rgb("canvas"))
        self.topbar, self.actions = self._make_topbar()
        self.body = self._make_body()
        self.status = shell.new_status()

    # -- 生命周期 ---------------------------------------------------------
    def on_show(self):
        """页面被切换到前台时调用, 每次显示都会调用"""

    def on_hide(self):
        """页面被切换到后台时调用"""

    def on_theme_changed(self):
        """主题配色改变后调用, 自绘控件可在此刷新颜色"""

    def on_close(self):
        """主窗口关闭前调用; 返回 False 可以阻止退出"""
        return True

    # -- 页面骨架 ---------------------------------------------------------
    def _make_topbar(self):
        """建立顶栏

        @return: (顶栏, 右侧操作区的容器)
        """
        bar = tk.Frame(self, bd=0, highlightthickness=0, height=TOPBAR_HEIGHT)
        tint(bar, bg="canvas")
        bar.configure(bg=self.theme.rgb("canvas"))
        bar.pack(side="top", fill="x")
        bar.pack_propagate(False)

        inner = tk.Frame(bar, bd=0, highlightthickness=0)
        tint(inner, bg="canvas")
        inner.configure(bg=self.theme.rgb("canvas"))
        inner.pack(fill="both", expand=True, padx=BODY_PAD_X)

        actions = tk.Frame(inner, bd=0, highlightthickness=0)
        tint(actions, bg="canvas")
        actions.configure(bg=self.theme.rgb("canvas"))
        actions.pack(side="right")

        titles = tk.Frame(inner, bd=0, highlightthickness=0)
        tint(titles, bg="canvas")
        titles.configure(bg=self.theme.rgb("canvas"))
        titles.pack(side="left")
        self.title_label = kit.text(titles, self.theme, value=self.title,
                                    size=SIZE_TITLE, bold=True, surface="canvas")
        self.title_label.pack(anchor="w")
        self.subtitle_label = kit.text(titles, self.theme, value=self.subtitle,
                                       size=SIZE_LABEL, token="muted",
                                       surface="canvas")
        self.subtitle_label.pack(anchor="w", pady=(3, 0))

        kit.hairline(bar, self.theme).pack(side="bottom", fill="x")
        return bar, actions

    def _make_body(self):
        """建立内容区, 页面把面板与工具条都放进这里

        @return: 内容区容器
        """
        body = tk.Frame(self, bd=0, highlightthickness=0)
        tint(body, bg="canvas")
        body.configure(bg=self.theme.rgb("canvas"))
        body.pack(side="top", fill="both", expand=True, padx=BODY_PAD_X,
                  pady=(BODY_PAD_TOP, 0))
        return body

    def add_actions(self, specs):
        """按从左到右的顺序往顶栏右端放按钮

        @param specs: (文案, 样式, 回调) 序列, 样式为 None 表示普通按钮
        @return: 与 specs 一一对应的按钮列表
        """
        buttons = []
        for caption, style, command in reversed(list(specs)):
            button = ttk.Button(self.actions, text=caption,
                                style=style or "TButton", command=command)
            button.pack(side="right", padx=(8, 0))
            buttons.append(button)
        return list(reversed(buttons))

    def add_row(self, parent=None, gap=BODY_GAP, fill="x", expand=False):
        """在内容区里加一行工具条 (`bar`)

        @param parent: 父容器, 省略时是页面内容区
        @param gap: 与下一行之间的间距
        @param fill: pack 的填充方式
        @param expand: 是否占据多余空间
        @return: 新建的行
        """
        row = tk.Frame(parent or self.body, bd=0, highlightthickness=0)
        tint(row, bg="canvas")
        row.configure(bg=self.theme.rgb("canvas"))
        row.pack(side="top", fill=fill, expand=expand, pady=(0, gap))
        return row

    def add_panel(self, title=None, right=None, parent=None, head=True,
                  grow=True, gap=BODY_GAP, body_pad=(14, 14)):
        """在内容区里加一个面板

        @param title: 面板头部左侧的小节标题
        @param right: 面板头部右侧的补充说明
        @param parent: 父容器, 省略时是页面内容区
        @param head: 是否要 34 像素高的头部
        @param grow: True 时面板占据剩余高度
        @param gap: 与下一个面板之间的间距
        @param body_pad: 面板内容区的内边距
        @return: kit.Panel 实例
        """
        panel = kit.Panel(parent or self.body, self.theme, title=title,
                          right=right, head=head, body_pad=body_pad)
        if grow:
            panel.pack(side="top", fill="both", expand=True, pady=(0, gap))
        else:
            panel.pack(side="top", fill="x", pady=(0, gap))
        return panel

    # -- 便捷访问 ---------------------------------------------------------
    @property
    def root(self):
        """根窗口. 仅用于 after/after_cancel 等定时器, 不要在这里改窗口属性"""
        return self.shell.root

    @property
    def window(self):
        """承载本页面的顶层窗口, 适合作为对话框的 parent"""
        return self.winfo_toplevel()

    def set_status(self, message):
        """把提示写到本页面状态栏的主说明位置

        @param message: 提示文字
        """
        self.status.set_text(message)
