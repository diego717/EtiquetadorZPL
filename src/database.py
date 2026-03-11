"""
Base de datos mejorada para EtiquetadorZPL
"""

import sqlite3
import json
import time
import os
import logging
import threading
import socket
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from contextlib import contextmanager
from datetime import datetime

# Importar constantes y excepciones
from constants import (
    APP_NAME,
    JOB_STATUS,
    MAX_FILE_SIZE_BYTES
)
from exceptions import (
    DatabaseException,
    DatabaseConnectionException,
    DatabaseQueryException
)

logger = logging.getLogger(__name__)


class DatabaseConnection:
    """Gestor de conexiones a la base de datos"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls, db_path: str = ""):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, db_path: str = ""):
        if db_path and not hasattr(self, 'db_path'):
            self.db_path = db_path
            self._local = threading.local()
            self._init_database()
    
    def _get_connection(self) -> sqlite3.Connection:
        """Obtener conexión (thread-local)"""
        if not hasattr(self._local, 'connection') or self._local.connection is None:
            self._local.connection = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
                timeout=30.0
            )
            # Habilitar WAL mode para mejor concurrencia
            self._local.connection.execute("PRAGMA journal_mode=WAL")
            # Habilitar foreign keys
            self._local.connection.execute("PRAGMA foreign_keys=ON")
        return self._local.connection
    
    @contextmanager
    def get_cursor(self):
        """Context manager para cursor"""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise
        finally:
            cursor.close()
    
    def _init_database(self):
        """Inicializar base de datos con estructura completa"""
        try:
            with self.get_cursor() as cursor:
                # Tabla de trabajos
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS jobs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        filename TEXT NOT NULL,
                        printer TEXT NOT NULL,
                        content_type TEXT DEFAULT 'zpl',
                        copies INTEGER DEFAULT 1,
                        priority INTEGER DEFAULT 0,
                        file_size INTEGER DEFAULT 0,
                        status TEXT DEFAULT 'pending',
                        error_message TEXT,
                        processing_time REAL,
                        retry_count INTEGER DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        completed_at TIMESTAMP,
                        hostname TEXT,
                        username TEXT
                    )
                """)
                
                # Migration: Añadir columnas que pueden no existir en BD antigua
                try:
                    cursor.execute("ALTER TABLE jobs ADD COLUMN priority INTEGER DEFAULT 0")
                except sqlite3.OperationalError:
                    pass  # Columna ya existe
                
                try:
                    cursor.execute("ALTER TABLE jobs ADD COLUMN retry_count INTEGER DEFAULT 0")
                except sqlite3.OperationalError:
                    pass
                
                try:
                    cursor.execute("ALTER TABLE jobs ADD COLUMN completed_at TIMESTAMP")
                except sqlite3.OperationalError:
                    pass
                
                try:
                    cursor.execute("ALTER TABLE jobs ADD COLUMN hostname TEXT")
                except sqlite3.OperationalError:
                    pass
                
                try:
                    cursor.execute("ALTER TABLE jobs ADD COLUMN username TEXT")
                except sqlite3.OperationalError:
                    pass
                
                # Crear índices para mejorar rendimiento
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_jobs_status 
                    ON jobs(status)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_jobs_created_at 
                    ON jobs(created_at DESC)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_jobs_printer 
                    ON jobs(printer)
                """)
                
                # Tabla de configuración
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS config (
                        key TEXT PRIMARY KEY,
                        value TEXT,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Tabla de métricas históricas
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS metrics_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        metric_type TEXT NOT NULL,
                        metric_value REAL NOT NULL,
                        metadata TEXT,
                        recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                logger.info("Base de datos inicializada correctamente")
                
        except sqlite3.Error as e:
            logger.error(f"Error inicializando base de datos: {e}")
            raise DatabaseConnectionException(str(e))
    
    def close(self):
        """Cerrar conexión"""
        if hasattr(self._local, 'connection') and self._local.connection:
            self._local.connection.close()
            self._local.connection = None


class Database:
    """Interfaz de base de datos para EtiquetadorZPL"""
    
    def __init__(self):
        # Obtener directorio de BD sin dependencia circular
        if os.name == 'nt':  # Windows
            base_dir = Path(os.environ.get('APPDATA', '.'))
        else:  # Linux/Mac
            base_dir = Path.home() / '.config'
        
        config_dir = base_dir / APP_NAME
        config_dir.mkdir(parents=True, exist_ok=True)
        
        db_path = config_dir / "etiquetador.db"
        
        # Inicializar conexión
        self.connection = DatabaseConnection(str(db_path))
        
        # Alias para compatibilidad
        self.db_path = db_path
    
    def add_job(
        self,
        filename: str,
        printer: str,
        content_type: str = 'zpl',
        copies: int = 1,
        file_size: int = 0,
        priority: int = 0,
        hostname: str = None,
        username: str = None
    ) -> Optional[int]:
        """Agregar nuevo trabajo"""
        try:
            # Obtener hostname y usuario si no se proporcionan
            if hostname is None:
                hostname = socket.gethostname()
            if username is None:
                username = os.environ.get('USERNAME', 'unknown')
            
            with self.connection.get_cursor() as cursor:
                cursor.execute("""
                    INSERT INTO jobs 
                    (filename, printer, content_type, copies, file_size, priority, status, hostname, username)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (filename, printer, content_type, copies, file_size, priority, JOB_STATUS['PENDING'], hostname, username))
                
                job_id = cursor.lastrowid
                logger.info(f"Trabajo {job_id} creado: {filename} -> {printer} (User: {username}@{hostname})")
                return job_id
                
        except sqlite3.Error as e:
            logger.error(f"Error agregando trabajo: {e}")
            return None
    
    def get_job(self, job_id: int) -> Optional[Dict[str, Any]]:
        """Obtener trabajo por ID"""
        try:
            with self.connection.get_cursor() as cursor:
                cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
                row = cursor.fetchone()
                
                if row:
                    return self._row_to_dict(cursor, row)
                return None
                
        except sqlite3.Error as e:
            logger.error(f"Error obteniendo trabajo {job_id}: {e}")
            return None
    
    def get_job_by_filename(self, filename: str) -> Optional[Dict[str, Any]]:
        """Obtener trabajo por nombre de archivo"""
        try:
            with self.connection.get_cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM jobs WHERE filename = ? ORDER BY created_at DESC LIMIT 1",
                    (filename,)
                )
                row = cursor.fetchone()
                
                if row:
                    return self._row_to_dict(cursor, row)
                return None
                
        except sqlite3.Error as e:
            logger.error(f"Error obteniendo trabajo por filename: {e}")
            return None
    
    def update_job_status(
        self,
        job_id: int,
        status: str,
        error_message: Optional[str] = None,
        processing_time: Optional[float] = None
    ) -> bool:
        """Actualizar estado del trabajo"""
        try:
            with self.connection.get_cursor() as cursor:
                # Construir query dinámicamente
                updates: List[str] = ["status = ?", "updated_at = CURRENT_TIMESTAMP"]
                params: List[Any] = [status]
                
                if error_message is not None:
                    updates.append("error_message = ?")
                    params.append(error_message)
                
                if processing_time is not None:
                    updates.append("processing_time = ?")
                    params.append(processing_time)
                
                # Agregar timestamp de completado si es estado final
                if status in [JOB_STATUS['COMPLETED'], JOB_STATUS['FAILED'], JOB_STATUS['CANCELLED']]:
                    updates.append("completed_at = CURRENT_TIMESTAMP")
                
                params.append(job_id)
                
                cursor.execute(f"""
                    UPDATE jobs 
                    SET {', '.join(updates)}
                    WHERE id = ?
                """, params)
                
                return cursor.rowcount > 0
                
        except sqlite3.Error as e:
            logger.error(f"Error actualizando trabajo {job_id}: {e}")
            return False
    
    def increment_retry_count(self, job_id: int) -> bool:
        """Incrementar contador de reintentos"""
        try:
            with self.connection.get_cursor() as cursor:
                cursor.execute("""
                    UPDATE jobs 
                    SET retry_count = retry_count + 1,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (job_id,))
                return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"Error incrementando retry count: {e}")
            return False
    
    def get_recent_jobs(self, limit: int = 20, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Obtener trabajos recientes"""
        try:
            with self.connection.get_cursor() as cursor:
                if status:
                    cursor.execute("""
                        SELECT * FROM jobs 
                        WHERE status = ?
                        ORDER BY priority DESC, created_at DESC 
                        LIMIT ?
                    """, (status, limit))
                else:
                    cursor.execute("""
                        SELECT * FROM jobs 
                        ORDER BY priority DESC, created_at DESC 
                        LIMIT ?
                    """, (limit,))
                
                rows = cursor.fetchall()
                return [self._row_to_dict(cursor, row) for row in rows]
                
        except sqlite3.Error as e:
            logger.error(f"Error obteniendo trabajos recientes: {e}")
            return []
    
    def get_pending_jobs(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Obtener trabajos pendientes ordenados por prioridad"""
        try:
            with self.connection.get_cursor() as cursor:
                cursor.execute("""
                    SELECT * FROM jobs 
                    WHERE status = ? AND retry_count < 3
                    ORDER BY priority DESC, created_at ASC 
                    LIMIT ?
                """, (JOB_STATUS['PENDING'], limit))
                
                rows = cursor.fetchall()
                return [self._row_to_dict(cursor, row) for row in rows]
                
        except sqlite3.Error as e:
            logger.error(f"Error obteniendo trabajos pendientes: {e}")
            return []
    
    def get_statistics(self) -> Dict[str, Any]:
        """Obtener estadísticas de trabajos"""
        try:
            with self.connection.get_cursor() as cursor:
                cursor.execute("""
                    SELECT 
                        COUNT(*) as total_jobs,
                        SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                        SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
                        SUM(CASE WHEN status = 'processing' THEN 1 ELSE 0 END) as processing,
                        SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
                        SUM(file_size) as total_bytes,
                        AVG(CASE WHEN status = 'completed' THEN processing_time END) as avg_processing_time,
                        COUNT(DISTINCT printer) as printer_count
                    FROM jobs
                """)
                row = cursor.fetchone()
                
                return {
                    'total_jobs': row[0] or 0,
                    'completed': row[1] or 0,
                    'failed': row[2] or 0,
                    'processing': row[3] or 0,
                    'pending': row[4] or 0,
                    'total_bytes': row[5] or 0,
                    'avg_processing_time': row[6] or 0,
                    'printer_count': row[7] or 0
                }
                
        except sqlite3.Error as e:
            logger.error(f"Error obteniendo estadísticas: {e}")
            return {
                'total_jobs': 0,
                'completed': 0,
                'failed': 0,
                'processing': 0,
                'pending': 0,
                'total_bytes': 0,
                'avg_processing_time': 0,
                'printer_count': 0
            }
    
    def get_user_statistics(self) -> List[Dict[str, Any]]:
        """Obtener estadísticas por usuario/equipo"""
        try:
            with self.connection.get_cursor() as cursor:
                cursor.execute("""
                    SELECT 
                        COALESCE(username, 'unknown') as username,
                        COALESCE(hostname, 'unknown') as hostname,
                        COUNT(*) as total,
                        SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                        SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed
                    FROM jobs
                    GROUP BY username, hostname
                    ORDER BY total DESC
                """)
                
                rows = cursor.fetchall()
                return [
                    {
                        'username': row[0],
                        'hostname': row[1],
                        'total': row[2],
                        'completed': row[3],
                        'failed': row[4]
                    }
                    for row in rows
                ]
                
        except sqlite3.Error as e:
            logger.error(f"Error obteniendo estadísticas por usuario: {e}")
            return []
    
    def get_printer_statistics(self) -> List[Dict[str, Any]]:
        """Obtener estadísticas por impresora"""
        try:
            with self.connection.get_cursor() as cursor:
                cursor.execute("""
                    SELECT 
                        printer,
                        COUNT(*) as total,
                        SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                        SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
                        AVG(CASE WHEN status = 'completed' THEN processing_time END) as avg_time
                    FROM jobs
                    GROUP BY printer
                    ORDER BY total DESC
                """)
                
                rows = cursor.fetchall()
                return [
                    {
                        'printer': row[0],
                        'total': row[1],
                        'completed': row[2],
                        'failed': row[3],
                        'avg_time': row[4] or 0
                    }
                    for row in rows
                ]
                
        except sqlite3.Error as e:
            logger.error(f"Error obteniendo estadísticas por impresora: {e}")
            return []
    
    def delete_old_jobs(self, days: int = 30) -> int:
        """Eliminar trabajos antiguos"""
        try:
            with self.connection.get_cursor() as cursor:
                cursor.execute("""
                    DELETE FROM jobs 
                    WHERE created_at < datetime('now', '-' || ? || ' days')
                    AND status IN ('completed', 'failed', 'cancelled')
                """, (days,))
                
                deleted = cursor.rowcount
                logger.info(f"Eliminados {deleted} trabajos antiguos")
                return deleted
                
        except sqlite3.Error as e:
            logger.error(f"Error eliminando trabajos antiguos: {e}")
            return 0
    
    def save_metric(self, metric_type: str, value: float, metadata: Optional[Dict] = None) -> bool:
        """Guardar métrica histórica"""
        try:
            with self.connection.get_cursor() as cursor:
                cursor.execute("""
                    INSERT INTO metrics_history (metric_type, metric_value, metadata)
                    VALUES (?, ?, ?)
                """, (metric_type, value, json.dumps(metadata) if metadata else None))
                return True
        except sqlite3.Error as e:
            logger.error(f"Error guardando métrica: {e}")
            return False
    
    def get_metrics_history(
        self,
        metric_type: Optional[str] = None,
        hours: int = 24,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Obtener historial de métricas"""
        try:
            with self.connection.get_cursor() as cursor:
                if metric_type:
                    cursor.execute("""
                        SELECT * FROM metrics_history
                        WHERE metric_type = ?
                        AND recorded_at > datetime('now', '-' || ? || ' hours')
                        ORDER BY recorded_at DESC
                        LIMIT ?
                    """, (metric_type, hours, limit))
                else:
                    cursor.execute("""
                        SELECT * FROM metrics_history
                        WHERE recorded_at > datetime('now', '-' || ? || ' hours')
                        ORDER BY recorded_at DESC
                        LIMIT ?
                    """, (hours, limit))
                
                rows = cursor.fetchall()
                return [
                    {
                        'id': row[0],
                        'metric_type': row[1],
                        'metric_value': row[2],
                        'metadata': json.loads(row[3]) if row[3] else None,
                        'recorded_at': row[4]
                    }
                    for row in rows
                ]
                
        except sqlite3.Error as e:
            logger.error(f"Error obteniendo historial de métricas: {e}")
            return []
    
    def _row_to_dict(self, cursor, row: Tuple) -> Dict[str, Any]:
        """Convertir fila a diccionario"""
        columns = [desc[0] for desc in cursor.description]
        return dict(zip(columns, row))
    
    def vacuum(self) -> bool:
        """Optimizar base de datos"""
        try:
            with self.connection.get_cursor() as cursor:
                cursor.execute("VACUUM")
                logger.info("Base de datos optimizada")
                return True
        except sqlite3.Error as e:
            logger.error(f"Error optimizando base de datos: {e}")
            return False
    
    def get_database_size(self) -> int:
        """Obtener tamaño de base de datos en bytes"""
        try:
            if Path(self.db_path).exists():
                return Path(self.db_path).stat().st_size
            return 0
        except Exception as e:
            logger.error(f"Error obteniendo tamaño de BD: {e}")
            return 0


# Instancia global
db = Database()


def get_database() -> Database:
    """Obtener instancia de base de datos"""
    return db
