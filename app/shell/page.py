"""工具页面基类。"""

from tkinter import ttk


class ToolPage(ttk.Frame):
    """外壳中一个工具页面的公共父类。

    子类通过类属性声明在侧栏中的呈现方式, 并按需实现生命周期回调。

    注意: 页面只是内容区里的一个 ttk.Frame, 因此不要在构造里创建 Tk 根窗口
    或调用 mainloop —— 根窗口与事件循环都由外壳持有。
    """

    #: 侧栏唯一标识, 同时也用于记录上次停留的页面
    key = ""
    #: 侧栏显示名
    title = ""
    #: 侧栏图标 (单个字符, 避免依赖外部图标资源)
    icon = ""
    #: 状态栏提示, 说明这个工具是做什么的
    subtitle = ""

    def __init__(self, master, shell):
        super().__init__(master)
        self.shell = shell
        self.theme = shell.theme

    # -- 生命周期 ---------------------------------------------------------
    def on_show(self):
        """页面被切换到前台时调用, 每次显示都会调用。"""

    def on_hide(self):
        """页面被切换到后台时调用。"""
    def on_close(self):
        """主窗口关闭前调用; 返回 False 可以阻止退出。"""
        return True

    # -- 页面骨架 ---------------------------------------------------------
    def build_toolbar(self):
        """建立页面顶部的工具条。

        工具条统一使用 panel 底色, 与侧栏连成一片; 标题与说明放在 head 的左侧,
        操作按钮放进 actions (已经右对齐)。需要第二行筛选控件时, 直接在返回的
        bar 里再 pack 一个子 Frame 即可。

        @return: (bar, head, actions) 三个 ttk.Frame
        """
        bar = ttk.Frame(self, style="Panel.TFrame", padding=(20, 16))
        bar.pack(side="top", fill="x")
        head = ttk.Frame(bar, style="Panel.TFrame")
        head.pack(side="top", fill="x")
        actions = ttk.Frame(head, style="Panel.TFrame")
        actions.pack(side="right")
        return bar, head, actions

    def add_divider(self):
        """在工具条与内容区之间补一条 1 像素分隔线。"""
        divider = ttk.Frame(self, style="Divider.TFrame", height=1)
        divider.pack(side="top", fill="x")
        return divider

    # -- 便捷访问 ---------------------------------------------------------
    @property
    def root(self):
        """根窗口。仅用于 after/after_cancel 等定时器, 不要在这里改窗口属性。"""
        return self.shell.root

    @property
    def window(self):
        """承载本页面的顶层窗口, 适合作为对话框的 parent。"""
        return self.winfo_toplevel()

    def set_status(self, message):
        """把提示写到外壳状态栏。"""
        self.shell.set_status(message)
