"""
Script simple para construir instalador
"""

import subprocess
import sys
import os
from pathlib import Path

def build_executable():
    """Construir ejecutable con PyInstaller"""
    print("Construyendo ejecutable...")
    
    cmd = [
        "pyinstaller",
        "--onefile",
        "--name=EtiquetadorZPL",
        "--add-data=web;web",
        "--add-data=config;config", 
        "--add-data=poppler;poppler",
        "--add-data=src;src",
        "--add-data=api;api",
        "--add-data=gui;gui",
        "quick_start.py"
    ]
    
    result = subprocess.run(cmd)
    
    if result.returncode == 0:
        print("OK: Ejecutable creado")
        return True
    else:
        print("ERROR: Fallo al crear ejecutable")
        return False

def build_installer():
    """Construir instalador con Inno Setup"""
    print("Construyendo instalador...")
    
    # Buscar Inno Setup
    inno_paths = [
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe"
    ]
    
    iscc_path = None
    for path in inno_paths:
        if Path(path).exists():
            iscc_path = path
            break
    
    if not iscc_path:
        print("ERROR: Inno Setup no encontrado")
        print("Instala desde: https://jrsoftware.org/isinfo.php")
        return False
    
    print(f"Usando: {iscc_path}")
    
    # Construir
    result = subprocess.run([iscc_path, "EtiquetadorZPL.iss"])
    
    if result.returncode == 0:
        print("OK: Instalador creado")
        return True
    else:
        print("ERROR: Fallo al crear instalador")
        return False

def main():
    """Funcion principal"""
    print("=== Constructor EtiquetadorZPL ===")
    
    # Paso 1: Ejecutable
    if not build_executable():
        return False
    
    # Verificar que se creo
    if not Path("dist/EtiquetadorZPL.exe").exists():
        print("ERROR: No se encontro el ejecutable")
        return False
    
    print(f"Ejecutable: {Path('dist/EtiquetadorZPL.exe').stat().st_size / (1024*1024):.1f} MB")
    
    # Paso 2: Instalador
    if not build_installer():
        return False
    
    # Verificar instalador
    installer_path = Path("installer/EtiquetadorZPL_Setup.exe")
    if installer_path.exists():
        size_mb = installer_path.stat().st_size / (1024 * 1024)
        print(f"Instalador: {size_mb:.1f} MB")
        print("LISTO PARA DISTRIBUIR")
        return True
    else:
        print("ERROR: Instalador no encontrado")
        return False

if __name__ == "__main__":
    success = main()
    input("Presiona Enter...")