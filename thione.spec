# -*- mode: python ; coding: utf-8 -*-

# PyInstaller 的 spec 就是普通 Python 脚本, 构建前先定好压缩级别与要排除的模块

import os

# 归档里的每个条目都用 zlib 压缩, 级别 9 比默认值更小 (代价是打包慢一点)
os.environ.setdefault("PYINSTALLER_ZLIB_COMPRESSION_LEVEL", "9")

#: 不参与打包的模块: 分四类, 都是依赖的可选导入或者 PyInstaller 运行时钩子带进来的
#  排除后六个工具的功能都不受影响, 依据见 docs/开发与打包.md
EXCLUDED_MODULES = [
    # 没有用到的界面库
    "PyQt5", "PySide2", "PySide6",
    # 数值计算: 查重的 dHash 只用 Python 整数计算
    "numpy", "scipy", "pywt", "imagehash",
    # Pillow 里用不到的插件: AVIF 解码 色彩管理 调用系统看图程序 与 Qt 绑定
    "PIL.AvifImagePlugin", "PIL.ImageCms", "PIL.ImageShow", "PIL.ImageQt",
    # Pillow 的文字绘制链: 界面不往图片上写字 缩略图与托盘图标都不需要 FreeType
    "PIL.ImageDraw", "PIL.ImageDraw2", "PIL.ImageFont",
    # setuptools 一族来自 PyInstaller 的 distutils 兼容钩子, 钩子内部已经 try/except
    "setuptools", "_distutils_hack", "packaging", "pkg_resources",
    # 交互式解释器与自带文档 窗口程序里不会用到
    # codeop 不在其中: Python 3.14 的 traceback 在模块级导入它 日志与错误提示都要用
    "pydoc", "pydoc_data", "_pyrepl", "code", "rlcompleter",
    "doctest", "pdb", "profile", "pstats", "cProfile", "lib2to3",
    # 用不到的远程协议客户端: 都在函数内部延迟导入 XML-RPC 与邮件 文件传输
    "xmlrpc", "smtplib", "ftplib", "netrc", "imaplib", "poplib", "telnetlib",
    # 只在其它的操作系统上使用的后端
    "pystray._darwin", "pystray._xorg", "pystray._gtk",
    "pystray._appindicator", "pystray._ayatana",
    "pynput.keyboard._darwin", "pynput.keyboard._xorg",
    "pynput.mouse._darwin", "pynput.mouse._xorg",
]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('assets/images/logo.ico', 'assets/images')],
    hiddenimports=[
        'openpyxl',
        'et_xmlfile',
        'pystray._win32',
        'PIL.Image',
        'PIL.ImageTk',
        'uapi',
        # 随包的 ffmpeg 引擎: 该依赖缺失时转换功能提示用户自备 ffmpeg
        'imageio_ffmpeg',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDED_MODULES,
    noarchive=False,
    optimize=2,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='thione',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets\\images\\logo.ico'],
    version='version_info.txt',
)
