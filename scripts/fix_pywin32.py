"""
Corregir instalacion pywin32
"""

import subprocess
import sys
import os
from pathlib import Path

def fix_pywin32():
    """Corregir pywin32"""
    print("=== Corrigiendo pywin32 ===")
    
    # Reinstalar pywin32
    print("Reinstalando pywin32...")
    subprocess.run([sys.executable, "-m", "pip", "uninstall", "pywin32", "-y"])
    subprocess.run([sys.executable, "-m", "pip", "install", "pywin32"])
    
    # Ejecutar post-install
    print("Ejecutando post-install...")
    try:
        import win32api
        scripts_path = Path(win32api.__file__).parent.parent / "Scripts"
        postinstall_script = scripts_path / "pywin32_postinstall.py"
        
        if postinstall_script.exists():
            subprocess.run([sys.executable, str(postinstall_script), "-install"])
            print("Post-install ejecutado")
        else:
            print("Script post-install no encontrado")
            
    except Exception as e:
        print(f"Error en post-install: {e}")
    
    # Verificar pythonservice.exe
    python_dir = Path(sys.executable).parent
    service_exe = python_dir / "pythonservice.exe"
    
    if service_exe.exists():
        print(f"pythonservice.exe encontrado: {service_exe}")
    else:
        print(f"pythonservice.exe NO encontrado en: {python_dir}")
        
        # Buscar en otros lugares
        possible_paths = [
            python_dir / "Lib" / "site-packages" / "win32" / "pythonservice.exe",
            Path(sys.prefix) / "pythonservice.exe",
            Path(sys.prefix) / "Scripts" / "pythonservice.exe"
        ]
        
        for path in possible_paths:
            if path.exists():
                print(f"Encontrado en: {path}")
                # Copiar al directorio de Python
                import shutil
                shutil.copy2(path, service_exe)
                print(f"Copiado a: {service_exe}")
                break

if __name__ == "__main__":
    fix_pywin32()
    input("Presiona Enter...")