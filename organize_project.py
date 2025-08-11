"""
Organizar estructura del proyecto
"""

import shutil
from pathlib import Path

def organize_project():
    """Organizar archivos en carpetas"""
    
    print("=== Organizando Proyecto ===")
    
    # Crear estructura de carpetas
    folders = {
        "src": "Código fuente principal",
        "api": "API y servicios",
        "gui": "Interfaz gráfica",
        "config": "Archivos de configuración",
        "scripts": "Scripts de utilidad",
        "tests": "Tests del sistema",
        "docs": "Documentación"
    }
    
    for folder, desc in folders.items():
        Path(folder).mkdir(exist_ok=True)
        print(f"Carpeta creada: {folder}/ - {desc}")
    
    # Mapeo de archivos a carpetas
    file_mapping = {
        # API y servicios
        "api": [
            "fast_api.py",
            "final_api.py",
            "network_server.py",
            "simple_service.py",
            "windows_service.py"
        ],
        
        # GUI
        "gui": [
            "main_gui_optimized.py",
            "launcher.pyw",
            "vista_previa.py"
        ],
        
        # Código fuente principal
        "src": [
            "handlers.py",
            "database.py",
            "notifications.py",
            "backup_manager.py",
            "user_manager.py",
            "system_monitor.py",
            "printer.py",
            "printer_utils.py",
            "pdf_printer.py",
            "validacion.py",
            "security.py",
            "security_logger.py",
            "permissions.py"
        ],
        
        # Configuración
        "config": [
            "config.ini",
            "notification_config.json",
            "backup_config.json",
            "network_config.json",
            "users.json",
            "api_port.txt"
        ],
        
        # Scripts
        "scripts": [
            "start_service.bat",
            "start_fast.bat",
            "start_gui_only.bat",
            "start_network.bat",
            "install_service.bat",
            "run_tests.bat",
            "install_service.py",
            "install_service_simple.py",
            "fix_pywin32.py",
            "clean_simple.py",
            "cleanup_files.py",
            "verificar_dependencias.py"
        ],
        
        # Tests
        "tests": [
            "test_system.py",
            "test_performance.py",
            "test_printer_validation.py"
        ],
        
        # Docs
        "docs": [
            "README_FINAL.md"
        ]
    }
    
    # Mover archivos
    moved_count = 0
    for folder, files in file_mapping.items():
        for file in files:
            source = Path(file)
            if source.exists():
                destination = Path(folder) / file
                try:
                    shutil.move(str(source), str(destination))
                    print(f"Movido: {file} -> {folder}/")
                    moved_count += 1
                except Exception as e:
                    print(f"Error moviendo {file}: {e}")
    
    # Crear archivo principal de inicio
    create_main_launcher()
    
    # Crear README de estructura
    create_structure_readme()
    
    print(f"\nArchivos movidos: {moved_count}")
    print("Proyecto organizado correctamente")

def create_main_launcher():
    """Crear launcher principal"""
    launcher_content = '''"""
EtiquetadorZPL - Launcher Principal
"""

import sys
from pathlib import Path

# Agregar carpetas al path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root / "api"))
sys.path.insert(0, str(project_root / "gui"))

def main():
    """Menu principal"""
    print("=== EtiquetadorZPL ===")
    print("1. Iniciar GUI")
    print("2. Iniciar Servicio")
    print("3. Iniciar API solamente")
    print("4. Tests del sistema")
    print("5. Salir")
    
    choice = input("Selecciona opcion (1-5): ")
    
    if choice == "1":
        from gui.launcher import main as gui_main
        gui_main()
    elif choice == "2":
        from api.simple_service import main as service_main
        service_main()
    elif choice == "3":
        from api.fast_api import start_fast_api
        start_fast_api()
    elif choice == "4":
        from tests.test_system import main as test_main
        test_main()
    elif choice == "5":
        return
    else:
        print("Opcion invalida")
        main()

if __name__ == "__main__":
    main()
'''
    
    with open("main.py", "w") as f:
        f.write(launcher_content)
    
    print("Launcher principal creado: main.py")

def create_structure_readme():
    """Crear README de estructura"""
    readme_content = """# EtiquetadorZPL - Estructura del Proyecto

## 📁 Estructura de Carpetas

```
EtiquetadorZPL/
├── main.py                 # Launcher principal
├── src/                    # Código fuente principal
│   ├── handlers.py         # Procesamiento de archivos
│   ├── database.py         # Base de datos
│   ├── notifications.py    # Sistema de notificaciones
│   ├── backup_manager.py   # Gestión de backups
│   └── ...
├── api/                    # API y servicios
│   ├── fast_api.py         # API optimizada
│   ├── simple_service.py   # Servicio simple
│   └── network_server.py   # Servidor de red
├── gui/                    # Interfaz gráfica
│   ├── launcher.pyw        # Launcher GUI
│   └── main_gui_optimized.py
├── config/                 # Configuraciones
│   ├── config.ini          # Configuración principal
│   └── *.json             # Configuraciones específicas
├── scripts/                # Scripts de utilidad
│   ├── start_service.bat   # Iniciar servicio
│   └── install_service.py  # Instalador
├── tests/                  # Tests del sistema
│   ├── test_system.py      # Tests principales
│   └── test_performance.py # Tests de rendimiento
├── web/                    # Dashboard web
├── logs/                   # Archivos de log
├── backups/                # Backups automáticos
└── docs/                   # Documentación
```

## 🚀 Uso

### Inicio Rápido
```bash
python main.py
```

### Opciones Específicas
```bash
# Solo GUI
python gui/launcher.pyw

# Solo servicio
python api/simple_service.py

# Solo API
python api/fast_api.py

# Tests
python tests/test_system.py
```

## 📊 Dashboard Web
- Local: http://localhost:8002/web/
- Red: http://IP_LOCAL:8002/web/
"""
    
    with open("README.md", "w") as f:
        f.write(readme_content)
    
    print("README.md creado")

if __name__ == "__main__":
    organize_project()
    input("Presiona Enter para continuar...")