"""
API optimizada para velocidad
"""

import http.server
import socketserver
import json
import socket
import time
import threading
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

# Agregar paths para imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root / "config"))

class FastAPIHandler(http.server.BaseHTTPRequestHandler):
    # Pool de hilos para procesamiento paralelo
    executor = ThreadPoolExecutor(max_workers=5)
    
    def log_message(self, format, *args):
        # Desactivar logs para velocidad
        pass
    
    def do_GET(self):
        try:
            if self.path == '/api/status':
                self.send_json_response({"status": "running", "fast": True})
            
            elif self.path == '/api/printers':
                # Cache de impresoras
                if not hasattr(self.__class__, '_printer_cache'):
                    from src.printer_utils import obtener_impresoras
                    self.__class__._printer_cache = obtener_impresoras()
                    self.__class__._cache_time = time.time()
                
                # Renovar cache cada 30 segundos
                if time.time() - self.__class__._cache_time > 30:
                    from src.printer_utils import obtener_impresoras
                    self.__class__._printer_cache = obtener_impresoras()
                    self.__class__._cache_time = time.time()
                
                self.send_json_response({
                    "printers": self.__class__._printer_cache,
                    "count": len(self.__class__._printer_cache)
                })
            
            elif self.path == '/api/jobs':
                # Solo últimos 20 trabajos para velocidad
                from src.database import db
                jobs = db.get_recent_jobs(20)
                self.send_json_response({"jobs": jobs, "count": len(jobs)})
            
            elif self.path == '/api/statistics':
                # Cache de estadísticas
                if not hasattr(self.__class__, '_stats_cache'):
                    from src.database import db
                    self.__class__._stats_cache = db.get_statistics()
                    self.__class__._stats_cache_time = time.time()
                
                # Renovar cada 60 segundos
                if time.time() - self.__class__._stats_cache_time > 60:
                    from src.database import db
                    self.__class__._stats_cache = db.get_statistics()
                    self.__class__._stats_cache_time = time.time()
                
                self.send_json_response(self.__class__._stats_cache)
            
            elif self.path == '/api/system/metrics':
                # Métricas del sistema
                from system_monitor import system_monitor
                metrics = system_monitor.collect_metrics()
                if metrics:
                    self.send_json_response(metrics)
                else:
                    self.send_json_response({"error": "No metrics available"}, 500)
            
            elif self.path == '/api/system/summary':
                # Resumen del sistema
                from system_monitor import system_monitor
                summary = system_monitor.get_summary()
                if summary:
                    self.send_json_response(summary)
                else:
                    self.send_json_response({"status": "no_data"})
            
            elif self.path.startswith('/api/jobs/'):
                # Obtener trabajo individual
                try:
                    job_id = int(self.path.split('/')[-1])
                    from database import db
                    job = db.get_job(job_id)
                    if job:
                        self.send_json_response(job)
                    else:
                        self.send_json_response({"error": "Job not found"}, 404)
                except ValueError:
                    self.send_json_response({"error": "Invalid job ID"}, 400)
            
            elif self.path == '/' or self.path == '':
                # Redirigir a dashboard
                self.send_response(302)
                self.send_header('Location', '/web/index.html')
                self.end_headers()
            
            elif self.path == '/api/config/notifications':
                # Cargar configuración de notificaciones
                try:
                    from get_writable_path import get_readable_config_path
                    config_path = get_readable_config_path('notification_config.json')
                    
                    if config_path:
                        with open(config_path, 'r') as f:
                            config = json.load(f)
                        self.send_json_response(config)
                    else:
                        # Configuración por defecto
                        default_config = {
                            "desktop_enabled": True,
                            "notify_on_error": True,
                            "notify_on_success": False,
                            "email_enabled": False,
                            "email_config": {}
                        }
                        self.send_json_response(default_config)
                        
                except Exception as e:
                    self.send_json_response({"error": str(e)}, 500)
            
            elif self.path == '/api/config/backup':
                # Cargar configuración de backup
                try:
                    from get_writable_path import get_readable_config_path
                    config_path = get_readable_config_path('backup_config.json')
                    
                    if config_path:
                        with open(config_path, 'r') as f:
                            config = json.load(f)
                        self.send_json_response(config)
                    else:
                        # Configuración por defecto
                        default_config = {
                            "enabled": True,
                            "daily_backup": True,
                            "weekly_backup": True,
                            "keep_daily": 7,
                            "keep_weekly": 4
                        }
                        self.send_json_response(default_config)
                        
                except Exception as e:
                    self.send_json_response({"error": str(e)}, 500)
            
            elif self.path.startswith('/web/'):
                self.serve_web_file_fast()
            
            else:
                self.send_error(404)
                
        except Exception as e:
            self.send_json_response({"error": str(e)}, 500)
    
    def do_POST(self):
        try:
            if self.path == '/api/config/notifications':
                # Guardar configuración de notificaciones
                try:
                    content_length = int(self.headers.get('Content-Length', 0))
                    if content_length > 0:
                        post_data = self.rfile.read(content_length)
                        data = json.loads(post_data.decode('utf-8'))
                    
                    from get_writable_path import get_writable_config_path
                    config_path = get_writable_config_path('notification_config.json')
                    
                    with open(config_path, 'w') as f:
                        json.dump(data, f, indent=2)
                    
                    self.send_json_response({"success": True, "path": config_path})
                    
                except Exception as e:
                    self.send_json_response({"error": str(e)}, 500)
            
            elif self.path == '/api/config/backup':
                # Guardar configuración de backup
                try:
                    content_length = int(self.headers.get('Content-Length', 0))
                    if content_length > 0:
                        post_data = self.rfile.read(content_length)
                        data = json.loads(post_data.decode('utf-8'))
                    
                    from get_writable_path import get_writable_config_path
                    config_path = get_writable_config_path('backup_config.json')
                    
                    with open(config_path, 'w') as f:
                        json.dump(data, f, indent=2)
                    
                    self.send_json_response({"success": True, "path": config_path})
                    
                except Exception as e:
                    self.send_json_response({"error": str(e)}, 500)
            
            elif self.path == '/api/process-file':
                content_length = int(self.headers.get('Content-Length', 0))
                if content_length > 0:
                    post_data = self.rfile.read(content_length)
                    data = json.loads(post_data.decode('utf-8'))
                
                # Crear trabajo rápidamente
                from database import db
                job_id = db.add_job(
                    filename=data.get('filename', f'job_{int(time.time())}'),
                    printer=data.get('printer', 'default'),
                    content_type='zpl',
                    copies=data.get('copies', 1),
                    file_size=len(data.get('content', ''))
                )
                
                # Procesar en background sin bloquear
                self.executor.submit(
                    self.process_job_fast,
                    job_id,
                    data.get('content', ''),
                    data.get('printer', ''),
                    data.get('copies', 1)
                )
                
                # Respuesta inmediata
                self.send_json_response({"job_id": job_id, "status": "processing"})
            
            else:
                self.send_error(404)
                
        except Exception as e:
            self.send_json_response({"error": str(e)}, 500)
    
    def process_job_fast(self, job_id, content, printer, copies):
        """Procesamiento rápido de trabajos"""
        start_time = time.time()
        
        try:
            from database import db
            db.update_job_status(job_id, 'processing')
            
            # Validación de impresora no configurada
            if printer == "IMPRESORA_NO_CONFIGURADA":
                processing_time = time.time() - start_time
                db.update_job_status(job_id, 'failed', 'Impresora no configurada', processing_time)
                self.send_notification(job_id, 'failed', 'Impresora no configurada')
                return
            
            # Validar que la impresora existe
            from printer_utils import obtener_impresoras
            impresoras_disponibles = obtener_impresoras()
            
            if printer not in impresoras_disponibles:
                processing_time = time.time() - start_time
                error_msg = f'Impresora "{printer}" no encontrada'
                db.update_job_status(job_id, 'failed', error_msg, processing_time)
                self.send_notification(job_id, 'failed', error_msg)
                print(f"Job {job_id} failed: {error_msg}")
                return
            
            # Procesamiento real (simulado)
            time.sleep(0.1)
            
            # Marcar como completado
            processing_time = time.time() - start_time
            db.update_job_status(job_id, 'completed', None, processing_time)
            self.send_notification(job_id, 'completed', None)
            print(f"Job {job_id} completed ({processing_time:.2f}s)")
            
        except Exception as e:
            processing_time = time.time() - start_time
            from database import db
            error_msg = str(e)
            db.update_job_status(job_id, 'failed', error_msg, processing_time)
            self.send_notification(job_id, 'failed', error_msg)
            print(f"Job {job_id} failed: {error_msg}")
    
    def send_notification(self, job_id, status, error_msg):
        """Enviar notificación"""
        try:
            from notifications import notification_manager
            from database import db
            
            job = db.get_job(job_id)
            if job:
                notification_manager.notify_job_completed(
                    job_id, status, job['filename'], job['printer'], error_msg
                )
        except Exception as e:
            print(f"Error enviando notificación: {e}")
    
    def serve_web_file_fast(self):
        """Servir archivos web optimizado"""
        try:
            file_path = self.path[1:]  # Remover /
            if file_path == 'web/' or file_path == 'web':
                file_path = 'web/index.html'
            
            from pathlib import Path
            full_path = Path(file_path)
            
            if full_path.exists() and full_path.is_file():
                # Cache de archivos estáticos
                cache_key = str(full_path)
                if not hasattr(self.__class__, '_file_cache'):
                    self.__class__._file_cache = {}
                
                if cache_key not in self.__class__._file_cache:
                    with open(full_path, 'rb') as f:
                        self.__class__._file_cache[cache_key] = f.read()
                
                content_type = 'text/html' if file_path.endswith('.html') else 'text/plain'
                
                self.send_response(200)
                self.send_header('Content-type', content_type)
                self.send_header('Cache-Control', 'max-age=3600')  # Cache 1 hora
                self.end_headers()
                
                self.wfile.write(self.__class__._file_cache[cache_key])
            else:
                self.send_error(404)
        except:
            self.send_error(500)
    
    def send_json_response(self, data, status=200):
        try:
            response_data = json.dumps(data, separators=(',', ':')).encode('utf-8')  # JSON compacto
            self.send_response(status)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            self.wfile.write(response_data)
        except:
            pass

class FastTCPServer(socketserver.TCPServer):
    """Servidor TCP optimizado"""
    allow_reuse_address = True
    request_queue_size = 10
    
    def server_bind(self):
        # Optimizaciones de socket
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, 'SO_REUSEPORT'):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        super().server_bind()

def find_free_port():
    """Encontrar puerto libre"""
    for port in range(8002, 8010):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('', port))
                return port
        except:
            continue
    return 8002

def start_fast_api():
    """Iniciar API rápida"""
    port = find_free_port()
    
    try:
        # Guardar puerto
        with open('api_port.txt', 'w') as f:
            f.write(str(port))
        
        # Inicializar cache
        FastAPIHandler._printer_cache = []
        FastAPIHandler._cache_time = 0
        FastAPIHandler._stats_cache = {}
        FastAPIHandler._stats_cache_time = 0
        FastAPIHandler._file_cache = {}
        
        with FastTCPServer(("", port), FastAPIHandler) as httpd:
            print(f"API RAPIDA ejecutandose en puerto {port}")
            print(f"Dashboard: http://localhost:{port}/web/")
            
            # Inicializar base de datos en background
            threading.Thread(target=lambda: __import__('src.database'), daemon=True).start()
            
            httpd.serve_forever()
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    start_fast_api()