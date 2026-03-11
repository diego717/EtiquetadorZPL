"""
Excepciones personalizadas para EtiquetadorZPL
"""

from typing import Optional, Any, Dict


class EtiquetadorZPLException(Exception):
    """Excepción base para la aplicación"""
    
    def __init__(self, message: str, code: str = "UNKNOWN_ERROR", details: Optional[Dict[str, Any]] = None):
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(self.message)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertir excepción a diccionario"""
        return {
            "error": self.code,
            "message": self.message,
            "details": self.details
        }


# ============================================
# EXCEPCIONES DE ARCHIVOS
# ============================================

class FileException(EtiquetadorZPLException):
    """Excepción base para errores de archivos"""
    pass


class FileNotFoundException(FileException):
    """Archivo no encontrado"""
    
    def __init__(self, filepath: str):
        super().__init__(
            message=f"Archivo no encontrado: {filepath}",
            code="FILE_NOT_FOUND",
            details={"filepath": filepath}
        )


class FileTooLargeException(FileException):
    """Archivo demasiado grande"""
    
    def __init__(self, filepath: str, size_mb: float, max_size_mb: float):
        super().__init__(
            message=f"Archivo demasiado grande: {size_mb:.1f}MB (máximo: {max_size_mb:.1f}MB)",
            code="FILE_TOO_LARGE",
            details={"filepath": filepath, "size_mb": size_mb, "max_size_mb": max_size_mb}
        )


class InvalidExtensionException(FileException):
    """Extensión de archivo no permitida"""
    
    def __init__(self, extension: str, allowed_extensions: set):
        super().__init__(
            message=f"Extensión no permitida: {extension}",
            code="INVALID_EXTENSION",
            details={"extension": extension, "allowed_extensions": list(allowed_extensions)}
        )


class InvalidFilenameException(FileException):
    """Nombre de archivo inválido"""
    
    def __init__(self, filename: str, reason: str):
        super().__init__(
            message=f"Nombre de archivo inválido: {filename} - {reason}",
            code="INVALID_FILENAME",
            details={"filename": filename, "reason": reason}
        )


# ============================================
# EXCEPCIONES DE IMPRESIÓN
# ============================================

class PrinterException(EtiquetadorZPLException):
    """Excepción base para errores de impresión"""
    pass


class PrinterNotFoundException(PrinterException):
    """Impresora no encontrada"""
    
    def __init__(self, printer_name: str):
        super().__init__(
            message=f"Impresora no encontrada: {printer_name}",
            code="PRINTER_NOT_FOUND",
            details={"printer_name": printer_name}
        )


class PrinterNotConfiguredException(PrinterException):
    """Impresora no configurada"""
    
    def __init__(self):
        super().__init__(
            message="Impresora no configurada",
            code="PRINTER_NOT_CONFIGURED"
        )


class PrinterConnectionException(PrinterException):
    """Error de conexión con impresora"""
    
    def __init__(self, printer_name: str, original_error: str):
        super().__init__(
            message=f"Error de conexión con impresora {printer_name}: {original_error}",
            code="PRINTER_CONNECTION_ERROR",
            details={"printer_name": printer_name, "original_error": original_error}
        )


# ============================================
# EXCEPCIONES DE ZPL
# ============================================

class ZPLException(EtiquetadorZPLException):
    """Excepción base para errores de ZPL"""
    pass


class InvalidZPLException(ZPLException):
    """Contenido ZPL inválido"""
    
    def __init__(self, reason: str):
        super().__init__(
            message=f"Contenido ZPL inválido: {reason}",
            code="INVALID_ZPL",
            details={"reason": reason}
        )


class ZPLSanitizeException(ZPLException):
    """Error al sanitizar ZPL"""
    
    def __init__(self, original_error: Optional[str] = None):
        message = "No se pudo sanitizar el contenido ZPL"
        if original_error:
            message += f": {original_error}"
        
        super().__init__(
            message=message,
            code="ZPL_SANITIZE_FAILED",
            details={"original_error": original_error} if original_error else {}
        )


# ============================================
# EXCEPCIONES DE BASE DE DATOS
# ============================================

class DatabaseException(EtiquetadorZPLException):
    """Excepción base para errores de base de datos"""
    pass


class DatabaseConnectionException(DatabaseException):
    """Error de conexión a base de datos"""
    
    def __init__(self, original_error: str):
        super().__init__(
            message=f"Error de conexión a base de datos: {original_error}",
            code="DATABASE_CONNECTION_ERROR",
            details={"original_error": original_error}
        )


class DatabaseQueryException(DatabaseException):
    """Error en consulta de base de datos"""
    
    def __init__(self, query: str, original_error: str):
        super().__init__(
            message=f"Error en consulta de base de datos: {original_error}",
            code="DATABASE_QUERY_ERROR",
            details={"query": query, "original_error": original_error}
        )


# ============================================
# EXCEPCIONES DE API
# ============================================

class APIException(EtiquetadorZPLException):
    """Excepción base para errores de API"""
    pass


class APIRateLimitException(APIException):
    """Límite de requests excedido"""
    
    def __init__(self, retry_after: int = 60):
        super().__init__(
            message=f"Límite de requests excedido. Intenta de nuevo en {retry_after} segundos",
            code="RATE_LIMIT_EXCEEDED",
            details={"retry_after": retry_after}
        )


class APIValidationException(APIException):
    """Error de validación en API"""
    
    def __init__(self, field: str, message: str):
        super().__init__(
            message=f"Error de validación en {field}: {message}",
            code="VALIDATION_ERROR",
            details={"field": field, "message": message}
        )


# ============================================
# EXCEPCIONES DE CONFIGURACIÓN
# ============================================

class ConfigException(EtiquetadorZPLException):
    """Excepción base para errores de configuración"""
    pass


class ConfigNotFoundException(ConfigException):
    """Archivo de configuración no encontrado"""
    
    def __init__(self, config_file: str):
        super().__init__(
            message=f"Archivo de configuración no encontrado: {config_file}",
            code="CONFIG_NOT_FOUND",
            details={"config_file": config_file}
        )


class ConfigValidationException(ConfigException):
    """Error de validación de configuración"""
    
    def __init__(self, field: str, message: str):
        super().__init__(
            message=f"Error de validación de configuración en {field}: {message}",
            code="CONFIG_VALIDATION_ERROR",
            details={"field": field, "message": message}
        )


# ============================================
# EXCEPCIONES DE PERMISOS
# ============================================

class PermissionException(EtiquetadorZPLException):
    """Error de permisos"""
    pass


class PermissionDeniedException(PermissionException):
    """Permiso denegado"""
    
    def __init__(self, resource: str, required_permission: str):
        super().__init__(
            message=f"Permiso denegado para {resource}: se requiere {required_permission}",
            code="PERMISSION_DENIED",
            details={"resource": resource, "required_permission": required_permission}
        )


# ============================================
# EXCEPCIONES DE HISTORIAL
# ============================================

class HistoryException(EtiquetadorZPLException):
    """Error al mover archivo al historial"""
    
    def __init__(self, filepath: str, history_dir: str, original_error: str):
        super().__init__(
            message=f"Error al mover archivo al historial: {original_error}",
            code="HISTORY_ERROR",
            details={
                "filepath": filepath,
                "history_dir": history_dir,
                "original_error": original_error
            }
        )


# ============================================
# MANEJADOR DE EXCEPCIONES
# ============================================

class ExceptionHandler:
    """Manejador centralizado de excepciones"""
    
    @staticmethod
    def handle_exception(exception: Exception, logger=None) -> Dict[str, Any]:
        """Manejar excepción y retornar diccionario de error"""
        
        if isinstance(exception, EtiquetadorZPLException):
            error_dict = exception.to_dict()
            
            if logger:
                logger.error(f"[{error_dict['error']}] {error_dict['message']}")
            
            return error_dict
        
        # Manejar excepciones genéricas
        error_dict = {
            "error": "UNKNOWN_ERROR",
            "message": str(exception),
            "details": {"exception_type": type(exception).__name__}
        }
        
        if logger:
            logger.exception("Error inesperado")
        
        return error_dict
    
    @staticmethod
    def is_retryable(exception: Exception) -> bool:
        """Determinar si la excepción es retryable"""
        
        retryable_exceptions = (
            PrinterConnectionException,
            DatabaseConnectionException,
            DatabaseQueryException,
        )
        
        # También retry enTimeout y ConnectionError
        if isinstance(exception, (TimeoutError, ConnectionError)):
            return True
        
        return isinstance(exception, retryable_exceptions)

