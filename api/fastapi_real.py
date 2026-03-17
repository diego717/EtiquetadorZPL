"""
API usando FastAPI real
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel
import uvicorn
import base64
import hashlib
import json
import os
import socket
import sys
import threading
import time
import logging
import tempfile
from logging.handlers import RotatingFileHandler
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

# Incluir endpoints de Electron
try:
    from electron_endpoints import router as electron_router
    app.include_router(electron_router)
except ImportError:
    print("ADVERTENCIA: Endpoints de Electron no disponibles")

# Incluir endpoints de Mercado Libre
try:
    from mercadolibre_endpoints import router as mercadolibre_router
    app.include_router(mercadolibre_router)
except ImportError as e:
    print(f"ADVERTENCIA: Endpoints de Mercado Libre no disponibles: {e}")

# Incluir endpoints de Administrado
try:
    from administrado_endpoints import router as administrado_router
    app.include_router(administrado_router)
except ImportError as e:
    print(f"ADVERTENCIA: Endpoints de Administrado no disponibles: {e}")

# Incluir endpoints de Odoo
try:
    from odoo_endpoints import router as odoo_router
    app.include_router(odoo_router)
except ImportError as e:
    print(f"ADVERTENCIA: Endpoints de Odoo no disponibles: {e}")

# Incluir endpoints de Auth Cloud (separado del flujo legacy)
try:
    from auth_endpoints import router as auth_router
    app.include_router(auth_router)
except ImportError as e:
    print(f"ADVERTENCIA: Endpoints de Auth no disponibles: {e}")

# Incluir endpoints de Cola Cloud (separado del flujo legacy)
try:
    from cloud_print_endpoints import router as cloud_print_router
    app.include_router(cloud_print_router)
except ImportError as e:
    print(f"ADVERTENCIA: Endpoints de Cola Cloud no disponibles: {e}")

# Montar archivos estáticos
try:
    if Path("web").exists():
        app.mount("/web", StaticFiles(directory="web", html=True), name="web")
        print("Archivos web montados correctamente")
    else:
        print("ADVERTENCIA: Directorio 'web' no encontrado")
except Exception as e:
    print(f"Error montando archivos web: {e}")

# Cache global
cache = {
    "printers": [],
    "printer_cache_time": 0,
    "stats": {},
    "stats_cache_time": 0
}

PNG_BASE64_PREFIX = "PNG_BASE64:"


def _build_print_audit_logger() -> logging.Logger:
    """Create a dedicated logger for print dispatch diagnostics."""
    logger = logging.getLogger("print_dispatch_audit")
    if logger.handlers:
        return logger

    log_dir = project_root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        log_dir / "print_dispatch.log",
        maxBytes=2 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s | %(message)s"))
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    logger.propagate = False
    return logger


PRINT_AUDIT_LOGGER = _build_print_audit_logger()


@app.on_event("startup")
async def startup_events():
    """Iniciar workers opcionales de automatizacion."""
    try:
        from odoo_automation import odoo_automation_worker

        odoo_automation_worker.start()
    except Exception as e:
        print(f"ADVERTENCIA: No se pudo iniciar worker Odoo: {e}")


@app.on_event("shutdown")
async def shutdown_events():
    """Detener workers opcionales de automatizacion."""
    try:
        from odoo_automation import odoo_automation_worker

        odoo_automation_worker.stop()
    except Exception as e:
        print(f"ADVERTENCIA: No se pudo detener worker Odoo: {e}")

@app.get("/")
async def root():
    """Redirigir a dashboard"""
    return RedirectResponse(url="/web/config.html#administrado")

@app.get("/api/status")
async def get_status():
    """Estado de la API"""
    return {"status": "running", "framework": "FastAPI", "version": "1.0.0"}

@app.get("/api/printers")
async def get_printers():
    """Obtener lista de impresoras (todas)"""
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

@app.get("/api/printers/network")
async def get_network_printers_endpoint():
    """Obtener impresoras de red disponibles"""
    try:
        from print_queue_monitor import get_network_printers as get_net_printers, get_printer_status
        
        printers = get_net_printers()
        printer_status = []
        
        for printer in printers:
            status = get_printer_status(printer)
            if status:
                printer_status.append(status)
        
        return {
            "printers": printers,
            "printer_status": printer_status,
            "count": len(printers)
        }
    except Exception as e:
        print(f"Error en get_network_printers_endpoint: {e}")
        return {"printers": [], "count": 0, "error": str(e)}

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
        print(f"Error en get_jobs: {e}")
        return {"jobs": [], "count": 0, "error": "Base de datos no disponible"}

@app.get("/api/jobs/spooler")
async def get_spooler_jobs(max_jobs: int = 20):
    """Obtener trabajos del spooler de Windows (impresoras de red)"""
    try:
        from print_queue_monitor import get_recent_print_jobs_from_network, get_network_printers
        
        # Obtener impresoras de red
        network_printers = get_network_printers()
        
        # Obtener trabajos recientes
        jobs = get_recent_print_jobs_from_network(max_jobs)
        
        return {
            "jobs": jobs,
            "count": len(jobs),
            "network_printers": network_printers,
            "source": "Windows Print Spooler"
        }
    except Exception as e:
        print(f"Error en get_spooler_jobs: {e}")
        return {"jobs": [], "count": 0, "error": str(e)}

@app.get("/api/printers/{printer_name}/jobs")
async def get_printer_jobs(printer_name: str, max_jobs: int = 20):
    """Obtener trabajos de una impresora específica"""
    try:
        from print_queue_monitor import get_print_jobs_from_spooler
        
        jobs = get_print_jobs_from_spooler(printer_name, max_jobs)
        
        return {
            "printer_name": printer_name,
            "jobs": jobs,
            "count": len(jobs)
        }
    except Exception as e:
        print(f"Error en get_printer_jobs: {e}")
        return {"printer_name": printer_name, "jobs": [], "count": 0, "error": str(e)}

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
            except Exception as e:
                print(f"Error BD en statistics: {e}")
                cache["stats"] = {"total_jobs": 0, "completed": 0, "failed": 0, "error": "BD no disponible"}
            cache["stats_cache_time"] = time.time()
        
        return cache["stats"]
    except Exception as e:
        print(f"Error en get_statistics: {e}")
        return {"total_jobs": 0, "completed": 0, "failed": 0, "error": "Estadísticas no disponibles"}

@app.get("/api/statistics/users")
async def get_user_statistics():
    """Obtener estadísticas por usuario/equipo"""
    try:
        from database import db
        users = db.get_user_statistics()
        return {"users": users, "count": len(users)}
    except Exception as e:
        print(f"Error en get_user_statistics: {e}")
        return {"users": [], "count": 0, "error": str(e)}

@app.post("/api/process-file")
async def process_file(request: ProcessFileRequest, background_tasks: BackgroundTasks):
    """Procesar archivo"""
    try:
        logging.info(f"Procesando archivo: {request.filename} -> {request.printer} ({request.copies} copias)")
        
        # Intentar usar base de datos
        try:
            from database import db
            content_type = "png" if request.content.startswith(PNG_BASE64_PREFIX) else "zpl"
            job_id = db.add_job(
                filename=request.filename,
                printer=request.printer,
                content_type=content_type,
                copies=request.copies,
                file_size=len(request.content)
            )
            logging.info(f"Trabajo creado en BD con ID: {job_id}")
        except Exception as e:
            logging.warning(f"BD no disponible, usando ID temporal: {e}")
            import random
            job_id = random.randint(1000, 9999)
        
        # Procesar en background
        background_tasks.add_task(
            process_job_background,
            job_id,
            request.content,
            request.printer,
            request.copies
        )
        
        logging.info(f"Trabajo {job_id} enviado a procesamiento en background")
        return {"job_id": job_id, "status": "processing"}
    except Exception as e:
        logging.error(f"Error en process_file: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def _print_job_content(content: str, printer: str, copies: int) -> tuple[bool, Optional[str]]:
    """Imprime contenido recibido por API. Soporta ZPL y PNG base64."""
    safe_copies = max(1, int(copies or 1))

    if content.startswith(PNG_BASE64_PREFIX):
        encoded_png = content[len(PNG_BASE64_PREFIX):].strip()
        if not encoded_png:
            return False, "Contenido PNG vacio"

        try:
            png_bytes = base64.b64decode(encoded_png, validate=True)
        except Exception as exc:
            return False, f"PNG base64 invalido: {exc}"

        if not png_bytes:
            return False, "Contenido PNG vacio"

        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as temp_file:
                temp_file.write(png_bytes)
                temp_path = temp_file.name

            from pdf_printer import imprimir_png
            for copy_idx in range(safe_copies):
                if not imprimir_png(temp_path, printer):
                    return False, f"Fallo al imprimir PNG en copia {copy_idx + 1}/{safe_copies}"
            return True, None
        except Exception as exc:
            return False, f"Error imprimiendo PNG: {exc}"
        finally:
            if temp_path:
                try:
                    Path(temp_path).unlink(missing_ok=True)
                except Exception:
                    pass

    if not content.strip():
        return False, "Contenido ZPL vacio"

    try:
        from printer import imprimir_zpl_directo
        if not imprimir_zpl_directo(content, printer, safe_copies):
            return False, "Fallo al imprimir contenido ZPL"
        return True, None
    except Exception as exc:
        return False, f"Error imprimiendo ZPL: {exc}"


def _content_kind(content: str) -> str:
    return "png" if content.startswith(PNG_BASE64_PREFIX) else "zpl"


def _content_digest(content: str) -> str:
    try:
        return hashlib.sha1(content.encode("utf-8", errors="ignore")).hexdigest()[:16]
    except Exception:
        return "unavailable"


def _spooler_snapshot(printer: str, max_jobs: int = 5) -> Dict[str, Any]:
    normalized_printer = (printer or "").strip()
    snapshot: Dict[str, Any] = {
        "printer": normalized_printer,
        "job_count": 0,
        "jobs": [],
        "error": None,
    }

    try:
        from print_queue_monitor import get_print_jobs_from_spooler

        jobs = get_print_jobs_from_spooler(normalized_printer or None, max_jobs=max_jobs)
        snapshot["job_count"] = len(jobs)
        snapshot["jobs"] = [
            {
                "job_id": job.get("job_id"),
                "document_name": job.get("document_name"),
                "status": job.get("status"),
                "submitted_time": job.get("submitted_time"),
                "size": job.get("size"),
            }
            for job in jobs
        ]
    except Exception as exc:
        snapshot["error"] = str(exc)

    return snapshot


def _log_print_dispatch(
    *,
    job_id: int,
    printer: str,
    copies: int,
    content: str,
    result: str,
    error: Optional[str] = None,
    processing_time: Optional[float] = None,
) -> None:
    payload = {
        "job_id": job_id,
        "printer": printer,
        "copies": max(1, int(copies or 1)),
        "content_type": _content_kind(content),
        "content_length": len(content),
        "content_sha1_16": _content_digest(content),
        "result": result,
        "error": error,
        "processing_time_sec": round(processing_time, 4) if processing_time is not None else None,
        "spooler": _spooler_snapshot(printer, max_jobs=5),
    }

    try:
        PRINT_AUDIT_LOGGER.info(json.dumps(payload, ensure_ascii=False))
    except Exception as exc:
        logging.warning(f"No se pudo registrar audit log de impresion para job {job_id}: {exc}")

async def process_job_background(job_id: int, content: str, printer: str, copies: int):
    """Procesar trabajo en background"""
    start_time = time.time()
    logging.info(f"Iniciando procesamiento background del trabajo {job_id}")
    
    try:
        from database import db
        db.update_job_status(job_id, 'processing')
        logging.info(f"Trabajo {job_id} marcado como 'processing'")
        
        # Validación de impresora
        if not printer or printer == "IMPRESORA_NO_CONFIGURADA":
            processing_time = time.time() - start_time
            logging.warning(f"Trabajo {job_id} fallido: Impresora no configurada")
            db.update_job_status(job_id, 'failed', 'Impresora no configurada', processing_time)
            await send_notification(job_id, 'failed', 'Impresora no configurada')
            _log_print_dispatch(
                job_id=job_id,
                printer=printer,
                copies=copies,
                content=content,
                result="failed_no_printer",
                error="Impresora no configurada",
                processing_time=processing_time,
            )
            return
        
        # Validar que la impresora existe
        try:
            from printer_utils import obtener_impresoras
            impresoras_disponibles = obtener_impresoras()
            logging.info(f"Impresoras disponibles: {impresoras_disponibles}")
            
            if printer not in impresoras_disponibles:
                logging.warning(
                    f'Impresora "{printer}" no encontrada en listado local. '
                    "Se intentara imprimir de todas formas."
                )
        except Exception as e:
            logging.warning(f"No se pudo verificar impresoras: {e}. Continuando...")
        
        # Procesamiento real
        logging.info(f"Procesando trabajo {job_id} en impresora {printer}")
        print_ok, print_error = _print_job_content(content, printer, copies)
        if not print_ok:
            processing_time = time.time() - start_time
            error_msg = print_error or "Error de impresion desconocido"
            logging.error(f"Trabajo {job_id} fallido: {error_msg}")
            db.update_job_status(job_id, 'failed', error_msg, processing_time)
            await send_notification(job_id, 'failed', error_msg)
            _log_print_dispatch(
                job_id=job_id,
                printer=printer,
                copies=copies,
                content=content,
                result="failed_print",
                error=error_msg,
                processing_time=processing_time,
            )
            return
        
        # Marcar como completado
        processing_time = time.time() - start_time
        logging.info(f"Trabajo {job_id} completado en {processing_time:.2f}s")
        db.update_job_status(job_id, 'completed', None, processing_time)
        await send_notification(job_id, 'completed', None)
        _log_print_dispatch(
            job_id=job_id,
            printer=printer,
            copies=copies,
            content=content,
            result="completed",
            processing_time=processing_time,
        )
        
    except Exception as e:
        processing_time = time.time() - start_time
        logging.error(f"Error procesando trabajo {job_id}: {e}")
        error_msg = str(e)
        try:
            from database import db
            db.update_job_status(job_id, 'failed', error_msg, processing_time)
            await send_notification(job_id, 'failed', error_msg)
        except Exception as e2:
            logging.error(f"Error actualizando estado fallido del trabajo {job_id}: {e2}")
        _log_print_dispatch(
            job_id=job_id,
            printer=printer,
            copies=copies,
            content=content,
            result="failed_exception",
            error=error_msg,
            processing_time=processing_time,
        )

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
    """Usar puerto fijo para Electron"""
    return 8002


def _is_port_listening(port: int, host: str = "127.0.0.1", timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _is_etiquetador_api_running(port: int) -> bool:
    if not _is_port_listening(port):
        return False

    try:
        import requests

        response = requests.get(f"http://127.0.0.1:{port}/api/status", timeout=2)
        data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
        return response.status_code == 200 and data.get("framework") == "FastAPI"
    except Exception:
        return False


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
        
        # Configurar logging
        try:
            from config_manager import get_config_manager
            config_mgr = get_config_manager()
            log_dir = config_mgr.get_log_directory()
            print(f"Logs configurados en: {log_dir}")
        except Exception as e:
            print(f"Error configurando logs: {e}")
            try:
                from log_config import setup_logging
                log_dir = setup_logging()
                print(f"Logs configurados (fallback) en: {log_dir}")
            except Exception as e2:
                print(f"Error configurando logs fallback: {e2}")
        
        # Inicializar base de datos en background (opcional)
        try:
            from database import db
            print("Base de datos inicializada")
        except Exception as e:
            print(f"ADVERTENCIA: BD no disponible - Dashboard funcionará con datos limitados: {e}")
        
        # Si ya hay una instancia corriendo en el puerto fijo, reutilizarla.
        if _is_etiquetador_api_running(port):
            print(f"API ya está ejecutándose en http://127.0.0.1:{port} (se reutiliza la instancia existente)")
            return

        # Verificar que uvicorn funciona
        print("Iniciando servidor uvicorn...")
        
        # Usar uvicorn.run directamente
        host = os.environ.get("ETIQUETADOR_API_HOST", "0.0.0.0").strip() or "0.0.0.0"
        print(f"Iniciando servidor en http://{host}:{port}")
        if host == "0.0.0.0":
            print(f"Acceso por red local: http://IP_DE_ESTA_PC:{port}")
        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level="info",
            access_log=False
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
