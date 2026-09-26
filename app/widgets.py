"""跨工具复用的 tkinter 部件辅助。

带滚动区的页面都需要「指针进入某块区域时接管鼠标滚轮」这一套绑定 而 bind_all 是全局的
绑错或者忘记解绑 会让别的页面跟着一起滚 因此把绑定与解绑收在同一个地方

@brief 存放既不属于外壳 也不属于某个具体工具的小部件辅助函数
"""

_WHEEL_EVENTS = ("<MouseWheel>", "<Button-4>", "<Button-5>")


def bind_mousewheel(containers, canvas, horizontal=False):
    """指针进入 containers 时把滚轮接到 canvas 上 离开时解除

    @param containers: 一个控件 或者控件序列
    @param canvas: 被滚动的 Canvas
    @param horizontal: True 时左右滚动 否则上下滚动
    """
    widgets = containers if isinstance(containers, (list, tuple)) else [containers]
    for widget in widgets:
        widget.bind("<Enter>", lambda _e: _bind(canvas, horizontal), add="+")
        widget.bind("<Leave>", lambda _e: unbind_mousewheel(canvas), add="+")


def unbind_mousewheel(canvas):
    """解除 bind_mousewheel 建立的全局滚轮绑定

    @param canvas: 建立绑定时传入的同一个 Canvas
    """
    for event in _WHEEL_EVENTS:
        canvas.unbind_all(event)


def _bind(canvas, horizontal):
    def handler(event):
        _scroll(canvas, event, horizontal)

    for event in _WHEEL_EVENTS:
        canvas.bind_all(event, handler)


def _scroll(canvas, event, horizontal):
    """把一次滚轮事件换算成滚动步数并作用到画布上"""
    steps = _steps(event)
    if steps == 0:
        return
    if not horizontal and not _overflows(canvas):
        return
    if horizontal:
        canvas.xview_scroll(steps, "units")
    else:
        canvas.yview_scroll(steps, "units")


def _steps(event):
    """把滚轮事件换算成滚动步数 向上或向左为负

    Windows 发 <MouseWheel> 靠 delta 判断方向 (每格 120) X11 发 <Button-4/5>
    且没有 delta
    """
    delta = getattr(event, "delta", 0)
    if delta:
        return -int(delta // 120)
    num = getattr(event, "num", 0)
    if num in (4, 5):
        return -1 if num == 4 else 1
    return 0


def _overflows(canvas):
    """内容高度超过可视高度时才允许滚动"""
    bbox = canvas.bbox("all")
    if bbox is None:
        return False
    return (bbox[3] - bbox[1]) > canvas.winfo_height()
