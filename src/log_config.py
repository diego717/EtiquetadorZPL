"""
Configuración de logging para EtiquetadorZPL
"""

import logging
import os
from pathlib import Path
from logging.handlers import RotatingFileHandler

def setup_logging():
    """Configurar logging para aplicación instalada"""
    try:
        # Determinar ubicación de logs
        try:
            # Intentar en directorio actual
            log_dir = Path("logs")
            log_dir.mkdir(exist_ok=True)
            test_file = log_dir / "test.tmp"
            test_file.write_text("test")
            test_file.unlink()
        except (PermissionError, OSError):
            # Usar AppData si no se puede escribir
            appdata = Path(os.environ.get('APPDATA', '.'))
            log_dir = appdata / 'EtiquetadorZPL' / 'logs'
            log_dir.mkdir(parents=True, exist_ok=True)
        
        # Configurar formato
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Log principal con rotación
        main_log = log_dir / 'etiquetador.log'
        main_handler = RotatingFileHandler(
            main_log, 
            maxBytes=5*1024*1024,  # 5MB
            backupCount=5
        )
        main_handler.setFormatter(formatter)
        main_handler.setLevel(logging.INFO)
        
        # Log de errores
        error_log = log_dir / 'errors.log'
        error_handler = RotatingFileHandler(
            error_log,
            maxBytes=2*1024*1024,  # 2MB
            backupCount=3
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
        
        # Handler para consola (solo en desarrollo)
        if not getattr(sys, 'frozen', False):
            import sys
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(formatter)
            console_handler.setLevel(logging.INFO)
            root_logger.addHandler(console_handler)
        
        logging.info(f"Logging configurado - Directorio: {log_dir}")
        return str(log_dir)
        
    except Exception as e:
        print(f"Error configurando logging: {e}")
        return None

def get_log_directory():
    """Obtener directorio de logs"""
    try:
        log_dir = Path("logs")
        if log_dir.exists():
            return str(log_dir)
    except:
        pass
    
    # Fallback a AppData
    appdata = Path(os.environ.get('APPDATA', '.'))
    log_dir = appdata / 'EtiquetadorZPL' / 'logs'
    return str(log_dir)