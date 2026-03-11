"""
Utilidades comunes para EtiquetadorZPL
"""

import functools
import logging
import time
import threading
from typing import Callable, Any, Optional, TypeVar, ParamSpec
from contextlib import contextmanager
from pathlib import Path
import hashlib
import json

from constants import (
    MAX_RETRY_ATTEMPTS,
    RETRY_BACKOFF_FACTOR,
    RETRY_INITIAL_DELAY
)

# ============================================
# DECORADORES
# ============================================

P = ParamSpec('P')
T = TypeVar('T')


def retry(
    max_attempts: int = MAX_RETRY_ATTEMPTS,
    backoff_factor: float = RETRY_BACKOFF_FACTOR,
    initial_delay: float = RETRY_INITIAL_DELAY,
    exceptions: tuple = (Exception,)
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """
    Decorador para reintentar funciones que pueden fallar.
    
    Args:
        max_attempts: Número máximo de intentos
        backoff_factor: Factor de espera exponencial
        initial_delay: Delay inicial en segundos
        exceptions: Tupla de excepciones que disparan retry
    """
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            last_exception = None
            delay = initial_delay
            
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt == max_attempts:
                        break
                    
                    logging.warning(
                        f"Intento {attempt}/{max_attempts} falló en {func.__name__}: {e}. "
                        f"Reintentando en {delay}s..."
                    )
                    time.sleep(delay)
                    delay *= backoff_factor
            
            # Si todos los intentos fallaron, lanzar la última excepción
            raise last_exception
        
        return wrapper
    return decorator


def async_retry(
    max_attempts: int = MAX_RETRY_ATTEMPTS,
    backoff_factor: float = RETRY_BACKOFF_FACTOR,
    initial_delay: float = RETRY_INITIAL_DELAY,
    exceptions: tuple = (Exception,)
):
    """Versión async del decorador retry"""
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            import asyncio
            last_exception = None
            delay = initial_delay
            
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt == max_attempts:
                        break
                    
                    logging.warning(
                        f"Intento {attempt}/{max_attempts} falló en {func.__name__}: {e}. "
                        f"Reintentando en {delay}s..."
                    )
                    await asyncio.sleep(delay)
                    delay *= backoff_factor
            
            raise last_exception
        
        return wrapper
    return decorator


def log_call(logger: Optional[logging.Logger] = None):
    """Decorador para loggear llamadas a funciones"""
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            nonlocal logger
            if logger is None:
                logger = logging.getLogger(func.__module__)
            
            # Log de entrada
            args_repr = [repr(a) for a in args]
            kwargs_repr = [f"{k}={v!r}" for k, v in kwargs.items()]
            signature = ", ".join(args_repr + kwargs_repr)
            
            logger.debug(f"Llamando a {func.__name__}({signature})")
            
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                elapsed = time.time() - start_time
                logger.debug(f"{func.__name__} completada en {elapsed:.3f}s")
                return result
            except Exception as e:
                elapsed = time.time() - start_time
                logger.error(f"{func.__name__} falló en {elapsed:.3f}s: {e}")
                raise
        
        return wrapper
    return decorator


def timing(logger: Optional[logging.Logger] = None):
    """Decorador para medir tiempo de ejecución"""
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            nonlocal logger
            if logger is None:
                logger = logging.getLogger(func.__module__)
            
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                elapsed = time.time() - start_time
                logger.info(f"{func.__name__} ejecutada en {elapsed:.3f}s")
                return result
            except Exception as e:
                elapsed = time.time() - start_time
                logger.error(f"{func.__name__} falló en {elapsed:.3f}s: {e}")
                raise
        
        return wrapper
    return decorator


def synchronized(lock: Optional[threading.Lock] = None):
    """Decorador para sincronizar acceso a funciones"""
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            with func._sync_lock:
                return func(*args, **kwargs)
        
        # Agregar lock a la función
        if not hasattr(func, '_sync_lock'):
            func._sync_lock = lock if lock else threading.Lock()
        
        return wrapper
    return decorator


def deprecated(message: str = "Esta función está obsoleta"):
    """Decorador para marcar funciones como obsoletas"""
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            logging.warning(f"{func.__name__} está obsoleta: {message}")
            return func(*args, **kwargs)
        
        return wrapper
    return decorator


# ============================================
# CONTEXT MANAGERS
# ============================================

@contextmanager
def temporary_file(filepath: Path, delete_on_exit: bool = True):
    """Context manager para archivos temporales"""
    try:
        yield filepath
    finally:
        if delete_on_exit and filepath.exists():
            try:
                filepath.unlink()
            except Exception as e:
                logging.warning(f"No se pudo eliminar archivo temporal {filepath}: {e}")


@contextmanager
def temporary_directory(dirpath: Path, delete_on_exit: bool = True):
    """Context manager para directorios temporales"""
    import shutil
    try:
        yield dirpath
    finally:
        if delete_on_exit and dirpath.exists():
            try:
                shutil.rmtree(dirpath)
            except Exception as e:
                logging.warning(f"No se pudo eliminar directorio temporal {dirpath}: {e}")


@contextmanager
def locked_resource(lock: threading.Lock):
    """Context manager para recursos bloqueados"""
    with lock:
        yield


class Timer:
    """Contexto para medir tiempo"""
    
    def __init__(self, name: str = "Operation", logger: Optional[logging.Logger] = None):
        self.name = name
        self.logger = logger
        self.start_time = None
        self.elapsed = None
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.elapsed = time.time() - self.start_time
        if self.logger:
            self.logger.info(f"{self.name} tomó {self.elapsed:.3f}s")
        return False


# ============================================
# FUNCIONES DE UTILIDAD
# ============================================

def get_file_hash(filepath: Path, algorithm: str = "md5") -> str:
    """Calcular hash de un archivo"""
    hash_func = hashlib.new(algorithm)
    
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            hash_func.update(chunk)
    
    return hash_func.hexdigest()


def ensure_directory(path: Path) -> Path:
    """Asegurar que un directorio existe"""
    path.mkdir(parents=True, exist_ok=True)
    return path


def safe_filename(filename: str, replacement: str = "_") -> str:
    """Convertir nombre de archivo a uno seguro"""
    import re
    
    # Reemplazar caracteres peligrosos
    dangerous_chars = '<>:"|?*'
    for char in dangerous_chars:
        filename = filename.replace(char, replacement)
    
    # Eliminar espacios múltiples
    filename = re.sub(r'\s+', replacement, filename)
    
    # Limitar longitud
    if len(filename) > 255:
        name, ext = filename.rsplit('.', 1) if '.' in filename else (filename, '')
        name = name[:255 - len(ext) - 1]
        filename = f"{name}.{ext}" if ext else name
    
    return filename


def format_bytes(bytes_count: int) -> str:
    """Formatear bytes a string legible"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_count < 1024:
            return f"{bytes_count:.1f} {unit}"
        bytes_count /= 1024
    return f"{bytes_count:.1f} PB"


def format_duration(seconds: float) -> str:
    """Formatear duración en segundos a string legible"""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}m"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}h"


def parse_bool(value: Any) -> bool:
    """Parsear valor a booleano"""
    if isinstance(value, bool):
        return value
    
    if isinstance(value, str):
        return value.lower() in ('true', '1', 'yes', 'on', 'enabled')
    
    return bool(value)


def deep_merge(dict1: dict, dict2: dict) -> dict:
    """Mergear dos diccionarios recursivamente"""
    result = dict1.copy()
    
    for key, value in dict2.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    
    return result


def load_json_safe(filepath: Path, default: Any = None) -> Any:
    """Cargar JSON de forma segura"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logging.warning(f"Error cargando JSON de {filepath}: {e}")
        return default


def save_json_safe(filepath: Path, data: Any, indent: int = 2) -> bool:
    """Guardar JSON de forma segura"""
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=indent, ensure_ascii=False)
        return True
    except Exception as e:
        logging.error(f"Error guardando JSON en {filepath}: {e}")
        return False


def chunks(lst: list, n: int):
    """Dividir lista en chunks de tamaño n"""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def clamp(value: float, min_value: float, max_value: float) -> float:
    """Limitar valor entre mínimo y máximo"""
    return max(min_value, min(max_value, value))


# ============================================
# VALIDACIONES
# ============================================

def is_valid_path(path: str) -> bool:
    """Validar que una ruta sea válida"""
    try:
        Path(path)
        return True
    except Exception:
        return False


def is_safe_path(base_path: Path, target_path: Path) -> bool:
    """Verificar que target_path esté dentro de base_path"""
    try:
        target_path.resolve().relative_to(base_path.resolve())
        return True
    except ValueError:
        return False


def is_valid_extension(filename: str, allowed_extensions: set) -> bool:
    """Verificar que la extensión sea válida"""
    ext = Path(filename).suffix.lower()
    return ext in allowed_extensions

