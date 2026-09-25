"""圆角底图元素。

ttk 的 clam 主题只能把控件画成矩形, Fluent 2 要求的控件圆角与状态底色靠它做不出来,
这里用 PIL 画出可平铺的圆角底图, 注册成 ttk 的 image element 供按钮族使用。

底图按浅色与深色各建一套元素, 元素名带模式后缀, 切换主题时只把按钮样式的布局指向
另一套, 因此不需要用同名元素重建 (ttk 不允许重复创建同名元素)。

@brief 供按钮族获得 Fluent 2 圆角与状态底色的图片元素工厂。
"""

from PIL import Image, ImageDraw, ImageTk

#: 控件圆角半径 (像素), 对应 Fluent 2 的 borderRadiusMedium
RADIUS = 4

#: 底图边长, 以及九宫格中不参与平铺的边界, 必须大于圆角半径
TILE = 32
BORDER = 12

#: 底图状态名到 ttk 状态名的映射, 顺序即匹配优先级:
#: 鼠标悬停在禁用按钮上时两个状态同时存在, 因此 disabled 必须先命中
STATES = (("disabled", "disabled"), ("pressed", "pressed"),
          ("focus", "focus"), ("hover", "active"))


def make_tile(fill, outline, radius=RADIUS, line=1, tile=TILE):
    """画一张圆角矩形底图。

    底图按九宫格铺进控件: 四边与四角原样绘制, 中间是纯色, 因此平铺与拉伸的
    视觉效果一致, 纯色底图不会出现接缝。

    @param fill: 填充色, #RRGGBB
    @param outline: 描边色, #RRGGBB
    @param radius: 圆角半径
    @param line: 描边宽度
    @param tile: 底图边长
    @return: PIL.Image, RGBA 模式
    """
    image = Image.new("RGBA", (tile, tile), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (0, 0, tile - 1, tile - 1), radius=radius,
        fill=fill, outline=outline, width=line,
    )
    return image


def tiles_for(palette, spec):
    """按调色板把一份状态配色画成一套底图。

    @param palette: build_palette() 的返回值
    @param spec: {状态: (填充令牌, 描边令牌, 描边宽度)}, normal 必填
    @return: {状态: PIL.Image}, 键与 spec 一致
    """
    return {
        state: make_tile(palette[fill], palette[outline], RADIUS, line)
        for state, (fill, outline, line) in spec.items()
    }


def create_element(style, name, tiles):
    """把一套底图注册成 ttk 元素。

    @param style: ttk.Style
    @param name: 元素名, 全局唯一且创建后不能重复创建
    @param tiles: {状态: PIL.Image}, 未给出的状态回落到 normal
    @return: 图片列表, 调用方必须持有, 否则 Tk 会回收它们
    """
    photos = {state: ImageTk.PhotoImage(image) for state, image in tiles.items()}
    spec = [(ttk_state, photos[state])
            for state, ttk_state in STATES if state in photos]
    style.element_create(name, "image", photos["normal"], *spec,
                         border=BORDER, sticky="nsew")
    return list(photos.values())


def button_layout(element):
    """按钮布局: 圆角底图铺满整个控件, 文字居中。

    不挂 Button.focus, 键盘焦点的视觉由底图的 focus 状态承担。

    @param element: 元素名
    @return: 可直接交给 style.layout() 的布局序列
    """
    return [(element, {"sticky": "nsew", "children": [
        ("Button.padding", {"sticky": "nsew", "children": [
            ("Button.label", {"sticky": "nsew"})]})]})]
