# -*- mode: python ; coding: utf-8 -*-

import os

# 归档里的每个条目都用zlib压缩, 级别9比默认值更小
os.environ.setdefault("PYINSTALLER_ZLIB_COMPRESSION_LEVEL", "9")

# 没有用到的界面库 
EXCLUDED_MODULES = [
    "PyQt5", "PySide2", "PySide6",
    "numpy", "scipy", "pywt", "imagehash",
    "PIL.AvifImagePlugin", "PIL.ImageCms", "PIL.ImageShow", "PIL.ImageQt",
    "PIL.ImageDraw", "PIL.ImageDraw2", "PIL.ImageFont",
    "setuptools", "_distutils_hack", "packaging", "pkg_resources",
    "pydoc", "pydoc_data", "_pyrepl", "code", "rlcompleter",
    "doctest", "pdb", "profile", "pstats", "cProfile", "lib2to3",
    "xmlrpc", "smtplib", "ftplib", "netrc", "imaplib", "poplib", "telnetlib",
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
        'imageio_ffmpeg',
        'serial.tools.list_ports',
        'serial.urlhandler.protocol_loop',
        'serial.urlhandler.protocol_socket',
        'serial.urlhandler.protocol_rfc2217',
        'serial.urlhandler.protocol_hwgrep',
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
