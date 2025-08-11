"""
Inicio rápido sin problemas de imports
"""

import sys
import os
from pathlib import Path

# Cambiar al directorio del proyecto
os.chdir(Path(__file__).parent)

# Agregar todos los paths necesarios
sys.path.insert(0, "src")
sys.path.insert(0, "api") 
sys.path.insert(0, "config")
sys.path.insert(0, ".")

def start_api_only():
    """Iniciar solo API"""
    try:
        from fast_api import start_fast_api
        start_fast_api()
    except Exception as e:
        print(f"Error: {e}")

def start_service():
    """Iniciar servicio completo"""
    try:
        from simple_service import SimpleService
        service = SimpleService()
        service.start()
    except Exception as e:
        print(f"Error: {e}")

def start_gui():
    """Iniciar GUI"""
    try:
        # Import directo de la GUI corregida
        import importlib.util
        spec = importlib.util.spec_from_file_location("main_gui_optimized_fixed", "gui/main_gui_optimized_fixed.py")
        gui_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gui_module)
        
        app = gui_module.EtiquetadorGUIOptimized()
        app.run()
    except Exception as e:
        print(f"Error iniciando GUI: {e}")

def start_all():
    """Iniciar todo: API + Monitoreo + GUI"""
    import threading
    
    print("Iniciando sistema completo...")
    
    # Iniciar API en hilo separado
    api_thread = threading.Thread(target=start_api_only, daemon=True)
    api_thread.start()
    
    # Iniciar monitoreo en hilo separado
    monitor_thread = threading.Thread(target=start_monitoring, daemon=True)
    monitor_thread.start()
    
    # Esperar un momento para que inicien
    import time
    time.sleep(3)
    
    print("API y monitoreo iniciados. Abriendo GUI...")
    
    # Iniciar GUI en hilo principal
    start_gui()

def start_monitoring():
    """Iniciar solo monitoreo de archivos"""
    try:
        import configparser
        config = configparser.ConfigParser()
        config.read('config/config.ini')
        
        from watchdog.observers import Observer
        
        # Import directo del handler
        import importlib.util
        spec = importlib.util.spec_from_file_location("handlers", "src/handlers.py")
        handlers_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(handlers_module)
        PDFHandler = handlers_module.PDFHandler
        
        observer = Observer()
        
        # Agregar carpetas configuradas
        for section in config.sections():
            if section.startswith('CARPETA'):
                carpeta_config = dict(config[section])
                if carpeta_config.get('entrada'):
                    handler = PDFHandler(carpeta_config, observer)
                    observer.schedule(handler, carpeta_config['entrada'], recursive=False)
                    print(f"Monitoreando: {carpeta_config['entrada']}")
        
        observer.start()
        
        # Mantener monitoreo activo
        try:
            while True:
                import time
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
        
        observer.join()
        
    except Exception as e:
        print(f"Error en monitoreo: {e}")

def main():
    """Menu principal"""
    print("=== EtiquetadorZPL Quick Start ===")
    print("1. API solamente")
    print("2. Servicio completo (API + Monitoreo)")
    print("3. GUI solamente")
    print("4. TODO (API + Monitoreo + GUI)")
    print("5. Salir")
    
    choice = input("Selecciona (1-5): ")
    
    if choice == "1":
        start_api_only()
    elif choice == "2":
        start_service()
    elif choice == "3":
        start_gui()
    elif choice == "4":
        start_all()
    elif choice == "5":
        return
    else:
        print("Opción inválida")
        main()

if __name__ == "__main__":
    main()