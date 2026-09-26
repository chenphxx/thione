# -*- mode: python ; coding: utf-8 -*-

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
        'PIL.ImageDraw',
        'PIL.ImageTk',
        'uapi',
        # 随包的 ffmpeg 引擎: 该依赖缺失时转换功能提示用户自备 ffmpeg
        'imageio_ffmpeg',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'PyQt5', 'PySide2', 'PySide6',
        'PIL.AvifImagePlugin',
        'numpy',
    ],
    noarchive=False,
    optimize=0,
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
