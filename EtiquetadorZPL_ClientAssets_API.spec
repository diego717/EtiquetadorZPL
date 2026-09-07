# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

hidden_imports = [
    'fastapi',
    'fastapi.applications',
    'fastapi.routing',
    'fastapi.middleware.cors',
    'fastapi.responses',
    'uvicorn',
    'uvicorn.main',
    'uvicorn.server',
    'uvicorn.config',
    'uvicorn.protocols.http.auto',
    'pydantic',
    'pydantic.main',
    'pydantic.fields',
    'starlette',
    'starlette.applications',
    'starlette.routing',
    'starlette.responses',
    'starlette.middleware',
    'anyio',
    'sniffio',
    'client_assets_endpoints',
    'client_assets_service',
    'get_writable_path',
    'pythoncom',
    'pywintypes',
    'win32com',
    'win32com.client',
    'win32com.client.gencache',
]

a = Analysis(
    ['api/client_assets_api_server.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='EtiquetadorZPL_ClientAssets_API',
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
    icon='etiquetador_icon.ico'
)
