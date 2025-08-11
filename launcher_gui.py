"""
Launcher con GUI para evitar problemas de consola
"""

import tkinter as tk
from tkinter import ttk
import subprocess
import sys
import os
from pathlib import Path

class LauncherGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("EtiquetadorZPL - Launcher")
        self.root.geometry("400x300")
        self.root.resizable(False, False)
        
        # Cambiar al directorio del ejecutable
        if hasattr(sys, '_MEIPASS'):
            os.chdir(sys._MEIPASS)
        else:
            os.chdir(Path(__file__).parent)
        
        # Agregar paths
        sys.path.insert(0, "src")
        sys.path.insert(0, "api") 
        sys.path.insert(0, "config")
        sys.path.insert(0, ".")
        
        self.create_widgets()
    
    def create_widgets(self):
        """Crear interfaz"""
        # Título
        title = tk.Label(self.root, text="🏷️ EtiquetadorZPL", 
                        font=("Arial", 18, "bold"))
        title.pack(pady=20)
        
        # Descripción
        desc = tk.Label(self.root, 
                       text="Selecciona el modo de ejecución:",
                       font=("Arial", 10))
        desc.pack(pady=10)
        
        # Botones
        btn_frame = tk.Frame(self.root)
        btn_frame.pack(pady=20)
        
        tk.Button(btn_frame, text="🌐 Solo API", 
                 command=self.start_api_only,
                 width=25, height=2).pack(pady=5)
        
        tk.Button(btn_frame, text="🔄 Servicio Completo", 
                 command=self.start_service,
                 width=25, height=2).pack(pady=5)
        
        tk.Button(btn_frame, text="🖥️ Solo GUI", 
                 command=self.start_gui,
                 width=25, height=2).pack(pady=5)
        
        tk.Button(btn_frame, text="🚀 TODO (Recomendado)", 
                 command=self.start_all,
                 width=25, height=2, 
                 bg="lightgreen").pack(pady=5)
        
        # Info
        info = tk.Label(self.root, 
                       text="Dashboard Web: http://localhost:8002/web/",
                       font=("Arial", 8), fg="blue")
        info.pack(pady=10)
    
    def start_api_only(self):
        """Iniciar solo API"""
        try:
            from fast_api import start_fast_api
            start_fast_api()
        except Exception as e:
            print(f"Error iniciando API: {e}")
    
    def start_service(self):
        """Iniciar servicio completo"""
        try:
            from simple_service import SimpleService
            service = SimpleService()
            service.start()
        except Exception as e:
            print(f"Error iniciando servicio: {e}")
    
    def start_gui(self):
        """Iniciar GUI"""
        self.show_status("Iniciando GUI...")
        try:
            import importlib.util
            import threading
            
            def run_gui():
                try:
                    spec = importlib.util.spec_from_file_location("main_gui_optimized_fixed", "gui/main_gui_optimized_fixed.py")
                    gui_module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(gui_module)
                    
                    app = gui_module.EtiquetadorGUIOptimized()
                    app.run()
                except Exception as e:
                    print(f"Error en GUI: {e}")
            
            # Ejecutar GUI en hilo separado para no bloquear
            gui_thread = threading.Thread(target=run_gui, daemon=False)
            gui_thread.start()
            
            # Ocultar launcher después de un momento
            self.root.after(2000, self.root.withdraw)
            
        except Exception as e:
            self.show_error(f"Error iniciando GUI: {e}")
    
    def start_all(self):
        """Iniciar todo"""
        self.show_status("Iniciando sistema completo...")
        try:
            import threading
            
            # Iniciar API en hilo separado
            api_thread = threading.Thread(target=self.start_api_only, daemon=True)
            api_thread.start()
            
            # Iniciar monitoreo en hilo separado
            monitor_thread = threading.Thread(target=self.start_monitoring, daemon=True)
            monitor_thread.start()
            
            # Esperar un momento usando after en lugar de sleep
            self.root.after(3000, self.delayed_start_gui)  # 3 segundos
            
        except Exception as e:
            self.show_error(f"Error iniciando sistema: {e}")
    
    def delayed_start_gui(self):
        """Iniciar GUI con retraso"""
        try:
            self.start_gui()
        except Exception as e:
            self.show_error(f"Error iniciando GUI: {e}")
    
    def start_monitoring(self):
        """Iniciar monitoreo de archivos"""
        try:
            import configparser
            config = configparser.ConfigParser()
            config.read('config/config.ini')
            
            from watchdog.observers import Observer
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
            
            observer.start()
            
            # Mantener monitoreo activo
            while True:
                import time
                time.sleep(1)
                
        except Exception as e:
            print(f"Error en monitoreo: {e}")
    
    def show_status(self, message):
        """Mostrar estado"""
        status = tk.Toplevel(self.root)
        status.title("Estado")
        status.geometry("300x100")
        status.resizable(False, False)
        
        tk.Label(status, text=message, font=("Arial", 10)).pack(pady=30)
        
        # Auto-cerrar después de 2 segundos
        status.after(2000, status.destroy)
    
    def show_error(self, message):
        """Mostrar error"""
        from tkinter import messagebox
        messagebox.showerror("Error", message)
    
    def run(self):
        """Ejecutar launcher"""
        self.root.mainloop()

if __name__ == "__main__":
    app = LauncherGUI()
    app.run()