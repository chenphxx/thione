"""划词翻译页面: 服务选择与凭据配置、启动开关与最近一次翻译结果。

翻译功能默认不启动: 打开 thione 只是把服务选择与凭据读进来, 热键与托盘图标都要等
用户在本页面点「启动翻译」之后才建立, 避免一开程序就挂上全局键盘钩子。
"""

import logging
import queue
import threading
import tkinter as tk
from tkinter import ttk

from ...errors import show_error
from ...shell.page import ToolPage
from ...widgets import bind_mousewheel, unbind_mousewheel
from . import storage
from .config import Config
from .constants import PAGE_TITLE, REGION
from .language import (
    AUTO_LANG,
    AUTO_TARGET_LABEL,
    DEFAULT_TARGET_LANG,
    LANGUAGE_LABELS,
    language_label,
    preferred_target,
    resolve_direction,
)
from .providers import (
    DEFAULT_PROVIDER,
    PROVIDER_SPECS,
    build_provider,
    spec_for,
)
from .service import TranslateService

logger = logging.getLogger(__name__)

FIELDS = (
    ("ak", "Access Key (AK)"),
    ("sk", "Secret Key (SK)"),
    ("project_id", "Project ID"),
    ("region", "Region"),
)

#: 服务选择区里服务名一列的宽度, 让两行的说明文案左对齐
PROVIDER_LABEL_WIDTH = 140

#: 语言下拉框的宽度 (字符数), 容得下最长的一项显示名
SOURCE_COMBO_WIDTH = 18
TARGET_COMBO_WIDTH = 26

#: 测试连接用的短文本, 只要能走通一次真实翻译即可
SKIP_TEST_TEXT = "Hello"

#: 最近一次结果在界面上最多显示的长度
MAX_RESULT_CHARS = 600

#: 还没有翻译过时结果区显示的引导文案
EMPTY_RESULT_HINT = "还没有翻译记录 启动翻译后选中任意文本 连续按两次 Ctrl 试试"


