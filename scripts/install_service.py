"""
Instalador del servicio EtiquetadorZPL
"""

import subprocess
import sys
import os
from pathlib import Path

def check_admin():
    """Verificar permisos de administrador"""
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except:
        return False

def run_as_admin():
    """Ejecutar como administrador"""
    try:
        import ctypes
        import sys
        
        if ctypes.windll.shell32.IsUserAnAdmin():
            return True
        else:
            # Re-ejecutar como administrador
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable, " ".join(sys.argv), None, 1
            )
            return False
    except:
        return False

def install_dependencies():
    """Instalar dependencias del servicio"""
    print("Instalando dependencias del servicio...")
    
    dependencies = [
        "pywin32",
        "watchdog",
        "requests"
    ]
    
    for dep in dependencies:
        try:
            print(f"Instalando {dep}...")
            result = subprocess.run([
                sys.executable, "-m", "pip", "install", dep
            ], capture_output=True, text=True)
            
            if result.returncode == 0:
                print(f"OK: {dep}")
            else:
                print(f"Error: {dep} - {result.stderr}")
                
        except Exception as e:
            print(f"Error instalando {dep}: {e}")

def create_service_config():
    """Crear configuración del servicio"""
    config_content = """[SERVICE]
name = EtiquetadorZPL
display_name = EtiquetadorZPL Service
description = Servicio de procesamiento automatico de etiquetas ZPL
start_type = auto
account = LocalSystem

[LOGGING]
log_file = service.log
log_level = INFO

[API]
port = 8080
host = 0.0.0.0
"""
    
    with open('service_config.ini', 'w') as f:
        f.write(config_content)
    
    print("Configuracion del servicio creada")

def install_service():
    """Instalar servicio"""
    if not run_as_admin():
        return False  # Se re-ejecutó como admin
    
    print("Ejecutando con permisos de administrador...")
    
    print("=== Instalador Servicio EtiquetadorZPL ===")
    
    # Verificar archivos necesarios
    required_files = [
        "windows_service.py",
        "fast_api.py",
        "database.py",
        "handlers.py",
        "config.ini"
    ]
    
    missing_files = []
    for file in required_files:
        if not Path(file).exists():
            missing_files.append(file)
    
    if missing_files:
        print("ERROR: Archivos faltantes:")
        for file in missing_files:
            print(f"  - {file}")
        return False
    
    # Instalar dependencias
    install_dependencies()
    
    # Crear configuración
    create_service_config()
    
    # Instalar servicio
    try:
        print("Instalando servicio...")
        result = subprocess.run([
            sys.executable, "windows_service.py", "install"
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            print("Servicio instalado correctamente")
            
            # Iniciar servicio
            print("Iniciando servicio...")
            result = subprocess.run([
                sys.executable, "windows_service.py", "start"
            ], capture_output=True, text=True)
            
            if result.returncode == 0:
                print("Servicio iniciado correctamente")
                print("\nServicio EtiquetadorZPL instalado y ejecutandose")
                print("Puedes administrarlo desde services.msc")
                return True
            else:
                print(f"Error iniciando servicio: {result.stderr}")
                return False
        else:
            print(f"Error instalando servicio: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"Error: {e}")
        return False

def uninstall_service():
    """Desinstalar servicio"""
    if not run_as_admin():
        return False  # Se re-ejecutó como admin
    
    try:
        print("Deteniendo servicio...")
        subprocess.run([sys.executable, "windows_service.py", "stop"], 
                      capture_output=True)
        
        print("Desinstalando servicio...")
        result = subprocess.run([
            sys.executable, "windows_service.py", "remove"
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            print("Servicio desinstalado correctamente")
            return True
        else:
            print(f"Error: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"Error: {e}")
        return False

def main():
    """Menu principal"""
    print("=== Gestor Servicio EtiquetadorZPL ===")
    print("1. Instalar servicio")
    print("2. Desinstalar servicio")
    print("3. Salir")
    
    choice = input("Selecciona opcion (1-3): ")
    
    if choice == "1":
        install_service()
    elif choice == "2":
        uninstall_service()
    elif choice == "3":
        return
    else:
        print("Opcion invalida")

if __name__ == "__main__":
    main()
    input("Presiona Enter para continuar...")