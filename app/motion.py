"""轻量补间动画。

tkinter 本身没有动画系统, 这里统一用 after() 推进帧: 调用方只给出时长与每帧
回调, 补间负责把线性进度映射成缓动后的进度, 并在结束或被取消时收尾。

所有补间都挂在某个控件的 after 上, 因此控件销毁后定时器随之消失; 万一控件
先被销毁再触发回调, 补间会忽略 TclError 并自行停止。

@brief 供主题过渡, 侧栏指示条滑动, 页面切换等场景复用的补间工具。
"""

import tkinter as tk

#: 默认每帧间隔 (毫秒), 约 60 fps
DEFAULT_INTERVAL_MS = 16


def ease_out_cubic(progress):
    """缓出曲线: 起步快, 收尾慢, 适合位移与颜色过渡。

    @param progress: 0-1 的线性进度
    @return: 缓动后的进度
    """
    return 1 - (1 - progress) ** 3


class Tween:
    """一段可取消的补间。

    参数:
        widget:      提供 after/after_cancel 的控件, 补间跟随它的生命周期
        duration_ms: 总时长
        on_frame:    callable(progress), 每帧调用, progress 是缓动后的 0-1 进度
        on_done:     callable(), 正常结束后调用一次; 被取消时不调用
        easing:      缓动函数, 缺省 ease_out_cubic
        interval_ms: 每帧间隔
    """

    def __init__(self, widget, duration_ms, on_frame, on_done=None,
                 easing=ease_out_cubic, interval_ms=DEFAULT_INTERVAL_MS):
        self._widget = widget
        self._frames = max(1, round(max(1, duration_ms) / max(1, interval_ms)))
        self._interval = max(1, interval_ms)
        self._on_frame = on_frame
        self._on_done = on_done
        self._easing = easing
        self._job = None
        self._index = 0
        self._cancelled = False

    @property
    def running(self):
        """补间是否还在推进。"""
        return self._job is not None

    def start(self):
        """开始补间; 立刻画第一帧, 不必等一个间隔。

        @return: 自身, 便于链式调用
        """
        if self._cancelled or self._job is not None:
            return self
        self._tick()
        return self

    def cancel(self):
        """停止补间, 不触发 on_done。"""
        self._cancelled = True
        job, self._job = self._job, None
        if job is not None:
            try:
                self._widget.after_cancel(job)
            except tk.TclError:
                pass

    def _tick(self):
        if self._cancelled:
            return
        self._index += 1
        ratio = min(1.0, self._index / self._frames)
        try:
            self._on_frame(self._easing(ratio))
        except tk.TclError:
            # 控件在补间过程中被销毁, 静默结束
            self._job = None
            return
        if ratio >= 1.0:
            self._job = None
            if self._on_done is not None:
                self._on_done()
            return
        try:
            self._job = self._widget.after(self._interval, self._tick)
        except tk.TclError:
            self._job = None

