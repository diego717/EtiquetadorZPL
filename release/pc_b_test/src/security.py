import os
import logging
import psutil
import threading
import time
from pathlib import Path
from security_logger import security_logger

class SecurityValidator:
    """Validador de seguridad para rutas y archivos"""
    
    # Extensiones permitidas
    ALLOWED_EXTENSIONS = {'.pdf', '.txt', '.zpl', '.zip', '.png', '.jpg', '.jpeg'}
    
    # Tamaños máximos (en bytes)
    MAX_FILE_SIZE = 200 * 1024 * 1024  # 200MB
    MAX_ZIP_SIZE = 500 * 1024 * 1024  # 500MB
    
    # Límites de recursos
    MAX_MEMORY_PERCENT = 95  # 95% de RAM máxima
    MAX_CPU_PERCENT = 98     # 98% de CPU máxima
    MAX_CONCURRENT_FILES = 10  # Máximo 10 archivos simultáneos
    
    # Nombres de archivo peligrosos
    DANGEROUS_NAMES = {
        'con', 'prn', 'aux', 'nul', 'com1', 'com2', 'com3', 'com4', 'com5',
        'com6', 'com7', 'com8', 'com9', 'lpt1', 'lpt2', 'lpt3', 'lpt4',
        'lpt5', 'lpt6', 'lpt7', 'lpt8', 'lpt9'
    }
    
    @staticmethod
    def validate_path(path_str, base_path=None):
        """Valida que una ruta sea segura"""
        try:
            path = Path(path_str).resolve()
            
            # Verificar path traversal
            if '..' in str(path) or str(path).startswith('\\\\'):
                logging.error(f"Path traversal detectado: {path_str}")
                return False
            
            # Si hay base_path, verificar que esté dentro
            if base_path:
                base = Path(base_path).resolve()
                try:
                    path.relative_to(base)
                except ValueError:
                    logging.error(f"Ruta fuera del directorio permitido: {path_str}")
                    return False
            
            return True
            
        except Exception as e:
            logging.error(f"Error validando ruta {path_str}: {e}")
            return False
    
    @staticmethod
    def validate_filename(filename):
        """Valida que un nombre de archivo sea seguro"""
        name_lower = filename.lower()
        
        # Verificar nombres peligrosos de Windows
        name_base = Path(filename).stem.lower()
        if name_base in SecurityValidator.DANGEROUS_NAMES:
            logging.error(f"Nombre de archivo peligroso: {filename}")
            return False
        
        # Verificar caracteres peligrosos
        dangerous_chars = ['<', '>', ':', '"', '|', '?', '*', '\0']
        if any(char in filename for char in dangerous_chars):
            logging.error(f"Caracteres peligrosos en nombre: {filename}")
            return False
        
        return True
    
    @staticmethod
    def validate_file_extension(filename):
        """Valida que la extensión del archivo sea permitida"""
        ext = Path(filename).suffix.lower()
        if ext not in SecurityValidator.ALLOWED_EXTENSIONS:
            logging.error(f"Extensión no permitida: {ext}")
            return False
        return True
    
    @staticmethod
    def validate_file_size(filepath):
        """Valida el tamaño del archivo"""
        try:
            file_path = Path(filepath)
            if not file_path.exists():
                logging.warning(f"Archivo no existe para validación de tamaño: {filepath}")
                return True  # Permitir continuar si el archivo no existe
            
            size = file_path.stat().st_size
            max_size = SecurityValidator.MAX_ZIP_SIZE if filepath.endswith('.zip') else SecurityValidator.MAX_FILE_SIZE
            
            if size > max_size:
                size_mb = size / (1024 * 1024)
                max_mb = max_size / (1024 * 1024)
                logging.error(f"Archivo demasiado grande: {size_mb:.1f}MB (máximo: {max_mb:.1f}MB)")
                return False
            
            size_mb = size / (1024 * 1024)
            logging.info(f"Archivo válido: {file_path.name} ({size_mb:.1f}MB)")
            return True
            
        except Exception as e:
            logging.error(f"Error verificando tamaño: {e}")
            return True  # Permitir continuar en caso de error
    
    @staticmethod
    def check_system_resources():
        """Verifica que el sistema tenga recursos disponibles"""
        try:
            # Verificar memoria
            memory = psutil.virtual_memory()
            if memory.percent > SecurityValidator.MAX_MEMORY_PERCENT:
                logging.warning(f"Memoria alta: {memory.percent}%")
                security_logger.log_resource_limit("MEMORIA", memory.percent, SecurityValidator.MAX_MEMORY_PERCENT)
                return False
            
            # Verificar CPU
            cpu_percent = psutil.cpu_percent(interval=1)
            if cpu_percent > SecurityValidator.MAX_CPU_PERCENT:
                logging.warning(f"CPU alta: {cpu_percent}%")
                security_logger.log_resource_limit("CPU", cpu_percent, SecurityValidator.MAX_CPU_PERCENT)
                return False
            
            return True
            
        except Exception as e:
            logging.error(f"Error verificando recursos: {e}")
            return True  # Permitir continuar si no se puede verificar

