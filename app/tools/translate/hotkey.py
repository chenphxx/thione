"""双击 Ctrl 触发翻译, 基于 pynput 监听键盘。

监听回调运行在 pynput 自己的后台线程里, 因此这里绝对不能直接创建或操作
tkinter 窗口 —— Tk 有线程亲和性, 跨线程操作会导致偶发崩溃或窗口不显示。
本模块只负责把待展示的文本交给 result_callback, 由它投递到主线程。
"""

import logging
import time

from pynput.keyboard import Controller, Key, Listener

from .clipboard import wait_for_text
from .constants import (
    COPY_SETTLE_TIME,
    CTRL_HOLD_LIMIT,
    DOUBLE_PRESS_INTERVAL,
    SYNTHETIC_EVENT_IGNORE,
)
from .language import AUTO_LANG, DEFAULT_TARGET_LANG, resolve_direction

logger = logging.getLogger(__name__)


class DoubleCtrlListener:
    """监听连续两次 Ctrl, 自动复制选中文本, 调用翻译并展示结果。

    翻成哪种语言由构造时传入的选择决定, 目标语言为 auto 时按文本内容决定
    方向; 运行中换服务或换语言时由 TranslateService 直接改写这两个属性。
    """

    def __init__(self, translator, result_callback,
                 source_lang=AUTO_LANG, target_lang=DEFAULT_TARGET_LANG):
        self.translator = translator
        self.result_callback = result_callback  # callable(str), 必须线程安全
        self.source_lang = source_lang
        self.target_lang = target_lang
        self._first_press = None
        self._ctrl_down = False
        #: 本次按住的落下时间, 用来区分「按一下」与长按
        self._ctrl_down_at = 0.0
        #: 正在执行 _handle(), 期间到达的按键事件来自自己合成的 Ctrl+C
        self._handling = False
        #: 合成事件的忽略截止时间, 它们要等 _handle() 返回后才轮到处理
        self._synthetic_until = 0.0
        self._controller = Controller()
        self._listener = None
        self._paused = False

    # -- 生命周期 ---------------------------------------------------------

    def start(self):
        """启动监听 (非阻塞)。"""
        if self._listener is not None:
            return
        self._listener = Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self._listener.start()  # 不阻塞调用方, 主线程要留给 tkinter
        logger.info("键盘监听已启动")

    def stop(self):
        """停止监听并释放键盘钩子。"""
        if self._listener is None:
            return
        try:
            self._listener.stop()
        except Exception:
            logger.debug("停止键盘监听失败", exc_info=True)
        self._listener = None
        logger.info("键盘监听已停止")

    def pause(self):
        self._paused = True
        self._first_press = None
        logger.info("已暂停翻译热键")

    def resume(self):
        self._paused = False
        logger.info("已恢复翻译热键")

    @property
    def paused(self):
        return self._paused

    # -- 事件处理 ---------------------------------------------------------

    def _on_press(self, key, injected=False):
        """Ctrl 按下事件。

        连续两次按下才算触发, 因此这里排除两类假按下: 自己合成的 Ctrl+C 与按住
        Ctrl 时系统持续补发的自动重复事件。

        @param key: pynput 给出的按键对象
        @param injected: 事件是否由注入产生, Windows 后端会给出, 其它后端为 False
        """
        if self._paused:
            return
        if self._is_synthetic(injected):
            # 自己合成的 Ctrl+C 产生的事件, 不代表用户按下
            return

        now = time.monotonic()
        if key not in (Key.ctrl_l, Key.ctrl_r):
            # 两次 Ctrl 之间按了别的键, 判定为普通操作而非双击手势,
            # 避免 Ctrl+C 之后紧接着一次 Ctrl 就误触发。
            self._first_press = None
            return

        # 按住 Ctrl 时系统会持续补发「按下」事件 (自动重复)。抬起之前到达的
        # 重复事件都属于同一次按住, 因此不能当成新的一次按下, 否则长按 Ctrl
        # 就会被当成连续双击。
        if self._ctrl_down:
            return
        self._ctrl_down = True
        self._ctrl_down_at = now

        # 上一次按下已经超过双击间隔就无法再配对, 直接以本次重新计时。
        # 否则长按 Ctrl 留在 _first_press 里的旧时间戳会吃掉下一次真正的
        # 双击的前一半, 表现为长按之后双击不灵, 过一会才恢复。
        if (self._first_press is None
                or now - self._first_press >= DOUBLE_PRESS_INTERVAL):
            self._first_press = now
            return

        self._first_press = None
        try:
            self._handle()
        except Exception:
            logger.exception("处理双击 Ctrl 时出错")

    def _on_release(self, key, injected=False):
        """记录 Ctrl 抬起。

        只有用户真正抬起才会清零: 长按产生的自动重复因此不会被当成新的按下,
        自己合成的 Ctrl+C 抬起也被忽略, 否则仍被按住的 Ctrl 会被误判成已松开。
        按住时间超过 CTRL_HOLD_LIMIT 的算长按, 一并丢弃待配对的那一次按下,
        免得长按之后紧接着的一次 Ctrl 被配成双击。

        @param key: pynput 给出的按键对象
        @param injected: 事件是否由注入产生
        """
        if self._is_synthetic(injected):
            return
        if key not in (Key.ctrl_l, Key.ctrl_r):
            return
        was_down = self._ctrl_down
        self._ctrl_down = False
        if not was_down:
            return
        if time.monotonic() - self._ctrl_down_at >= CTRL_HOLD_LIMIT:
            self._first_press = None

    def _is_synthetic(self, injected):
        """事件是否由 _handle() 自己合成的 Ctrl+C 产生。

        合成事件同样会回到本监听器, 且要等 _handle() 返回后才轮到处理, 因此除了
        注入标记, 还要看当前是否正在执行 _handle() 或刚执行完。

        @param injected: 监听回调给出的注入标记
        @return: True 表示该事件应被忽略
        """
        if not injected:
            return False
        return self._handling or time.monotonic() < self._synthetic_until

    def _handle(self):
        """复制选中文本并翻译, 结果交给 UI 层。"""
        # 合成的 Ctrl+C 同样会回到本监听器, 且要等本函数返回后才轮到处理,
        # 因此整个执行期间都不可信, 结束后再补一小段忽略窗口
        self._handling = True
        try:
            # 模拟 Ctrl+C 复制当前选中的文本
            with self._controller.pressed(Key.ctrl):
                self._controller.press("c")
                self._controller.release("c")

            text = wait_for_text(COPY_SETTLE_TIME)
            if not text:
                self._show("未检测到剪贴板文本 (请先选中要翻译的内容)。")
                return

            try:
                source_lang, target_lang = resolve_direction(
                    text, self.source_lang, self.target_lang
                )
                result = self.translator.translate(text, source_lang, target_lang)
            except Exception as exc:
                logger.warning("翻译失败: %s", exc)
                self._show(f"翻译失败:\n{exc}")
                return

            self._show(result)
        finally:
            self._handling = False
            self._synthetic_until = time.monotonic() + SYNTHETIC_EVENT_IGNORE

    def _show(self, text):
        """把文本交给 UI 层; 这里只是回调, 不涉及任何 tkinter 对象。"""
        try:
            self.result_callback(text)
        except Exception:
            logger.exception("把结果投递给主线程失败")
