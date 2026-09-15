"""重命名核心逻辑：任务构建与原地重命名辅助。"""

import os
import uuid


def build_tasks(items, save_folder, prefix, start_num):
    """把 (文件夹, 文件名) 列表转为重命名任务。

    返回 [(src, dst, inplace, src_name), ...]：
      - src/dst: 源/目标完整路径
      - inplace: 是否在原文件夹内原地重命名
      - src_name: 源文件名（用于临时文件还原）
    编号按 items 顺序依次分配，与结果无关。
    """
    norm_save = os.path.normcase(os.path.normpath(save_folder))

    def is_inplace(folder):
        return os.path.normcase(os.path.normpath(folder)) == norm_save

    tasks = []
    cur_num = start_num
    for folder, name in items:
        ext = os.path.splitext(name)[1]
        new_name = f"{prefix}{cur_num}{ext}"
        inplace = is_inplace(folder)
        src = os.path.join(folder, name)
        dst = os.path.join(folder if inplace else save_folder, new_name)
        tasks.append((src, dst, inplace, name))
        cur_num += 1
    return tasks


def prepare_inplace_temps(folder, jobs):
    """将目标名与其他待处理源文件同名的文件先移到临时名，防止互相覆盖。

    jobs: [(源文件名, 目标文件名), ...]，均位于 folder 内。
    返回 {源文件名: 临时完整路径}；中途出错时自动还原已移动的文件并抛出异常。
    """
    moved = {}
    try:
        target_names = {new_name for _, new_name in jobs}
        for src_name, new_name in jobs:
            if src_name == new_name or src_name not in target_names:
                continue
            tmp = os.path.join(folder, f".{src_name}.renamepy_tmp_{uuid.uuid4().hex}")
            os.rename(os.path.join(folder, src_name), tmp)
            moved[src_name] = tmp
    except Exception:
        restore_inplace_temps(folder, moved)
        raise
    return moved


def restore_inplace_temp(folder, src_name, tmp):
    """把单个临时文件还原为原名（仅当原名尚不存在时）。"""
    original = os.path.join(folder, src_name)
    if os.path.exists(tmp) and not os.path.exists(original):
        try:
            os.rename(tmp, original)
        except OSError:
            pass


def restore_inplace_temps(folder, moved):
    """还原所有仍处于临时名的文件。"""
    for src_name, tmp in list(moved.items()):
        restore_inplace_temp(folder, src_name, tmp)