class ResourceMonitor:
    """Monitor de recursos del sistema"""
    
    def __init__(self):
        self.active_files = 0
        self.lock = threading.Lock()
    
    def can_process_file(self):
        """Verifica si se puede procesar otro archivo"""
        with self.lock:
            if self.active_files >= SecurityValidator.MAX_CONCURRENT_FILES:
                logging.warning(f"Máximo de archivos concurrentes alcanzado: {self.active_files}")
                return False
            return SecurityValidator.check_system_resources()
    
    def start_processing(self):
        """Marca el inicio del procesamiento de un archivo"""
        with self.lock:
            self.active_files += 1
            logging.info(f"Archivos en procesamiento: {self.active_files}")
    
    def finish_processing(self):
        """Marca el fin del procesamiento de un archivo"""
        with self.lock:
            self.active_files = max(0, self.active_files - 1)
            logging.info(f"Archivos en procesamiento: {self.active_files}")

class ZPLSanitizer:
    """Sanitizador de contenido ZPL"""
    
    # Comandos ZPL peligrosos o no permitidos
    FORBIDDEN_COMMANDS = {
        '^ID',  # Borrar memoria
        '^JU',  # Configuración de red
        '^NC',  # Cambiar configuración
        '^WD',  # Descargar objetos
        '^XF',  # Recall format
        '^DF',  # Download format
    }
    
    # Límites de contenido
    MAX_ZPL_SIZE = 1024 * 1024  # 1MB máximo
    MAX_LINES = 1000  # Máximo 1000 líneas
    
    @staticmethod
    def sanitize_zpl_content(content):
        """Sanitiza y valida contenido ZPL"""
        if not content or not isinstance(content, str):
            logging.error("Contenido ZPL vacío o inválido")
            return None
        
        # Verificar tamaño
        if len(content.encode('utf-8')) > ZPLSanitizer.MAX_ZPL_SIZE:
            logging.error(f"Contenido ZPL demasiado grande: {len(content)} caracteres")
            return None
        
        # Verificar número de líneas
        lines = content.split('\n')
        if len(lines) > ZPLSanitizer.MAX_LINES:
            logging.error(f"Demasiadas líneas en ZPL: {len(lines)}")
            return None
        
        # Verificar comandos prohibidos
        content_upper = content.upper()
        forbidden_found = []
        for forbidden in ZPLSanitizer.FORBIDDEN_COMMANDS:
            if forbidden in content_upper:
                forbidden_found.append(forbidden)
        
        if forbidden_found:
            logging.error(f"Comandos ZPL prohibidos detectados: {forbidden_found}")
            security_logger.log_zpl_blocked("archivo_zpl", forbidden_found)
            return None
        
        # Verificar estructura básica ZPL
        if not content_upper.startswith('^XA'):
            logging.warning("ZPL no comienza con ^XA, agregando...")
            content = '^XA\n' + content
        
        if not content_upper.endswith('^XZ'):
            logging.warning("ZPL no termina con ^XZ, agregando...")
            content = content + '\n^XZ'
        
        # Limpiar caracteres peligrosos
        dangerous_chars = ['\x00', '\x01', '\x02', '\x03', '\x04', '\x05']
        for char in dangerous_chars:
            if char in content:
                content = content.replace(char, '')
                logging.warning(f"Caracter peligroso removido: {repr(char)}")
        
        logging.info("Contenido ZPL sanitizado correctamente")
        return content
    
    @staticmethod
    def validate_zpl_structure(content):
        """Valida la estructura básica del ZPL"""
        if not content:
            return False
        
        content_upper = content.upper()
        
        # Debe tener inicio y fin
        if '^XA' not in content_upper or '^XZ' not in content_upper:
            logging.error("ZPL sin estructura válida (falta ^XA o ^XZ)")
            return False
        
        # Verificar balance de comandos
        xa_count = content_upper.count('^XA')
        xz_count = content_upper.count('^XZ')
        
        if xa_count != xz_count:
            logging.error(f"ZPL desbalanceado: {xa_count} ^XA vs {xz_count} ^XZ")
            return False
        
        return True

# Instancia global del monitor
resource_monitor = ResourceMonitor()