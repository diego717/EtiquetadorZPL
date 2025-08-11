"""
Launcher moderno para EtiquetadorZPL
"""

import tkinter as tk
from tkinter import ttk
import subprocess
import sys
import os
from pathlib import Path
import threading

class ModernLauncher:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("EtiquetadorZPL")
        self.root.geometry("550x500")
        self.root.resizable(True, True)
        self.root.minsize(550, 500)
        self.root.configure(bg='#f0f0f0')
        
        # Centrar ventana
        self.center_window()
        
        # Cambiar al directorio correcto
        if hasattr(sys, '_MEIPASS'):
            os.chdir(sys._MEIPASS)
        else:
            os.chdir(Path(__file__).parent)
        
        self.create_modern_ui()
    
    def center_window(self):
        """Centrar ventana en pantalla"""
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f'{width}x{height}+{x}+{y}')
    
    def create_modern_ui(self):
        """Crear interfaz moderna"""
        # Header
        header_frame = tk.Frame(self.root, bg='#2c3e50', height=80)
        header_frame.pack(fill='x')
        header_frame.pack_propagate(False)
        
        title = tk.Label(header_frame, text="🏷️ EtiquetadorZPL", 
                        font=("Segoe UI", 20, "bold"), 
                        fg='white', bg='#2c3e50')
        title.pack(pady=20)
        
        # Subtitle
        subtitle = tk.Label(self.root, text="Selecciona el modo de ejecución", 
                           font=("Segoe UI", 11), 
                           fg='#7f8c8d', bg='#f0f0f0')
        subtitle.pack(pady=(20, 30))
        
        # Options container simple
        options_frame = tk.Frame(self.root, bg='#f0f0f0')
        options_frame.pack(fill='both', expand=True, padx=30, pady=(0, 20))
        
        # Option 1: Solo API
        self.create_option_card(
            options_frame,
            "🌐 Solo API",
            "Servidor web - Dashboard: localhost:8002/web/",
            "#3498db",
            self.start_api
        )
        
        # Option 2: Solo GUI
        self.create_option_card(
            options_frame,
            "🖥️ Solo GUI",
            "Interfaz gráfica - Configuración local",
            "#27ae60",
            self.start_gui
        )
        
        # Option 3: Completo (Recomendado)
        self.create_option_card(
            options_frame,
            "🚀 Completo",
            "API + GUI + Monitoreo - Todas las funciones",
            "#e74c3c",
            self.start_complete,
            recommended=True
        )
        
        # Footer
        footer = tk.Label(self.root, text="v1.0 - Sistema de Etiquetas ZPL", 
                         font=("Segoe UI", 8), 
                         fg='#95a5a6', bg='#f0f0f0')
        footer.pack(side='bottom', pady=10)
    
    def create_option_card(self, parent, title, description, color, command, recommended=False):
        """Crear tarjeta de opción moderna"""
        # Card frame
        card = tk.Frame(parent, bg='white', relief='solid', bd=1, highlightbackground='#e0e0e0')
        card.pack(fill='x', pady=5, ipady=10)
        
        # Card content
        content_frame = tk.Frame(card, bg='white')
        content_frame.pack(fill='both', expand=True, padx=15, pady=10)
        
        # Title with color indicator
        title_frame = tk.Frame(content_frame, bg='white')
        title_frame.pack(fill='x', pady=(0, 8))
        
        color_indicator = tk.Frame(title_frame, bg=color, width=4, height=25)
        color_indicator.pack(side='left', padx=(0, 10))
        
        title_label = tk.Label(title_frame, text=title, 
                              font=("Segoe UI", 12, "bold"), 
                              fg='#2c3e50', bg='white')
        title_label.pack(side='left')
        
        if recommended:
            rec_label = tk.Label(title_frame, text="⭐ RECOMENDADO", 
                               font=("Segoe UI", 8, "bold"), 
                               fg='white', bg='#f39c12', 
                               padx=8, pady=2)
            rec_label.pack(side='right')
        
        # Description
        desc_label = tk.Label(content_frame, text=description, 
                             font=("Segoe UI", 8), 
                             fg='#7f8c8d', bg='white',
                             justify='left', wraplength=400)
        desc_label.pack(anchor='w', pady=(0, 8))
        
        # Button
        btn = tk.Button(content_frame, text="Iniciar", 
                       font=("Segoe UI", 10, "bold"),
                       fg='white', bg=color,
                       relief='flat', bd=0,
                       padx=20, pady=8,
                       cursor='hand2',
                       command=command)
        btn.pack(anchor='e')
        
        # Hover effects
        def on_enter(e):
            card.configure(bg='#f8f9fa')
            content_frame.configure(bg='#f8f9fa')
            title_frame.configure(bg='#f8f9fa')
            title_label.configure(bg='#f8f9fa')
            desc_label.configure(bg='#f8f9fa')
            if recommended:
                rec_label.configure(bg='#f39c12')
        
        def on_leave(e):
            card.configure(bg='white')
            content_frame.configure(bg='white')
            title_frame.configure(bg='white')
            title_label.configure(bg='white')
            desc_label.configure(bg='white')
            if recommended:
                rec_label.configure(bg='#f39c12')
        
        card.bind("<Enter>", on_enter)
        card.bind("<Leave>", on_leave)
        content_frame.bind("<Enter>", on_enter)
        content_frame.bind("<Leave>", on_leave)
    
    def start_api(self):
        """Iniciar solo API"""
        self.show_loading("Iniciando API...")
        
        def run_api():
            try:
                sys.path.insert(0, "src")
                sys.path.insert(0, "api")
                sys.path.insert(0, "config")
                
                try:
                    from fastapi_real import start_fastapi_server
                    start_fastapi_server()
                except Exception as e:
                    print(f"FastAPI falló, usando API original: {e}")
                    from fast_api import start_fast_api
                    start_fast_api()
            except Exception as e:
                self.show_error(f"Error iniciando API: {e}")
        
        threading.Thread(target=run_api, daemon=True).start()
        self.root.after(3000, self.root.withdraw)
    
    def start_gui(self):
        """Iniciar solo GUI"""
        self.show_loading("Iniciando GUI...")
        
        def run_gui():
            try:
                sys.path.insert(0, "src")
                sys.path.insert(0, "api")
                sys.path.insert(0, "config")
                sys.path.insert(0, "gui")
                
                import importlib.util
                spec = importlib.util.spec_from_file_location("main_gui_optimized_fixed", "gui/main_gui_optimized_fixed.py")
                gui_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(gui_module)
                
                app = gui_module.EtiquetadorGUIOptimized()
                app.run()
                
            except Exception as e:
                self.show_error(f"Error iniciando GUI: {e}")
        
        self.root.after(100, self.root.withdraw)
        threading.Thread(target=run_gui, daemon=False).start()
    
    def start_complete(self):
        """Iniciar sistema completo"""
        self.show_loading("Iniciando sistema completo...")
        
        def run_complete():
            try:
                sys.path.insert(0, "src")
                sys.path.insert(0, "api")
                sys.path.insert(0, "config")
                
                # Iniciar API con fallback
                def start_api_with_fallback():
                    try:
                        from fastapi_real import start_fastapi_server
                        start_fastapi_server()
                    except Exception as e:
                        print(f"FastAPI falló, usando API original: {e}")
                        from fast_api import start_fast_api
                        start_fast_api()
                
                api_thread = threading.Thread(target=start_api_with_fallback, daemon=True)
                api_thread.start()
                
                # Esperar un momento
                import time
                time.sleep(2)
                
                # Iniciar GUI
                import importlib.util
                spec = importlib.util.spec_from_file_location("main_gui_optimized_fixed", "gui/main_gui_optimized_fixed.py")
                gui_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(gui_module)
                
                app = gui_module.EtiquetadorGUIOptimized()
                app.run()
                
            except Exception as e:
                self.show_error(f"Error iniciando sistema: {e}")
        
        self.root.after(100, self.root.withdraw)
        threading.Thread(target=run_complete, daemon=False).start()
    
    def show_loading(self, message):
        """Mostrar mensaje de carga"""
        loading = tk.Toplevel(self.root)
        loading.title("Cargando...")
        loading.geometry("300x100")
        loading.resizable(False, False)
        loading.configure(bg='white')
        
        # Centrar ventana de carga
        loading.transient(self.root)
        loading.grab_set()
        
        tk.Label(loading, text=message, 
                font=("Segoe UI", 10), 
                fg='#2c3e50', bg='white').pack(pady=30)
        
        # Auto-cerrar después de 3 segundos
        loading.after(3000, loading.destroy)
    
    def show_error(self, message):
        """Mostrar error en ventana de comando"""
        # Solo mostrar ventana de comando en caso de error
        if hasattr(sys, '_MEIPASS'):
            # En ejecutable, mostrar ventana de error
            import subprocess
            subprocess.run(['cmd', '/c', f'echo {message} && pause'], shell=True)
        else:
            print(f"ERROR: {message}")
            input("Presiona Enter para continuar...")
    
    def run(self):
        """Ejecutar launcher"""
        self.root.mainloop()

if __name__ == "__main__":
    app = ModernLauncher()
    app.run()