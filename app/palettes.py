"""默认主题的令牌表。

配色取自 ui-ux-pro-max 的 Flat Design 设计系统 (folder blue + file amber):
主色是蓝色, 语义色与进度色用琥珀色, 界面不出现渐变与阴影, 只靠描边和留白分层。

这里只保留浅色与深色两组基础令牌, 界面用到的其余令牌 (悬停, 输入框, 滚动条,
缩略图占位色等) 由 build_palette() 按当前明暗方向推导, 不重复维护。

每套主题本身的令牌是独立数据, 目前只保留默认的一套; 若日后要支持多套预设,
在下面再加一组同样结构的令牌, 并让 ThemeManager 记住选中的那一套即可。
"""

#: 主题圆角基准 (像素), 自绘控件按它取圆角半径
RADIUS = 10

#: 浅色模式的基础令牌
LIGHT = {
    "bg": "#f8fafc",
    "cardBg": "#ffffff",
    "text": "#0f172a",
    "muted": "#475569",
    "border": "#e4ecfc",
    "borderStrong": "#cbd9f2",
    "primary": "#2563eb",
    "primaryStrong": "#1d4ed8",
    "primaryWeak": "#eff6ff",
    "onPrimary": "#ffffff",
    "secondary": "#3b82f6",
    "accentAlt": "#d97706",
    "link": "#1d4ed8",
    "ok": "#059669",
    "warn": "#b45309",
    "danger": "#dc2626",
    "codeBg": "#f1f5fd",
}

#: 深色模式的基础令牌
DARK = {
    "bg": "#0b1220",
    "cardBg": "#111c31",
    "text": "#e6ecf5",
    "muted": "#93a3bc",
    "border": "#1e2c46",
    "borderStrong": "#2b3b58",
    "primary": "#2563eb",
    "primaryStrong": "#3b82f6",
    "primaryWeak": "#16243d",
    "onPrimary": "#ffffff",
    "secondary": "#3b82f6",
    "accentAlt": "#f59e0b",
    "link": "#93b4fd",
    "ok": "#34d399",
    "warn": "#fbbf24",
    "danger": "#f87171",
    "codeBg": "#0a101c",
}

#: 深浅模式在界面上的显示名
MODE_NAMES = {"light": "浅色", "dark": "深色"}

#: 模式对应的基础令牌
BASE_TOKENS = {"light": LIGHT, "dark": DARK}


def to_rgb(color):
    """把 #RRGGBB 解析成 (r, g, b) 三元组。

    @param color: 十六进制颜色字符串
    @return: 三个 0-255 的整数
    """
    value = color.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def to_hex(rgb):
    """把 (r, g, b) 转回 #RRGGBB, 分量先夹到 0-255。

    @param rgb: 三个分量, 允许是浮点数
    @return: 大写十六进制颜色字符串
    """
    return "#%02X%02X%02X" % tuple(
        max(0, min(255, round(channel))) for channel in rgb
    )


def mix(color_a, color_b, ratio):
    """把 color_a 按比例混向 color_b。

    @param color_a: 起点颜色
    @param color_b: 终点颜色
    @param ratio: 0 返回 color_a, 1 返回 color_b
    @return: 混合后的十六进制颜色
    """
    start = to_rgb(color_a)
    end = to_rgb(color_b)
    return to_hex(tuple(
        s + (e - s) * ratio for s, e in zip(start, end)
    ))


def build_palette(mode):
    """把基础令牌展开成界面实际使用的完整调色板。

    派生令牌统一写成「从某个既有色往文字色方向混」: 深色模式下文字色更亮、
    浅色模式下更暗, 因此同一套比例在两种模式里都指向正确的方向, 不需要为
    每种模式手写悬停色与输入框色。

    @param mode: "light" 或 "dark"
    @return: 令牌字典, 键名与 ThemeManager 及各页面取值保持一致
    @throws KeyError: 模式不存在
    """
    if mode not in BASE_TOKENS:
        raise KeyError("未知模式: " + mode)

    base = BASE_TOKENS[mode]
    dark = mode == "dark"

    bg = base["bg"]
    card = base["cardBg"]
    text = base["text"]
    border_strong = base["borderStrong"]
    primary = base["primary"]

    # 派生底色统一往描边色方向混: 既保证深浅两侧都朝正确的明暗方向走,
    # 又让输入框与悬停底色带上和描边一致的一点冷色, 而不是脏灰

    return {
        # 表面层
        "bg": bg,
        "panel": card,
        "card": card,
        "input": mix(card, border_strong, 0.30),
        "hover": mix(card, border_strong, 0.45),
        "active": mix(card, border_strong, 0.70),
        "border": base["border"],
        "border_strong": border_strong,
        "text": text,
        "muted": base["muted"],
        "header": text,
        # 主色层
        "accent": primary,
        "accent_hover": base["primaryStrong"],
        "accent_weak": base["primaryWeak"],
        "accent_alt": base["accentAlt"],
        "secondary": base["secondary"],
        "on_accent": base["onPrimary"],
        "link": base["link"],
        "ring": mix(bg, primary, 0.5),
        # 语义色
        "ok": base["ok"],
        "warn": base["warn"],
        "success": base["ok"],
        "danger": base["danger"],
        "danger_hover": mix(base["danger"], text, 0.22),
        # 容器与装饰
        "scroll": mix(border_strong, text, 0.2),
        "trough": card,
        "preview": base["codeBg"],
        # 缩略图占位色直接交给 PIL, 保持 RGB 三元组
        "placeholder": to_rgb(mix(card, text, 0.18)),
        # 元信息
        "radius": RADIUS,
        "mode": mode,
        "mode_name": MODE_NAMES[mode],
        "is_dark": dark,
    }


def blend_palette(start, end, ratio):
    """在两套调色板之间插值, 用于主题切换时的颜色过渡。

    只有颜色类令牌参与插值: 字符串色值按十六进制混色, RGB 三元组逐分量插值;
    其余令牌 (圆角, 模式名) 直接取目标值。

    @param start: 起始调色板, build_palette() 的返回值
    @param end: 目标调色板
    @param ratio: 0 表示完全是 start, 1 表示完全是 end
    @return: 插值后的新字典
    """
    blended = {}
    for key, end_value in end.items():
        start_value = start.get(key)
        if (
            isinstance(end_value, str)
            and end_value.startswith("#")
            and isinstance(start_value, str)
        ):
            blended[key] = mix(start_value, end_value, ratio)
        elif (
            isinstance(end_value, tuple)
            and len(end_value) == 3
            and isinstance(start_value, tuple)
            and len(start_value) == 3
        ):
            blended[key] = tuple(
                int(round(s + (e - s) * ratio))
                for s, e in zip(start_value, end_value)
            )
        else:
            blended[key] = end_value
    return blended
