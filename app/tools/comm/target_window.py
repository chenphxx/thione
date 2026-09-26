"""TCP Server 发送对象的多选窗口

发送对象下拉框一次只能选一个客户端, 要给其中几个客户端单独发送时弹出本窗口勾选,
勾选结果交回页面写进下拉框; 取消时返回 None, 页面保持原来的选择

@brief 发送对象的多选窗口
"""

import tkinter as tk
from tkinter import ttk

#: 窗口标题与说明
TITLE = "选择发送对象"
HINT = "勾选要发送到的设备, 一个都不勾选表示发送给全部设备"

#: 命令行
LIST_WIDTH = 28
MIN_ROWS = 3
MAX_ROWS = 12

#: 内容与窗口边框的间距
PADDING = 14


class TargetWindow(tk.Toplevel):
    """勾选要发送到的客户端"""

    def __init__(self, master, addresses, selected=(), theme=None):
        super().__init__(master)

        self.withdraw()
        self.title(TITLE)
        self.transient(master)
        self.resizable(False, False)
        self.result = None
        self.theme = theme
        self._thione_surface = "card"

        addresses = list(addresses)
        chosen = set(selected)
        self.listbox = tk.Listbox(
            self, selectmode="extended", exportselection=False,
            width=LIST_WIDTH, height=_rows(len(addresses)), activestyle="none",
            borderwidth=0, highlightthickness=1,
        )
        # 主题管理器按 _thione_surface 给原生控件上色, 列表按输入框的底色处理
        self.listbox._thione_surface = "input"
        for index, address in enumerate(addresses):
            self.listbox.insert("end", address)
            if address in chosen:
                self.listbox.selection_set(index)
        self.listbox.pack(side="top", fill="both", expand=True, padx=PADDING,
                          pady=(PADDING, 8))

        ttk.Label(self, text=HINT, style="CardMuted.TLabel").pack(
            side="top", anchor="w", padx=PADDING)

        buttons = ttk.Frame(self, style="CardFlat.TFrame")
        buttons.pack(side="top", fill="x", padx=PADDING, pady=(10, PADDING))
        ttk.Button(buttons, text="确定", style="Accent.TButton",
                   command=self._confirm).pack(side="right")
        ttk.Button(buttons, text="取消", style="Secondary.TButton",
                   command=self._cancel).pack(side="right", padx=(0, 8))
        ttk.Button(buttons, text="清空选择", style="Secondary.TButton",
                   command=self._clear).pack(side="left")

        self.bind("<Return>", lambda _event: self._confirm())
        self.bind("<Escape>", lambda _event: self._cancel())
        if theme is not None:
            theme.register(self)
            theme.apply_theme(self)

    def ask(self):
        """显示窗口并等待用户操作

        @return: 勾选的地址列表; 取消时返回 None
        """
        self._place()
        self.deiconify()
        self.grab_set()
        self.listbox.focus_set()
        self.wait_window(self)
        return self.result

    # ---------------- 内部 ----------------
    def _place(self):
        """把窗口摆在父窗口中间偏上的位置"""
        self.update_idletasks()
        parent = self.master
        try:
            x = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_reqwidth()) // 2
            y = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_reqheight()) // 3
        except tk.TclError:
            return
        self.geometry("+%d+%d" % (max(x, 0), max(y, 0)))

    def _clear(self):
        """清空勾选, 效果等同于发送给全部设备"""
        self.listbox.selection_clear(0, "end")

    def _confirm(self):
        """记下勾选结果并关窗"""
        self.result = [self.listbox.get(int(index))
                       for index in self.listbox.curselection()]
        self.destroy()

    def _cancel(self):
        """放弃这次选择"""
        self.result = None
        self.destroy()


def _rows(count):
    """列表高度 (行数)

    @param count: 地址数量
    @return: 夹在 MIN_ROWS 与 MAX_ROWS 之间的行数
    """
    return max(MIN_ROWS, min(MAX_ROWS, count))


def ask_targets(master, addresses, selected=(), theme=None):
    """弹出多选窗口

    @param master: 父窗口
    @param addresses: 可选的客户端地址列表
    @param selected: 已经选中的地址
    @param theme: ThemeManager, 用来应用当前配色
    @return: 勾选的地址列表; 取消时返回 None
    """
    return TargetWindow(master, addresses, selected, theme).ask()
