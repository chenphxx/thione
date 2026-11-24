"""常见图片格式转换

图片转换使用 Pillow 直接处理像素, 不经过有损中间格式. PNG WEBP TIFF 与 BMP
按无损方式写出, JPG 使用最高质量参数, GIF 受 256 色限制只能尽量保留观感

@brief 图片格式转换与最高质量参数
"""

import logging
import os

from PIL import Image, ImageOps, ImageSequence, UnidentifiedImageError
from PIL import __version__ as PILLOW_VERSION

logger = logging.getLogger(__name__)

FORMATS = {
    "png": "PNG",
    "jpg": "JPEG",
    "webp": "WEBP",
    "bmp": "BMP",
    "tiff": "TIFF",
    "gif": "GIF",
}

#: 可以保留多帧动画的目标格式
ANIMATED_FORMATS = frozenset({"png", "webp", "tiff", "gif"})


class ImageConvertError(RuntimeError):
    """图片转换过程中可向用户说明的错误"""


def version():
    """当前 Pillow 版本

    @return: 版本号字符串
    """
    return PILLOW_VERSION


def convert(source, target, extension, on_progress=None):
    """把一个图片文件转换为目标格式

    先写到目标文件旁边的临时文件, 成功后再原子替换, 失败时不会留下半成品

    @param source: 源图片路径
    @param target: 输出图片路径
    @param extension: 目标扩展名, 不带点
    @param on_progress: 可选进度回调, 接收 0 到 1 的比例
    @throws ImageConvertError: 图片无法读取 动画目标不支持或者写入失败
    """
    extension = extension.lower().lstrip(".")
    if extension not in FORMATS:
        raise ImageConvertError(f"不支持的图片格式: {extension}")

    part_path = target + ".part"
    _progress(on_progress, 0.02)
    try:
        with Image.open(source) as opened:
            info = dict(opened.info)
            frame_count = max(int(getattr(opened, "n_frames", 1)), 1)
            if frame_count > 1:
                if extension not in ANIMATED_FORMATS:
                    raise ImageConvertError(
                        "动态图片只能转换为 PNG WEBP TIFF 或 GIF")
                frames, durations = _read_frames(opened, info)
                transparent = any(_has_alpha(frame) for frame in frames)
                if extension == "png":
                    prepared = [_to_rgba(frame) if _has_alpha(frame)
                                else frame.convert("RGB") for frame in frames]
                else:
                    prepared = [_prepare_frame(frame, extension, transparent)
                                for frame in frames]
                _progress(on_progress, 0.72)
                _save_animation(prepared, part_path, extension, info,
                                durations, transparent)
            else:
                opened.load()
                image = ImageOps.exif_transpose(opened)
                exif = image.getexif()
                if exif:
                    info["exif"] = exif.tobytes()
                else:
                    info.pop("exif", None)
                _progress(on_progress, 0.35)
                reserve_gif = extension == "gif" and _has_alpha(image)
                if reserve_gif:
                    info["transparency"] = 255
                prepared = _prepare_frame(image, extension, reserve_gif)
                _save_still(prepared, part_path, extension, info)
            _progress(on_progress, 0.94)
        os.replace(part_path, target)
        _progress(on_progress, 1.0)
    except ImageConvertError:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ImageConvertError(f"无法转换图片: {exc}") from exc
    finally:
        if os.path.exists(part_path):
            try:
                os.remove(part_path)
            except OSError:
                logger.warning("删除图片临时文件失败: %s", part_path,
                               exc_info=True)


def _read_frames(image, info):
    """读取动画的全部帧与持续时间

    @param image: 已打开的 Pillow 图片
    @param info: 原图的 info
    @return: (帧列表, 每帧持续时间毫秒)
    """
    frames = []
    durations = []
    fallback = info.get("duration", 100)
    for frame in ImageSequence.Iterator(image):
        frames.append(frame.copy())
        duration = frame.info.get("duration", fallback)
        try:
            duration = int(duration)
        except (TypeError, ValueError):
            duration = 100
        durations.append(max(duration, 10))
    return frames, durations


def _prepare_frame(image, extension, reserve_gif_transparency):
    """把一帧转成目标格式支持的像素模式

    @param image: 原帧
    @param extension: 目标扩展名, 不带点
    @param reserve_gif_transparency: GIF 是否预留透明索引
    @return: 可直接保存的 Pillow 图片
    """
    if extension == "jpg":
        return _for_jpeg(image)
    if extension == "webp":
        return _for_webp(image)
    if extension == "bmp":
        return _to_rgb(image)
    if extension == "tiff":
        return _for_tiff(image)
    if extension == "gif":
        return _for_gif(image, reserve_gif_transparency)
    return _for_png(image)


def _for_jpeg(image):
    """转换成 JPG 支持的像素模式, 透明区域填白"""
    if image.mode in ("L", "CMYK"):
        return image.copy()
    if image.mode == "1":
        return image.convert("L")
    return _to_rgb(image)


