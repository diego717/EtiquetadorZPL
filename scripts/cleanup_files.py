"""
Limpiar archivos innecesarios
"""

import os
from pathlib import Path

def cleanup_files():
    """Eliminar archivos innecesarios"""
    
    # Archivos obsoletos/duplicados
    obsolete_files = [
        # APIs obsoletas
        "fastapi_server.py",
        "final_api.py",  # Reemplazado por fast_api.py
        
        # GUIs obsoletas
        "main_gui.py",
        "main_gui_backup.py",
        "main.py",
        
        # Handlers obsoletos
        "fast_handler.py",  # Integrado en handlers.py
        
        # Configuraciones obsoletas
        "network_config_gui.py",
        "network_config.py",
        "performance_config.py",
        "performance_optimizer.py",
        "speed_optimizer.py",  # Integrado en fast_api.py
        
        # Tests obsoletos
        "test_watchdog.py",
        "test_api_integration.py",
        "quick_test.py",
        "simple_test.py",
        
        # Scripts obsoletos
        "actualizar_optimizado.bat",
        "start_enhanced.bat",
        "start_hybrid.bat",
        "start_simple.bat",
        "start_system.bat",
        
        # Instaladores obsoletos
        "install_fastapi.py",
        "enable_fast_mode.py",
        
        # Configuraciones obsoletas
        "guardar_config_multiple.py",
        "crear_acceso_directo.py",
        "crear_acceso_directo.bat",
        
        # Validaciones obsoletas
        "validacion_avanzada.py",  # Integrado en validacion.py
        
        # Logs duplicados
        "etiquetador.log",  # Ya está en logs/
        "logs_export_20250808_210422.zip",
        
        # READMEs obsoletos
        "README_OPTIMIZACION.md"
    ]
    
    # Directorios obsoletos
    obsolete_dirs = [
        "services",  # Funcionalidad integrada
        "config",    # Vacío
        "python_full"  # Instalador no necesario
    ]
    
    print("=== Limpieza de Archivos ===")
    
    # Eliminar archivos
    removed_files = 0
    for file in obsolete_files:
        file_path = Path(file)
        if file_path.exists():
            try:
                file_path.unlink()
                print(f"✓ Eliminado: {file}")
                removed_files += 1
            except Exception as e:
                print(f"✗ Error eliminando {file}: {e}")
    
    # Eliminar directorios
    removed_dirs = 0
    for dir_name in obsolete_dirs:
        dir_path = Path(dir_name)
        if dir_path.exists():
            try:
                import shutil
                shutil.rmtree(dir_path)
                print(f"✓ Eliminado directorio: {dir_name}")
                removed_dirs += 1
            except Exception as e:
                print(f"✗ Error eliminando {dir_name}: {e}")
    
    print(f"\n📊 Resumen:")
    print(f"Archivos eliminados: {removed_files}")
    print(f"Directorios eliminados: {removed_dirs}")
    
    # Mostrar archivos principales que quedan
    print(f"\n📁 Archivos principales restantes:")
    essential_files = [
        "launcher.pyw",           # Launcher principal
        "fast_api.py",           # API optimizada
        "main_gui_optimized.py", # GUI optimizada
        "handlers.py",           # Procesamiento de archivos
        "database.py",           # Base de datos
        "notifications.py",      # Notificaciones
        "backup_manager.py",     # Backups
        "user_manager.py",       # Usuarios
        "network_server.py",     # Servidor de red
        "test_system.py",        # Tests principales
        "test_performance.py",   # Tests de rendimiento
    ]
    
    for file in essential_files:
        if Path(file).exists():
            print(f"  ✓ {file}")
        else:
            print(f"  ✗ {file} (FALTA)")
    
    print(f"\n🎯 Sistema limpio y optimizado")

if __name__ == "__main__":
    cleanup_files()
    input("Presiona Enter para continuar...")