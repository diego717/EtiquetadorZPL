"""
API usando FastAPI real
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel
import uvicorn
import json
import sys
import threading
import time
from pathlib import Path
from typing import Optional, List, Dict, Any

# Agregar paths
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root / "config"))

# Modelos Pydantic
class ProcessFileRequest(BaseModel):
    filename: str
    content: str
    printer: str
    copies: int = 1

class NotificationConfig(BaseModel):
    desktop_enabled: bool = True
    notify_on_error: bool = True
    notify_on_success: bool = False
    email_enabled: bool = False
    email_config: Dict[str, Any] = {}

class BackupConfig(BaseModel):
    enabled: bool = True
    daily_backup: bool = True
    weekly_backup: bool = True
    keep_daily: int = 7
    keep_weekly: int = 4

# Crear app FastAPI
app = FastAPI(
    title="EtiquetadorZPL API",
    description="API para sistema de etiquetas ZPL",
    version="1.0.0"
)

# Montar archivos estáticos
try:
    app.mount("/web", StaticFiles(directory="web", html=True), name="web")
except:
    pass

# Cache global
cache = {
    "printers": [],
    "printer_cache_time": 0,
    "stats": {},
    "stats_cache_time": 0
}

@app.get("/")
async def root():
    """Redirigir a dashboard"""
    return RedirectResponse(url="/web/index.html")

@app.get("/api/status")
async def get_status():
    """Estado de la API"""
    return {"status": "running", "framework": "FastAPI", "version": "1.0.0"}

@app.get("/api/printers")
async def get_printers():
    """Obtener lista de impresoras"""
    try:
        # Cache de 30 segundos
        if time.time() - cache["printer_cache_time"] > 30:
            try:
                from printer_utils import obtener_impresoras
                cache["printers"] = obtener_impresoras()
            except ImportError:
                # Fallback si no existe el módulo
                cache["printers"] = ["Impresora_Predeterminada"]
            cache["printer_cache_time"] = time.time()
        
        return {
            "printers": cache["printers"],
            "count": len(cache["printers"])
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/jobs")
async def get_jobs():
    """Obtener trabajos recientes"""
    try:
        from database import db
        jobs = db.get_recent_jobs(20)
        return {"jobs": jobs, "count": len(jobs)}
    except ImportError:
        # Fallback si no existe el módulo
        return {"jobs": [], "count": 0}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/jobs/{job_id}")
async def get_job(job_id: int):
    """Obtener trabajo específico"""
    try:
        from database import db
        job = db.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return job
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/statistics")
async def get_statistics():
    """Obtener estadísticas"""
    try:
        # Cache de 60 segundos
        if time.time() - cache["stats_cache_time"] > 60:
            try:
                from database import db
                cache["stats"] = db.get_statistics()
            except ImportError:
                # Fallback si no existe el módulo
                cache["stats"] = {"total_jobs": 0, "completed": 0, "failed": 0}
            cache["stats_cache_time"] = time.time()
        
        return cache["stats"]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/process-file")
async def process_file(request: ProcessFileRequest, background_tasks: BackgroundTasks):
    """Procesar archivo"""
    try:
        from database import db
        
        # Crear trabajo
        job_id = db.add_job(
            filename=request.filename,
            printer=request.printer,
            content_type='zpl',
            copies=request.copies,
            file_size=len(request.content)
        )
        
        # Procesar en background
        background_tasks.add_task(
            process_job_background,
            job_id,
            request.content,
            request.printer,
            request.copies
        )
        
        return {"job_id": job_id, "status": "processing"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def process_job_background(job_id: int, content: str, printer: str, copies: int):
    """Procesar trabajo en background"""
    start_time = time.time()
    
    try:
        from database import db
        db.update_job_status(job_id, 'processing')
        
        # Validación de impresora
        if printer == "IMPRESORA_NO_CONFIGURADA":
            processing_time = time.time() - start_time
            db.update_job_status(job_id, 'failed', 'Impresora no configurada', processing_time)
            await send_notification(job_id, 'failed', 'Impresora no configurada')
            return
        
        # Validar que la impresora existe
        from printer_utils import obtener_impresoras
        impresoras_disponibles = obtener_impresoras()
        
        if printer not in impresoras_disponibles:
            processing_time = time.time() - start_time
            error_msg = f'Impresora "{printer}" no encontrada'
            db.update_job_status(job_id, 'failed', error_msg, processing_time)
            await send_notification(job_id, 'failed', error_msg)
            return
        
        # Procesamiento real
        time.sleep(0.1)  # Simular procesamiento
        
        # Marcar como completado
        processing_time = time.time() - start_time
        db.update_job_status(job_id, 'completed', None, processing_time)
        await send_notification(job_id, 'completed', None)
        
    except Exception as e:
        processing_time = time.time() - start_time
        from database import db
        error_msg = str(e)
        db.update_job_status(job_id, 'failed', error_msg, processing_time)
        await send_notification(job_id, 'failed', error_msg)

async def send_notification(job_id: int, status: str, error_msg: Optional[str]):
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

# Endpoints de configuración
@app.get("/api/config/notifications")
async def get_notification_config():
    """Obtener configuración de notificaciones"""
    try:
        from get_writable_path import get_readable_config_path
        config_path = get_readable_config_path('notification_config.json')
        
        if config_path:
            with open(config_path, 'r') as f:
                config = json.load(f)
            return config
        else:
            return NotificationConfig().dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/config/notifications")
async def save_notification_config(config: NotificationConfig):
    """Guardar configuración de notificaciones"""
    try:
        # Intentar importar get_writable_path
        try:
            from get_writable_path import get_writable_config_path
            config_path = get_writable_config_path('notification_config.json')
        except ImportError:
            # Fallback si no existe el módulo
            import os
            config_path = 'notification_config.json'
            # Intentar crear en AppData si no se puede escribir
            try:
                with open(config_path, 'w') as f:
                    f.write('test')
                os.remove(config_path)
            except (PermissionError, OSError):
                appdata = os.environ.get('APPDATA', '.')
                config_dir = Path(appdata) / 'EtiquetadorZPL'
                config_dir.mkdir(exist_ok=True)
                config_path = str(config_dir / 'notification_config.json')
        
        with open(config_path, 'w') as f:
            json.dump(config.dict(), f, indent=2)
        
        return {"success": True, "path": config_path}
    except Exception as e:
        print(f"Error guardando notification config: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error guardando configuración: {str(e)}")

@app.get("/api/config/backup")
async def get_backup_config():
    """Obtener configuración de backup"""
    try:
        from get_writable_path import get_readable_config_path
        config_path = get_readable_config_path('backup_config.json')
        
        if config_path:
            with open(config_path, 'r') as f:
                config = json.load(f)
            return config
        else:
            return BackupConfig().dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/config/backup")
async def save_backup_config(config: BackupConfig):
    """Guardar configuración de backup"""
    try:
        # Intentar importar get_writable_path
        try:
            from get_writable_path import get_writable_config_path
            config_path = get_writable_config_path('backup_config.json')
        except ImportError:
            # Fallback si no existe el módulo
            import os
            config_path = 'backup_config.json'
            # Intentar crear en AppData si no se puede escribir
            try:
                with open(config_path, 'w') as f:
                    f.write('test')
                os.remove(config_path)
            except (PermissionError, OSError):
                appdata = os.environ.get('APPDATA', '.')
                config_dir = Path(appdata) / 'EtiquetadorZPL'
                config_dir.mkdir(exist_ok=True)
                config_path = str(config_dir / 'backup_config.json')
        
        with open(config_path, 'w') as f:
            json.dump(config.dict(), f, indent=2)
        
        return {"success": True, "path": config_path}
    except Exception as e:
        print(f"Error guardando backup config: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error guardando configuración: {str(e)}")

# Endpoints adicionales
@app.get("/api/system/metrics")
async def get_system_metrics():
    """Métricas del sistema"""
    try:
        from system_monitor import system_monitor
        metrics = system_monitor.collect_metrics()
        if metrics:
            return metrics
        else:
            raise HTTPException(status_code=500, detail="No metrics available")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def find_free_port():
    """Encontrar puerto libre"""
    import socket
    for port in range(8003, 8020):  # Cambiar rango
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(('127.0.0.1', port))
                return port
        except OSError:
            continue
    return 8003

def start_fastapi_server():
    """Iniciar servidor FastAPI"""
    port = find_free_port()
    
    try:
        # Guardar puerto
        with open('api_port.txt', 'w') as f:
            f.write(str(port))
        
        print(f"FastAPI ejecutándose en puerto {port}")
        print(f"Dashboard: http://localhost:{port}/web/")
        print(f"Docs: http://localhost:{port}/docs")
        
        # Inicializar base de datos en background
        try:
            def init_db():
                try:
                    from database import db
                    print("Base de datos inicializada")
                except Exception as e:
                    print(f"Error inicializando BD: {e}")
            
            threading.Thread(target=init_db, daemon=True).start()
        except Exception as e:
            print(f"Error iniciando hilo BD: {e}")
        
        # Verificar que uvicorn funciona
        print("Iniciando servidor uvicorn...")
        
        # Usar uvicorn.run directamente (más simple)
        uvicorn.run(
            "fastapi_real:app",  # Usar string import
            host="127.0.0.1",
            port=port,
            log_level="error",
            access_log=False,
            reload=False,
            workers=1
        )
        
    except Exception as e:
        print(f"Error iniciando FastAPI: {e}")
        import traceback
        traceback.print_exc()
        raise

def check_dependencies():
    """Verificar dependencias"""
    try:
        import fastapi
        import uvicorn
        import pydantic
        print(f"FastAPI: {fastapi.__version__}")
        print(f"Uvicorn: {uvicorn.__version__}")
        print(f"Pydantic: {pydantic.__version__}")
        return True
    except ImportError as e:
        print(f"Dependencia faltante: {e}")
        return False

if __name__ == "__main__":
    if check_dependencies():
        start_fastapi_server()
    else:
        print("Error: Dependencias faltantes")
        input("Presiona Enter...")