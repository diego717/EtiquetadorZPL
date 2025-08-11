import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import sys
import os
import logging
from pathlib import Path
from watchdog.observers import Observer

# Agregar paths para imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root / "config"))

# Importar módulos del proyecto usando imports absolutos
import importlib.util

# Cargar config
spec = importlib.util.spec_from_file_location("config", project_root / "config.py")
config_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(config_module)
cargar_configuracion = config_module.cargar_configuracion

# Cargar handlers
spec = importlib.util.spec_from_file_location("handlers", project_root / "src" / "handlers.py")
handlers_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(handlers_module)
PDFHandler = handlers_module.PDFHandler

# Cargar validacion
spec = importlib.util.spec_from_file_location("validacion", project_root / "src" / "validacion.py")
validacion_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validacion_module)
validar_configuracion = validacion_module.validar_configuracion
validar_impresora = validacion_module.validar_impresora

# Cargar printer_utils
spec = importlib.util.spec_from_file_location("printer_utils", project_root / "src" / "printer_utils.py")
printer_utils_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(printer_utils_module)
obtener_impresoras = printer_utils_module.obtener_impresoras
obtener_impresora_predeterminada = printer_utils_module.obtener_impresora_predeterminada

class EtiquetadorGUIOptimized:
    def __init__(self):
        # Crear ventana principal
        self.root = tk.Tk()
        self.root.title("Generador Automático de Etiquetas ZPL")
        self.root.geometry("800x600")
        self.root.resizable(True, True)
        
        # Variables
        self.observer = None
        self.handler = None
        self.config = None
        self.monitoring = False
        self.carpetas_config = []
        
        # Crear interfaz
        self.create_widgets()
        
        # Cargar configuración inicial
        self.load_config()
        self.load_printers()
        
    def create_widgets(self):
        """Crea la interfaz de usuario"""
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
        
        # Frame de log
        self.create_log_frame()
        
    def create_config_frame(self):
        """Crea el frame de configuración de carpetas"""
        config_frame = ttk.LabelFrame(self.main_frame, text="Configuración de Carpetas", padding="10")
        config_frame.grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))
        config_frame.columnconfigure(0, weight=1)
        
        # Notebook para las 3 carpetas
        self.notebook = ttk.Notebook(config_frame)
        self.notebook.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        
        # Crear tabs de carpetas
        for i in range(3):
            self.create_folder_tab(i)
            
        # Botón para actualizar impresoras
        self.update_printers_btn = ttk.Button(config_frame, text="🔄 Actualizar Impresoras", 
                                            command=self.load_printers)
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
            'activa': tk.BooleanVar(value=False),
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
        entry_ruta = ttk.Entry(carpeta_frame, textvariable=carpeta_vars['ruta'], width=40)
        entry_ruta.grid(row=row, column=1, sticky=(tk.W, tk.E), padx=(5, 5))
        carpeta_vars['entry_ruta'] = entry_ruta  # Guardar referencia
        ttk.Button(carpeta_frame, text="Buscar", 
                  command=lambda idx=index: self.browse_carpeta(idx)).grid(row=row, column=2, padx=(5, 0))
        row += 1
        
        # Impresora
        ttk.Label(carpeta_frame, text="Impresora:").grid(row=row, column=0, sticky=tk.W, pady=2)
        combo = ttk.Combobox(carpeta_frame, textvariable=carpeta_vars['impresora'], width=37, state='readonly')
        combo.grid(row=row, column=1, sticky=(tk.W, tk.E), padx=(5, 5), pady=2)
        carpeta_vars['combo'] = combo
        row += 1
        
        # Carpeta historial
        ttk.Label(carpeta_frame, text="Historial:").grid(row=row, column=0, sticky=tk.W, pady=2)
        entry_historial = ttk.Entry(carpeta_frame, textvariable=carpeta_vars['historial'], width=40)
        entry_historial.grid(row=row, column=1, sticky=(tk.W, tk.E), padx=(5, 5))
        carpeta_vars['entry_historial'] = entry_historial  # Guardar referencia
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
                                      command=self.start_monitoring)
        self.start_button.pack(side=tk.LEFT, padx=5)
        
        self.stop_button = ttk.Button(control_frame, text="⏹️ Detener", 
                                     command=self.stop_monitoring, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(control_frame, text="💾 Guardar Config", 
                  command=self.save_config).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(control_frame, text="🔄 Recargar", 
                  command=self.load_config).pack(side=tk.LEFT, padx=5)
        
    def create_status_frame(self):
        """Crea el frame de estado"""
        status_frame = ttk.LabelFrame(self.main_frame, text="Estado", padding="10")
        status_frame.grid(row=3, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))
        
        self.status_var = tk.StringVar(value="⏸️ Detenido")
        self.status_label = ttk.Label(status_frame, textvariable=self.status_var, 
                                     font=("Arial", 10, "bold"))
        self.status_label.pack()
        
    def create_log_frame(self):
        """Crea el frame de log"""
        log_frame = ttk.LabelFrame(self.main_frame, text="Registro de Actividad", padding="10")
        log_frame.grid(row=4, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        
        # ScrolledText
        self.log_text = scrolledtext.ScrolledText(log_frame, height=15, width=80)
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Botones de log
        log_buttons_frame = ttk.Frame(log_frame)
        log_buttons_frame.grid(row=1, column=0, pady=(5, 0))
        
        ttk.Button(log_buttons_frame, text="🗑️ Limpiar", 
                  command=self.clear_log).pack(side=tk.LEFT, padx=5)
        
    def load_config(self):
        """Carga la configuración"""
        try:
            # LIMPIAR configuración actual primero
            self.clear_all_config()
            
            # Buscar config.ini en diferentes ubicaciones
            config_paths = [
                'config/config.ini',
                'config.ini',
                str(project_root / 'config' / 'config.ini'),
                str(project_root / 'config.ini')
            ]
            
            config_file = None
            for path in config_paths:
                if Path(path).exists():
                    config_file = path
                    break
            
            if config_file:
                self.config = cargar_configuracion(config_file)
                if self.config:
                    self.apply_config_to_ui(self.config)
                    self.log_message(f"Configuración cargada desde: {config_file}")
                else:
                    self.log_message("No se pudo cargar la configuración")
            else:
                self.log_message("Archivo config.ini no encontrado")
                
        except Exception as e:
            self.log_message(f"Error al cargar configuración: {e}")
    
    def clear_all_config(self):
        """Limpiar toda la configuración"""
        for i in range(3):
            # Limpiar StringVar
            self.carpetas_config[i]['ruta'].set('')
            self.carpetas_config[i]['impresora'].set('')
            self.carpetas_config[i]['historial'].set('')
            self.carpetas_config[i]['activa'].set(False)
            self.carpetas_config[i]['recortar_pdf'].set(True)
            self.carpetas_config[i]['copias'].set('1')
            
            # FORZAR limpieza de Entry widgets
            if 'entry_ruta' in self.carpetas_config[i]:
                self.carpetas_config[i]['entry_ruta'].delete(0, tk.END)
            if 'entry_historial' in self.carpetas_config[i]:
                self.carpetas_config[i]['entry_historial'].delete(0, tk.END)
            if 'combo' in self.carpetas_config[i]:
                combo = self.carpetas_config[i]['combo']
                combo.set('')  # Limpiar selección
                combo['values'] = []  # Limpiar lista
        
        self.log_message("Configuración limpiada")
    
    def create_default_config(self):
        """Crear configuración por defecto"""
        try:
            import configparser
            config = configparser.ConfigParser()
            
            # Configuración básica
            config['etiqueta'] = {
                'ancho_mm': '100',
                'alto_mm': '150'
            }
            
            config['impresora'] = {
                'nombre': 'Impresora_Predeterminada'
            }
            
            config['rutas'] = {
                'entrada': 'C:/EtiquetasFlex/Entrada1',
                'salida': 'C:/EtiquetasFlex/Salida1',
                'historial': 'C:/EtiquetasFlex/Historial1',
                'poppler_path': 'poppler/poppler-23.08.0/Library/bin'
            }
            
            # Crear directorio config en ubicación escribible
            try:
                config_dir = Path('config')
                config_dir.mkdir(exist_ok=True)
                config_path = config_dir / 'config.ini'
                
                # Probar si se puede escribir
                test_file = config_dir / 'test.tmp'
                test_file.write_text('test')
                test_file.unlink()
                
            except (PermissionError, OSError):
                import os
                appdata = Path(os.environ.get('APPDATA', '.'))
                config_dir = appdata / 'EtiquetadorZPL'
                config_dir.mkdir(exist_ok=True)
                config_path = config_dir / 'config.ini'
            with open(config_path, 'w') as f:
                config.write(f)
            
            self.log_message(f"Configuración por defecto creada: {config_path}")
            
            # Cargar la configuración recién creada
            self.config = cargar_configuracion(str(config_path))
            if self.config:
                self.apply_config_to_ui(self.config)
                
        except Exception as e:
            self.log_message(f"Error creando configuración por defecto: {e}")
            
    def apply_config_to_ui(self, config):
        """Aplica la configuración cargada a la UI"""
        try:
            # Limpiar configuración actual primero
            for i in range(3):
                self.carpetas_config[i]['ruta'].set('')
                self.carpetas_config[i]['impresora'].set('')
                self.carpetas_config[i]['historial'].set('')
                self.carpetas_config[i]['activa'].set(False)
                self.carpetas_config[i]['recortar_pdf'].set(True)
                self.carpetas_config[i]['copias'].set('1')
            
            # Aplicar nueva configuración
            if hasattr(config, 'sections'):  # ConfigParser object
                for i in range(3):
                    section = f"CARPETA{i+1}"
                    if config.has_section(section):
                        self.carpetas_config[i]['ruta'].set(config.get(section, 'entrada', fallback=''))
                        # NO cargar impresora desde config - usar impresoras actuales
                        self.carpetas_config[i]['historial'].set(config.get(section, 'historial', fallback=''))
                        self.carpetas_config[i]['activa'].set(config.getboolean(section, 'activa', fallback=False))
                        self.carpetas_config[i]['recortar_pdf'].set(config.getboolean(section, 'recortar_pdf', fallback=True))
                        self.carpetas_config[i]['copias'].set(config.get(section, 'copias', fallback='1'))
                        
                        # FORZAR actualización de Entry widgets
                        if 'entry_ruta' in self.carpetas_config[i]:
                            entry = self.carpetas_config[i]['entry_ruta']
                            entry.delete(0, tk.END)
                            entry.insert(0, config.get(section, 'entrada', fallback=''))
                        
                        if 'entry_historial' in self.carpetas_config[i]:
                            entry = self.carpetas_config[i]['entry_historial']
                            entry.delete(0, tk.END)
                            entry.insert(0, config.get(section, 'historial', fallback=''))
                        
                        self.log_message(f"Configuración aplicada - Carpeta {i+1}: {config.get(section, 'entrada', fallback='N/A')}")
            else:
                # Formato dict (legacy)
                carpetas = config.get("carpetas", [])
                for i in range(min(3, len(carpetas))):
                    carpeta = carpetas[i]
                    self.carpetas_config[i]['ruta'].set(carpeta.get('ruta', ''))
                    # NO cargar impresora desde config - usar impresoras actuales
                    self.carpetas_config[i]['historial'].set(carpeta.get('historial', ''))
                    self.carpetas_config[i]['activa'].set(carpeta.get('activa', False))
                    self.carpetas_config[i]['recortar_pdf'].set(carpeta.get('recortar_pdf', True))
                    self.carpetas_config[i]['copias'].set(str(carpeta.get('copias', 1)))
                    
                    # FORZAR actualización de Entry widgets
                    if 'entry_ruta' in self.carpetas_config[i]:
                        entry = self.carpetas_config[i]['entry_ruta']
                        entry.delete(0, tk.END)
                        entry.insert(0, carpeta.get('ruta', ''))
                    
                    if 'entry_historial' in self.carpetas_config[i]:
                        entry = self.carpetas_config[i]['entry_historial']
                        entry.delete(0, tk.END)
                        entry.insert(0, carpeta.get('historial', ''))
            
            # Forzar actualización de UI
            self.root.update()
            
        except Exception as e:
            self.log_message(f"Error aplicando configuración: {e}")
            
    def load_printers(self):
        """Carga las impresoras"""
        try:
            # FORZAR recarga de impresoras
            printers = obtener_impresoras()
            self.log_message(f"Impresoras detectadas: {printers}")
            self.update_printer_combos(printers)
            self.log_message(f"✅ {len(printers)} impresoras encontradas")
        except Exception as e:
            self.log_message(f"❌ Error al cargar impresoras: {e}")
            
    def update_printer_combos(self, printers):
        """Actualiza los combobox de impresoras"""
        default_printer = obtener_impresora_predeterminada()
        self.log_message(f"Impresora predeterminada: {default_printer}")
        
        for i, carpeta_vars in enumerate(self.carpetas_config):
            combo = carpeta_vars['combo']
            
            # LIMPIAR completamente el combo
            combo.set('')
            combo['values'] = []
            carpeta_vars['impresora'].set('')
            
            # Establecer nuevas impresoras
            combo['values'] = printers
            
            # Solo seleccionar impresora predeterminada si hay impresoras
            if printers:
                if default_printer and default_printer in printers:
                    carpeta_vars['impresora'].set(default_printer)
                    combo.set(default_printer)
                else:
                    carpeta_vars['impresora'].set(printers[0])
                    combo.set(printers[0])
                
                self.log_message(f"Carpeta {i+1} - Impresora asignada: {carpeta_vars['impresora'].get()}")
            else:
                self.log_message(f"Carpeta {i+1} - Sin impresoras disponibles")
                    
    def browse_carpeta(self, idx):
        """Buscar carpeta de entrada"""
        try:
            folder = filedialog.askdirectory(title=f"Seleccionar carpeta de monitoreo {idx+1}")
            if folder:
                # Normalizar la ruta
                folder = str(Path(folder).resolve()).replace('\\', '/')
                
                # Actualizar StringVar
                self.carpetas_config[idx]['ruta'].set(folder)
                
                # FORZAR actualización directa del Entry
                entry_widget = self.carpetas_config[idx]['entry_ruta']
                entry_widget.delete(0, tk.END)
                entry_widget.insert(0, folder)
                
                # Sugerir carpeta de historial si no existe
                if not self.carpetas_config[idx]['historial'].get():
                    historial = folder + "/historial"
                    self.carpetas_config[idx]['historial'].set(historial)
                    
                    # FORZAR actualización directa del Entry historial
                    entry_historial = self.carpetas_config[idx]['entry_historial']
                    entry_historial.delete(0, tk.END)
                    entry_historial.insert(0, historial)
                
                self.log_message(f"Carpeta de monitoreo {idx+1}: {folder}")
                self.root.update()
            else:
                self.log_message(f"Selección cancelada")
        except Exception as e:
            self.log_message(f"Error: {e}")
                
    def browse_historial(self, idx):
        """Buscar carpeta de historial"""
        try:
            folder = filedialog.askdirectory(title=f"Seleccionar carpeta de historial {idx+1}")
            if folder:
                # Normalizar la ruta
                folder = str(Path(folder).resolve()).replace('\\', '/')
                
                # Actualizar StringVar
                self.carpetas_config[idx]['historial'].set(folder)
                
                # FORZAR actualización directa del Entry
                entry_widget = self.carpetas_config[idx]['entry_historial']
                entry_widget.delete(0, tk.END)
                entry_widget.insert(0, folder)
                
                self.log_message(f"Carpeta de historial {idx+1}: {folder}")
                self.root.update()
            else:
                self.log_message(f"Selección cancelada")
        except Exception as e:
            self.log_message(f"Error: {e}")
            
    def start_monitoring(self):
        """Inicia el monitoreo"""
        if self.monitoring:
            return
            
        try:
            # Verificar que hay al menos una carpeta activa
            carpetas_activas_count = sum(1 for vars in self.carpetas_config if vars['activa'].get())
            if carpetas_activas_count == 0:
                messagebox.showerror("Error", "Debe activar al menos una carpeta para monitorear")
                return
                
            # Preparar carpetas para monitoreo
            carpetas_activas = self.prepare_monitoring_folders()
            if not carpetas_activas:
                messagebox.showerror("Error", "No hay carpetas válidas para monitorear")
                return
                
            self.carpetas_monitoreadas = carpetas_activas
            threading.Thread(target=self._start_monitoring_thread, daemon=True).start()
            
        except Exception as e:
            error_msg = str(e)
            self.log_message(f"Error de validación: {error_msg}")
            messagebox.showerror("Error de Configuración", error_msg)
            
    def prepare_monitoring_folders(self):
        """Prepara las carpetas para monitoreo"""
        carpetas_activas = []
        
        for i, carpeta_vars in enumerate(self.carpetas_config):
            if not carpeta_vars['activa'].get():
                continue
                
            ruta = carpeta_vars['ruta'].get().strip()
            impresora = carpeta_vars['impresora'].get().strip()
            historial = carpeta_vars['historial'].get().strip()
            
            # Validaciones estrictas
            if not ruta:
                raise Exception(f"Carpeta {i+1}: Debe seleccionar una carpeta de monitoreo")
                
            if not impresora:
                raise Exception(f"Carpeta {i+1}: Debe seleccionar una impresora")
                
            if not historial:
                raise Exception(f"Carpeta {i+1}: Debe seleccionar una carpeta de historial")
                
            if not Path(ruta).exists():
                raise Exception(f"Carpeta {i+1}: La carpeta de monitoreo no existe: {ruta}")
                
            # Crear carpeta de historial si no existe
            historial_path = Path(historial)
            try:
                historial_path.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                raise Exception(f"Carpeta {i+1}: No se puede crear carpeta de historial: {e}")
                
            # Verificar que las carpetas sean diferentes
            if Path(ruta).resolve() == historial_path.resolve():
                raise Exception(f"Carpeta {i+1}: La carpeta de monitoreo y historial no pueden ser la misma")
            
            try:
                copias = int(carpeta_vars['copias'].get() or 1)
                if copias < 1 or copias > 10:
                    raise ValueError("Copias debe estar entre 1 y 10")
            except ValueError as e:
                raise Exception(f"Carpeta {i+1}: {e}")
                
            carpetas_activas.append({
                'entrada': ruta,
                'impresora': impresora,
                'historial': str(historial_path),
                'ancho_mm': 100,
                'alto_mm': 150,
                'poppler': self.config.get('poppler', '') if self.config else '',
                'recortar_pdf': carpeta_vars['recortar_pdf'].get(),
                'copias': copias
            })
            
            self.log_message(f"Carpeta {i+1} validada: {ruta} -> {impresora} ({copias} copias)")
            
        return carpetas_activas
        
    def _start_monitoring_thread(self):
        """Hilo de monitoreo"""
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
                    
        self._update_ui_monitoring_stopped()
        self.log_message("⏹️ Monitoreo detenido")
        
    def save_config(self):
        """Guarda la configuración"""
        try:
            # Guardar configuración usando ConfigParser
            import configparser
            config = configparser.ConfigParser()
            
            # Guardar todas las carpetas (incluso las vacías)
            for i in range(3):
                carpeta_vars = self.carpetas_config[i]
                section = f"CARPETA{i+1}"
                
                try:
                    copias = int(carpeta_vars['copias'].get() or 1)
                    copias = max(1, min(10, copias))
                except ValueError:
                    copias = 1
                
                config[section] = {
                    'entrada': carpeta_vars['ruta'].get().strip(),
                    'impresora': carpeta_vars['impresora'].get().strip(),
                    'historial': carpeta_vars['historial'].get().strip(),
                    'activa': str(carpeta_vars['activa'].get()),
                    'recortar_pdf': str(carpeta_vars['recortar_pdf'].get()),
                    'copias': str(copias)
                }
                
                self.log_message(f"Guardando Carpeta {i+1}: {carpeta_vars['ruta'].get() or 'VACÍA'}")
            
            # Buscar directorio de configuración
            config_paths = [
                project_root / 'config' / 'config.ini',
                project_root / 'config.ini',
                Path('config/config.ini'),
                Path('config.ini')
            ]
            
            # Usar directorio escribible (AppData o directorio actual)
            try:
                # Intentar en directorio actual primero
                config_dir = Path('config')
                config_dir.mkdir(exist_ok=True)
                config_path = config_dir / 'config.ini'
                
                # Probar si se puede escribir
                test_file = config_dir / 'test.tmp'
                test_file.write_text('test')
                test_file.unlink()
                
            except (PermissionError, OSError):
                # Usar AppData si no se puede escribir en directorio actual
                import os
                appdata = Path(os.environ.get('APPDATA', '.'))
                config_dir = appdata / 'EtiquetadorZPL'
                config_dir.mkdir(exist_ok=True)
                config_path = config_dir / 'config.ini'
                self.log_message(f"Usando directorio AppData: {config_dir}")
            
            # Escribir configuración
            with open(config_path, 'w') as f:
                config.write(f)
                
            self.log_message(f"Configuración guardada en: {config_path}")
            
            # Verificar que se guardó correctamente
            if config_path.exists():
                self.log_message("Archivo de configuración creado exitosamente")
            else:
                self.log_message("ERROR: No se pudo crear el archivo de configuración")
                
            self.log_message("💾 Configuración guardada")
            messagebox.showinfo("Éxito", "Configuración guardada correctamente")
            
        except Exception as e:
            self.log_message(f"❌ Error al guardar: {e}")
            messagebox.showerror("Error", f"No se pudo guardar: {e}")
        
    def log_message(self, message):
        """Agrega mensaje al log"""
        try:
            self.log_text.insert(tk.END, f"{message}\n")
            self.log_text.see(tk.END)
        except:
            print(f"LOG: {message}")
        
    def clear_log(self):
        """Limpia el log"""
        self.log_text.delete(1.0, tk.END)
        
    def on_closing(self):
        """Maneja el cierre de la aplicación"""
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
        """Ejecuta la aplicación"""
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.root.mainloop()

if __name__ == "__main__":
    app = EtiquetadorGUIOptimized()
    app.run()