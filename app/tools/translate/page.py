"""划词翻译页面: 服务选择与凭据配置, 启动开关与最近一次翻译结果

翻译功能默认不启动: 打开 thione 只是把服务选择与凭据读进来, 热键与托盘图标都要等
用户在本页面点'启动翻译'之后才建立, 避免一开程序就挂上全局键盘钩子
"""

import logging
import queue
import threading
import tkinter as tk
from tkinter import ttk

from ... import kit
from ...dpi import scale
from ...errors import show_error
from ...shell.page import ToolPage
from ...theme import BODY_GAP, SIZE_BODY, SIZE_LABEL, tint
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
PROVIDER_LABEL_WIDTH = scale(140)

#: 最近一次翻译面板的宽度 (像素), 与设计稿一致
REPORT_WIDTH = scale(364)

#: 测试连接用的短文本, 只要能走通一次真实翻译即可
SKIP_TEST_TEXT = "Hello"

#: 最近一次结果在界面上最多显示的长度
MAX_RESULT_CHARS = 600

#: 还没有翻译过时结果区显示的引导文案
EMPTY_RESULT_HINT = "还没有翻译记录 启动翻译后选中任意文本 连续按两次 Ctrl 试试"

#: 还没有翻译过时原文区显示的引导文案
EMPTY_SOURCE_HINT = "还没有翻译记录"