def _for_webp(image):
    """转换成 WEBP 支持的 RGB 或 RGBA"""
    if _has_alpha(image):
        return image.convert("RGBA")
    return image.convert("RGB")


def _for_png(image):
    """转换成 PNG 支持的像素模式"""
    if image.mode in ("1", "L", "LA", "P", "RGB", "RGBA", "I", "I;16"):
        return image.copy()
    if _has_alpha(image):
        return image.convert("RGBA")
    return image.convert("RGB")


def _for_tiff(image):
    """转换成 TIFF 支持的像素模式"""
    if image.mode in ("1", "L", "LA", "P", "RGB", "RGBA", "CMYK",
                      "I", "I;16", "F"):
        return image.copy()
    if _has_alpha(image):
        return image.convert("RGBA")
    return image.convert("RGB")


def _for_gif(image, reserve_transparency):
    """量化成 GIF 的 256 色索引图

    有透明像素时保留一个透明索引, 其余颜色使用中位切分量化与抖动, 尽量接近原图

    @param image: 原帧
    @param reserve_transparency: 是否为透明索引预留一个槽位
    @return: P 模式图片
    """
    rgba = image.convert("RGBA")
    alpha = rgba.getchannel("A")
    rgb = Image.new("RGB", rgba.size, (255, 255, 255))
    rgb.paste(rgba, mask=alpha)
    colors = 255 if reserve_transparency else 256
    result = rgb.quantize(colors=colors,
                          method=Image.Quantize.MEDIANCUT,
                          dither=Image.Dither.FLOYDSTEINBERG)
    if reserve_transparency:
        transparent = alpha.point(lambda value: 255 if value < 128 else 0)
        result.paste(255, mask=transparent)
    return result


def _to_rgb(image):
    """转换成 RGB, 透明区域铺白底"""
    if not _has_alpha(image):
        return image.convert("RGB")
    rgba = image.convert("RGBA")
    background = Image.new("RGB", rgba.size, (255, 255, 255))
    background.paste(rgba, mask=rgba.getchannel("A"))
    return background


def _has_alpha(image):
    """判断图片是否带透明通道"""
    return "A" in image.getbands() or (
        image.mode == "P" and "transparency" in image.info)


def _save_still(image, path, extension, info):
    """保存单帧图片

    @param image: 已转换像素模式的图片
    @param path: 临时输出路径
    @param extension: 目标扩展名
    @param info: 原图元数据
    """
    options = _save_options(image, extension, info)
    image.save(path, format=FORMATS[extension], **options)


def _save_animation(frames, path, extension, info, durations, transparent):
    """保存多帧图片

    @param frames: 已转换像素模式的帧
    @param path: 临时输出路径
    @param extension: 目标扩展名
    @param info: 原图元数据
    @param durations: 每帧持续时间毫秒
    @param transparent: GIF 是否需要透明索引
    """
    options = _save_options(frames[0], extension, info)
    if extension == "png":
        options.pop("transparency", None)
    options.update(
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=max(int(info.get("loop", 0) or 0), 0),
    )
    if extension == "gif":
        options.update(optimize=False, disposal=2)
        if transparent:
            options["transparency"] = 255
    frames[0].save(path, format=FORMATS[extension], **options)


def _save_options(image, extension, info):
    """各目标格式的最高质量保存参数

    @param image: 待保存图片
    @param extension: 目标扩展名
    @param info: 原图元数据
    @return: 传给 Pillow save 的参数字典
    """
    del image
    options = {}
    if extension == "jpg":
        options.update(quality=100, subsampling=0, optimize=True)
        _copy_metadata(options, info, exif=True, icc=True, dpi=True)
    elif extension == "png":
        options.update(compress_level=9)
        _copy_metadata(options, info, exif=True, icc=True, dpi=True)
        if "transparency" in info:
            options["transparency"] = info["transparency"]
    elif extension == "webp":
        options.update(lossless=True, quality=100, method=6, exact=True)
        _copy_metadata(options, info, exif=True, icc=True)
    elif extension == "tiff":
        options.update(compression="tiff_adobe_deflate")
        _copy_metadata(options, info, icc=True, dpi=True)
    elif extension == "gif":
        options["optimize"] = False
        if "transparency" in info:
            options["transparency"] = info["transparency"]
    return options


def _copy_metadata(options, info, exif=False, icc=False, dpi=False):
    """把原图能复用的元数据写进保存参数

    @param options: 保存参数
    @param info: 原图 info
    @param exif: 是否复制 EXIF
    @param icc: 是否复制 ICC 色彩配置
    @param dpi: 是否复制 DPI
    """
    if exif and info.get("exif"):
        options["exif"] = info["exif"]
    if icc and info.get("icc_profile"):
        options["icc_profile"] = info["icc_profile"]
    if dpi and isinstance(info.get("dpi"), tuple) and len(info["dpi"]) == 2:
        options["dpi"] = info["dpi"]


def _progress(callback, value):
    """安全地调用进度回调"""
    if callback is not None:
        callback(value)
