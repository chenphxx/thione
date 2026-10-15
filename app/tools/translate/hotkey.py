"""双击 Ctrl 触发翻译, 基于 pynput 监听键盘

监听回调运行在 pynput 自己的后台线程里, 因此这里绝对不能直接创建或操作
tkinter 窗口 - Tk 有线程亲和性, 跨线程操作会导致偶发崩溃或窗口不显示
本模块只负责把待展示的文本交给 result_callback, 由它投递到主线程
"""

import logging
import threading
import time

from pynput.keyboard import Controller, Key, Listener

from .clipboard import wait_for_text
from .constants import (
    COPY_SETTLE_TIME,
    DOUBLE_PRESS_INTERVAL,
    PRESS_DEBOUNCE,
    SYNTHETIC_EVENT_IGNORE,
)
from .language import AUTO_LANG, DEFAULT_TARGET_LANG, resolve_direction

logger = logging.getLogger(__name__)


class DoubleCtrlListener:
    """监听连续两次 Ctrl, 自动复制选中文本, 调用翻译并展示结果

    翻成哪种语言由构造时传入的选择决定, 目标语言为 auto 时按文本内容决定
    方向; 运行中换服务或换语言时由 TranslateService 直接改写这两个属性
    """

    def __init__(self, translator, result_callback,
                 source_lang=AUTO_LANG, target_lang=DEFAULT_TARGET_LANG):
        self.translator = translator
        self.result_callback = result_callback  # callable(str), 必须线程安全
        self.source_lang = source_lang
        self.target_lang = target_lang
        #: 上一次 Ctrl 按下的时间, 配对只看按下事件
        self._last_press = None
        #: 正在合成 Ctrl+C, 期间的事件都来自自己
        self._injecting = False
        #: 合成事件在结束后仍需忽略的时间 (钩子回调可能晚于合成返回)
        self._synthetic_until = 0.0
        #: 已经有一次翻译在跑, 期间不再重复触发
        self._busy = False
        self._controller = Controller()
        self._listener = None
        self._paused = False

    # -- 生命周期 ---------------------------------------------------------

    def start(self):
        """启动监听 (非阻塞)"""
        if self._listener is not None:
            return
        self._listener = Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self._listener.start()  # 不阻塞调用方, 主线程要留给 tkinter
        logger.info("键盘监听已启动")

    def stop(self):
        """停止监听并释放键盘钩子"""
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
        self._last_press = None
        logger.info("已暂停翻译热键")

    def resume(self):
        self._paused = False
        logger.info("已恢复翻译热键")

    @property
    def paused(self):
        return self._paused

    # -- 事件处理 ---------------------------------------------------------

    def _on_press(self, key, injected=False):
        """Ctrl 按下事件

        连续两次按下才算触发. 配对只看两次按下之间的间隔, 因此按住多久都不影响
        判定, 也不会因为漏掉一次抬起 (自己合成的 Ctrl+C 抬起会被忽略) 就吃掉
        下一次手势的第一次按下

        同一时刻重复到达的按下要丢掉: 按住 Ctrl 时系统可能补发的自动重复, 以及
        _handle() 自己合成的那个 Ctrl

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
            # 避免 Ctrl+C 之后紧接着一次 Ctrl 就误触发
            self._last_press = None
            return

        if self._last_press is not None and now - self._last_press < PRESS_DEBOUNCE:
            # 同一次按住里的重复按下, 或者刚由自己合成的 Ctrl
            return

        # 上一次按下已经超过双击间隔就无法再配对, 以本次重新计时
        if (self._last_press is None
                or now - self._last_press > DOUBLE_PRESS_INTERVAL):
            self._last_press = now
            return

        # 配对成功: 连按三次只会触发一次
        self._last_press = None
        try:
            self._start_handle()
        except Exception:
            logger.exception("处理双击 Ctrl 时出错")

    def _on_release(self, key, injected=False):
        """抬起事件不参与判定

        配对以两次按下为准, 这样自己合成的 Ctrl 抬起被忽略也不会影响下一次
        手势; 这里保留回调只是为了方便后续需要时接管

        @param key: pynput 给出的按键对象
        @param injected: 事件是否由注入产生
        """
        return

    def _is_synthetic(self, injected):
        """事件是否由 _handle() 自己合成的 Ctrl+C 产生

        合成事件同样会回到本监听器. 正在合成时一律忽略; 合成刚结束时钩子回调
        可能还没派发完, 因此在注入标记之外再留一小段忽略窗口

        @param injected: 监听回调给出的注入标记
        @return: True 表示该事件应被忽略
        """
        if self._injecting:
            return True
        if not injected:
            return False
        return time.monotonic() < self._synthetic_until

    def _start_handle(self):
        """把复制与翻译放到后台线程, 监听线程必须立刻返回

        键盘钩子的回调运行在系统要求的时限内, 翻译又要等网络, 一旦在回调里同步
        做完整件事, 回调期间到达的按键会被丢掉, 表现为'按两次有时不生效'

        上一次翻译还没结束就不再重复触发
        """
        if self._busy:
            logger.debug("上一次翻译还没结束, 忽略这次双击")
            return
        self._busy = True
        threading.Thread(target=self._handle, name="translate-hotkey",
                         daemon=True).start()

    def _handle(self):
        """复制选中文本并翻译, 结果交给 UI 层"""
        try:
            # 模拟 Ctrl+C 复制当前选中的文本
            self._injecting = True
            try:
                with self._controller.pressed(Key.ctrl):
                    self._controller.press("c")
                    self._controller.release("c")
            finally:
                # 合成事件可能比这里晚一点回到钩子, 因此再留一段忽略窗口
                self._synthetic_until = time.monotonic() + SYNTHETIC_EVENT_IGNORE
                self._injecting = False

            text = wait_for_text(COPY_SETTLE_TIME)
            if not text:
                self._show("未检测到剪贴板文本 (请先选中要翻译的内容)")
                return

            try:
                source_lang, target_lang = resolve_direction(
                    text, self.source_lang, self.target_lang
                )
                result = self.translator.translate(text, source_lang, target_lang)
            except Exception as exc:
                logger.warning("翻译失败: %s", exc)
                self._show(f"翻译失败:\n{exc}", text)
                return

            self._show(result, text)
        finally:
            self._busy = False

    def _show(self, text, source=""):
        """把结果交给 UI 层; 这里只是回调, 不涉及任何 tkinter 对象

        @param text: 要展示的结果文本
        @param source: 本次翻译的原文, 没有原文时为空串
        """
        try:
            self.result_callback(text, source)
        except Exception:
            logger.exception("把结果投递给主线程失败")
