import logging
import os
from datetime import datetime
from pathlib import Path

class SecurityLogger:
    """Logger especializado para eventos de seguridad"""
    
    def __init__(self):
        self.setup_security_logger()
    
    def setup_security_logger(self):
        """Configura el logger de seguridad"""
        # Crear directorio de logs si no existe
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        # Configurar logger de seguridad
        self.security_logger = logging.getLogger('security')
        self.security_logger.setLevel(logging.INFO)
        
        # Evitar duplicar handlers
        if not self.security_logger.handlers:
            # Handler para archivo de seguridad
            security_file = log_dir / "security.log"
            file_handler = logging.FileHandler(security_file, encoding='utf-8')
            file_handler.setLevel(logging.INFO)
            
            # Formato específico para seguridad
            formatter = logging.Formatter(
                '%(asctime)s | SECURITY | %(levelname)s | %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            file_handler.setFormatter(formatter)
            self.security_logger.addHandler(file_handler)
    
    def log_file_blocked(self, filename, reason, source_path=None):
        """Log cuando un archivo es bloqueado"""
        msg = f"ARCHIVO BLOQUEADO: {filename} | Razón: {reason}"
        if source_path:
            msg += f" | Ruta: {source_path}"
        self.security_logger.warning(msg)
    
    def log_resource_limit(self, resource_type, current_value, limit):
        """Log cuando se alcanza un límite de recursos"""
        msg = f"LÍMITE DE RECURSOS: {resource_type} = {current_value}% (límite: {limit}%)"
        self.security_logger.warning(msg)
    
    def log_zpl_sanitized(self, filename, issues_found):
        """Log cuando se sanitiza contenido ZPL"""
        msg = f"ZPL SANITIZADO: {filename} | Problemas encontrados: {', '.join(issues_found)}"
        self.security_logger.info(msg)
    
    def log_zpl_blocked(self, filename, forbidden_commands):
        """Log cuando se bloquea ZPL por comandos prohibidos"""
        msg = f"ZPL BLOQUEADO: {filename} | Comandos prohibidos: {', '.join(forbidden_commands)}"
        self.security_logger.error(msg)
    
    def log_path_traversal(self, attempted_path, base_path):
        """Log intento de path traversal"""
        msg = f"PATH TRAVERSAL DETECTADO: {attempted_path} | Base permitida: {base_path}"
        self.security_logger.error(msg)
    
    def log_file_processed(self, filename, file_type, processing_time):
        """Log archivo procesado exitosamente"""
        msg = f"ARCHIVO PROCESADO: {filename} | Tipo: {file_type} | Tiempo: {processing_time:.2f}s"
        self.security_logger.info(msg)
    
    def log_print_job(self, filename, printer, copies, success):
        """Log trabajo de impresión"""
        status = "EXITOSO" if success else "FALLIDO"
        msg = f"IMPRESIÓN {status}: {filename} | Impresora: {printer} | Copias: {copies}"
        self.security_logger.info(msg)
    
    def log_system_resources(self, cpu_percent, memory_percent, active_files):
        """Log estado de recursos del sistema"""
        msg = f"RECURSOS SISTEMA: CPU={cpu_percent}% | RAM={memory_percent}% | Archivos activos={active_files}"
        self.security_logger.debug(msg)

# Instancia global del security logger
security_logger = SecurityLogger()