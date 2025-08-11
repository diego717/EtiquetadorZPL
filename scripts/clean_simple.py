"""
Limpiar archivos innecesarios - version simple
"""

import os
import shutil
from pathlib import Path

def clean_files():
    """Eliminar archivos obsoletos"""
    
    # Archivos a eliminar
    files_to_remove = [
        "fastapi_server.py",
        "final_api.py", 
        "main_gui.py",
        "main_gui_backup.py",
        "main.py",
        "fast_handler.py",
        "network_config_gui.py",
        "network_config.py",
        "performance_config.py",
        "performance_optimizer.py",
        "speed_optimizer.py",
        "test_watchdog.py",
        "test_api_integration.py",
        "quick_test.py",
        "simple_test.py",
        "actualizar_optimizado.bat",
        "start_enhanced.bat",
        "start_hybrid.bat",
        "start_simple.bat",
        "start_system.bat",
        "install_fastapi.py",
        "enable_fast_mode.py",
        "guardar_config_multiple.py",
        "crear_acceso_directo.py",
        "crear_acceso_directo.bat",
        "validacion_avanzada.py",
        "etiquetador.log",
        "logs_export_20250808_210422.zip",
        "README_OPTIMIZACION.md"
    ]
    
    # Directorios a eliminar
    dirs_to_remove = [
        "services",
        "config", 
        "python_full"
    ]
    
    print("Limpiando archivos...")
    
    removed = 0
    
    # Eliminar archivos
    for file in files_to_remove:
        if Path(file).exists():
            try:
                Path(file).unlink()
                print(f"Eliminado: {file}")
                removed += 1
            except:
                print(f"Error eliminando: {file}")
    
    # Eliminar directorios
    for dir_name in dirs_to_remove:
        if Path(dir_name).exists():
            try:
                shutil.rmtree(dir_name)
                print(f"Eliminado directorio: {dir_name}")
                removed += 1
            except:
                print(f"Error eliminando directorio: {dir_name}")
    
    print(f"\nArchivos eliminados: {removed}")
    print("Limpieza completada")

if __name__ == "__main__":
    clean_files()
    input("Presiona Enter...")