"""划词翻译页面: 凭据配置、启动开关与最近一次翻译结果。

翻译功能默认不启动: 打开 thione 只是把凭据读进来, 全局热键与托盘图标都要等
用户在本页面点「启动翻译」之后才建立, 避免一开程序就挂上全局键盘钩子。
"""

import logging
import queue
import threading
import tkinter as tk
from tkinter import ttk

from ...errors import show_error
from ...shell.page import ToolPage
from . import storage
from .config import Config
from .constants import APP_TITLE, REGION
from .service import TranslateService
from .translator import Translator

logger = logging.getLogger(__name__)

FIELDS = (
    ("ak", "Access Key (AK)"),
    ("sk", "Secret Key (SK)"),
    ("project_id", "Project ID"),
    ("region", "Region"),
)

#: 测试连接用的短文本, 只要能走通一次真实翻译即可
SKIP_TEST_TEXT = "Hello"

#: 最近一次结果在界面上最多显示的长度
MAX_RESULT_CHARS = 600

#: 还没有翻译过时结果区显示的引导文案
EMPTY_RESULT_HINT = "还没有翻译记录 启动翻译后选中任意文本 连续按两次 Ctrl 试试"


class TranslatePage(ToolPage):
    """配置华为云 NLP 凭据并常驻划词翻译热键的工具页面。"""

    key = "translate"
    title = "划词翻译"
    icon = "🌐"
    subtitle = "配置华为云凭据并启动, 之后选中文本连续按两次 Ctrl 即可翻译"

    def __init__(self, master, shell):
        super().__init__(master, shell)

        self._vars = {key: tk.StringVar() for key, _ in FIELDS}
        self._status_var = tk.StringVar(value="")
        self._result_var = tk.StringVar(value=EMPTY_RESULT_HINT)
        self._test_queue = queue.Queue()
        self._test_poll_id = None
        self._testing = False
        self._saved_path = ""

        self.service = TranslateService(
            shell.root,
            on_state_change=self._refresh_state,
            on_show_window=self._show_me,
            on_exit=shell.on_close,
            theme=self.theme,
        )

        self._build_toolbar()
        self.add_divider()
        self._build_form()
        self._build_report()

        self._prefill()
        self._load_config()
        self._refresh_state()

    # ---------------- 界面构建 ----------------
    def _build_toolbar(self):
        bar, head, actions = self.build_toolbar()

        ttk.Label(head, text=APP_TITLE, style="PanelHeader.TLabel").pack(
            side="left"
        )
        ttk.Label(head, text="启动后选中文本, 连续按两次 Ctrl 即可翻译",
                  style="PanelHint.TLabel").pack(side="left", padx=(12, 0))

        # 右侧按 主操作 在最外, 次操作 靠内 的顺序排
        self.btn_toggle = ttk.Button(
            actions, text="启动翻译", style="Accent.TButton",
            command=self._toggle_running,
        )
        self.btn_toggle.pack(side="right")

        self.btn_pause = ttk.Button(
            actions, text="暂停热键", style="Secondary.TButton",
            command=self._toggle_pause, state="disabled",
        )
        self.btn_pause.pack(side="right", padx=(0, 8))

    def _build_form(self):
        body = ttk.Frame(self, padding=(16, 14))
        body.pack(side="top", fill="x")

        card = ttk.LabelFrame(body, text="华为云 NLP 凭据", padding=16)
        card.pack(side="top", fill="x")
        card.columnconfigure(1, weight=1)

        ttk.Label(
            card,
            text="填写后点击「保存凭据」或「启动翻译」都会写入用户配置目录。",
            style="CardMuted.TLabel",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))

        for index, (key, label) in enumerate(FIELDS, start=1):
            ttk.Label(card, text=label, style="Card.TLabel").grid(
                row=index, column=0, sticky="e", padx=(0, 10), pady=3
            )
            entry = ttk.Entry(card, textvariable=self._vars[key], width=48)
            if key == "sk":
                entry.configure(show="*")
            entry.grid(row=index, column=1, sticky="we", pady=3)

        buttons = ttk.Frame(card, style="Card.TFrame")
        buttons.grid(row=len(FIELDS) + 1, column=0, columnspan=2,
                     sticky="e", pady=(12, 0))

        self.btn_test = ttk.Button(
            buttons, text="测试连接", style="Secondary.TButton",
            command=self._test_connection,
        )
        self.btn_test.pack(side="left", padx=(0, 6))
        ttk.Button(buttons, text="保存凭据", style="Accent.TButton",
                   command=self._save).pack(side="left")

    def _build_report(self):
        body = ttk.Frame(self, padding=(16, 0))
        body.pack(side="top", fill="both", expand=True)

        ttk.Label(body, textvariable=self._status_var,
                  style="Muted.TLabel").pack(anchor="w")

        card = ttk.LabelFrame(body, text="最近一次翻译", padding=16)
        card.pack(side="top", fill="both", expand=True, pady=(12, 16))
        ttk.Label(
            card, textvariable=self._result_var, style="Card.TLabel",
            wraplength=820, justify="left", anchor="nw",
        ).pack(anchor="w", fill="both", expand=True)

    # ---------------- 初始数据 ----------------
    def _prefill(self):
        """把已有来源 (环境变量 / 旧版配置 / .env / csv) 的值预填进表单。"""
        try:
            values = storage.current_values()
        except Exception:
            logger.warning("读取已有凭据失败", exc_info=True)
            values = {}
        for key, _ in FIELDS:
            self._vars[key].set(values.get(key, "") or "")

    def _load_config(self):
        """启动时只装载已有凭据, 翻译功能默认不开启, 等用户点启动。"""
        try:
            config = storage.load()
        except Exception as exc:
            logger.info("尚无完整凭据, 划词翻译待配置: %s", exc)
            return
        self.service.set_config(config)

    def _values(self):
        return {key: var.get().strip() for key, var in self._vars.items()}

    def _build_config(self, values):
        return Config(
            ak=values["ak"],
            sk=values["sk"],
            project_id=values["project_id"],
            region=values["region"] or REGION,
        )

    # ---------------- 状态刷新 ----------------
    def on_show(self):
        self._refresh_state()

    def _refresh_state(self):
        running = self.service.running
        ready = self.service.ready
        paused = self.service.paused

        self.btn_toggle.configure(
            text="停止翻译" if running else "启动翻译",
            style="Danger.TButton" if running else "Accent.TButton",
        )
        self.btn_pause.configure(
            text="恢复热键" if paused else "暂停热键",
            state="normal" if running else "disabled",
        )

        if running and paused:
            self._status_var.set(
                "已暂停: 全局热键当前不响应, 点击「恢复热键」继续"
            )
            indicator = "翻译热键: 已暂停"
        elif running:
            region = self.service.config.region if self.service.config else REGION
            self._status_var.set(
                f"运行中: 选中文本后连续按两次 Ctrl 触发翻译 (region={region})"
            )
            indicator = "翻译热键: 已启用"
        elif ready:
            self._status_var.set("未启动: 点击「启动翻译」开始划词翻译")
            indicator = ""
        else:
            self._status_var.set(
                "未配置: 填写 AK / SK / Project ID 后点击「启动翻译」"
            )
            indicator = ""

        self.shell.set_indicator("translate", indicator)

        result = self.service.last_result or EMPTY_RESULT_HINT
        if len(result) > MAX_RESULT_CHARS:
            result = result[:MAX_RESULT_CHARS] + " ..."
        self._result_var.set(result)

    def _show_me(self):
        """托盘菜单: 切回本页面并把主窗口拉到前台。"""
        self.shell.show(self.key)
        self.shell.raise_window()

    # ---------------- 交互 ----------------
    def _toggle_pause(self):
        self.service.toggle_paused()

    def _toggle_running(self):
        """启动或停止翻译; 启动前先把表单里的凭据落盘。"""
        if self.service.running:
            self.service.stop()
            return

        values = self._values()
        if not (values["ak"] and values["sk"] and values["project_id"]):
            self._status_var.set("AK / SK / Project ID 都不能为空")
            return
        if not self._store_config(values):
            return
        self.service.start()

    def _store_config(self, values):
        """把凭据写入用户配置目录并交给服务; 失败返回 False。"""
        config = self._build_config(values)
        try:
            path = storage.save(config)
        except OSError as exc:
            logger.exception("保存凭据失败")
            show_error(f"保存配置失败: {exc}", parent=self.window)
            return False

        self._saved_path = path
        logger.info("凭据已保存: %s", path)
        self.service.set_config(config)
        return True

    def _save(self):
        values = self._values()
        if not (values["ak"] and values["sk"] and values["project_id"]):
            self._status_var.set("AK / SK / Project ID 都不能为空")
            return
        if not self._store_config(values):
            return
        self._status_var.set(f"凭据已保存: {self._saved_path}")

    def _test_connection(self):
        if self._testing:
            return
        values = self._values()
        if not (values["ak"] and values["sk"] and values["project_id"]):
            self._status_var.set("AK / SK / Project ID 都不能为空")
            return

        self._set_testing(True, "正在测试连接 ...")
        config = self._build_config(values)

        def worker():
            try:
                Translator(config).translate(SKIP_TEST_TEXT)
                self._test_queue.put((True, "连接成功, 凭据可用"))
            except Exception as exc:  # 网络/鉴权错误都要展示给用户
                logger.warning("测试连接失败: %s", exc)
                self._test_queue.put((False, f"连接失败: {exc}"))

        threading.Thread(
            target=worker, name="thione-translate-test", daemon=True
        ).start()
        self._schedule_test_poll()

    def _set_testing(self, busy, message=""):
        self._testing = busy
        self.btn_test.configure(state="disabled" if busy else "normal")
        if message:
            self._status_var.set(message)

    def _schedule_test_poll(self):
        """轮询后台的测试结果; 页面销毁后不再续排。"""
        try:
            self._test_poll_id = self.after(80, self._poll_test)
        except tk.TclError:
            self._test_poll_id = None

    def _poll_test(self):
        self._test_poll_id = None
        try:
            ok, message = self._test_queue.get_nowait()
        except queue.Empty:
            self._schedule_test_poll()
            return
        self._set_testing(False, message)
        if not ok:
            self.bell()

    # ---------------- 收尾 ----------------
    def on_close(self):
        """停掉热键与托盘; 主窗口随外壳一起关闭, 因此这里不阻止退出。"""
        if self._test_poll_id is not None:
            try:
                self.after_cancel(self._test_poll_id)
            except tk.TclError:
                pass
            self._test_poll_id = None
        self.service.shutdown()
        return True
