# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

# Todos los imports ocultos necesarios (análisis completo del código)
hidden_imports = [
    # Tkinter completo
    'tkinter',
    'tkinter.ttk',
    'tkinter.filedialog',
    'tkinter.messagebox',
    'tkinter.scrolledtext',
    'tkinter.font',
    'tkinter.constants',
    
    # HTTP y servidor
    'http.server',
    'socketserver',
    'urllib.parse',
    'urllib.request',
    
    # Sistema y archivos
    'configparser',
    'sqlite3',
    'threading',
    'json',
    'pathlib',
    'importlib.util',
    'os',
    'sys',
    'time',
    'datetime',
    'logging',
    'shutil',
    'zipfile',
    'tempfile',
    'io',
    'subprocess',
    
    # Queue y threading
    'queue',
    'Queue',
    
    # Watchdog
    'watchdog',
    'watchdog.observers',
    'watchdog.events',
    
    # Requests
    'requests',
    'requests.adapters',
    'requests.auth',
    'requests.cookies',
    'requests.models',
    'requests.sessions',
    'requests.utils',
    'requests.exceptions',
    
    # PIL/Pillow
    'PIL',
    'PIL.Image',
    'PIL.ImageDraw',
    'PIL.ImageFont',
    
    # PDF processing
    'pdf2image',
    'pdf2image.pdf2image',
    
    # System monitoring
    'psutil',
    
    # Windows specific (completo)
    'win32print',
    'win32api',
    'win32con',
    'win32gui',
    'win32ui',
    'win32clipboard',
    'win32file',
    'win32pipe',
    'win32process',
    'win32security',
    'win32service',
    'win32serviceutil',
    'pywintypes',
    'win32event',
    'servicemanager',
    'win32timezone',
    'win32pdh',
    'win32evtlog',
    
    # Concurrent futures
    'concurrent.futures',
    'concurrent.futures.thread',
    
    # Email (para notificaciones)
    'smtplib',
    'email.mime.text',
    'email.mime.multipart',
    
    # Backup y compresión
    'tarfile',
    'gzip',
    
    # Networking
    'socket',
    'ssl',
    'http.client',
    
    # Collections
    'collections',
    'collections.abc',
    
    # Functools
    'functools',
    
    # Base64
    'base64',
    
    # UUID
    'uuid',
    
    # Hashlib
    'hashlib',
    
    # Re
    're',
    
    # Math
    'math',
    
    # Random
    'random',
    
    # Pickle
    'pickle',
    
    # CSV
    'csv',
    
    # XML
    'xml.etree.ElementTree',
    
    # FastAPI y dependencias
    'fastapi',
    'fastapi.applications',
    'fastapi.routing',
    'fastapi.staticfiles',
    'fastapi.responses',
    'fastapi.exceptions',
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
    'starlette.staticfiles',
    'starlette.middleware',
    'anyio',
    'sniffio',
    
    # Módulos específicos del proyecto
    'validacion',
    'security',
    'security_logger', 
    'permissions',
    'printer',
    'pdf_printer',
    'vista_previa',
    'config',
    'handlers',
    'database',
    'notifications',
    'backup_manager',
    'user_manager',
    'system_monitor',
    'printer_utils',
    'poppler_manager',
    'fastapi_real',
]

# Datos a incluir
datas = [
    ('web', 'web'),
    ('poppler', 'poppler'),
    ('config', 'config'),
    ('src', 'src'),
    ('api', 'api'),
    ('gui', 'gui'),
    ('config.py', '.'),  # Archivo config.py en la raíz
    ('poppler_manager.py', '.'),  # Otros archivos en la raíz
    ('get_writable_path.py', '.'),  # Utilidad para rutas escribibles
    ('MANUAL_USUARIO.md', '.'),
]

a = Analysis(
    ['launcher_modern.py'],
    pathex=[],
    binaries=[],
    datas=datas,
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
    name='EtiquetadorZPL',
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
    icon='etiquetador_icon.ico'
)