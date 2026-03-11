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
import json
import urllib.request

class ModernLauncher:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("EtiquetadorZPL")
        
        # Calcular tamaño adaptativo
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        
        # Tamaño adaptativo: 40% del ancho, 70% del alto (mínimos y máximos)
        width = max(650, min(900, int(screen_width * 0.4)))
        height = max(700, min(1000, int(screen_height * 0.7)))
        
        self.root.geometry(f"{width}x{height}")
        self.root.resizable(True, True)
        self.root.minsize(650, 700)
        self.root.configure(bg='#f0f0f0')
        
        # Centrar ventana
        self.center_window(width, height)
        
        # Cambiar al directorio correcto
        if hasattr(sys, '_MEIPASS'):
            os.chdir(sys._MEIPASS)
        else:
            os.chdir(Path(__file__).parent)
        
        self.create_modern_ui()
    
    def center_window(self, width, height):
        """Centrar ventana en pantalla"""
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f'{width}x{height}+{x}+{y}')
    
    def create_modern_ui(self):
        """Crear interfaz moderna"""
        # Header con gradiente visual
        header_frame = tk.Frame(self.root, bg='#34495e', height=100)
        header_frame.pack(fill='x')
        header_frame.pack_propagate(False)
        
        title = tk.Label(header_frame, text="🏷️ EtiquetadorZPL", 
                        font=("Segoe UI", 24, "bold"), 
                        fg='white', bg='#34495e')
        title.pack(pady=15)
        
        version = tk.Label(header_frame, text="Sistema Profesional de Etiquetas", 
                          font=("Segoe UI", 10), 
                          fg='#bdc3c7', bg='#34495e')
        version.pack()
        
        # Subtitle mejorado
        subtitle = tk.Label(self.root, text="Selecciona el modo de ejecución que mejor se adapte a tus necesidades", 
                           font=("Segoe UI", 12), 
                           fg='#2c3e50', bg='#f0f0f0')
        subtitle.pack(pady=(25, 35))
        
        # Options container con scroll
        canvas = tk.Canvas(self.root, bg='#f0f0f0')
        scrollbar = ttk.Scrollbar(self.root, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg='#f0f0f0')
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Frame principal para las opciones
        main_options_frame = tk.Frame(self.root, bg='#f0f0f0')
        main_options_frame.pack(fill='both', expand=True, padx=50, pady=(0, 20))
        
        # Configurar grid para centrar verticalmente
        main_options_frame.grid_rowconfigure(0, weight=1)
        main_options_frame.grid_rowconfigure(1, weight=0)
        main_options_frame.grid_rowconfigure(2, weight=1)
        main_options_frame.grid_columnconfigure(0, weight=1)
        
        # Frame centrado para las opciones
        options_container = tk.Frame(main_options_frame, bg='#f0f0f0')
        options_container.grid(row=1, column=0, sticky='ew', padx=20)
        
        # Sin scroll - las 3 opciones se muestran siempre
        
        options_frame = options_container
        
        # Option 1: Completo (Recomendado) - PRIMERO
        self.create_option_card(
            options_frame,
            "🚀 Ejecutar Completo",
            "API + GUI + Monitoreo automático - Todas las funciones disponibles",
            "#e74c3c",
            self.start_complete,
            recommended=True
        )
        
        # Option 2: Solo GUI
        self.create_option_card(
            options_frame,
            "🖥️ Solo Interfaz Gráfica",
            "Configuración manual y monitoreo local únicamente",
            "#27ae60",
            self.start_gui
        )
        
        # Option 3: Solo API
        self.create_option_card(
            options_frame,
            "🌐 Solo Servidor API",
            "Servidor web para integración - Dashboard: localhost:8002/web/",
            "#3498db",
            self.start_api
        )
        
        # Footer
        footer = tk.Label(self.root, text="v1.0 - Sistema de Etiquetas ZPL", 
                         font=("Segoe UI", 8), 
                         fg='#95a5a6', bg='#f0f0f0')
        footer.pack(side='bottom', pady=10)
    
    def create_option_card(self, parent, title, description, color, command, recommended=False):
        """Crear tarjeta de opción moderna"""
        # Card frame con padding adaptativo
        card = tk.Frame(parent, bg='white', relief='solid', bd=1, highlightbackground='#e0e0e0')
        card.pack(fill='x', pady=12, ipady=15, padx=10)
        
        # Card content con padding adaptativo
        content_frame = tk.Frame(card, bg='white')
        content_frame.pack(fill='both', expand=True, padx=20, pady=15)
        
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
                               font=("Segoe UI", 9, "bold"), 
                               fg='white', bg='#f39c12', 
                               padx=12, pady=4)
            rec_label.pack(side='right')
        
        # Description con wraplength adaptativo
        desc_label = tk.Label(content_frame, text=description, 
                             font=("Segoe UI", 10), 
                             fg='#7f8c8d', bg='white',
                             justify='left', wraplength=400)
        desc_label.pack(anchor='w', pady=(0, 10))
        
        # Button mejorado
        btn = tk.Button(content_frame, text="▶ Iniciar", 
                       font=("Segoe UI", 12, "bold"),
                       fg='white', bg=color,
                       relief='flat', bd=0,
                       padx=35, pady=12,
                       cursor='hand2',
                       command=command)
        btn.pack(anchor='e', pady=(20, 0))
        
        # Efecto hover para botón
        def btn_enter(e):
            btn.configure(bg=self.darken_color(color))
        def btn_leave(e):
            btn.configure(bg=color)
        btn.bind("<Enter>", btn_enter)
        btn.bind("<Leave>", btn_leave)
        
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
    
    def darken_color(self, color):
        """Oscurecer color para efecto hover"""
        color_map = {
            '#e74c3c': '#c0392b',
            '#27ae60': '#229954', 
            '#3498db': '#2980b9'
        }
        return color_map.get(color, color)

    def _read_api_port(self):
        """Leer puerto API configurado."""
        config_files = ['config/api_port.txt', 'api_port.txt']
        for config_file in config_files:
            try:
                with open(config_file, 'r') as f:
                    port = f.read().strip()
                if port:
                    return port
            except Exception:
                continue
        return "8002"

    def _is_api_running(self, port):
        """Verificar si la API de Etiquetador ya está activa."""
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status", timeout=1.5) as response:
                if response.status != 200:
                    return False
                payload = json.loads(response.read().decode("utf-8", errors="ignore"))
                return payload.get("framework") == "FastAPI"
        except Exception:
            return False

    def _open_administrado(self, port):
        """Abrir panel de Administrado."""
        self.open_url(f"http://localhost:{port}/web/config.html#administrado")
    
    def start_api(self):
        """Iniciar solo API"""
        api_port = self._read_api_port()
        if self._is_api_running(api_port):
            self.show_loading("API ya estaba activa. Abriendo panel web...")
            self.root.after(500, lambda: self._open_administrado(api_port))
            return

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
        self.root.after(4000, lambda: self.show_api_info())
    
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
                api_port = self._read_api_port()
                if not self._is_api_running(api_port):
                    # Iniciar API con fallback
                    def start_api_with_fallback():
                        try:
                            from fastapi_real import start_fastapi_server
                            start_fastapi_server()
                        except Exception as e:
                            print(f"FastAPI fallo, usando API original: {e}")
                            from fast_api import start_fast_api
                            start_fast_api()
                    
                    api_thread = threading.Thread(target=start_api_with_fallback, daemon=True)
                    api_thread.start()
                else:
                    print(f"API ya activa en puerto {api_port}, se reutiliza la instancia existente.")
                
                # Esperar un momento
                import time
                time.sleep(2)
                
                # Mostrar info de API después de un delay
                self.root.after(4000, lambda: self.show_api_info())
                
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
    
    def show_api_info(self):
        """Mostrar información de la API"""
        try:
            # Leer puerto de la API
            api_port = None
            config_files = ['config/api_port.txt', 'api_port.txt']
            
            for config_file in config_files:
                try:
                    with open(config_file, 'r') as f:
                        api_port = f.read().strip()
                    break
                except:
                    continue
            
            if not api_port:
                api_port = "8002"  # Puerto por defecto
            
            # Crear ventana de información
            info_window = tk.Toplevel()
            info_window.title("API Iniciada")
            info_window.geometry("450x250")
            info_window.resizable(False, False)
            info_window.configure(bg='white')
            info_window.attributes('-topmost', True)
            
            # Centrar ventana en pantalla
            info_window.update_idletasks()
            x = (info_window.winfo_screenwidth() // 2) - (450 // 2)
            y = (info_window.winfo_screenheight() // 2) - (250 // 2)
            info_window.geometry(f'450x250+{x}+{y}')
            
            # Contenido
            tk.Label(info_window, text="API Iniciada Correctamente", 
                    font=("Segoe UI", 16, "bold"), 
                    fg='#27ae60', bg='white').pack(pady=20)
            
            tk.Label(info_window, text=f"Puerto: {api_port}", 
                    font=("Segoe UI", 14, "bold"), 
                    fg='#2c3e50', bg='white').pack(pady=8)
            
            tk.Label(info_window, text=f"Dashboard: http://localhost:{api_port}/web/", 
                    font=("Segoe UI", 11), 
                    fg='#3498db', bg='white').pack(pady=5)
            
            tk.Label(info_window, text=f"API Docs: http://localhost:{api_port}/docs", 
                    font=("Segoe UI", 11), 
                    fg='#3498db', bg='white').pack(pady=5)
            
            # Botones
            btn_frame = tk.Frame(info_window, bg='white')
            btn_frame.pack(pady=20)
            
            tk.Button(btn_frame, text="Abrir Dashboard", 
                     font=("Segoe UI", 10, "bold"),
                     fg='white', bg='#3498db',
                     relief='flat', bd=0,
                     padx=20, pady=8,
                     command=lambda: self.open_url(f"http://localhost:{api_port}/web/")).pack(side='left', padx=5)
            
            tk.Button(btn_frame, text="Cerrar", 
                     font=("Segoe UI", 10, "bold"),
                     fg='white', bg='#95a5a6',
                     relief='flat', bd=0,
                     padx=20, pady=8,
                     command=info_window.destroy).pack(side='left', padx=5)
            
            # No ocultar la ventana principal si es modo completo
            
        except Exception as e:
            print(f"Error mostrando info API: {e}")
    
    def open_url(self, url):
        """Abrir URL en navegador"""
        import webbrowser
        webbrowser.open(url)
    
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
    try:
        app = ModernLauncher()
        app.run()
    except KeyboardInterrupt:
        print("\nAplicación cerrada por el usuario.")
    except Exception as e:
        print(f"Error: {e}")
        input("Presiona Enter para salir...")
