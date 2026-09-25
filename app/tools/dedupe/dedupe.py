"""重复图片检测工作线程。"""

from PIL import Image

from .constants import HASH_THRESHOLD


def difference_hash(image, hash_size=8):
    """计算水平差值哈希, 用于判断两张图片的视觉相似度.

    @param image: 已打开的 Pillow 图片
    @param hash_size: 每行和每列的比较数量
    @return: 整数形式的哈希值, 默认结果与 8x8 dHash 一致
    """
    pixels = list(
        image.convert("L").resize(
            (hash_size + 1, hash_size), Image.Resampling.LANCZOS
        ).getdata()
    )
    value = 0
    for row in range(hash_size):
        offset = row * (hash_size + 1)
        for column in range(hash_size):
            value = (value << 1) | int(
                pixels[offset + column + 1] > pixels[offset + column]
            )
    return value


def dedupe_worker(file_list, progress_queue, stop_event,
                  hash_func=difference_hash, threshold=HASH_THRESHOLD):
    """在后台线程中计算感知哈希并按相似度分组。

    通过 progress_queue 发送消息:
      ("progress", processed, total) - 进度
      ("result", groups)             - 重复分组结果
      ("done",)                      - 正常完成
      ("stopped",)                   - 被终止

    @param file_list 待扫描的图片路径
    @param progress_queue 用于向界面发送进度和结果的队列
    @param stop_event 用于请求终止扫描的事件
    @param hash_func 将 Pillow 图片转换为哈希值的函数
    @param threshold 两个哈希值允许的最大汉明距离
    @return 无
    """
    total = len(file_list)
    processed = 0
    hashes = []
    for path in file_list:
        if stop_event.is_set():
            progress_queue.put(("stopped",))
            return
        try:
            with Image.open(path) as im:
                h = hash_func(im)
        except Exception:
            h = None
        hashes.append((h, path))
        processed += 1
        progress_queue.put(("progress", processed, total))

    groups = []
    used = [False] * len(hashes)
    for i, (hi, pi) in enumerate(hashes):
        if stop_event.is_set():
            progress_queue.put(("stopped",))
            return
        if used[i] or hi is None:
            continue
        group = [pi]
        used[i] = True
        for j in range(i + 1, len(hashes)):
            hj, pj = hashes[j]
            if used[j] or hj is None:
                continue
            try:
                if isinstance(hi, int) and isinstance(hj, int):
                    distance = (hi ^ hj).bit_count()
                else:
                    distance = abs(hi - hj)
                if distance <= threshold:
                    group.append(pj)
                    used[j] = True
            except Exception:
                pass
        if len(group) > 1:
            groups.append(group)
    progress_queue.put(("result", groups))
    progress_queue.put(("done",))
