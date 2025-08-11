"""
Servicio simple sin pywin32
"""

import time
import threading
import signal
import sys
from pathlib import Path

# Agregar paths para imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root / "config"))
sys.path.insert(0, str(project_root / "api"))

class SimpleService:
    def __init__(self):
        self.running = True
        self.api_thread = None
        self.monitor_thread = None
    
    def start(self):
        """Iniciar servicio"""
        print("Iniciando EtiquetadorZPL Service...")
        
        # Manejar señales
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
        # Iniciar API
        self.api_thread = threading.Thread(target=self.start_api, daemon=True)
        self.api_thread.start()
        
        # Iniciar monitoreo
        self.monitor_thread = threading.Thread(target=self.start_monitoring, daemon=True)
        self.monitor_thread.start()
        
        print("Servicio iniciado. Presiona Ctrl+C para detener.")
        
        # Mantener servicio activo
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        
        self.stop()
    
    def stop(self):
        """Detener servicio"""
        print("Deteniendo servicio...")
        self.running = False
    
    def signal_handler(self, signum, frame):
        """Manejar señales"""
        print(f"Señal recibida: {signum}")
        self.stop()
    
    def start_api(self):
        """Iniciar API"""
        try:
            # Import directo del archivo
            import importlib.util
            spec = importlib.util.spec_from_file_location("fast_api", "api/fast_api.py")
            fast_api_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(fast_api_module)
            fast_api_module.start_fast_api()
        except Exception as e:
            print(f"Error iniciando API: {e}")
    
    def start_monitoring(self):
        """Iniciar monitoreo de archivos"""
        try:
            import configparser
            config = configparser.ConfigParser()
            config.read('config.ini')
            
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
            
            while self.running:
                time.sleep(1)
            
            observer.stop()
            observer.join()
            
        except Exception as e:
            print(f"Error en monitoreo: {e}")

def main():
    """Función principal"""
    service = SimpleService()
    service.start()

if __name__ == "__main__":
    main()