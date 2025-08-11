"""
Launcher simple sin bloqueos
"""

import tkinter as tk
from tkinter import ttk
import subprocess
import sys
import os
from pathlib import Path
import threading

class SimpleLauncher:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("EtiquetadorZPL")
        self.root.geometry("350x250")
        self.root.resizable(False, False)
        
        # Cambiar al directorio correcto
        if hasattr(sys, '_MEIPASS'):
            os.chdir(sys._MEIPASS)
        else:
            os.chdir(Path(__file__).parent)
        
        self.create_widgets()
    
    def create_widgets(self):
        """Crear interfaz simple"""
        # Título
        title = tk.Label(self.root, text="🏷️ EtiquetadorZPL", 
                        font=("Arial", 16, "bold"))
        title.pack(pady=15)
        
        # Botones
        btn_frame = tk.Frame(self.root)
        btn_frame.pack(pady=10)
        
        tk.Button(btn_frame, text="🌐 Solo API", 
                 command=self.start_api,
                 width=20, height=2).pack(pady=3)
        
        tk.Button(btn_frame, text="🖥️ Solo GUI", 
                 command=self.start_gui,
                 width=20, height=2).pack(pady=3)
        
        tk.Button(btn_frame, text="🚀 API + GUI", 
                 command=self.start_both,
                 width=20, height=2, 
                 bg="lightgreen").pack(pady=3)
        
        tk.Button(btn_frame, text="❌ Salir", 
                 command=self.root.quit,
                 width=20, height=2).pack(pady=3)
        
        # Info
        info = tk.Label(self.root, 
                       text="Dashboard: http://localhost:8002/web/",
                       font=("Arial", 8), fg="blue")
        info.pack(pady=5)
    
    def start_api(self):
        """Iniciar solo API"""
        def run_api():
            try:
                # Agregar paths
                sys.path.insert(0, "src")
                sys.path.insert(0, "api")
                sys.path.insert(0, "config")
                
                from fast_api import start_fast_api
                start_fast_api()
            except Exception as e:
                print(f"Error API: {e}")
        
        threading.Thread(target=run_api, daemon=True).start()
        self.show_message("API iniciada en puerto 8002")
    
    def start_gui(self):
        """Iniciar solo GUI"""
        def run_gui():
            try:
                print("Iniciando GUI...")
                
                # Agregar paths
                sys.path.insert(0, "src")
                sys.path.insert(0, "api")
                sys.path.insert(0, "config")
                sys.path.insert(0, "gui")
                
                print("Paths agregados")
                
                # Verificar que el archivo existe
                gui_file = Path("gui/main_gui_optimized_fixed.py")
                if not gui_file.exists():
                    print(f"ERROR: No se encuentra {gui_file}")
                    input("Presiona Enter para continuar...")
                    return
                
                print(f"Archivo GUI encontrado: {gui_file}")
                
                # Importar y ejecutar GUI
                import importlib.util
                spec = importlib.util.spec_from_file_location("main_gui_optimized_fixed", str(gui_file))
                if spec is None:
                    print("ERROR: No se pudo crear spec")
                    input("Presiona Enter para continuar...")
                    return
                
                print("Spec creado")
                
                gui_module = importlib.util.module_from_spec(spec)
                if gui_module is None:
                    print("ERROR: No se pudo crear modulo")
                    input("Presiona Enter para continuar...")
                    return
                
                print("Modulo creado")
                
                spec.loader.exec_module(gui_module)
                print("Modulo cargado")
                
                app = gui_module.EtiquetadorGUIOptimized()
                print("App creada")
                
                app.run()
                print("App ejecutada")
                
            except Exception as e:
                print(f"ERROR GUI: {e}")
                import traceback
                traceback.print_exc()
                input("Presiona Enter para continuar...")
        
        # Cerrar launcher y abrir GUI
        self.root.after(100, self.root.destroy)
        threading.Thread(target=run_gui, daemon=False).start()
    
    def start_both(self):
        """Iniciar API + GUI"""
        try:
            print("Iniciando API + GUI...")
            
            # Primero iniciar API
            self.start_api()
            
            # Luego iniciar GUI después de un momento
            self.root.after(2000, self.start_gui)
            
        except Exception as e:
            print(f"ERROR en start_both: {e}")
            import traceback
            traceback.print_exc()
            input("Presiona Enter para continuar...")
    
    def show_message(self, message):
        """Mostrar mensaje temporal"""
        msg_window = tk.Toplevel(self.root)
        msg_window.title("Info")
        msg_window.geometry("250x80")
        msg_window.resizable(False, False)
        
        tk.Label(msg_window, text=message, wraplength=200).pack(pady=20)
        
        # Auto-cerrar después de 3 segundos
        msg_window.after(3000, msg_window.destroy)
    
    def run(self):
        """Ejecutar launcher"""
        self.root.mainloop()

if __name__ == "__main__":
    app = SimpleLauncher()
    app.run()