class TranslatePage(ToolPage):
    """选择翻译服务与凭据并常驻划词翻译热键的工具页面"""

    key = "translate"
    title = "划词翻译"
    icon = "\uE774"
    subtitle = "启动后选中文本, 连续按两次 Ctrl 即可翻译"

    def __init__(self, master, shell):
        super().__init__(master, shell)

        self._vars = {key: tk.StringVar() for key, _ in FIELDS}
        self._provider_var = tk.StringVar(value=DEFAULT_PROVIDER)
        self._cred_hint_var = tk.StringVar(value="")
        self._lang_hint_var = tk.StringVar(value="")
        self._cred_state_var = tk.StringVar(value="")
        # 源语言与目标语言的领域语言代码, 显示名与代码的对应关系随服务变化
        self._source_lang = AUTO_LANG
        self._target_lang = DEFAULT_TARGET_LANG
        self._source_labels = {}
        self._target_labels = {}
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
        self._build_statusbar()
        self._build_body()

        self._prefill()
        self._sync_provider_ui()
        self._load_config()
        self._refresh_state()

    # ---------------- 界面构建 ----------------
    def _build_toolbar(self):
        """顶栏按钮: 测试连接 与 启动翻译, 与设计稿一致"""
        self.btn_test, self.btn_toggle = self.add_actions((
            ("测试连接", None, self._test_connection),
            ("启动翻译", "Primary.TButton", self._toggle_running),
        ))

    def _build_statusbar(self):
        """状态栏: 圆点 说明 本日次数 与右侧的暂停 停止按钮"""
        self.status.set_kind("idle")
        self.status.set_text("翻译未启动")
        self.metric = kit.text(self.status.tail, self.theme, size=SIZE_LABEL,
                               mono_font=True, surface="side")
        self.status.add_tail(self.metric)
        self.btn_pause = ttk.Button(self.status.actions, text="暂停热键",
                                    style="TButton", state="disabled",
                                    command=self._toggle_pause)
        self.status.add_action(self.btn_pause)
        self.btn_stop = ttk.Button(self.status.actions, text="停止翻译",
                                   style="TButton", state="disabled",
                                   command=self._toggle_running)
        self.status.add_action(self.btn_stop)

    def _build_body(self):
        """左栏是服务 语言与凭据, 右栏固定 364 像素宽显示最近一次翻译"""
        area = tk.Frame(self.body, bd=0, highlightthickness=0)
        tint(area, bg="canvas")
        area.configure(bg=self.theme.rgb("canvas"))
        area.pack(side="top", fill="both", expand=True)

        self._build_report(area)
        left = tk.Frame(area, bd=0, highlightthickness=0)
        tint(left, bg="canvas")
        left.configure(bg=self.theme.rgb("canvas"))
        left.pack(side="left", fill="both", expand=True, padx=(0, 14))
        self._build_provider_card(left)
        self._build_language_card(left)
        self._build_credential_card(left)

    def _build_provider_card(self, body):
        """翻译服务二选一; 换服务后不必重启, 下一次翻译就用新的服务

        @param body: 放置面板的容器
        """
        panel = kit.Panel(body, self.theme, title="翻译服务", body_pad=(14, 8))
        panel.pack(side="top", fill="x", pady=(0, BODY_GAP))
        self._provider_rows = {}
        for spec in PROVIDER_SPECS:
            row = kit.RadioRow(panel.body, self.theme, value=spec.name,
                               label=spec.label, hint=spec.hint,
                               variable=self._provider_var,
                               command=self._on_provider_change,
                               surface="panel")
            row.pack(side="top", fill="x")
            self._provider_rows[spec.name] = row

    def _build_language_card(self, body):
        """源语言与目标语言; 可选范围随当前服务变化, 换语言立即生效

        @param body: 放置面板的容器
        """
        panel = kit.Panel(body, self.theme, title="翻译语言")
        panel.pack(side="top", fill="x", pady=(0, BODY_GAP))
        row = tk.Frame(panel.body, bd=0, highlightthickness=0)
        tint(row, bg="panel")
        row.configure(bg=self.theme.rgb("panel"))
        row.pack(side="top", fill="x")
        row.columnconfigure(0, weight=1, uniform="lang")
        row.columnconfigure(1, weight=1, uniform="lang")
        self.combo_source = self._language_field(row, 0, "源语言", None)
        self.combo_target = self._language_field(row, 1, "目标语言", None)
        kit.text(panel.body, self.theme, variable=self._lang_hint_var,
                 size=SIZE_LABEL, token="muted",
                 surface="panel").pack(anchor="w", pady=(10, 0))

    def _build_credential_card(self, body):
        """华为云凭据: 四个字段排成两列, 右下角是清空与保存

        @param body: 放置面板的容器
        """
        panel = kit.Panel(body, self.theme, title="华为云 NLP 凭据",
                          right="已保存到 config.ini")
        panel.pack(side="top", fill="x")
        grid = tk.Frame(panel.body, bd=0, highlightthickness=0)
        tint(grid, bg="panel")
        grid.configure(bg=self.theme.rgb("panel"))
        grid.pack(side="top", fill="x")
        grid.columnconfigure(1, weight=1)
        grid.columnconfigure(3, weight=1)
        holders = {}
        for index, (key, label) in enumerate(FIELDS):
            column = (index % 2) * 2
            line = index // 2
            caption = kit.text(grid, self.theme, value=label, size=SIZE_LABEL,
                               token="muted", surface="panel", anchor="w")
            caption.grid(row=line, column=column, sticky="w",
                         padx=(0, 10) if column == 0 else (14, 10),
                         pady=(0, 8))
            field = kit.EntryField(grid, self.theme,
                                   variable=self._vars[key], width=None,
                                   mono_font=True)
            if key == "sk":
                field.entry.configure(show="*")
            field.grid(row=line, column=column + 1, sticky="ew", pady=(0, 8))
            holders[key] = field
        self._cred_fields = holders
        kit.text(panel.body, self.theme, variable=self._cred_hint_var,
                 size=SIZE_LABEL, token="muted",
                 surface="panel").pack(anchor="w", pady=(2, 10))
        buttons = tk.Frame(panel.body, bd=0, highlightthickness=0)
        tint(buttons, bg="panel")
        buttons.configure(bg=self.theme.rgb("panel"))
        buttons.pack(side="top", anchor="e")
        ttk.Button(buttons, text="清空凭据", style="TButton",
                   command=self._clear_credentials).pack(side="left")
        ttk.Button(buttons, text="保存凭据", style="Primary.TButton",
                   command=self._save).pack(side="left", padx=(8, 0))

    def _language_field(self, row, column, caption, previous):
        """建立一列语言下拉框: 标签在上, 控件框在下

        @param row: 父容器
        @param column: 列号
        @param caption: 标签文字
        @param previous: 已经建好的下拉控件, 不为空时直接复用
        @return: 下拉控件
        """
        holder = tk.Frame(row, bd=0, highlightthickness=0)
        tint(holder, bg="panel")
        holder.configure(bg=self.theme.rgb("panel"))
        holder.grid(row=0, column=column, sticky="ew",
                    padx=(0, 14) if column == 0 else (0, 0))
        kit.text(holder, self.theme, value=caption, size=SIZE_LABEL,
                 token="muted", surface="panel").pack(anchor="w", pady=(0, 5))
        if previous is not None:
            previous.pack(fill="x")
            return previous
        combo = kit.Dropdown(holder, self.theme, values=[], surface="panel",
                             command=lambda _label: self._on_language_change())
        combo.pack(fill="x")
        return combo

    def _build_report(self, area):
        """右栏: 最近一次翻译的原文与译文

        @param area: 承载左右两栏的容器
        """
        panel = kit.Panel(area, self.theme, title="最近一次翻译", right="",
                          body_pad=(14, 14))
        panel.configure(width=REPORT_WIDTH)
        panel.pack(side="right", fill="y")
        panel.pack_propagate(False)
        self.report_panel = panel
        self.source_view = kit.Area(panel.body, self.theme, height=140,
                                    size=SIZE_LABEL, token="muted",
                                    editable=False, wrap="word")
        self.source_view.pack(fill="x")
        self.result_view = kit.Area(panel.body, self.theme, height=180,
                                    size=SIZE_BODY, token="text",
                                    editable=False, wrap="word")
        self.result_view.pack(fill="both", expand=True, pady=(12, 0))
        buttons = tk.Frame(panel.body, bd=0, highlightthickness=0)
        tint(buttons, bg="panel")
        buttons.configure(bg=self.theme.rgb("panel"))
        buttons.pack(side="top", anchor="w", pady=(12, 0))
        ttk.Button(buttons, text="复制结果", style="TButton",
                   command=self._copy_result).pack(side="left")
        ttk.Button(buttons, text="重新翻译", style="TButton",
                   command=self._retry_translation).pack(side="left",
                                                         padx=(8, 0))
        self.source_view.set(EMPTY_RESULT_HINT)

    def _prefill(self):
        """把已有来源 (环境变量 / 旧版配置 / .env / csv) 的选择与凭据预填进表单"""
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
        """启动时只装载已有配置, 翻译功能默认不开启, 等用户点启动"""
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
        """是否具备翻译条件: 不需要凭据的服务直接可用, 需要的要求三项填全

        @param values: _values() 的结果
        @return: 当前服务是否可以直接使用
        """
        if not spec_for(values["provider"]).requires_credentials:
            return True
        return all(values[key] for key in ("ak", "sk", "project_id"))

    def _apply_config(self, values):
        """把表单里的选择交给服务, 换服务与换凭据都会立即生效

        @param values: _values() 的结果
        @return: 是否已经装载 (华为云凭据不全时不装载)
        """
        if not self._ready_to_run(values):
            return False
        self.service.set_config(self._build_config(values))
        return True

    # ---------------- 状态刷新 ----------------
    def _sync_provider_ui(self):
        """按当前服务刷新凭据提示与可选语言"""
        spec = spec_for(self._provider_var.get())
        if spec.requires_credentials:
            self._cred_hint_var.set(
                "填写后点击'保存凭据'或'启动翻译'都会写入用户配置目录"
            )
        else:
            self._cred_hint_var.set(
                f"当前使用{spec.label}, 下面的凭据不会被使用, 切回华为云时再填"
            )
        self._sync_language_ui()

    def _sync_language_ui(self):
        """按当前服务重建两个语言下拉框, 并把选择收敛到支持的范围"""
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
        self.combo_source.set_values(list(self._source_labels))
        self.combo_target.set_values(list(self._target_labels))
        # 只有自动识别一项时说明该服务不能指定源语言, 直接置灰
        self.combo_source.set_enabled(len(self._source_labels) > 1)

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
        """目标语言下拉框里某一项的显示名"""
        return AUTO_TARGET_LABEL if code == AUTO_LANG else language_label(code)

    def _read_language_ui(self):
        """把下拉框上选中的显示名换回领域语言代码"""
        self._source_lang = self._source_labels.get(
            self.combo_source.value(), AUTO_LANG
        )
        self._target_lang = self._target_labels.get(
            self.combo_target.value(), DEFAULT_TARGET_LANG
        )

    def _apply_preferred_target(self):
        """两边都选了中文时把目标语言换成英文, 并同步下拉框的显示

        目标语言默认是自动, 因此只有用户明确选了中文才会走到这里
        """
        self._target_lang = preferred_target(self._source_lang, self._target_lang)
        self.combo_target.set(self._target_label(self._target_lang))

    def _service_detail(self):
        """状态行里的服务说明: 服务名, 需要凭据时带上区域, 再跟上翻译方向"""
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
        return " | ".join(parts)

    def on_show(self):
        self._refresh_state()

    def on_hide(self):
        """页面切走时的清理; 本页没有需要解绑的资源"""

    def _refresh_state(self):
        running = self.service.running
        ready = self.service.ready
        paused = self.service.paused

        self._sync_provider_ui()

        self.btn_toggle.configure(
            text="停止翻译" if running else "启动翻译",
            style="TButton" if running else "Primary.TButton",
        )
        self.btn_pause.configure(
            text="恢复热键" if paused else "暂停热键",
            state="normal" if running else "disabled",
        )
        self.btn_stop.configure(state="normal" if running else "disabled")
        self.btn_test.configure(state="disabled" if self._testing else "normal")
        self.status.set_kind("ok" if running and not paused else
                             ("warn" if paused else "idle"))
        self.metric.configure(
            text=f"本日 {self.service.daily_count} 次"
            if self.service.daily_count else "")
        self.report_panel.set_right(self._provider_label())

        if running and paused:
            self.status.set_text(
                "已暂停: 全局热键当前不响应, 点击'恢复热键'继续"
            )
            indicator = "翻译热键: 已暂停"
        elif running:
            self.status.set_text("翻译已启动 · 双击 Ctrl 可用")
            indicator = "翻译热键: 已启用"
        elif ready:
            self.status.set_text(
                f"未启动 ({self._service_detail()}): 点击'启动翻译'开始划词翻译")
            indicator = ""
        else:
            self.status.set_text("未配置: 填写 AK / SK / Project ID 后点击'启动翻译'")
            indicator = ""

        self.shell.set_indicator("translate", indicator)

        source = self.service.last_source or EMPTY_SOURCE_HINT
        self.source_view.set(source[:MAX_RESULT_CHARS])
        result = self.service.last_result or EMPTY_RESULT_HINT
        if len(result) > MAX_RESULT_CHARS:
            result = result[:MAX_RESULT_CHARS] + " ..."
        self.result_view.set(result)

    def _provider_label(self):
        """当前服务的显示名

        @return: 服务名
        """
        config = self.service.config
        provider = (config.provider if config is not None
                    else self._provider_var.get())
        return spec_for(provider).label

    def _copy_result(self):
        """把译文复制到剪贴板"""
        text = self.result_view.get()
        if not text or text == EMPTY_RESULT_HINT:
            self.status.set_text("还没有可复制的结果")
            self.status.set_kind("fail")
            return
        self.clipboard_clear()
        self.clipboard_append(text)
        self.status.set_kind("ok")
        self.status.set_text("已复制翻译结果")

    def _retry_translation(self):
        """用最近一次的原文重新翻译一次"""
        source = self.service.last_source
        if not source:
            self.status.set_text("还没有可重新翻译的原文")
            self.status.set_kind("fail")
            return
        self.service.translate_text(source)

    def _clear_credentials(self):
        """清空表单里的凭据并落盘"""
        for var in self._vars.values():
            var.set("")
        self._save()
        self.status.set_text("凭据已清空")

    def _show_me(self):
        """托盘菜单: 切回本页面并把主窗口拉到前台"""
        self.shell.show(self.key)
        self.shell.raise_window()

    # ---------------- 交互 ----------------
    def _toggle_pause(self):
        self.service.toggle_paused()

    def _on_provider_change(self):
        """换服务: 立即生效, 不必先停止翻译; 凭据不全时只记下选择"""
        self._sync_language_ui()
        self._apply_config(self._values())
        self._refresh_state()

    def _on_language_change(self):
        """换语言: 与换服务一样立即生效, 下一次翻译就用新的方向"""
        self._read_language_ui()
        self._apply_preferred_target()
        self._apply_config(self._values())
        self._refresh_state()

    def _toggle_running(self):
        """启动或停止翻译; 启动前先把表单里的选择与凭据落盘"""
        if self.service.running:
            self.service.stop()
            return

        values = self._values()
        if not self._ready_to_run(values):
            self.status.set_text("AK / SK / Project ID 都不能为空")
            return
        if not self._store_config(values):
            return
        self.service.start()

    def _store_config(self, values):
        """把服务选择与凭据写入用户配置目录并交给服务; 失败返回 False"""
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
            self.status.set_text("AK / SK / Project ID 都不能为空")
            return
        if not self._store_config(values):
            return
        label = spec_for(values["provider"]).label
        self.status.set_text(f"已保存 ({label}): {self._saved_path}")

    def _test_connection(self):
        if self._testing:
            return
        values = self._values()
        if not self._ready_to_run(values):
            self.status.set_text("AK / SK / Project ID 都不能为空")
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
            self.status.set_text(message)

    def _schedule_test_poll(self):
        """轮询后台的测试结果; 页面销毁后不再续排"""
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
        """停掉热键与托盘; 主窗口随外壳一起关闭, 因此这里不阻止退出"""
        if self._test_poll_id is not None:
            try:
                self.after_cancel(self._test_poll_id)
            except tk.TclError:
                pass
            self._test_poll_id = None
        self.service.shutdown()
        return True
