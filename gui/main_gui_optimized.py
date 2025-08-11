import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import sys
import os
import logging
from pathlib import Path
from watchdog.observers import Observer

# Importar optimizador de rendimiento
from performance_optimizer import (
    PerformanceOptimizer, AsyncTaskManager, UICache, 
    optimize_tkinter_performance, create_optimized_scrolledtext,
    optimize_combobox_loading, ProgressiveLoader
)

# Importar sistemas mejorados
from logger_manager import log_manager, logger
from validacion_avanzada import validador
from network_config import network_config
from permissions import permission_manager

# Importar tema moderno
try:
    import sv_ttk
    TEMA_MODERNO = True
except ImportError:
    TEMA_MODERNO = False

from config import cargar_configuracion
from handlers import PDFHandler
from validacion import validar_configuracion, validar_impresora
from printer_utils import obtener_impresoras, obtener_impresora_predeterminada

class EtiquetadorGUIOptimized:
    def __init__(self):
        # Crear ventana principal optimizada
        self.root = tk.Tk()
        optimize_tkinter_performance(self.root)
        
        self.root.title("Generador Automático de Etiquetas ZPL")
        self.root.geometry("800x600")
        self.root.resizable(True, True)
        
        # Inicializar optimizadores
        self.performance_optimizer = PerformanceOptimizer(self.root)
        self.task_manager = AsyncTaskManager(self.root)
        self.ui_cache = UICache()
        self.progressive_loader = ProgressiveLoader(self.root)
        
        # Variables
        self.observer = None
        self.handler = None
        self.config = None
        self.monitoring = False
        self.carpetas_config = []
        
        # Configurar logging mejorado
        log_manager.add_gui_handler(self.update_log)
        logger.info("=== Aplicación iniciada ===")
        
        # Mostrar splash screen mientras carga
        self.show_loading_screen()
        
        # Configurar pasos de carga progresiva
        self.setup_progressive_loading()
        
        # Iniciar carga
        self.progressive_loader.start_loading(self.update_loading_progress)
        
    def show_loading_screen(self):
        """Muestra pantalla de carga inicial"""
        self.loading_frame = ttk.Frame(self.root)
        self.loading_frame.pack(fill=tk.BOTH, expand=True)
        
        # Logo/Título
        title_label = ttk.Label(self.loading_frame, 
                               text="🏷️ Generador de Etiquetas ZPL", 
                               font=("Arial", 20, "bold"))
        title_label.pack(pady=50)
        
        # Barra de progreso
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(self.loading_frame, 
                                          variable=self.progress_var, 
                                          maximum=100)
        self.progress_bar.pack(pady=20, padx=50, fill=tk.X)
        
        # Texto de estado
        self.status_var = tk.StringVar(value="Iniciando...")
        self.status_label = ttk.Label(self.loading_frame, textvariable=self.status_var)
        self.status_label.pack(pady=10)
        
    def setup_progressive_loading(self):
        """Configura los pasos de carga progresiva"""
        self.progressive_loader.add_step(self.apply_theme, "Aplicando tema...")
        self.progressive_loader.add_step(self.create_basic_widgets, "Creando interfaz...")
        self.progressive_loader.add_step(self.load_config_async, "Cargando configuración...")
        self.progressive_loader.add_step(self.load_printers_async, "Detectando impresoras...")
        self.progressive_loader.add_step(self.finalize_ui, "Finalizando...")
        
    def update_loading_progress(self, progress, description):
        """Actualiza la barra de progreso"""
        self.progress_var.set(progress)
        self.status_var.set(description)
        self.root.update_idletasks()
        
        if progress >= 100:
            # Ocultar pantalla de carga
            self.loading_frame.destroy()
            
    def apply_theme(self):
        """Aplica tema moderno si está disponible"""
        if TEMA_MODERNO:
            try:
                sv_ttk.set_theme("light")
                logging.info("Tema moderno aplicado")
            except Exception as e:
                logging.warning(f"Error al aplicar tema: {e}")
        else:
            self.root.configure(bg='white')
            
    def create_basic_widgets(self):
        """Crea la estructura básica de widgets (sin datos)"""
        # Frame principal
        self.main_frame = ttk.Frame(self.root, padding="10")
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Configurar grid
        self.main_frame.columnconfigure(1, weight=1)
        self.main_frame.rowconfigure(4, weight=1)
        
        # Título
        title_label = ttk.Label(self.main_frame, 
                               text="🏷️ Generador de Etiquetas ZPL", 
                               font=("Arial", 16, "bold"))
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 20))
        
        # Frame de configuración
        self.create_config_frame()
        
        # Botones de control
        self.create_control_buttons()
        
        # Frame de estado
        self.create_status_frame()
        
        # Frame de log (optimizado)
        self.create_log_frame()
        
    def create_config_frame(self):
        """Crea el frame de configuración de carpetas"""
        config_frame = ttk.LabelFrame(self.main_frame, text="Configuración de Carpetas", padding="10")
        config_frame.grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))
        config_frame.columnconfigure(0, weight=1)
        
        # Notebook para las 3 carpetas
        self.notebook = ttk.Notebook(config_frame)
        self.notebook.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        
        # Crear tabs de carpetas (sin datos inicialmente)
        for i in range(3):
            self.create_folder_tab(i)
            
        # Botón para actualizar impresoras
        self.update_printers_btn = ttk.Button(config_frame, text="🔄 Actualizar Impresoras", 
                                            command=self.update_printers_async)
        self.update_printers_btn.grid(row=1, column=0, pady=5)
        
    def create_folder_tab(self, index):
        """Crea un tab de configuración de carpeta"""
        carpeta_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(carpeta_frame, text=f"Carpeta {index+1}")
        carpeta_frame.columnconfigure(1, weight=1)
        
        # Variables para esta carpeta
        carpeta_vars = {
            'ruta': tk.StringVar(),
            'impresora': tk.StringVar(),
            'historial': tk.StringVar(),
            'activa': tk.BooleanVar(value=False),  # Inactiva por defecto
            'recortar_pdf': tk.BooleanVar(value=True),
            'copias': tk.StringVar(value='1')
        }
        self.carpetas_config.append(carpeta_vars)
        
        # Widgets de la carpeta
        row = 0
        
        # Checkbox activa
        ttk.Checkbutton(carpeta_frame, text="Activa", 
                       variable=carpeta_vars['activa']).grid(row=row, column=0, sticky=tk.W, pady=2)
        
        # Checkbox recortar PDF
        ttk.Checkbutton(carpeta_frame, text="Recortar PDF automáticamente", 
                       variable=carpeta_vars['recortar_pdf']).grid(row=row, column=1, columnspan=2, sticky=tk.W, pady=2)
        row += 1
        
        # Carpeta de entrada
        ttk.Label(carpeta_frame, text="Carpeta:").grid(row=row, column=0, sticky=tk.W, pady=2)
        ttk.Entry(carpeta_frame, textvariable=carpeta_vars['ruta'], width=40).grid(row=row, column=1, sticky=(tk.W, tk.E), padx=(5, 5))
        ttk.Button(carpeta_frame, text="Buscar", 
                  command=lambda idx=index: self.browse_carpeta(idx)).grid(row=row, column=2, padx=(5, 0))
        row += 1
        
        # Impresora (combobox optimizado)
        ttk.Label(carpeta_frame, text="Impresora:").grid(row=row, column=0, sticky=tk.W, pady=2)
        combo = ttk.Combobox(carpeta_frame, textvariable=carpeta_vars['impresora'], width=37, state='disabled')
        combo.grid(row=row, column=1, sticky=(tk.W, tk.E), padx=(5, 5), pady=2)
        carpeta_vars['combo'] = combo
        row += 1
        
        # Carpeta historial
        ttk.Label(carpeta_frame, text="Historial:").grid(row=row, column=0, sticky=tk.W, pady=2)
        ttk.Entry(carpeta_frame, textvariable=carpeta_vars['historial'], width=40).grid(row=row, column=1, sticky=(tk.W, tk.E), padx=(5, 5))
        ttk.Button(carpeta_frame, text="Buscar", 
                  command=lambda idx=index: self.browse_historial(idx)).grid(row=row, column=2, padx=(5, 0))
        row += 1
        
        # Cantidad de copias
        ttk.Label(carpeta_frame, text="Copias:").grid(row=row, column=0, sticky=tk.W, pady=2)
        copias_entry = ttk.Entry(carpeta_frame, textvariable=carpeta_vars['copias'], width=10)
        copias_entry.grid(row=row, column=1, sticky=tk.W, padx=(5, 5))
        ttk.Label(carpeta_frame, text="(1-10)", font=("Arial", 8)).grid(row=row, column=2, sticky=tk.W)
        
    def create_control_buttons(self):
        """Crea los botones de control"""
        control_frame = ttk.Frame(self.main_frame)
        control_frame.grid(row=2, column=0, columnspan=3, pady=10)
        
        self.start_button = ttk.Button(control_frame, text="▶️ Iniciar Monitoreo", 
                                      command=self.start_monitoring_async)
        self.start_button.pack(side=tk.LEFT, padx=5)
        
        self.stop_button = ttk.Button(control_frame, text="⏹️ Detener", 
                                     command=self.stop_monitoring, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(control_frame, text="💾 Guardar Config", 
                  command=self.save_config_async).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(control_frame, text="🔄 Recargar", 
                  command=self.load_config_async).pack(side=tk.LEFT, padx=5)
        
    def create_status_frame(self):
        """Crea el frame de estado"""
        status_frame = ttk.LabelFrame(self.main_frame, text="Estado", padding="10")
        status_frame.grid(row=3, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))
        
        self.status_var = tk.StringVar(value="⏸️ Detenido")
        self.status_label = ttk.Label(status_frame, textvariable=self.status_var, 
                                     font=("Arial", 10, "bold"))
        self.status_label.pack()
        
    def create_log_frame(self):
        """Crea el frame de log optimizado"""
        log_frame = ttk.LabelFrame(self.main_frame, text="Registro de Actividad", padding="10")
        log_frame.grid(row=4, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        
        # ScrolledText optimizado
        self.log_text = create_optimized_scrolledtext(log_frame, height=15, width=80)
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Botones de log
        log_buttons_frame = ttk.Frame(log_frame)
        log_buttons_frame.grid(row=1, column=0, pady=(5, 0))
        
        ttk.Button(log_buttons_frame, text="🗑️ Limpiar", 
                  command=self.clear_log).pack(side=tk.LEFT, padx=5)
        ttk.Button(log_buttons_frame, text="💾 Exportar Logs", 
                  command=self.export_logs_async).pack(side=tk.LEFT, padx=5)
        ttk.Button(log_buttons_frame, text="⚙️ Config Red", 
                  command=self.show_network_config).pack(side=tk.LEFT, padx=5)
        
    def load_config_async(self):
        """Carga la configuración de forma asíncrona"""
        def load_task():
            return cargar_configuracion()
            
        def on_config_loaded(config):
            self.config = config
            if config:
                self.apply_config_to_ui(config)
                self.log_message("✅ Configuración cargada")
            else:
                self.log_message("⚠️ No se pudo cargar la configuración")
                
        def on_error(error):
            self.log_message(f"❌ Error al cargar configuración: {error}")
            
        self.task_manager.add_task(load_task, on_config_loaded, on_error)
        
    def apply_config_to_ui(self, config):
        """Aplica la configuración cargada a la UI"""
        carpetas = config.get("carpetas", [])
        
        for i in range(min(3, len(carpetas))):
            carpeta = carpetas[i]
            self.carpetas_config[i]['ruta'].set(carpeta.get('ruta', ''))
            self.carpetas_config[i]['impresora'].set(carpeta.get('impresora', ''))
            self.carpetas_config[i]['historial'].set(carpeta.get('historial', ''))
            self.carpetas_config[i]['activa'].set(carpeta.get('activa', True))
            self.carpetas_config[i]['recortar_pdf'].set(carpeta.get('recortar_pdf', True))
            self.carpetas_config[i]['copias'].set(str(carpeta.get('copias', 1)))
            
    def load_printers_async(self):
        """Carga las impresoras de forma asíncrona"""
        def load_printers():
            return obtener_impresoras()
            
        def on_printers_loaded(printers):
            self.update_printer_combos(printers)
            
        def on_error(error):
            self.log_message(f"❌ Error al cargar impresoras: {error}")
            
        self.task_manager.add_task(load_printers, on_printers_loaded, on_error)
        
    def update_printer_combos(self, printers):
        """Actualiza los combobox de impresoras"""
        default_printer = obtener_impresora_predeterminada()
        
        for carpeta_vars in self.carpetas_config:
            combo = carpeta_vars['combo']
            combo.configure(state='normal')
            combo['values'] = printers
            
            # Seleccionar impresora predeterminada si no hay ninguna
            if printers and not carpeta_vars['impresora'].get():
                if default_printer and default_printer in printers:
                    carpeta_vars['impresora'].set(default_printer)
                else:
                    carpeta_vars['impresora'].set(printers[0])
                    
    def update_printers_async(self):
        """Actualiza impresoras de forma asíncrona"""
        self.update_printers_btn.configure(state='disabled', text="Actualizando...")
        
        def load_task():
            return obtener_impresoras()
            
        def on_success(printers):
            self.update_printer_combos(printers)
            self.log_message(f"✅ {len(printers)} impresoras encontradas")
            self.update_printers_btn.configure(state='normal', text="🔄 Actualizar Impresoras")
            
        def on_error(error):
            self.log_message(f"❌ Error al actualizar impresoras: {error}")
            self.update_printers_btn.configure(state='normal', text="🔄 Actualizar Impresoras")
            
        self.task_manager.add_task(load_task, on_success, on_error)
        
    def finalize_ui(self):
        """Finaliza la configuración de la UI"""
        # Configurar eventos de cierre
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Aplicar optimizaciones finales
        self.root.update_idletasks()
        
    # Métodos de navegación de archivos (sin cambios)
    def browse_carpeta(self, idx):
        folder = filedialog.askdirectory(title=f"Seleccionar carpeta {idx+1}")
        if folder:
            self.carpetas_config[idx]['ruta'].set(folder)
            if not self.carpetas_config[idx]['historial'].get():
                historial = folder + "/historial"
                self.carpetas_config[idx]['historial'].set(historial)
                
    def browse_historial(self, idx):
        folder = filedialog.askdirectory(title=f"Seleccionar carpeta de historial {idx+1}")
        if folder:
            self.carpetas_config[idx]['historial'].set(folder)
            
    # Métodos de monitoreo (optimizados)
    def start_monitoring_async(self):
        """Inicia el monitoreo de forma asíncrona"""
        if self.monitoring:
            return
            
        def start_task():
            # Validación y preparación
            carpetas_activas = self.prepare_monitoring_folders()
            if not carpetas_activas:
                raise Exception("No hay carpetas válidas para monitorear")
            return carpetas_activas
            
        def on_success(carpetas_activas):
            self.carpetas_monitoreadas = carpetas_activas
            threading.Thread(target=self._start_monitoring_thread, daemon=True).start()
            
        def on_error(error):
            messagebox.showerror("Error", str(error))
            
        self.task_manager.add_task(start_task, on_success, on_error)
        
    def prepare_monitoring_folders(self):
        """Prepara las carpetas para monitoreo"""
        carpetas_activas = []
        
        for i, carpeta_vars in enumerate(self.carpetas_config):
            if not carpeta_vars['activa'].get():
                continue
                
            ruta = carpeta_vars['ruta'].get().strip()
            impresora = carpeta_vars['impresora'].get().strip()
            
            if not ruta or not impresora:
                raise Exception(f"Carpeta {i+1} incompleta")
                
            if not Path(ruta).exists():
                raise Exception(f"Carpeta {i+1} no existe: {ruta}")
                
            historial_path = carpeta_vars['historial'].get() or ruta + "/historial"
            os.makedirs(ruta, exist_ok=True)
            os.makedirs(historial_path, exist_ok=True)
            
            try:
                copias = int(carpeta_vars['copias'].get() or 1)
                copias = max(1, min(10, copias))
            except ValueError:
                copias = 1
                
            carpetas_activas.append({
                'entrada': ruta,
                'impresora': impresora,
                'historial': historial_path,
                'ancho_mm': 100,
                'alto_mm': 150,
                'poppler': self.config.get('poppler', '') if self.config else '',
                'recortar_pdf': carpeta_vars['recortar_pdf'].get(),
                'copias': copias
            })
            
        return carpetas_activas
        
    def _start_monitoring_thread(self):
        """Hilo de monitoreo optimizado"""
        try:
            self.handlers = []
            self.observers = []
            
            for i, carpeta_config in enumerate(self.carpetas_monitoreadas):
                handler = PDFHandler(carpeta_config, observer=None, root=self.root)
                handler.carpeta_numero = i + 1
                handler.gui_instance = self
                
                observer = Observer()
                observer.schedule(handler, path=carpeta_config["entrada"], recursive=False)
                handler.observer = observer
                
                self.handlers.append(handler)
                self.observers.append(observer)
                observer.start()
                
                self.log_message(f"📁 Monitoreando: {carpeta_config['entrada']} -> {carpeta_config['impresora']}")
            
            self.monitoring = True
            self.root.after(0, self._update_ui_monitoring_started)
            
            while self.monitoring and any(obs.is_alive() for obs in self.observers):
                threading.Event().wait(1)
                
        except Exception as e:
            self.log_message(f"❌ Error en monitoreo: {e}")
            self.root.after(0, self._update_ui_monitoring_stopped)
            
    def _update_ui_monitoring_started(self):
        """Actualiza UI cuando inicia el monitoreo"""
        carpetas_count = len(self.carpetas_monitoreadas)
        self.status_var.set(f"▶️ Monitoreando {carpetas_count} carpeta(s)")
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        
    def _update_ui_monitoring_stopped(self):
        """Actualiza UI cuando se detiene el monitoreo"""
        self.status_var.set("⏹️ Detenido")
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        
    def stop_monitoring(self):
        """Detiene el monitoreo"""
        if not self.monitoring:
            return
            
        self.monitoring = False
        
        if hasattr(self, 'observers'):
            for observer in self.observers:
                try:
                    observer.stop()
                    observer.join(timeout=5)
                except Exception as e:
                    logging.error(f"Error deteniendo observer: {e}")
                    
        if hasattr(self, 'handlers'):
            for handler in self.handlers:
                try:
                    if hasattr(handler, 'shutdown'):
                        handler.shutdown()
                except Exception as e:
                    logging.error(f"Error deteniendo handler: {e}")
                    
        self._update_ui_monitoring_stopped()
        self.log_message("⏹️ Monitoreo detenido")
        
    # Métodos de logging optimizados
    def update_log(self, message, level="INFO"):
        """Callback optimizado para logging"""
        if hasattr(self, 'log_text'):
            self._append_log(message, level)
        
    def _append_log(self, message, level="INFO"):
        """Agrega mensaje al log de forma optimizada"""
        if not hasattr(self, 'log_text') or not self.log_text:
            return
            
        try:
            # Usar tags preconfigurados
            tag = level
            
            self.log_text.insert(tk.END, f"{message}\n", tag)
            self.log_text.see(tk.END)
            
            # Limitar líneas para mejor rendimiento
            lines = int(self.log_text.index('end-1c').split('.')[0])
            if lines > 1000:
                self.log_text.delete('1.0', '100.0')
        except Exception as e:
            print(f"Error en log: {e}")
            
    def log_message(self, message, level="INFO"):
        """Método público para logging"""
        logger.info(message)
        if hasattr(self, 'log_text'):
            self.update_log(message, level)
        else:
            print(f"[{level}] {message}")
        
    def clear_log(self):
        """Limpia el log"""
        self.log_text.delete(1.0, tk.END)
        
    # Métodos asíncronos adicionales
    def save_config_async(self):
        """Guarda configuración de forma asíncrona"""
        def save_task():
            from guardar_config_multiple import guardar_configuracion_multiple
            
            carpetas = []
            for carpeta_vars in self.carpetas_config:
                ruta = carpeta_vars['ruta'].get().strip()
                if ruta:
                    try:
                        copias = int(carpeta_vars['copias'].get() or 1)
                        copias = max(1, min(10, copias))
                    except ValueError:
                        copias = 1
                        
                    carpetas.append({
                        'ruta': ruta,
                        'impresora': carpeta_vars['impresora'].get(),
                        'historial': carpeta_vars['historial'].get(),
                        'activa': carpeta_vars['activa'].get(),
                        'recortar_pdf': carpeta_vars['recortar_pdf'].get(),
                        'copias': copias
                    })
                    
            if not carpetas:
                raise Exception("Debe configurar al menos una carpeta")
                
            guardar_configuracion_multiple(carpetas)
            return True
            
        def on_success(result):
            self.log_message("💾 Configuración guardada")
            messagebox.showinfo("Éxito", "Configuración guardada correctamente")
            
        def on_error(error):
            self.log_message(f"❌ Error al guardar: {error}")
            messagebox.showerror("Error", f"No se pudo guardar: {error}")
            
        self.task_manager.add_task(save_task, on_success, on_error)
        
    def export_logs_async(self):
        """Exporta logs de forma asíncrona"""
        def export_task():
            return log_manager.export_logs()
            
        def on_success(archivo):
            messagebox.showinfo("Éxito", f"Logs exportados a: {archivo}")
            
        def on_error(error):
            messagebox.showerror("Error", f"No se pudieron exportar los logs: {error}")
            
        self.task_manager.add_task(export_task, on_success, on_error)
        
    def show_network_config(self):
        """Mostrar configuración de red"""
        try:
            from network_config_gui import NetworkConfigGUI
            NetworkConfigGUI(self.root)
        except Exception as e:
            self.log_message(f"Error abriendo config de red: {e}")
            
    def on_closing(self):
        """Maneja el cierre optimizado de la aplicación"""
        try:
            if self.monitoring:
                if messagebox.askokcancel("Salir", "¿Detener el monitoreo y salir?"):
                    self.stop_monitoring()
                    self.root.destroy()
            else:
                self.root.destroy()
        except Exception as e:
            logging.error(f"Error al cerrar: {e}")
            self.root.destroy()
            
    def run(self):
        """Ejecuta la aplicación optimizada"""
        self.root.mainloop()

if __name__ == "__main__":
    app = EtiquetadorGUIOptimized()
    app.run()