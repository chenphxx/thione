"""默认主题的令牌表。

配色取自 Fluent 2 设计语言: 窗口底, 内容层, 卡片与描边用中性灰堆出层级,
品牌色是 Communication Blue, 语义色用 Fluent 的状态色; 圆角取
borderRadiusMedium, 界面不出现渐变与阴影, 层次只靠中性层与 1 像素描边表达。

这里只保留浅色与深色两组基础令牌, 界面用到的其余令牌 (悬停, 按下, 选中,
输入框, 滚动条, 缩略图占位色等) 由 build_palette() 按当前明暗方向推导,
不重复维护。

每套主题本身的令牌是独立数据, 目前只保留默认的一套; 若日后要支持多套预设,
在下面再加一组同样结构的令牌, 并让 ThemeManager 记住选中的那一套即可。
"""

#: 控件圆角半径 (像素), 取自 Fluent 2 的 borderRadiusMedium
RADIUS = 4

#: 浅色模式的基础令牌, 注释里是 Fluent 2 的对应令牌名
LIGHT = {
    "bg": "#f5f5f5",             # colorNeutralBackground3
    "cardBg": "#ffffff",         # colorNeutralBackground1
    "text": "#242424",           # colorNeutralForeground1
    "muted": "#616161",          # colorNeutralForeground3
    "border": "#e0e0e0",         # colorNeutralStroke2
    "borderStrong": "#d1d1d1",   # colorNeutralStroke1
    "layerHover": "#ebebeb",     # colorNeutralBackground1Hover 略压暗, 使页面底上也可辨
    "layerPressed": "#e0e0e0",   # colorNeutralBackground1Pressed
    "layerSelected": "#ebebeb",  # colorNeutralBackground1Selected
    "inputBg": "#ffffff",        # colorNeutralBackground1
    "disabledBg": "#f0f0f0",     # colorNeutralBackgroundDisabled
    "disabledText": "#bdbdbd",   # colorNeutralForegroundDisabled
    "primary": "#0f6cbd",        # colorBrandBackground
    "primaryStrong": "#115ea3",  # colorBrandBackgroundHover
    "primaryPressed": "#0c3b5e", # colorBrandBackgroundPressed
    "primaryWeak": "#ebf3fc",    # colorBrandBackground2
    "onPrimary": "#ffffff",      # colorNeutralForegroundOnBrand
    "secondary": "#479ef5",      # colorBrandForeground1
    "accentAlt": "#da3b01",      # colorPaletteDarkOrangeBackground3
    "link": "#0f6cbd",           # colorBrandForegroundLink
    "ok": "#0e700e",             # colorPaletteGreenForeground1
    "warn": "#bc4b09",           # colorPaletteDarkOrangeForeground1
    "danger": "#b10e1c",         # colorStatusDangerForeground1
    "codeBg": "#fafafa",         # colorNeutralBackground2
}

#: 深色模式的基础令牌, 层次方向与浅色一致: 内容层比窗口底更亮
DARK = {
    "bg": "#1f1f1f",             # colorNeutralBackground2
    "cardBg": "#292929",         # colorNeutralBackground1
    "text": "#ffffff",           # colorNeutralForeground1
    "muted": "#adadad",          # colorNeutralForeground3
    "border": "#3d3d3d",         # colorNeutralStroke3
    "borderStrong": "#525252",   # colorNeutralStroke2
    "layerHover": "#3a3a3a",     # colorNeutralBackground1Hover
    "layerPressed": "#333333",   # colorNeutralBackground1Pressed
    "layerSelected": "#333333",  # colorNeutralBackground1Selected
    "inputBg": "#1f1f1f",        # colorNeutralBackground3
    "disabledBg": "#141414",     # colorNeutralBackgroundDisabled
    "disabledText": "#5c5c5c",   # colorNeutralForegroundDisabled
    "primary": "#115ea3",        # colorBrandBackground
    "primaryStrong": "#0f6cbd",  # colorBrandBackgroundHover
    "primaryPressed": "#0c3b5e", # colorBrandBackgroundPressed
    "primaryWeak": "#082338",    # colorBrandBackground2
    "onPrimary": "#ffffff",      # colorNeutralForegroundOnBrand
    "secondary": "#479ef5",      # colorBrandForeground1
    "accentAlt": "#f7630c",      # colorPaletteDarkOrangeBackground3
    "link": "#479ef5",           # colorBrandForegroundLink
    "ok": "#54b054",             # colorPaletteGreenForeground1
    "warn": "#e9835e",           # colorPaletteDarkOrangeForeground1
    "danger": "#dc626d",         # colorStatusDangerForeground1
    "codeBg": "#141414",         # colorNeutralBackground3
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

    悬停, 按下, 选中这三种中性层直接取 Fluent 2 的层叠值, 不参与推导: 它们是
    设计规范里的字面值, 与明暗方向无关。其余底色仍按「从卡片往文字色方向混」
    推导, 深色模式下文字色更亮, 浅色模式下更暗, 同一套比例在两种模式里都指向
    正确的方向, 不需要为每种模式手写悬停色与输入框色。

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
    border = base["border"]
    primary = base["primary"]
    danger = base["danger"]

    # 派生底色统一往描边色或文字色方向混: 既保证深浅两侧都朝正确的明暗方向走,
    # 又让输入框与悬停底色带上和描边一致的一点冷色, 而不是脏灰

    return {
        # 表面层
        "bg": bg,
        "panel": card,
        "card": card,
        "input": base["inputBg"],
        "disabled": base["disabledBg"],
        "disabled_text": base["disabledText"],
        "hover": base["layerHover"],
        "active": base["layerPressed"],
        "selected": base["layerSelected"],
        "border": border,
        "border_strong": base["borderStrong"],
        "text": text,
        "muted": base["muted"],
        "header": text,
        # 主色层
        "accent": primary,
        "accent_hover": base["primaryStrong"],
        "accent_pressed": base["primaryPressed"],
        "accent_weak": base["primaryWeak"],
        "accent_soft_hover": mix(base["primaryWeak"], primary, 0.14),
        "secondary": base["secondary"],
        "accent_alt": base["accentAlt"],
        "on_accent": base["onPrimary"],
        "link": base["link"],
        "ring": primary,
        # 语义色
        "ok": base["ok"],
        "warn": base["warn"],
        "success": base["ok"],
        "danger": danger,
        "danger_weak": mix(card, danger, 0.08),
        "danger_weak_pressed": mix(card, danger, 0.18),
        "danger_hover": mix(danger, text, 0.22),
        # 容器与装饰
        "scroll": mix(border, text, 0.25),
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
