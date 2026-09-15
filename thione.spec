# -*- mode: python ; coding: utf-8 -*-
#
# thione 的打包配置。与旧版命令行打包相比有四处区别:
#   1. datas 带上 assets 目录, 保证托盘图标在打包后也能加载;
#   2. excludes 不再排除 PIL —— 托盘图标 (pystray) 与缩略图都依赖它;
#   3. hiddenimports 显式声明动态导入的模块, 否则静态分析会漏掉它们:
#      openpyxl 在预览面板里是函数内延迟导入, pystray 的 Windows 后端
#      也只能靠显式声明;
#   4. 写入版本资源, 让任务栏与文件属性显示 thione 而不是 python。

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
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PyQt5', 'PySide2', 'PySide6'],
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
