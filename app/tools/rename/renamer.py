"""重命名核心逻辑: 任务构建, 任务执行与原地重命名辅助。

执行过程中需要与界面交互的地方 (冲突选择, 进度上报, 中止判断) 一律用回调
表达, 因此这里不依赖 tkinter。
"""

import os
import shutil
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


class CancelledError(Exception):
    """用户在任务执行过程中终止了操作。"""


class TaskError(RuntimeError):
    """单项任务执行失败。

    @ivar src: 出错时正在处理的源文件路径
    """

    def __init__(self, src, cause):
        super().__init__(str(cause))
        self.src = src


def run_tasks(tasks, folder, moved, on_conflict, on_progress, is_cancelled):
    """逐项执行 build_tasks 生成的任务。

    @param tasks: build_tasks 的返回值
    @param folder: 原地重命名所在的目录 (非原地任务时传保存目录)
    @param moved: prepare_inplace_temps 的返回值, 执行过程中就地更新
    @param on_conflict: callable(目标文件名) -> "overwrite" | "skip" | "cancel"
    @param on_progress: callable(processed, total), 每处理完一项调用一次
    @param is_cancelled: callable() -> bool, 返回 True 时中止
    @return: 完成的项数
    @raise CancelledError: 用户中止, 或冲突对话框选了取消
    @raise TaskError: 某项执行失败; 调用方应调用 restore_inplace_temps 收尾
    """
    total = len(tasks)
    processed = 0
    for src, dst, inplace, src_name in tasks:
        if is_cancelled():
            raise CancelledError()

        # 原地重命名: 文件已是指定名称, 无需处理
        if inplace and _same_path(src, dst):
            processed += 1
            on_progress(processed, total)
            continue

        # 冲突文件可能已被挪到临时名, 优先用临时名作为当前源
        cur_src = moved.get(src_name) or src
        try:
            if os.path.exists(dst):
                action = on_conflict(os.path.basename(dst))
                if action == "cancel":
                    raise CancelledError()
                if action == "skip":
                    restore_inplace_temp(folder, src_name, cur_src)
                    moved.pop(src_name, None)
                    processed += 1
                    on_progress(processed, total)
                    continue
                # overwrite: 继续往下走

            if inplace:
                os.replace(cur_src, dst)
                moved.pop(src_name, None)
            else:
                shutil.copy2(cur_src, dst)
        except CancelledError:
            raise
        except Exception as e:
            raise TaskError(src, e) from e

        processed += 1
        on_progress(processed, total)
    return processed


def _same_path(path_a, path_b):
    """判断两个路径是否指向同一个文件。"""
    return (os.path.normcase(os.path.normpath(path_a))
            == os.path.normcase(os.path.normpath(path_b)))
