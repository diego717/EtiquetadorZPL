"""
Limpieza y organización del proyecto EtiquetadorZPL
"""

import os
import shutil
from pathlib import Path

def cleanup_project():
    """Limpiar archivos innecesarios y organizar proyecto"""
    
    print("Limpiando proyecto EtiquetadorZPL...")
    
    # Archivos a eliminar (redundantes/innecesarios)
    files_to_remove = [
        # Launchers redundantes
        'launcher_gui.py',
        'launcher_simple.py',
        'main.py',
        'simple_gui.py',
        'quick_start.py',
        
        # APIs redundantes
        'api/fast_api.py',  # Usar solo fastapi_real.py
        'api/network_server.py',
        'api/simple_service.py',
        'api/windows_service.py',
        
        # GUIs redundantes
        'gui/main_gui_optimized.py',  # Usar solo main_gui_optimized_fixed.py
        'gui/launcher.pyw',
        
        # Scripts redundantes
        'build_installer.py',
        'build_simple.py',
        'cleanup.py',
        'organize_project.py',
        
        # Archivos de configuración duplicados
        'config.ini',  # Usar solo config/config.ini
        'EtiquetadorZPL.spec',  # Usar solo EtiquetadorZPL_Complete.spec
        'EtiquetadorZPL.iss',
        
        # Archivos temporales/test
        'test_config_api.py',
        'logger_manager.py',
        'install_poppler.py',
        'poppler_path.txt',
        'api_port.txt',
        
        # Scripts batch redundantes
        'scripts/start_fast.bat',
        'scripts/start_gui_only.bat',
        'scripts/start_network.bat',
        'scripts/start_service.bat',
        'start_service_fixed.bat',
    ]
    
    # Eliminar archivos
    removed_count = 0
    for file_path in files_to_remove:
        full_path = Path(file_path)
        if full_path.exists():
            try:
                full_path.unlink()
                print(f"Eliminado: {file_path}")
                removed_count += 1
            except Exception as e:
                print(f"AVISO: No se pudo eliminar {file_path}: {e}")
    
    # Directorios a limpiar
    dirs_to_clean = [
        'installer',  # Limpiar instaladores viejos
        'logs',       # Limpiar logs viejos
    ]
    
    for dir_path in dirs_to_clean:
        dir_full_path = Path(dir_path)
        if dir_full_path.exists():
            try:
                shutil.rmtree(dir_full_path)
                dir_full_path.mkdir()
                print(f"Limpiado directorio: {dir_path}")
            except Exception as e:
                print(f"AVISO: No se pudo limpiar {dir_path}: {e}")
    
    # Crear estructura organizada
    create_organized_structure()
    
    print(f"OK: Limpieza completada. {removed_count} archivos eliminados.")

def create_organized_structure():
    """Crear estructura de directorios organizada"""
    
    # Directorios necesarios
    required_dirs = [
        'config',
        'logs',
        'installer',
        'temp',
    ]
    
    for dir_name in required_dirs:
        Path(dir_name).mkdir(exist_ok=True)
    
    # Crear archivo de estructura del proyecto
    structure_content = """
# Estructura del Proyecto EtiquetadorZPL

## Directorios principales:
- `api/` - API FastAPI
- `src/` - Código fuente principal
- `gui/` - Interfaz gráfica
- `web/` - Dashboard web
- `config/` - Archivos de configuración
- `poppler/` - Herramientas PDF
- `scripts/` - Scripts de utilidad
- `tests/` - Pruebas
- `docs/` - Documentación

## Archivos principales:
- `launcher_modern.py` - Launcher principal
- `build_with_inno.py` - Constructor de instalador
- `requirements.txt` - Dependencias Python
- `EtiquetadorZPL_Complete.spec` - Configuración PyInstaller

## Archivos de configuración:
- `config/config.ini` - Configuración principal
- `config/notification_config.json` - Configuración de notificaciones
- `config/backup_config.json` - Configuración de backups
"""
    
    with open('PROJECT_STRUCTURE.md', 'w', encoding='utf-8') as f:
        f.write(structure_content)
    
    print("Estructura de proyecto creada")

if __name__ == "__main__":
    cleanup_project()
    input("Presiona Enter para continuar...")