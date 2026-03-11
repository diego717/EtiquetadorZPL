"""
Script para verificar que todos los paths estén correctos antes del build
"""

import os
from pathlib import Path

def verify_paths():
    """Verificar que todos los archivos y carpetas necesarios existan"""
    
    print("=== Verificación de Paths para Build ===\n")
    
    required_files = [
        "launcher_modern.py",
        "EtiquetadorZPL_Complete.spec",
        "EtiquetadorZPL_Simple.iss",
        "config.py",
        "poppler_manager.py",
        "get_writable_path.py",
        "MANUAL_USUARIO.md",
        "etiquetador_icon.ico",
        "src/config_manager.py",
        "src/log_config.py",
        "src/database.py"
    ]
    
    required_dirs = [
        "web",
        "config",
        "src",
        "api", 
        "gui",
        "poppler/poppler-23.08.0/Library/bin",
        "poppler/poppler-23.08.0/share"
    ]
    
    critical_files = [
        "poppler/poppler-23.08.0/Library/bin/pdftoppm.exe",
        "gui/main_gui_optimized_fixed.py",
        "api/fastapi_real.py"
    ]
    
    all_good = True
    
    # Verificar archivos requeridos
    print("Verificando archivos requeridos:")
    for file in required_files:
        if Path(file).exists():
            print(f"  OK {file}")
        else:
            print(f"  ERROR {file} - FALTANTE")
            all_good = False
    
    print("\nVerificando directorios requeridos:")
    for dir_path in required_dirs:
        if Path(dir_path).exists():
            print(f"  OK {dir_path}/")
        else:
            print(f"  ERROR {dir_path}/ - FALTANTE")
            all_good = False
    
    print("\nVerificando archivos criticos:")
    for file in critical_files:
        if Path(file).exists():
            print(f"  OK {file}")
        else:
            print(f"  ERROR {file} - CRITICO FALTANTE")
            all_good = False
    
    # Verificar estructura de poppler
    print("\nVerificando estructura de Poppler:")
    poppler_bin = Path("poppler/poppler-23.08.0/Library/bin")
    if poppler_bin.exists():
        exe_files = list(poppler_bin.glob("*.exe"))
        dll_files = list(poppler_bin.glob("*.dll"))
        print(f"  OK Binarios encontrados: {len(exe_files)} .exe, {len(dll_files)} .dll")
        
        # Verificar archivos específicos de poppler
        critical_poppler = ["pdftoppm.exe", "pdfinfo.exe", "poppler.dll"]
        for file in critical_poppler:
            if (poppler_bin / file).exists():
                print(f"    OK {file}")
            else:
                print(f"    ERROR {file} - FALTANTE")
                all_good = False
    else:
        print("  ERROR Directorio de binarios de Poppler no encontrado")
        all_good = False
    
    # Verificar archivos web
    print("\nVerificando archivos web:")
    web_files = ["index.html", "config.html", "login.html", "config.js"]
    for file in web_files:
        web_path = Path("web") / file
        if web_path.exists():
            print(f"  OK web/{file}")
        else:
            print(f"  ERROR web/{file} - FALTANTE")
            all_good = False
    
    print(f"\n{'='*50}")
    if all_good:
        print("VERIFICACION EXITOSA - Todos los archivos estan presentes")
        print("El proyecto esta listo para el build")
    else:
        print("VERIFICACION FALLIDA - Faltan archivos criticos")
        print("Corrige los problemas antes de continuar con el build")
    
    return all_good

def fix_common_issues():
    """Intentar corregir problemas comunes"""
    
    print("\nIntentando corregir problemas comunes...")
    
    # Crear carpetas faltantes
    required_dirs = ["logs", "temp", "installer"]
    for dir_name in required_dirs:
        Path(dir_name).mkdir(exist_ok=True)
        print(f"  OK Creado/verificado: {dir_name}/")
    
    # Verificar icono
    if not Path("etiquetador_icon.ico").exists():
        print("  Creando icono...")
        try:
            exec(open("create_icon.py").read())
            print("  OK Icono creado")
        except Exception as e:
            print(f"  ERROR creando icono: {e}")

if __name__ == "__main__":
    if verify_paths():
        print("\nPuedes proceder con el build usando: python build_with_inno.py")
    else:
        print("\nIntentando corregir problemas...")
        fix_common_issues()
        print("\nEjecuta este script nuevamente para verificar")
    
    input("\nPresiona Enter para continuar...")