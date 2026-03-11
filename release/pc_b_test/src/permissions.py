import os
import stat
import logging
from pathlib import Path
from security_logger import security_logger

class PermissionManager:
    """Gestor de permisos y configuración de acceso"""
    
    def __init__(self):
        self.config_file = Path("config/permissions.json")
        self.ensure_config_directory()
    
    def ensure_config_directory(self):
        """Asegura que el directorio de configuración existe con permisos correctos"""
        config_dir = Path("config")
        config_dir.mkdir(exist_ok=True)
        
        # Configurar permisos del directorio (solo propietario)
        try:
            os.chmod(config_dir, stat.S_IRWXU)  # 700 - solo propietario
            logging.info("Directorio config configurado con permisos restrictivos")
        except Exception as e:
            logging.warning(f"No se pudieron configurar permisos de config: {e}")
    
    def validate_directory_permissions(self, directory_path):
        """Valida permisos de un directorio"""
        try:
            path = Path(directory_path)
            
            if not path.exists():
                logging.error(f"Directorio no existe: {directory_path}")
                return False
            
            # Verificar permisos de lectura
            if not os.access(path, os.R_OK):
                logging.error(f"Sin permisos de lectura: {directory_path}")
                security_logger.log_file_blocked(str(path), "Sin permisos de lectura")
                return False
            
            # Verificar permisos de escritura
            if not os.access(path, os.W_OK):
                logging.error(f"Sin permisos de escritura: {directory_path}")
                security_logger.log_file_blocked(str(path), "Sin permisos de escritura")
                return False
            
            return True
            
        except Exception as e:
            logging.error(f"Error validando permisos de {directory_path}: {e}")
            return False
    
    def secure_file_creation(self, file_path):
        """Crea archivo con permisos seguros"""
        try:
            path = Path(file_path)
            
            # Crear archivo
            path.touch()
            
            # Configurar permisos (solo propietario puede leer/escribir)
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)  # 600
            
            logging.info(f"Archivo creado con permisos seguros: {file_path}")
            return True
            
        except Exception as e:
            logging.error(f"Error creando archivo seguro {file_path}: {e}")
            return False
    
    def validate_printer_access(self, printer_name):
        """Valida acceso a impresora"""
        try:
            import win32print
            
            # Intentar abrir la impresora
            try:
                handle = win32print.OpenPrinter(printer_name)
                win32print.ClosePrinter(handle)
                logging.info(f"Acceso a impresora validado: {printer_name}")
                return True
            except win32print.error as e:
                logging.error(f"Sin acceso a impresora {printer_name}: {e}")
                security_logger.log_file_blocked(printer_name, f"Sin acceso a impresora: {e}")
                return False
                
        except ImportError:
            logging.warning("win32print no disponible, saltando validación de impresora")
            return True
        except Exception as e:
            logging.error(f"Error validando impresora {printer_name}: {e}")
            return False
    
    def create_secure_temp_file(self, content, suffix=".tmp"):
        """Crea archivo temporal con permisos seguros"""
        try:
            import tempfile
            
            # Crear archivo temporal
            with tempfile.NamedTemporaryFile(mode='w', suffix=suffix, delete=False, encoding='utf-8') as temp_file:
                temp_file.write(content)
                temp_path = temp_file.name
            
            # Configurar permisos seguros
            os.chmod(temp_path, stat.S_IRUSR | stat.S_IWUSR)  # 600
            
            logging.info(f"Archivo temporal seguro creado: {temp_path}")
            return temp_path
            
        except Exception as e:
            logging.error(f"Error creando archivo temporal seguro: {e}")
            return None
    
    def cleanup_temp_file(self, temp_path):
        """Limpia archivo temporal de forma segura"""
        try:
            if temp_path and Path(temp_path).exists():
                # Sobrescribir contenido antes de eliminar
                with open(temp_path, 'w') as f:
                    f.write('0' * 1024)  # Sobrescribir con ceros
                
                os.unlink(temp_path)
                logging.info(f"Archivo temporal limpiado: {temp_path}")
                return True
                
        except Exception as e:
            logging.error(f"Error limpiando archivo temporal {temp_path}: {e}")
            return False
    
    def validate_config_integrity(self):
        """Valida integridad de archivos de configuración"""
        config_files = [
            "config.ini",
            "config/permissions.json",
            "logs/security.log"
        ]
        
        for config_file in config_files:
            path = Path(config_file)
            if path.exists():
                try:
                    # Verificar que no sea un enlace simbólico
                    if path.is_symlink():
                        logging.error(f"Archivo de configuración es un enlace simbólico: {config_file}")
                        security_logger.log_file_blocked(config_file, "Enlace simbólico detectado")
                        return False
                    
                    # Verificar permisos
                    if not os.access(path, os.R_OK):
                        logging.error(f"Sin permisos de lectura en configuración: {config_file}")
                        return False
                        
                except Exception as e:
                    logging.error(f"Error validando configuración {config_file}: {e}")
                    return False
        
        return True

# Instancia global del gestor de permisos
permission_manager = PermissionManager()