class TranslatePage(ToolPage):
    """选择翻译服务与凭据并常驻划词翻译热键的工具页面。"""

    key = "translate"
    title = "划词翻译"
    icon = "🌐"
    subtitle = "选择翻译服务并启动, 之后选中文本连续按两次 Ctrl 即可翻译"

    def __init__(self, master, shell):
        super().__init__(master, shell)

        self._vars = {key: tk.StringVar() for key, _ in FIELDS}
        self._provider_var = tk.StringVar(value=DEFAULT_PROVIDER)
        self._cred_hint_var = tk.StringVar(value="")
        self._lang_hint_var = tk.StringVar(value="")
        # 源语言与目标语言的领域语言代码, 显示名与代码的对应关系随服务变化
        self._source_lang = AUTO_LANG
        self._target_lang = DEFAULT_TARGET_LANG
        self._source_labels = {}
        self._target_labels = {}
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
        # 结果区先 pack 并贴住底部, 窗口变矮时挤压的是上面的表单而不是它
        self._build_report()
        self._build_form()

        self._prefill()
        self._sync_provider_ui()
        self._load_config()
        self._refresh_state()

    # ---------------- 界面构建 ----------------
    def _build_provider_card(self, body):
        """翻译服务二选一; 换服务后不必重启, 下一次翻译就用新的服务。

        @param body: 放置卡片的容器
        """
        card = ttk.LabelFrame(body, text="翻译服务", padding=(16, 12))
        card.pack(side="top", fill="x", pady=(0, 10))

        for spec in PROVIDER_SPECS:
            row = ttk.Frame(card, style="Card.TFrame")
            row.pack(side="top", fill="x", pady=2)
            # 第一列固定宽度, 三行的说明文案才会对齐
            row.columnconfigure(0, minsize=PROVIDER_LABEL_WIDTH)
            ttk.Radiobutton(
                row, text=spec.label, value=spec.name,
                variable=self._provider_var, style="Card.TRadiobutton",
                command=self._on_provider_change,
            ).grid(row=0, column=0, sticky="w")
            ttk.Label(row, text=spec.hint, style="CardMuted.TLabel").grid(
                row=0, column=1, sticky="w", padx=(12, 0)
            )

    def _build_toolbar(self):
        bar, head, actions = self.build_toolbar()

        ttk.Label(head, text=PAGE_TITLE, style="PanelHeader.TLabel").pack(
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

    def _build_language_card(self, body):
        """源语言与目标语言; 可选范围随当前服务变化, 换语言立即生效。

        @param body: 放置卡片的容器
        """
        card = ttk.LabelFrame(body, text="翻译语言", padding=(16, 12))
        card.pack(side="top", fill="x", pady=(0, 10))

        row = ttk.Frame(card, style="Card.TFrame")
        row.pack(side="top", fill="x")

        ttk.Label(row, text="源语言", style="Card.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        self.combo_source = ttk.Combobox(
            row, state="readonly", width=SOURCE_COMBO_WIDTH
        )
        self.combo_source.grid(row=0, column=1, sticky="w", padx=(10, 20))
        self.combo_source.bind("<<ComboboxSelected>>",
                               lambda e: self._on_language_change())

        ttk.Label(row, text="目标语言", style="Card.TLabel").grid(
            row=0, column=2, sticky="w"
        )
        self.combo_target = ttk.Combobox(
            row, state="readonly", width=TARGET_COMBO_WIDTH
        )
        self.combo_target.grid(row=0, column=3, sticky="w", padx=(10, 0))
        self.combo_target.bind("<<ComboboxSelected>>",
                               lambda e: self._on_language_change())

        # 提示跟在两个下拉框右边, 少占一行高度
        ttk.Label(row, textvariable=self._lang_hint_var,
                  style="CardMuted.TLabel").grid(
            row=0, column=4, sticky="w", padx=(16, 0)
        )

    def _build_form(self):
        """服务选择 语言选择与凭据表单。

        表单放在可滚动的画布里: 窗口高度不足时滚动条才出现, 表单不会被裁掉,
        也不会把下面的结果区挤出可视区。
        """
        outer = ttk.Frame(self)
        outer.pack(side="top", fill="both", expand=True)

        self.form_canvas = tk.Canvas(outer, highlightthickness=0, bd=0)
        self.form_canvas._thione_surface = "bg"
        self.form_scroll = ttk.Scrollbar(
            outer, orient="vertical", command=self.form_canvas.yview
        )
        self.form_canvas.configure(yscrollcommand=self.form_scroll.set)
        self.form_canvas.pack(side="left", fill="both", expand=True)

        body = ttk.Frame(self.form_canvas, padding=(16, 14))
        self._form_window = self.form_canvas.create_window(
            (0, 0), window=body, anchor="nw"
        )
        body.bind("<Configure>", self._on_form_content_configure)
        self.form_canvas.bind("<Configure>", self._on_form_canvas_configure)
        bind_mousewheel((body, self.form_canvas), self.form_canvas)

        self._build_provider_card(body)
        self._build_language_card(body)

        card = ttk.LabelFrame(body, text="华为云 NLP 凭据", padding=(16, 12))
        card.pack(side="top", fill="x")
        card.columnconfigure(1, weight=1)

        ttk.Label(
            card,
            textvariable=self._cred_hint_var,
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
        """运行状态与最近一次翻译, 固定贴住页面底部。"""
        body = ttk.Frame(self, padding=(16, 10))
        body.pack(side="bottom", fill="x")

        ttk.Label(body, textvariable=self._status_var,
                  style="Muted.TLabel").pack(anchor="w")

        card = ttk.LabelFrame(body, text="最近一次翻译", padding=16)
        card.pack(side="top", fill="x", pady=(8, 0))
        self.result_label = ttk.Label(
            card, textvariable=self._result_var, style="Card.TLabel",
            justify="left", anchor="nw",
        )
        self.result_label.pack(anchor="w", fill="both", expand=True)
        # 结果文本可能很长, 换行宽度跟着卡片宽度走, 窄窗口下不会被横向裁掉
        card.bind("<Configure>", self._on_result_card_configure)

    def _on_result_card_configure(self, event):
        """结果文本按卡片实际宽度换行。

        @param event: Tk 的 Configure 事件, width 为卡片宽度
        """
        self.result_label.configure(wraplength=max(event.width - 32, 200))

    # ---------------- 表单滚动 ----------------
    def _on_form_content_configure(self, _event=None):
        """表单高度变化时刷新滚动范围, 并同步滚动条的显隐。"""
        self.form_canvas.configure(scrollregion=self.form_canvas.bbox("all"))
        self._sync_form_scrollbar()

    def _on_form_canvas_configure(self, event):
        """画布尺寸变化时让表单跟着变宽, 并重新判断是否需要滚动条。"""
        self.form_canvas.itemconfigure(self._form_window, width=event.width)
        self._sync_form_scrollbar()

    def _sync_form_scrollbar(self):
        """表单装得下就不显示滚动条, 装不下时才显示并允许滚动。"""
        bbox = self.form_canvas.bbox("all")
        overflows = (
            bbox is not None
            and (bbox[3] - bbox[1]) > self.form_canvas.winfo_height()
        )
        if overflows:
            if not self.form_scroll.winfo_ismapped():
                self.form_scroll.pack(side="right", fill="y")
        elif self.form_scroll.winfo_ismapped():
            self.form_scroll.pack_forget()
            self.form_canvas.yview_moveto(0)

    # ---------------- 初始数据 ----------------
    def _prefill(self):
        """把已有来源 (环境变量 / 旧版配置 / .env / csv) 的选择与凭据预填进表单。"""
        try:
            values = storage.current_values()
        except Exception:
            logger.warning("读取已有凭据失败", exc_info=True)
            values = {}
        for key, _ in FIELDS:
            self._vars[key].set(values.get(key, "") or "")
        self._provider_var.set(values.get("provider") or DEFAULT_PROVIDER)
        self._source_lang = values.get("source_lang") or AUTO_LANG
        self._target_lang = values.get("target_lang") or DEFAULT_TARGET_LANG

    def _load_config(self):
        """启动时只装载已有配置, 翻译功能默认不开启, 等用户点启动。"""
        try:
            config = storage.load()
        except Exception as exc:
            logger.info("翻译服务尚未就绪, 划词翻译待配置: %s", exc)
            return
        self.service.set_config(config)

    def _values(self):
        values = {key: var.get().strip() for key, var in self._vars.items()}
        values["provider"] = self._provider_var.get()
        values["source_lang"] = self._source_lang
        values["target_lang"] = self._target_lang
        return values

    def _build_config(self, values):
        return Config(
            ak=values["ak"],
            sk=values["sk"],
            project_id=values["project_id"],
            region=values["region"] or REGION,
            provider=values.get("provider") or DEFAULT_PROVIDER,
            source_lang=values.get("source_lang") or AUTO_LANG,
            target_lang=values.get("target_lang") or DEFAULT_TARGET_LANG,
        )

    @staticmethod
    def _ready_to_run(values):
        """是否具备翻译条件: 不需要凭据的服务直接可用, 需要的要求三项填全。

        @param values: _values() 的结果
        @return: 当前服务是否可以直接使用
        """
        if not spec_for(values["provider"]).requires_credentials:
            return True
        return all(values[key] for key in ("ak", "sk", "project_id"))

    def _apply_config(self, values):
        """把表单里的选择交给服务, 换服务与换凭据都会立即生效。

        @param values: _values() 的结果
        @return: 是否已经装载 (华为云凭据不全时不装载)
        """
        if not self._ready_to_run(values):
            return False
        self.service.set_config(self._build_config(values))
        return True

    # ---------------- 状态刷新 ----------------
    def _sync_provider_ui(self):
        """按当前服务刷新凭据提示与可选语言。"""
        spec = spec_for(self._provider_var.get())
        if spec.requires_credentials:
            self._cred_hint_var.set(
                "填写后点击「保存凭据」或「启动翻译」都会写入用户配置目录。"
            )
        else:
            self._cred_hint_var.set(
                f"当前使用{spec.label}, 下面的凭据不会被使用, 切回华为云时再填。"
            )
        self._sync_language_ui()

    def _sync_language_ui(self):
        """按当前服务重建两个语言下拉框, 并把选择收敛到支持的范围。"""
        spec = spec_for(self._provider_var.get())
        self._source_labels = {
            language_label(code): code
            for code in (AUTO_LANG,) + tuple(LANGUAGE_LABELS)
            if code in spec.source_languages
        }
        self._target_labels = {
            self._target_label(code): code
            for code in (AUTO_LANG,) + tuple(LANGUAGE_LABELS)
            if code == AUTO_LANG or code in spec.languages
        }
        self.combo_source["values"] = list(self._source_labels)
        self.combo_target["values"] = list(self._target_labels)
        # 只有自动识别一项时说明该服务不能指定源语言, 直接置灰
        self.combo_source.configure(
            state="readonly" if len(self._source_labels) > 1 else "disabled"
        )

        if self._source_lang not in self._source_labels.values():
            self._source_lang = AUTO_LANG
        if self._target_lang not in self._target_labels.values():
            self._target_lang = DEFAULT_TARGET_LANG
        self.combo_source.set(language_label(self._source_lang))
        self._apply_preferred_target()

        if len(self._source_labels) > 1:
            hint = f"可选 {len(spec.languages)} 种目标语言"
        else:
            hint = "该服务由服务端识别源语言"
        self._lang_hint_var.set(hint)

    @staticmethod
    def _target_label(code):
        """目标语言下拉框里某一项的显示名。"""
        return AUTO_TARGET_LABEL if code == AUTO_LANG else language_label(code)

    def _read_language_ui(self):
        """把下拉框上选中的显示名换回领域语言代码。"""
        self._source_lang = self._source_labels.get(
            self.combo_source.get(), AUTO_LANG
        )
        self._target_lang = self._target_labels.get(
            self.combo_target.get(), DEFAULT_TARGET_LANG
        )

    def _apply_preferred_target(self):
        """两边都选了中文时把目标语言换成英文, 并同步下拉框的显示。

        目标语言默认是自动, 因此只有用户明确选了中文才会走到这里。
        """
        self._target_lang = preferred_target(self._source_lang, self._target_lang)
        self.combo_target.set(self._target_label(self._target_lang))

    def _service_detail(self):
        """状态行里的服务说明: 服务名, 需要凭据时带上区域, 再跟上翻译方向。"""
        config = self.service.config
        provider = (config.provider if config is not None
                    else self._provider_var.get())
        spec = spec_for(provider)
        parts = [spec.label]
        if spec.requires_credentials:
            region = config.region if config is not None else REGION
            parts.append(f"region={region}")
        # 目标语言用下拉框里的显示名, 自动项才说清它代表什么方向
        parts.append(f"{language_label(self._source_lang)} → "
                     f"{self._target_label(self._target_lang)}")
        return " · ".join(parts)

    def on_show(self):
        self._refresh_state()

    def on_hide(self):
        """切走时解除滚轮绑定, 避免在其他页面上仍然响应本页的滚动。"""
        unbind_mousewheel(self.form_canvas)

    def _refresh_state(self):
        running = self.service.running
        ready = self.service.ready
        paused = self.service.paused

        self._sync_provider_ui()

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
            self._status_var.set(
                "运行中: 选中文本后连续按两次 Ctrl 触发翻译 "
                f"({self._service_detail()})"
            )
            indicator = "翻译热键: 已启用"
        elif ready:
            self._status_var.set(
                f"未启动 ({self._service_detail()}): 点击「启动翻译」开始划词翻译"
            )
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

    def _on_provider_change(self):
        """换服务: 立即生效, 不必先停止翻译; 凭据不全时只记下选择。"""
        self._sync_language_ui()
        self._apply_config(self._values())
        self._refresh_state()

    def _on_language_change(self):
        """换语言: 与换服务一样立即生效, 下一次翻译就用新的方向。"""
        self._read_language_ui()
        self._apply_preferred_target()
        self._apply_config(self._values())
        self._refresh_state()

    def _toggle_running(self):
        """启动或停止翻译; 启动前先把表单里的选择与凭据落盘。"""
        if self.service.running:
            self.service.stop()
            return

        values = self._values()
        if not self._ready_to_run(values):
            self._status_var.set("AK / SK / Project ID 都不能为空")
            return
        if not self._store_config(values):
            return
        self.service.start()

    def _store_config(self, values):
        """把服务选择与凭据写入用户配置目录并交给服务; 失败返回 False。"""
        config = self._build_config(values)
        try:
            path = storage.save(config)
        except OSError as exc:
            logger.exception("保存凭据失败")
            show_error(f"保存配置失败: {exc}", parent=self.window)
            return False

        self._saved_path = path
        logger.info("配置已保存: %s", path)
        self._apply_config(values)
        return True

    def _save(self):
        values = self._values()
        if not self._ready_to_run(values):
            self._status_var.set("AK / SK / Project ID 都不能为空")
            return
        if not self._store_config(values):
            return
        label = spec_for(values["provider"]).label
        self._status_var.set(f"已保存 ({label}): {self._saved_path}")

    def _test_connection(self):
        if self._testing:
            return
        values = self._values()
        if not self._ready_to_run(values):
            self._status_var.set("AK / SK / Project ID 都不能为空")
            return

        label = spec_for(values["provider"]).label
        self._set_testing(True, f"正在测试连接 ({label}) ...")
        config = self._build_config(values)

        def worker():
            try:
                source_lang, target_lang = resolve_direction(
                    SKIP_TEST_TEXT, config.source_lang, config.target_lang
                )
                build_provider(config).translate(
                    SKIP_TEST_TEXT, source_lang, target_lang
                )
                self._test_queue.put((True, f"{label} 连接成功"))
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
        unbind_mousewheel(self.form_canvas)
        if self._test_poll_id is not None:
            try:
                self.after_cancel(self._test_poll_id)
            except tk.TclError:
                pass
            self._test_poll_id = None
        self.service.shutdown()
        return True
