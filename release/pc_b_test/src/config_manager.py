"""
Gestor centralizado de configuración y logs para EtiquetadorZPL
"""

import os
import sys
import json
import logging
import configparser
from pathlib import Path
from logging.handlers import RotatingFileHandler

class ConfigManager:
    def __init__(self):
        self.app_name = "EtiquetadorZPL"
        self.config_dir = self._get_config_directory()
        self.log_dir = self.config_dir / "logs"
        self.config_file = self.config_dir / "config.ini"
        self.settings_file = self.config_dir / "settings.json"
        
        # Crear directorios
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Configurar logging
        self._setup_logging()
        
    def _get_config_directory(self):
        """Obtener directorio de configuración persistente"""
        if os.name == 'nt':  # Windows
            base_dir = Path(os.environ.get('APPDATA', '.'))
        else:  # Linux/Mac
            base_dir = Path.home() / '.config'
        
        return base_dir / self.app_name
    
    def _setup_logging(self):
        """Configurar sistema de logging"""
        try:
            # Formato de logs
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            
            # Log principal
            main_log = self.log_dir / 'etiquetador.log'
            main_handler = RotatingFileHandler(
                main_log, 
                maxBytes=5*1024*1024,  # 5MB
                backupCount=5,
                encoding='utf-8'
            )
            main_handler.setFormatter(formatter)
            main_handler.setLevel(logging.INFO)
            
            # Log de errores
            error_log = self.log_dir / 'errores.log'
            error_handler = RotatingFileHandler(
                error_log,
                maxBytes=2*1024*1024,  # 2MB
                backupCount=3,
                encoding='utf-8'
            )
            error_handler.setFormatter(formatter)
            error_handler.setLevel(logging.ERROR)
            
            # Configurar logger root
            root_logger = logging.getLogger()
            root_logger.setLevel(logging.INFO)
            
            # Limpiar handlers existentes
            for handler in root_logger.handlers[:]:
                root_logger.removeHandler(handler)
            
            # Agregar nuevos handlers
            root_logger.addHandler(main_handler)
            root_logger.addHandler(error_handler)
            
            # Console handler solo en desarrollo
            if not getattr(sys, 'frozen', False):
                console_handler = logging.StreamHandler(sys.stdout)
                console_handler.setFormatter(formatter)
                console_handler.setLevel(logging.INFO)
                root_logger.addHandler(console_handler)
            
            logging.info(f"Logging configurado - Directorio: {self.log_dir}")
            
        except Exception as e:
            print(f"Error configurando logging: {e}")
    
    def load_config(self):
        """Cargar configuración desde archivo INI"""
        if not self.config_file.exists():
            return self._create_default_config()
        
        try:
            config = configparser.ConfigParser()
            config.read(self.config_file, encoding='utf-8')
            
            # Convertir a formato estándar
            carpetas = []
            
            # Buscar carpetas configuradas
            for section_name in config.sections():
                if section_name.upper().startswith('CARPETA'):
                    section = config[section_name]
                    carpeta_config = {
                        'ruta': section.get('entrada', ''),
                        'impresora': section.get('impresora', ''),
                        'historial': section.get('historial', ''),
                        'activa': section.getboolean('activa', fallback=True),
                        'recortar_pdf': section.getboolean('recortar_pdf', fallback=True),
                        'copias': section.getint('copias', fallback=1)
                    }
                    if carpeta_config['ruta']:  # Solo si tiene ruta
                        carpetas.append(carpeta_config)
            
            # Si no hay carpetas, crear configuración por defecto
            if not carpetas:
                return self._create_default_config()
            
            # Obtener configuración de etiqueta
            etiqueta_config = {}
            if config.has_section('etiqueta'):
                etiqueta_section = config['etiqueta']
                etiqueta_config = {
                    'ancho_mm': etiqueta_section.getint('ancho_mm', fallback=100),
                    'alto_mm': etiqueta_section.getint('alto_mm', fallback=150)
                }
            else:
                etiqueta_config = {'ancho_mm': 100, 'alto_mm': 150}
            
            config_data = {
                'carpetas': carpetas,
                'etiqueta': etiqueta_config
            }
            
            logging.info(f"Configuración cargada: {len(carpetas)} carpetas configuradas")
            return config_data
            
        except Exception as e:
            logging.error(f"Error cargando configuración: {e}")
            return self._create_default_config()
    
    def save_config(self, config_data):
        """Guardar configuración en archivo INI"""
        try:
            config = configparser.ConfigParser()
            
            # Sección etiqueta
            config.add_section('etiqueta')
            etiqueta = config_data.get('etiqueta', {})
            config.set('etiqueta', 'ancho_mm', str(etiqueta.get('ancho_mm', 100)))
            config.set('etiqueta', 'alto_mm', str(etiqueta.get('alto_mm', 150)))
            
            # Secciones de carpetas
            carpetas = config_data.get('carpetas', [])
            for i, carpeta in enumerate(carpetas, 1):
                section_name = f'CARPETA{i}'
                config.add_section(section_name)
                config.set(section_name, 'entrada', carpeta.get('ruta', ''))
                config.set(section_name, 'impresora', carpeta.get('impresora', ''))
                config.set(section_name, 'historial', carpeta.get('historial', ''))
                config.set(section_name, 'activa', str(carpeta.get('activa', True)))
                config.set(section_name, 'recortar_pdf', str(carpeta.get('recortar_pdf', True)))
                config.set(section_name, 'copias', str(carpeta.get('copias', 1)))
            
            # Escribir archivo
            with open(self.config_file, 'w', encoding='utf-8') as f:
                config.write(f)
            
            logging.info("Configuración guardada correctamente")
            return True
            
        except Exception as e:
            logging.error(f"Error guardando configuración: {e}")
            return False
    
    def _create_default_config(self):
        """Crear configuración por defecto"""
        default_config = {
            'carpetas': [{
                'ruta': 'C:/EtiquetasFlex',
                'impresora': 'Godex GE300',
                'historial': 'C:/EtiquetasFlex/Historial1',
                'activa': True,
                'recortar_pdf': True,
                'copias': 1
            }],
            'etiqueta': {
                'ancho_mm': 100,
                'alto_mm': 150
            }
        }
        
        # Crear carpetas por defecto
        try:
            for carpeta in default_config['carpetas']:
                os.makedirs(carpeta['ruta'], exist_ok=True)
                os.makedirs(carpeta['historial'], exist_ok=True)
        except Exception as e:
            logging.warning(f"No se pudieron crear carpetas por defecto: {e}")
        
        # Guardar configuración
        self.save_config(default_config)
        logging.info("Configuración por defecto creada")
        
        return default_config
    
    def get_log_directory(self):
        """Obtener directorio de logs"""
        return str(self.log_dir)
    
    def get_config_directory(self):
        """Obtener directorio de configuración"""
        return str(self.config_dir)

# Instancia global
config_manager = ConfigManager()

def get_config_manager():
    """Obtener instancia del gestor de configuración"""
    return config_manager