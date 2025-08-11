import logging
import logging.handlers
import os
from datetime import datetime
from pathlib import Path

class LoggerManager:
    def __init__(self, log_dir="logs", max_bytes=10*1024*1024, backup_count=5):
        """
        Sistema de logging mejorado con rotación automática
        
        Args:
            log_dir: Directorio para archivos de log
            max_bytes: Tamaño máximo por archivo (10MB por defecto)
            backup_count: Número de archivos de backup a mantener
        """
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        
        # Configurar logger principal
        self.logger = logging.getLogger('EtiquetadorZPL')
        self.logger.setLevel(logging.DEBUG)
        
        # Limpiar handlers existentes
        self.logger.handlers.clear()
        
        # Handler para archivo con rotación
        log_file = self.log_dir / "etiquetador.log"
        file_handler = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=max_bytes, backupCount=backup_count, encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)
        
        # Handler para errores críticos (archivo separado)
        error_file = self.log_dir / "errores.log"
        error_handler = logging.handlers.RotatingFileHandler(
            error_file, maxBytes=max_bytes, backupCount=backup_count, encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        
        # Formato detallado
        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(name)s | %(funcName)s:%(lineno)d | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        file_handler.setFormatter(formatter)
        error_handler.setFormatter(formatter)
        
        self.logger.addHandler(file_handler)
        self.logger.addHandler(error_handler)
        
        # Handler para GUI (opcional)
        self.gui_handler = None
        
    def add_gui_handler(self, gui_callback):
        """Agregar handler para mostrar logs en la GUI"""
        if self.gui_handler:
            self.logger.removeHandler(self.gui_handler)
            
        self.gui_handler = GUILogHandler(gui_callback)
        self.gui_handler.setLevel(logging.INFO)
        
        gui_formatter = logging.Formatter('%(asctime)s | %(levelname)s | %(message)s', '%H:%M:%S')
        self.gui_handler.setFormatter(gui_formatter)
        
        self.logger.addHandler(self.gui_handler)
    
    def set_level(self, level_name):
        """Cambiar nivel de logging (DEBUG, INFO, WARNING, ERROR, CRITICAL)"""
        level = getattr(logging, level_name.upper(), logging.INFO)
        self.logger.setLevel(level)
    
    def get_logger(self):
        """Obtener el logger configurado"""
        return self.logger
    
    def export_logs(self, output_file=None):
        """Exportar logs para soporte técnico"""
        if not output_file:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = f"logs_export_{timestamp}.zip"
        
        import zipfile
        
        with zipfile.ZipFile(output_file, 'w') as zipf:
            for log_file in self.log_dir.glob("*.log*"):
                zipf.write(log_file, log_file.name)
        
        return output_file
    
    def clean_old_logs(self, days_to_keep=30):
        """Limpiar logs antiguos"""
        import time
        cutoff_time = time.time() - (days_to_keep * 24 * 60 * 60)
        
        for log_file in self.log_dir.glob("*.log*"):
            if log_file.stat().st_mtime < cutoff_time:
                log_file.unlink()

class GUILogHandler(logging.Handler):
    """Handler personalizado para mostrar logs en la GUI"""
    def __init__(self, callback):
        super().__init__()
        self.callback = callback
        
    def emit(self, record):
        try:
            msg = self.format(record)
            self.callback(msg, record.levelname)
        except:
            pass

# Instancia global del logger
log_manager = LoggerManager()
logger = log_manager.get_logger()

# Funciones de conveniencia
def debug(msg): logger.debug(msg)
def info(msg): logger.info(msg)
def warning(msg): logger.warning(msg)
def error(msg): logger.error(msg)
def critical(msg): logger.critical(msg)
def exception(msg): logger.exception(msg)