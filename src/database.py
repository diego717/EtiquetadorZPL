"""
Base de datos mejorada para EtiquetadorZPL
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path

class EtiquetadorDB:
    def __init__(self, db_path="etiquetador.db"):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        """Inicializar base de datos"""
        conn = sqlite3.connect(self.db_path)
        
        # Tabla de trabajos de impresión
        conn.execute('''
            CREATE TABLE IF NOT EXISTS print_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                printer TEXT NOT NULL,
                content_type TEXT DEFAULT 'zpl',
                status TEXT DEFAULT 'pending',
                copies INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                error_message TEXT,
                file_size INTEGER,
                processing_time REAL
            )
        ''')
        
        # Tabla de configuraciones
        conn.execute('''
            CREATE TABLE IF NOT EXISTS configurations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                config_data TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Tabla de estadísticas
        conn.execute('''
            CREATE TABLE IF NOT EXISTS statistics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                printer TEXT NOT NULL,
                jobs_count INTEGER DEFAULT 0,
                success_count INTEGER DEFAULT 0,
                error_count INTEGER DEFAULT 0,
                total_pages INTEGER DEFAULT 0,
                UNIQUE(date, printer)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def add_job(self, filename, printer, content_type='zpl', copies=1, file_size=0):
        """Agregar trabajo de impresión"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute('''
            INSERT INTO print_jobs (filename, printer, content_type, copies, file_size)
            VALUES (?, ?, ?, ?, ?)
        ''', (filename, printer, content_type, copies, file_size))
        job_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return job_id
    
    def update_job_status(self, job_id, status, error_message=None, processing_time=None):
        """Actualizar estado del trabajo"""
        conn = sqlite3.connect(self.db_path)
        
        if status == 'processing':
            conn.execute('''
                UPDATE print_jobs 
                SET status = ?, started_at = CURRENT_TIMESTAMP 
                WHERE id = ?
            ''', (status, job_id))
        elif status in ['completed', 'failed']:
            conn.execute('''
                UPDATE print_jobs 
                SET status = ?, completed_at = CURRENT_TIMESTAMP, 
                    error_message = ?, processing_time = ?
                WHERE id = ?
            ''', (status, error_message, processing_time, job_id))
        
        conn.commit()
        conn.close()
    
    def get_job(self, job_id):
        """Obtener trabajo por ID"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute('SELECT * FROM print_jobs WHERE id = ?', (job_id,))
        job = cursor.fetchone()
        conn.close()
        return dict(job) if job else None
    
    def get_recent_jobs(self, limit=50):
        """Obtener trabajos recientes"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute('''
            SELECT * FROM print_jobs 
            ORDER BY created_at DESC 
            LIMIT ?
        ''', (limit,))
        jobs = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return jobs
    
    def get_statistics(self, days=7):
        """Obtener estadísticas"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        
        # Estadísticas generales
        cursor = conn.execute('''
            SELECT 
                COUNT(*) as total_jobs,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
                SUM(CASE WHEN status = 'processing' THEN 1 ELSE 0 END) as processing,
                AVG(processing_time) as avg_processing_time
            FROM print_jobs 
            WHERE created_at >= datetime('now', '-{} days')
        '''.format(days))
        
        stats = dict(cursor.fetchone())
        
        # Por impresora
        cursor = conn.execute('''
            SELECT 
                printer,
                COUNT(*) as jobs,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as success
            FROM print_jobs 
            WHERE created_at >= datetime('now', '-{} days')
            GROUP BY printer
        '''.format(days))
        
        stats['by_printer'] = [dict(row) for row in cursor.fetchall()]
        
        conn.close()
        return stats
    
    def save_config(self, name, config_data):
        """Guardar configuración"""
        conn = sqlite3.connect(self.db_path)
        conn.execute('''
            INSERT OR REPLACE INTO configurations (name, config_data, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
        ''', (name, json.dumps(config_data)))
        conn.commit()
        conn.close()
    
    def load_config(self, name):
        """Cargar configuración"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute('SELECT config_data FROM configurations WHERE name = ?', (name,))
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return json.loads(result[0])
        return None

# Instancia global
db = EtiquetadorDB()