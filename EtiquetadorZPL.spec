# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['launcher_gui.py'],
    pathex=[],
    binaries=[],
    datas=[('web', 'web'), ('config', 'config'), ('poppler', 'poppler'), ('src', 'src'), ('api', 'api'), ('gui', 'gui')],
    hiddenimports=['tkinter', 'tkinter.filedialog', 'tkinter.messagebox', 'tkinter.scrolledtext', 'tkinter.ttk', 'http.server', 'socketserver', 'configparser', 'sqlite3', 'threading', 'json', 'pathlib', 'importlib.util', 'watchdog', 'watchdog.observers', 'watchdog.events', 'requests', 'PIL', 'PIL.Image', 'pdf2image', 'psutil'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name='EtiquetadorZPL',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
