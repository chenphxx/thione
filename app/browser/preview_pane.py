"""右侧预览窗格: 图片 / 文本 / 表格, 未知类型尝试以文本模式预览。

原本只属于批量重命名, 图片查重也需要同一份预览逻辑, 因此移到共享层
可预览的类型见 constants, 与 Windows 资源管理器的预览窗格覆盖范围一致
"""

import csv
import os
import tkinter as tk
from tkinter import ttk

from ..errors import open_path
from ..theme import mono
from .constants import (
    IMAGE_EXTS,
    MAX_PREVIEW_BYTES,
    MAX_PREVIEW_ROWS,
    PREVIEW_WIDTH,
    TABLE_EXTS,
    TEXT_EXTS,
)


class PreviewPane(ttk.Frame):
    """文件预览窗格; 通过 show(path) 展示内容, 随窗格大小自适应。"""

    def __init__(self, master, theme):
        super().__init__(master, style="Panel.TFrame", padding=(12, 8))
        self.configure(width=PREVIEW_WIDTH)
        self.pack_propagate(False)
        self.theme = theme

        self._preview_path = None
        self._preview_img = None
        self._preview_rendered_size = None

        header = ttk.Frame(self, style="Panel.TFrame")
        header.pack(fill="x")
        self.lbl_title = ttk.Label(header, text="预览", style="PanelHeader.TLabel")
        self.lbl_title.pack(anchor="w")
        self.lbl_info = ttk.Label(header, text="选中文件后在这里查看",
                                  style="PanelMuted.TLabel")
        self.lbl_info.pack(anchor="w", pady=(2, 0))

        self.body = ttk.Frame(self)
        self.body.pack(fill="both", expand=True, pady=(8, 0))
        self.body.bind("<Configure>", self._on_body_resize)

        self.show(None)

    # ---------------- 对外接口 ----------------
    @property
    def path(self):
        """当前预览的文件路径。"""
        return self._preview_path

    def show(self, path):
        """根据文件路径刷新预览; path 为空时显示占位提示。"""
        self._preview_path = path
        self._clear_body()
        self._preview_img = None
        self._preview_rendered_size = None

        if not path or not os.path.isfile(path):
            self.lbl_title.config(text="预览")
            self.lbl_info.config(text="选中文件后在这里查看")
            self._placeholder("在左侧选中文件, 即可在这里查看预览")
            return

        name = os.path.basename(path)
        ext = os.path.splitext(name)[1].lower()
        self.lbl_title.config(text=_shorten(name))
        try:
            size = os.path.getsize(path)
        except OSError:
            size = 0
        self.lbl_info.config(text=self._format_size(size))

        if ext in IMAGE_EXTS:
            self._preview_image(path)
        elif ext in TEXT_EXTS:
            self._preview_text(path)
        elif ext in TABLE_EXTS:
            self._preview_table(path, ext)
        else:
            message = f"暂不支持预览 {ext} 文件" if ext else "暂不支持预览该文件"
            self._try_text_fallback(path, message)

    def refresh(self):
        """使用当前主题重新绘制正在显示的预览内容。"""
        self.show(self._preview_path)

    def _clear_body(self):
        for child in self.body.winfo_children():
            child.destroy()

    def _placeholder(self, message):
        ttk.Label(self.body, text=message, style="Muted.TLabel",
                  anchor="center", wraplength=PREVIEW_WIDTH - 40,
                  justify="center").pack(fill="both", expand=True)

    def _preview_image(self, path):
        p = self.theme.palette
        try:
            from PIL import ImageTk

            from ..imaging import load_thumbnail
        except ImportError:
            self._placeholder("未安装 Pillow, 无法预览图片\npip install pillow")
            return
        self.winfo_toplevel().update_idletasks()
        max_w = max(self.body.winfo_width() - 24, 100)
        max_h = max(self.body.winfo_height() - 16, 60)
        if self._preview_rendered_size == (max_w, max_h):
            return  # 尺寸未变化, 避免重复渲染
        self._preview_rendered_size = (max_w, max_h)
        img = load_thumbnail(path, (max_w, max_h))
        if img is None:
            self._preview_img = None
            self._preview_rendered_size = None
            self._try_text_fallback(path, "图片加载失败")
            return
        self._preview_img = ImageTk.PhotoImage(img)
        self._clear_body()
        label = tk.Label(self.body, image=self._preview_img, bg=p["bg"])
        label.pack(padx=8, pady=6)
        # 双击图片用系统默认程序打开
        label.bind("<Double-1>", lambda e: self._open_preview_file(path))
        current = self.lbl_info.cget("text")
        if "双击打开" not in current:
            self.lbl_info.config(text=f"{current} · 双击打开")

    def _open_preview_file(self, path):
        open_path(path, parent=self.winfo_toplevel())

    def _preview_text(self, path):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read(MAX_PREVIEW_BYTES)
        except Exception:
            self._try_text_fallback(path, "无法读取文本文件")
            return
        self._show_text_content(content)

    def _show_text_content(self, content):
        p = self.theme.palette
        frame = ttk.Frame(self.body)
        frame.pack(fill="both", expand=True)

        text = tk.Text(
            frame, wrap="none", bg=p["preview"], fg=p["text"],
            insertbackground=p["text"], font=mono(),
            relief="flat", borderwidth=0, padx=10, pady=8,
        )
        text._thione_surface = "preview"
        v_scroll = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        h_scroll = ttk.Scrollbar(frame, orient="horizontal", command=text.xview)
        text.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)

        text.insert("1.0", content)
        if len(content) >= MAX_PREVIEW_BYTES:
            text.insert("end", "\n\n... 文件较大, 仅预览前 200KB")
        text.configure(state="disabled")

        v_scroll.pack(side="right", fill="y")
        h_scroll.pack(side="bottom", fill="x")
        text.pack(side="left", fill="both", expand=True)

    def _try_text_fallback(self, path, fail_message):
        """无法按原类型预览时, 尝试把文件当作文本读取。"""
        try:
            with open(path, "rb") as f:
                data = f.read(MAX_PREVIEW_BYTES)
        except Exception:
            self._placeholder(fail_message)
            return
        if self._looks_binary(data):
            self._placeholder(fail_message)
            return
        text = data.decode("utf-8", errors="replace")
        current = self.lbl_info.cget("text")
        self.lbl_info.config(text=f"{current} · 文本模式")
        self._show_text_content(text)

    @staticmethod
    def _looks_binary(data):
        if not data:
            return False
        sample = data[:8000]
        if b"\x00" in sample:
            return True
        control = sum(1 for b in sample if b < 32 and b not in (9, 10, 13, 12, 27))
        return control / len(sample) > 0.30

    def _preview_table(self, path, ext):
        if ext == ".xlsx":
            rows = self._read_xlsx(path)
        else:
            rows = []
            try:
                with open(path, "r", encoding="utf-8-sig", errors="replace", newline="") as f:
                    dialect = "excel-tab" if ext == ".tsv" else "excel"
                    for row in csv.reader(f, dialect):
                        rows.append(row)
                        if len(rows) >= MAX_PREVIEW_ROWS:
                            break
            except Exception:
                self._try_text_fallback(path, "无法读取表格文件")
                return
        if rows is None:
            return  # 读取失败时已显示提示
        self._show_table(rows)

    def _read_xlsx(self, path):
        try:
            from openpyxl import load_workbook
        except ImportError:
            self._placeholder("未安装 openpyxl, 无法预览 Excel 表格\npip install openpyxl")
            return None
        try:
            wb = load_workbook(path, read_only=True, data_only=True)
            ws = wb[wb.sheetnames[0]]
            sheet = ws.title
            rows = []
            for row in ws.iter_rows(values_only=True):
                rows.append([self._cell_text(v) for v in row])
                if len(rows) >= MAX_PREVIEW_ROWS:
                    break
            wb.close()
            current = self.lbl_info.cget("text")
            self.lbl_info.config(text=f"{current} · 工作表: {sheet}")
            return rows
        except Exception:
            self._try_text_fallback(path, "Excel 文件读取失败")
            return None

    def _show_table(self, rows):
        p = self.theme.palette
        if not rows:
            self._placeholder("表格内容为空")
            return

        cols = min(max(len(r) for r in rows), 12)
        frame = ttk.Frame(self.body)
        frame.pack(fill="both", expand=True)

        tree = ttk.Treeview(frame, columns=[f"c{i}" for i in range(cols)], show="headings")
        tree.tag_configure("odd", background=p["bg"])
        tree.tag_configure("even", background=p["hover"])
        for i in range(cols):
            tree.heading(f"c{i}", text=f"列 {i + 1}")
            tree.column(f"c{i}", width=110, anchor="w", stretch=True)

        for idx, row in enumerate(rows):
            values = [""] * cols
            for i, v in enumerate(row[:cols]):
                values[i] = self._cell_text(v)
            tree.insert("", "end", values=values, tags=("odd" if idx % 2 == 0 else "even"))

        v_scroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        h_scroll = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)

        tree.grid(row=0, column=0, sticky="nsew")
        v_scroll.grid(row=0, column=1, sticky="ns")
        h_scroll.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

    # ---------------- 自适应 ----------------
    def _on_body_resize(self, event):
        if self._preview_img is not None and self._preview_path:
            self._preview_image(self._preview_path)

    # ---------------- 工具 ----------------
    @staticmethod
    def _cell_text(value):
        if value is None:
            return ""
        return str(value).replace("\n", " ")[:60]

    @staticmethod
    def _format_size(size):
        if size < 1024:
            return f"{size} B"
        if size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        return f"{size / 1024 / 1024:.1f} MB"


def _shorten(name, limit=32):
    """标题一行放不下时保留尾部, 便于看出真实文件名。"""
    return name if len(name) <= limit else "..." + name[-(limit - 3):]
