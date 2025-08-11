"""
Limpiar archivos innecesarios
"""

import os
from pathlib import Path

# Archivos a eliminar (obsoletos/duplicados)
FILES_TO_DELETE = [
    "api_server.py",
    "simple_api.py", 
    "robust_api.py",
    "test_api.py",
    "test_robust_api.py",
    "test_performance.py",
    "test_performance_simple.py",
    "start_complete.py",
    "start_hybrid_fixed.py",
    "quick_start.py",
    "start_final.py",
    "hybrid_gui.py",  # Usar main_gui_optimized.py
    "launcher_optimized.pyw",  # Usar launcher.pyw
    "requirements_api.txt",
    "requirements_minimal.txt",
    "process_manager.py",  # Muy complejo
    "windows_service.py",  # Para más adelante
    "install_service.py",  # Para más adelante
    "simple_manager.py",  # Usar start_system.bat
    "docker-compose.yml",  # Para más adelante
    "Dockerfile",  # Para más adelante
]

# Archivos temporales
TEMP_FILES = [
    "api_port.txt",
    "etiquetador_pids.txt",
    "etiquetador.db",
    "*.pyc",
    "__pycache__",
]

def cleanup():
    """Limpiar archivos"""
    print("=== Limpieza de Archivos ===")
    
    deleted_count = 0
    
    # Eliminar archivos obsoletos
    for filename in FILES_TO_DELETE:
        file_path = Path(filename)
        if file_path.exists():
            try:
                if file_path.is_file():
                    file_path.unlink()
                    print(f"Eliminado: {filename}")
                    deleted_count += 1
                elif file_path.is_dir():
                    import shutil
                    shutil.rmtree(file_path)
                    print(f"Eliminado directorio: {filename}")
                    deleted_count += 1
            except Exception as e:
                print(f"Error eliminando {filename}: {e}")
    
    # Eliminar archivos temporales
    for pattern in TEMP_FILES:
        if "*" in pattern:
            # Usar glob para patrones
            import glob
            for file_path in glob.glob(pattern):
                try:
                    Path(file_path).unlink()
                    print(f"Eliminado temporal: {file_path}")
                    deleted_count += 1
                except:
                    pass
        else:
            file_path = Path(pattern)
            if file_path.exists():
                try:
                    if file_path.is_file():
                        file_path.unlink()
                    elif file_path.is_dir():
                        import shutil
                        shutil.rmtree(file_path)
                    print(f"Eliminado temporal: {pattern}")
                    deleted_count += 1
                except:
                    pass
    
    # Limpiar __pycache__
    for pycache in Path(".").rglob("__pycache__"):
        try:
            import shutil
            shutil.rmtree(pycache)
            print(f"Eliminado: {pycache}")
            deleted_count += 1
        except:
            pass
    
    print(f"\nEliminados {deleted_count} archivos/directorios")
    print("\n=== Archivos Principales Restantes ===")
    
    # Mostrar archivos importantes que quedan
    important_files = [
        "launcher.pyw",
        "main_gui_optimized.py", 
        "main_gui.py",
        "main.py",
        "final_api.py",
        "fastapi_server.py",
        "start_system.bat",
        "performance_optimizer.py",
        "performance_config.py",
        "handlers.py",
        "printer.py",
        "printer_utils.py",
        "config.py",
        "verificar_dependencias.py"
    ]
    
    for filename in important_files:
        if Path(filename).exists():
            print(f"✓ {filename}")
        else:
            print(f"✗ {filename} (faltante)")

if __name__ == "__main__":
    cleanup()
    input("\nPresiona Enter para continuar...")