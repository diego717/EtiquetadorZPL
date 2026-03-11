"""
Endpoints adicionales para Electron
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any
import json
import configparser
from pathlib import Path
import sys
import threading
from watchdog.observers import Observer

# Agregar paths para imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

try:
    from handlers import PDFHandler
    print("PDFHandler importado correctamente")
except ImportError as e:
    print(f"Error importando PDFHandler: {e}")
    PDFHandler = None

router = APIRouter(prefix="/api/electron")

# Variables globales para el monitoreo
monitoring_active = False
observers = []
handlers = []

class FolderConfig(BaseModel):
    active: bool = False
    path: str = ""
    printer: str = ""
    history: str = ""
    copies: int = 1
    cropPdf: bool = True

class ElectronConfig(BaseModel):
    folders: List[FolderConfig]

@router.post("/start-monitoring")
async def start_monitoring(config: Dict[str, Any]):
    """Iniciar monitoreo desde Electron"""
    global monitoring_active, observers, handlers
    
    try:
        print(f"Recibiendo config de monitoreo: {config}")
        
        if monitoring_active:
            return {"success": False, "message": "Monitoring already active"}
        
        folders = config.get("folders", [])
        print(f"Carpetas a monitorear: {len(folders)}")
        
        if not folders:
            raise HTTPException(status_code=400, detail="No folders configured")
        
        if not PDFHandler:
            print("PDFHandler no disponible, usando monitoreo simple")
            # Fallback sin PDFHandler
            monitoring_active = True
            return {"success": True, "message": f"Simple monitoring started for {len(folders)} folders"}
        
        # Limpiar observers anteriores
        stop_monitoring_internal()
        
        # Crear handlers y observers para cada carpeta
        for i, folder_config in enumerate(folders):
            print(f"Procesando carpeta {i+1}: {folder_config}")
            
            # Obtener ruta de la carpeta
            folder_path = folder_config.get('path', '')
            if not folder_path:
                print(f"Carpeta {i+1}: Sin ruta configurada")
                continue
                
            if not Path(folder_path).exists():
                print(f"Carpeta {i+1}: Ruta no existe: {folder_path}")
                continue
            
            # Preparar configuración para PDFHandler
            handler_config = {
                'entrada': folder_path,
                'impresora': folder_config.get('printer', ''),
                'historial': folder_config.get('history', ''),
                'ancho_mm': 100,
                'alto_mm': 150,
                'poppler': '',
                'recortar_pdf': folder_config.get('cropPdf', True),
                'copias': folder_config.get('copies', 1)
            }
            
            print(f"Handler config {i+1}: {handler_config}")
            
            # Crear handler
            handler = PDFHandler(handler_config, observer=None, root=None)
            handler.carpeta_numero = i + 1
            
            # Crear observer
            observer = Observer()
            observer.schedule(handler, path=folder_path, recursive=False)
            handler.observer = observer
            
            handlers.append(handler)
            observers.append(observer)
            observer.start()
            
            print(f"Carpeta {i+1} monitoreando: {folder_path} -> {folder_config.get('printer')}")
        
        monitoring_active = True
        return {"success": True, "message": f"Monitoring started for {len(handlers)} folders"}
        
    except Exception as e:
        print(f"Error starting monitoring: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

def stop_monitoring_internal():
    """Detener monitoreo interno"""
    global monitoring_active, observers, handlers
    
    for observer in observers:
        try:
            observer.stop()
            observer.join(timeout=5)
        except Exception as e:
            print(f"Error stopping observer: {e}")
    
    observers.clear()
    handlers.clear()
    monitoring_active = False

@router.post("/stop-monitoring")
async def stop_monitoring():
    """Detener monitoreo"""
    try:
        stop_monitoring_internal()
        return {"success": True, "message": "Monitoring stopped"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/config")
async def get_config():
    """Obtener configuración actual"""
    try:
        # Buscar archivo de configuración
        config_paths = [
            Path("config/config.ini"),
            Path("config.ini"),
            Path(__file__).parent.parent / "config" / "config.ini"
        ]
        
        config_file = None
        for path in config_paths:
            if path.exists():
                config_file = path
                break
        
        if not config_file:
            return {"folders": []}
        
        # Leer configuración
        config = configparser.ConfigParser()
        config.read(config_file)
        
        folders = []
        for i in range(3):
            section = f"CARPETA{i+1}"
            if config.has_section(section):
                folders.append({
                    "active": config.getboolean(section, "activa", fallback=False),
                    "path": config.get(section, "entrada", fallback=""),
                    "printer": config.get(section, "impresora", fallback=""),
                    "history": config.get(section, "historial", fallback=""),
                    "copies": config.getint(section, "copias", fallback=1),
                    "cropPdf": config.getboolean(section, "recortar_pdf", fallback=True)
                })
            else:
                folders.append({
                    "active": False,
                    "path": "",
                    "printer": "",
                    "history": "",
                    "copies": 1,
                    "cropPdf": True
                })
        
        return {"folders": folders}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/save-config")
async def save_config(config: ElectronConfig):
    """Guardar configuración"""
    try:
        # Crear configuración
        config_parser = configparser.ConfigParser()
        
        for i, folder in enumerate(config.folders):
            section = f"CARPETA{i+1}"
            config_parser[section] = {
                "entrada": folder.path,
                "impresora": folder.printer,
                "historial": folder.history,
                "activa": str(folder.active),
                "recortar_pdf": str(folder.cropPdf),
                "copias": str(folder.copies)
            }
        
        # Guardar archivo
        config_dir = Path("config")
        config_dir.mkdir(exist_ok=True)
        config_path = config_dir / "config.ini"
        
        with open(config_path, 'w') as f:
            config_parser.write(f)
        
        return {"success": True, "path": str(config_path)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))