"""
Script para crear instalador de EtiquetadorZPL
"""

import subprocess
import sys
import os
from pathlib import Path

def install_pyinstaller():
    """Instalar PyInstaller"""
    print("Instalando PyInstaller...")
    subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"])

def create_spec_file():
    """Crear archivo .spec personalizado"""
    spec_content = '''
# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

# Datos adicionales a incluir
added_files = [
    ('web', 'web'),
    ('poppler', 'poppler'),
    ('config', 'config'),
    ('src', 'src'),
    ('api', 'api'),
    ('gui', 'gui'),
    ('MANUAL_USUARIO.md', '.'),
    ('README.md', '.'),
]

a = Analysis(
    ['quick_start.py'],
    pathex=[],
    binaries=[],
    datas=added_files,
    hiddenimports=[
        'tkinter',
        'tkinter.ttk',
        'tkinter.filedialog',
        'tkinter.messagebox',
        'tkinter.scrolledtext',
        'watchdog',
        'watchdog.observers',
        'watchdog.events',
        'requests',
        'configparser',
        'sqlite3',
        'threading',
        'json',
        'pathlib',
        'importlib.util',
    ],
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
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.ico'  # Si tienes un icono
)
'''
    
    with open('EtiquetadorZPL.spec', 'w') as f:
        f.write(spec_content)
    
    print("Archivo .spec creado")

def build_executable():
    """Construir ejecutable"""
    print("Construyendo ejecutable...")
    
    # Crear spec file
    create_spec_file()
    
    # Construir con PyInstaller
    cmd = [
        "pyinstaller",
        "--clean",
        "--noconfirm", 
        "EtiquetadorZPL.spec"
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        print("✅ Ejecutable creado exitosamente")
        print("📁 Ubicación: dist/EtiquetadorZPL.exe")
        return True
    else:
        print("❌ Error creando ejecutable:")
        print(result.stderr)
        return False

def create_installer_script():
    """Crear script de instalación"""
    installer_content = '''@echo off
echo === Instalador EtiquetadorZPL ===
echo.

REM Crear directorio de instalación
set INSTALL_DIR=C:\\EtiquetadorZPL
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"

REM Copiar archivos
echo Copiando archivos...
copy "EtiquetadorZPL.exe" "%INSTALL_DIR%\\"
copy "MANUAL_USUARIO.md" "%INSTALL_DIR%\\"

REM Crear acceso directo en escritorio
echo Creando acceso directo...
powershell "$WshShell = New-Object -comObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%USERPROFILE%\\Desktop\\EtiquetadorZPL.lnk'); $Shortcut.TargetPath = '%INSTALL_DIR%\\EtiquetadorZPL.exe'; $Shortcut.Save()"

REM Crear carpetas de trabajo
if not exist "C:\\EtiquetasFlex" mkdir "C:\\EtiquetasFlex"
if not exist "C:\\EtiquetasFlex\\Entrada1" mkdir "C:\\EtiquetasFlex\\Entrada1"
if not exist "C:\\EtiquetasFlex\\Historial1" mkdir "C:\\EtiquetasFlex\\Historial1"

echo.
echo ✅ Instalación completada
echo 📁 Instalado en: %INSTALL_DIR%
echo 🖥️ Acceso directo creado en escritorio
echo 📂 Carpetas de trabajo creadas en C:\\EtiquetasFlex
echo.
pause
'''
    
    with open('dist/instalar.bat', 'w') as f:
        f.write(installer_content)
    
    print("Script de instalación creado: dist/instalar.bat")

def create_portable_version():
    """Crear versión portable"""
    portable_content = '''@echo off
echo === EtiquetadorZPL Portable ===
echo.
echo Iniciando aplicación...
echo.

REM Crear carpetas temporales si no existen
if not exist "temp" mkdir "temp"
if not exist "config" mkdir "config"
if not exist "logs" mkdir "logs"

REM Ejecutar aplicación
EtiquetadorZPL.exe

echo.
echo Aplicación cerrada.
pause
'''
    
    with open('dist/EtiquetadorZPL_Portable.bat', 'w') as f:
        f.write(portable_content)
    
    print("Versión portable creada: dist/EtiquetadorZPL_Portable.bat")

def main():
    """Función principal"""
    print("=== Constructor de Instalador EtiquetadorZPL ===")
    
    # Verificar PyInstaller
    try:
        import PyInstaller
        print("PyInstaller disponible")
    except ImportError:
        install_pyinstaller()
    
    # Construir ejecutable
    if build_executable():
        # Crear scripts adicionales
        create_installer_script()
        create_portable_version()
        
        print("\n🎉 Paquete de distribución creado:")
        print("📁 dist/EtiquetadorZPL.exe - Ejecutable principal")
        print("📁 dist/instalar.bat - Instalador automático")
        print("📁 dist/EtiquetadorZPL_Portable.bat - Versión portable")
        print("\n📋 Para distribuir:")
        print("1. Comprimir carpeta 'dist' en ZIP")
        print("2. Distribuir archivo ZIP")
        print("3. Usuario ejecuta 'instalar.bat' o usa versión portable")
    else:
        print("❌ Error en la construcción")

if __name__ == "__main__":
    main()
    input("Presiona Enter para continuar...")